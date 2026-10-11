"""Emir defteri denemesinin tek sayfalık özeti (sonuç sayfası /defter, Telegram /defter).

Kaydı (user_data/kayit/defter.sqlite) salt okunur açar. Yalnız standart kütüphane.
Mevcut sonuç sayfasından (karabasan.sayfa) bağımsızdır; ona dokunmaz.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from html import escape
from pathlib import Path

UFUKLAR = ("5dk", "15dk")
UFUK_ADI = {"5dk": "5 dakika", "15dk": "15 dakika"}
NEDEN_ADI = {"hedef": "Hedefe ulaştı", "stop": "Stop", "sure": "Süre doldu", "tasfiye": "Tasfiye"}
# Kayıt bu kadar saniyedir güncellenmiyorsa sayfa uyarır.
BAYAT_SANIYE = 120


def _zaman_metni(saniye) -> str:
    if saniye is None:
        return "-"
    return datetime.fromtimestamp(int(saniye), timezone.utc).strftime("%d.%m %H:%M:%S UTC")


def _sayi(deger, basamak=2, isaret=False) -> str:
    if deger is None:
        return "-"
    metin = f"{deger:{'+' if isaret else ''},.{basamak}f}"
    # 1,234.56 -> 1.234,56
    return metin.replace(",", "_").replace(".", ",").replace("_", ".")


def ozet_cikar(yol: Path, simdi: int | None = None) -> dict:
    """Sayfanın ve Telegram özetinin ihtiyacı olan her şey, tek sözlükte."""
    simdi = int(time.time()) if simdi is None else simdi
    if not Path(yol).exists():
        return {"var": False, "simdi": simdi}
    vt = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    try:
        return _ozet(vt, simdi)
    except sqlite3.OperationalError:
        # Tablolar henüz kurulmamış (servis ilk kez açılıyor).
        return {"var": False, "simdi": simdi}
    finally:
        vt.close()


def _ozet(vt: sqlite3.Connection, simdi: int) -> dict:
    durum = {k: json.loads(v) for k, v in vt.execute("SELECT anahtar, deger FROM durum_v1")}
    ilk, son, adet = vt.execute("SELECT MIN(zaman), MAX(zaman), COUNT(*) FROM ornek_v1").fetchone()
    son_satir = vt.execute(
        "SELECT zaman, orta, alis, satis, tahmin_5dk, tahmin_15dk FROM ornek_v1 ORDER BY zaman DESC LIMIT 1"
    ).fetchone()

    ufuklar = {}
    for u in UFUKLAR:
        sayi, basarili, net, ort_net = vt.execute(
            "SELECT COUNT(*), COALESCE(SUM(basarili), 0), COALESCE(SUM(net_usdt), 0), AVG(net_yuzde) "
            "FROM islem_v1 WHERE ufuk = ? AND cikis_zamani IS NOT NULL", (u,)).fetchone()
        nedenler = dict(vt.execute(
            "SELECT neden, COUNT(*) FROM islem_v1 WHERE ufuk = ? AND cikis_zamani IS NOT NULL GROUP BY neden",
            (u,)).fetchall())
        # Tahmin isabeti: sonucu belli olan son 7 günün tahminleri.
        n, yon_dogru, yon_sayi, hata_model, hata_sifir = vt.execute(
            f"SELECT COUNT(*), "
            f"SUM(CASE WHEN tahmin_{u} * gercek_{u} > 0 THEN 1 ELSE 0 END), "
            f"SUM(CASE WHEN tahmin_{u} != 0 AND gercek_{u} != 0 THEN 1 ELSE 0 END), "
            f"AVG(ABS(gercek_{u} - tahmin_{u})), AVG(ABS(gercek_{u})) "
            f"FROM ornek_v1 WHERE tahmin_{u} IS NOT NULL AND gercek_{u} IS NOT NULL AND zaman >= ?",
            (simdi - 7 * 86400,)).fetchone()
        ufuklar[u] = {
            "islem": sayi, "basarili": basarili, "basarisiz": sayi - basarili,
            "kazanma_orani": (basarili / sayi * 100.0) if sayi else None,
            "net_usdt": net, "ort_net_yuzde": ort_net, "nedenler": nedenler,
            "tahmin_sayisi": n,
            "yon_isabeti": (yon_dogru / yon_sayi * 100.0) if yon_sayi else None,
            "hata_model": hata_model, "hata_sifir": hata_sifir,
            "model": (durum.get("model") or {}).get(u, {}),
        }

    alanlar = ["id", "ufuk", "yon", "giris_zamani", "giris", "tahmin_yuzde", "hedef", "stop", "cikis_zamani",
               "cikis", "neden", "net_yuzde", "net_usdt", "basarili", "en_kotu_yuzde", "en_iyi_yuzde"]
    islemler = [dict(zip(alanlar, s)) for s in vt.execute(
        f"SELECT {', '.join(alanlar)} FROM islem_v1 ORDER BY giris_zamani DESC, id DESC LIMIT 200")]
    son_tahminler = [
        dict(zip(["zaman", "orta", "tahmin_5dk", "gercek_5dk", "tahmin_15dk", "gercek_15dk"], s))
        for s in vt.execute(
            "SELECT zaman, orta, tahmin_5dk, gercek_5dk, tahmin_15dk, gercek_15dk FROM ornek_v1 "
            "WHERE zaman % 60 = 0 ORDER BY zaman DESC LIMIT 12")
    ]
    toplam = {
        "islem": sum(v["islem"] for v in ufuklar.values()),
        "basarili": sum(v["basarili"] for v in ufuklar.values()),
        "basarisiz": sum(v["basarisiz"] for v in ufuklar.values()),
        "net_usdt": sum(v["net_usdt"] for v in ufuklar.values()),
        "acik": sum(1 for i in islemler if i["cikis_zamani"] is None),
    }
    return {
        "var": True, "simdi": simdi, "ilk": ilk, "son": son, "kayit_sayisi": adet,
        "bayat": son is None or simdi - son > BAYAT_SANIYE,
        "son_satir": dict(zip(["zaman", "orta", "alis", "satis", "tahmin_5dk", "tahmin_15dk"], son_satir))
        if son_satir else None,
        "ufuklar": ufuklar, "toplam": toplam, "islemler": islemler, "son_tahminler": son_tahminler,
    }


# --------------------------------------------------------------------------
# Telegram için kısa metin
# --------------------------------------------------------------------------


def metin_ozeti(ozet: dict) -> str:
    if not ozet.get("var"):
        return "Emir defteri denemesi henüz kayıt yazmadı. Servis yeni açıldıysa birkaç dakika bekle."
    t = ozet["toplam"]
    satirlar = ["Emir defteri denemesi (BTC/USDT vadeli, sanal)"]
    if ozet["bayat"]:
        satirlar.append(f"UYARI: kayıt {_zaman_metni(ozet['son'])} tarihinden beri güncellenmiyor.")
    s = ozet["son_satir"]
    if s:
        satirlar.append(f"Fiyat: {_sayi(s['orta'], 1)} USDT")
    satirlar.append(f"İşlem: {t['islem']} (başarılı {t['basarili']}, başarısız {t['basarisiz']}, açık {t['acik']})")
    satirlar.append(f"Net: {_sayi(t['net_usdt'], 2, True)} USDT (işlem başına 100 USDT)")
    for u in UFUKLAR:
        v = ozet["ufuklar"][u]
        model = v["model"]
        if not model.get("hazir"):
            kalan = max(0, int(model.get("gereken_saniye", 0)) - int(model.get("kayit_saniye", 0)))
            durum = f"model öğreniyor (yaklaşık {kalan // 60} dakika kaldı)"
        else:
            durum = f"yön isabeti %{_sayi(v['yon_isabeti'], 1)}"
        satirlar.append(f"{UFUK_ADI[u]}: {v['islem']} işlem, {v['basarili']} başarılı, {durum}")
    return "\n".join(satirlar)


# --------------------------------------------------------------------------
# Sayfa
# --------------------------------------------------------------------------

BICIM = """
:root{color-scheme:dark;--zemin:#0b1018;--kart:#121a26;--cizgi:#22304a;--yazi:#e4eef8;--soluk:#8ca0b8;
--arti:#4fe0a6;--eksi:#ff7a6b;--uyari:#ffc24a}
*{box-sizing:border-box}body{margin:0;background:var(--zemin);color:var(--yazi);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-variant-numeric:tabular-nums}
main{max-width:960px;margin:0 auto;padding:16px}h1{font-size:1.3rem;margin:.2em 0}
h2{font-size:1.05rem;margin:1.6em 0 .5em}p{margin:.4em 0}.soluk{color:var(--soluk)}
.uyari{background:#3a2a08;border:1px solid var(--uyari);padding:10px 12px;border-radius:8px;margin:12px 0}
.kartlar{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:12px 0}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;padding:10px 12px}
.kart b{display:block;font-size:1.5rem;line-height:1.2}.kart span{color:var(--soluk);font-size:.85rem}
.arti{color:var(--arti)}.eksi{color:var(--eksi)}
.tablo{overflow-x:auto;border:1px solid var(--cizgi);border-radius:10px}
table{border-collapse:collapse;width:100%;min-width:560px}th,td{padding:6px 8px;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}thead th{color:var(--soluk);font-weight:600;background:var(--kart)}
tbody tr+tr td{border-top:1px solid var(--cizgi)}
"""


def _isaret_sinifi(deger) -> str:
    if deger is None or deger == 0:
        return ""
    return "arti" if deger > 0 else "eksi"


def _kart(baslik: str, deger: str, sinif: str = "") -> str:
    return f'<div class="kart"><b class="{sinif}">{deger}</b><span>{escape(baslik)}</span></div>'


def html_uret(ozet: dict, yenile_saniye: int = 30) -> str:
    yenile = f'<meta http-equiv="refresh" content="{int(yenile_saniye)}">' if yenile_saniye else ""
    bas = (f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width, initial-scale=1">{yenile}'
           f'<meta name="robots" content="noindex"><title>Emir defteri denemesi</title>'
           f'<style>{BICIM}</style></head><body><main>')
    son = "</main></body></html>"
    govde = ['<h1>Emir defteri denemesi</h1>',
             '<p class="soluk">BTC/USDT vadeli, 1 kat, yalnız sanal. Borsaya hiçbir emir gitmez. '
             'Her saniye açık emirlere bakılır, 5 ve 15 dakika sonrası için fiyat tahmin edilir; '
             'tahmin komisyonu karşılıyorsa sanal pozisyon açılır.</p>']
    if not ozet.get("var"):
        govde.append('<div class="uyari">Henüz kayıt yok. Servis yeni açıldıysa birkaç dakika sonra yenile.</div>')
        return bas + "".join(govde) + son

    if ozet["bayat"]:
        govde.append(f'<div class="uyari">Kayıt {escape(_zaman_metni(ozet["son"]))} tarihinden beri '
                     'güncellenmiyor. Servis durmuş ya da borsaya ulaşamıyor olabilir.</div>')
    s = ozet["son_satir"]
    t = ozet["toplam"]
    kazanma = (t["basarili"] / t["islem"] * 100.0) if t["islem"] else None
    govde.append('<div class="kartlar">'
                 + _kart("toplam işlem", str(t["islem"]))
                 + _kart("başarılı", str(t["basarili"]), "arti" if t["basarili"] else "")
                 + _kart("başarısız", str(t["basarisiz"]), "eksi" if t["basarisiz"] else "")
                 + _kart("kazanma oranı", f"%{_sayi(kazanma, 1)}" if kazanma is not None else "-")
                 + _kart("net (USDT)", _sayi(t["net_usdt"], 2, True), _isaret_sinifi(t["net_usdt"]))
                 + _kart("açık işlem", str(t["acik"]))
                 + "</div>")
    if s:
        tahminler = []
        for u in UFUKLAR:
            tahmin = s.get(f"tahmin_{u}")
            if tahmin is None:
                tahminler.append(f"{UFUK_ADI[u]} sonra: model henüz öğreniyor")
            else:
                hedef = s["orta"] * (1 + tahmin / 100.0)
                tahminler.append(f"{UFUK_ADI[u]} sonra: {_sayi(hedef, 1)} "
                                 f"(<span class=\"{_isaret_sinifi(tahmin)}\">%{_sayi(tahmin, 3, True)}</span>)")
        govde.append(f'<p>Şu an ({escape(_zaman_metni(s["zaman"]))}): <b>{_sayi(s["orta"], 1)}</b> USDT. '
                     + " · ".join(tahminler) + "</p>")
    govde.append(f'<p class="soluk">Kayıt başlangıcı {escape(_zaman_metni(ozet["ilk"]))}, '
                 f'{_sayi(ozet["kayit_sayisi"], 0)} saniyelik kayıt.</p>')

    # Ufuk başına özet
    govde.append('<h2>Ufuk başına</h2><div class="tablo"><table><thead><tr><th>Ufuk</th><th>İşlem</th>'
                 '<th>Başarılı</th><th>Başarısız</th><th>Kazanma</th><th>Net USDT</th><th>Hedef</th>'
                 '<th>Stop</th><th>Süre doldu</th><th>Yön isabeti</th><th>Tahmin hatası</th>'
                 '<th>"Değişmez" hatası</th></tr></thead><tbody>')
    for u in UFUKLAR:
        v = ozet["ufuklar"][u]
        n = v["nedenler"]
        govde.append(
            f'<tr><td>{UFUK_ADI[u]}</td><td>{v["islem"]}</td><td>{v["basarili"]}</td><td>{v["basarisiz"]}</td>'
            f'<td>{"%" + _sayi(v["kazanma_orani"], 1) if v["kazanma_orani"] is not None else "-"}</td>'
            f'<td class="{_isaret_sinifi(v["net_usdt"])}">{_sayi(v["net_usdt"], 2, True)}</td>'
            f'<td>{n.get("hedef", 0)}</td><td>{n.get("stop", 0)}</td><td>{n.get("sure", 0)}</td>'
            f'<td>{"%" + _sayi(v["yon_isabeti"], 1) if v["yon_isabeti"] is not None else "-"}</td>'
            f'<td>{"%" + _sayi(v["hata_model"], 3) if v["hata_model"] is not None else "-"}</td>'
            f'<td>{"%" + _sayi(v["hata_sifir"], 3) if v["hata_sifir"] is not None else "-"}</td></tr>')
    govde.append('</tbody></table></div>')
    govde.append('<p class="soluk">Yön isabeti: tahminin yönü (yukarı / aşağı) gerçekleşenle kaç kez aynı. '
                 'Tahmin hatası: tahmin ile gerçekleşen değişim arasındaki ortalama fark. "Değişmez" hatası: '
                 '"fiyat hiç değişmeyecek" deseydik yapacağımız hata. Model işe yarıyorsa tahmin hatası '
                 'bundan küçük, yön isabeti %50\'den belirgin büyük olmalı. Başarılı işlem: komisyon '
                 'düşüldükten sonra artıda kapanan. 1 kat kaldıraçta tasfiye (likidasyon) için fiyatın '
                 'yaklaşık %100 ters gitmesi gerekir; bu yüzden başarısız işlem stop ya da süre sonunda '
                 'zarardır. Her işlemin "en kötü an" sütunu fiyatın en çok ne kadar ters gittiğini gösterir.</p>')
    for u in UFUKLAR:
        model = ozet["ufuklar"][u]["model"]
        if model and not model.get("hazir"):
            kalan = max(0, int(model.get("gereken_saniye", 0)) - int(model.get("kayit_saniye", 0)))
            govde.append(f'<p class="soluk">{UFUK_ADI[u]} modeli öğreniyor: tahmin vermeden önce '
                         f'yaklaşık {kalan // 60} dakikalık daha kayıt bekliyor.</p>')

    # Son tahminler
    govde.append('<h2>Son tahminler (dakikada bir)</h2><div class="tablo"><table><thead><tr><th>Zaman</th>'
                 '<th>Fiyat</th><th>5 dk tahmini</th><th>5 dk gerçek</th><th>15 dk tahmini</th>'
                 '<th>15 dk gerçek</th></tr></thead><tbody>')
    for r in ozet["son_tahminler"]:
        hucreler = []
        for u in UFUKLAR:
            for alan in (f"tahmin_{u}", f"gercek_{u}"):
                deger = r[alan]
                hucreler.append(f'<td class="{_isaret_sinifi(deger)}">'
                                f'{"%" + _sayi(deger, 3, True) if deger is not None else "-"}</td>')
        govde.append(f'<tr><td>{escape(_zaman_metni(r["zaman"]))}</td><td>{_sayi(r["orta"], 1)}</td>'
                     + "".join(hucreler) + "</tr>")
    govde.append('</tbody></table></div>')

    # İşlemler
    govde.append('<h2>İşlemler (en yeni 200)</h2>')
    if not ozet["islemler"]:
        govde.append('<p class="soluk">Henüz işlem yok. Model öğrenmeyi bitirip komisyonu karşılayacak '
                     'kadar büyük bir hareket tahmin ettiğinde ilk işlem açılır.</p>')
    else:
        govde.append('<div class="tablo"><table><thead><tr><th>Açılış</th><th>Ufuk</th><th>Yön</th>'
                     '<th>Giriş</th><th>Tahmin</th><th>Hedef</th><th>Stop</th><th>Çıkış</th><th>Sonuç</th>'
                     '<th>Net %</th><th>Net USDT</th><th>En kötü an</th></tr></thead><tbody>')
        for i in ozet["islemler"]:
            acik = i["cikis_zamani"] is None
            sonuc = "Açık" if acik else NEDEN_ADI.get(i["neden"], i["neden"] or "-")
            govde.append(
                f'<tr><td>{escape(_zaman_metni(i["giris_zamani"]))}</td><td>{UFUK_ADI.get(i["ufuk"], "")}</td>'
                f'<td>{"Alım" if i["yon"] == "alim" else "Açığa satış"}</td><td>{_sayi(i["giris"], 1)}</td>'
                f'<td>%{_sayi(i["tahmin_yuzde"], 3, True)}</td><td>{_sayi(i["hedef"], 1)}</td>'
                f'<td>{_sayi(i["stop"], 1)}</td><td>{_sayi(i["cikis"], 1) if not acik else "-"}</td>'
                f'<td>{escape(sonuc)}</td>'
                f'<td class="{_isaret_sinifi(i["net_yuzde"])}">'
                f'{"%" + _sayi(i["net_yuzde"], 3, True) if i["net_yuzde"] is not None else "-"}</td>'
                f'<td class="{_isaret_sinifi(i["net_usdt"])}">{_sayi(i["net_usdt"], 2, True)}</td>'
                f'<td>%{_sayi(i["en_kotu_yuzde"], 3, True)}</td></tr>')
        govde.append('</tbody></table></div>')
    govde.append(f'<p class="soluk">Sayfa {escape(_zaman_metni(ozet["simdi"]))} anında hazırlandı.</p>')
    return bas + "".join(govde) + son
