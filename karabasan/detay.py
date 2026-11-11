"""Bot bazlı işlem detayı ve oranlar (8 Kasım 2026, Ahmet'in isteği).

Panel adresi /detay?bot=<bot adı>. Üç bölüm:
1. İşlem listesi: coin, giriş, gerçek K/Z %, girişin ters yönüne inen en büyük mesafe (alttan alım var mı),
   stop olmayan işlemlerde o max düşüş, trailing 0,6 olsaydı sonuç.
2. Oranlar (son en çok 100 kapanmış işlem): kazanç / stop sayısı (100 işlemde kaçı), stop olmayanların ortalama
   max düşüşü, tetik %2 + trailing 0,5 olsaydı toplam sonuç.
3. Günlük kullanım: her gün bot en çok kaç USDT'ini kullandı, kaç USDT'ine hiç dokunulmadı (bütçe 1000 USDT).

Simülasyon yaklaşıktır: işlemin 5 dakikalık mumlarında (Binance vadeli, anahtarsız) stop ve iz süren stop, bağımsız
benzetim ile aynı kurala göre yürütülür; bir mumda hem stop hem iz seviyesi görülürse stop önce sayılır. Ek giriş
(zararda ekleme) simülasyonda yok sayılır: yüzdeler ilk girişe göredir.
Yalnız okur; hiçbir ayar, kayıt ya da emir değişmez.
"""

from __future__ import annotations

import concurrent.futures as cf
import threading
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from . import botlar as _botlar
from . import site_gezinti
from . import gostergeler as g
from . import islem_grafik as ig
from .kural import kural_yukle
from .sonuc import islemleri_oku

SON_N_ISLEM = 100          # oran ve simülasyon bölümünde en çok bu kadar kapanmış işlem
GUN_TABLO = 30             # günlük kullanım tablosunda son kaç gün
ILK_TUTAR = float(_botlar.VARSAYILAN_AYARLAR["islem_tutari"])     # 50 USDT: simülasyon USDT'leri bu üzerinden
BUTCE = float(_botlar.VARSAYILAN_AYARLAR["sanal_bakiye"])          # 1000 USDT
KOMISYON = float(_botlar.VARSAYILAN_AYARLAR["komisyon_yuzde"]["vadeli"])   # taraf başına %
ISCI = 8                    # aynı anda mum indirme sayısı
MUM_ONBELLEK = ig.MumOnbellegi(en_fazla=600)
SENARYO_T2 = (2.0, 0.5)     # tetik %2, mesafe %0,5 (Ahmet'in istediği ayar)
SENARYO_M06 = 0.6           # mevcut tetik, mesafe 0,6


# --------------------------------------------------------------------------
# Simülasyon (saf fonksiyon; testli)
# --------------------------------------------------------------------------


def simule(mumlar: list[tuple], giris: float, yon: str, stop_yuzde: float | None,
           tetik_yuzde: float | None, mesafe_yuzde: float | None, komisyon: float = KOMISYON) -> dict:
    """Bir işlemi mum mum yürütür. Dönen: cikis_fiyati, neden ('stop', 'iz', 'veri_bitti'), kz_yuzde
    (komisyon sonrası, ilk girişe göre), mae (girişin ters yönüne en büyük mesafe, %, pozitif), mfe.

    mumlar: (zaman, açılış, tepe, dip, kapanış) giriş anından itibaren, kronolojik.
    """
    d = 1.0 if yon == "alim" else -1.0

    def fav(p: float) -> float:   # lehe hareket yüzdesi (alım: yukarı, açığa satış: aşağı pozitif)
        return d * (p - giris) / giris * 100.0

    def fiyat(f: float) -> float:
        return giris * (1.0 + d * f / 100.0)

    en_iyi_onceki = 0.0    # önceki mumların en iyi lehe hareketi (iz süren stop buradan taşınır)
    mae = 0.0
    mfe = 0.0
    neden, cikis = "veri_bitti", None
    son_kapanis = giris
    for _t, _a, tepe, dip, kapanis in mumlar:
        f_tepe, f_dip = fav(tepe), fav(dip)
        kotu, iyi = min(f_tepe, f_dip), max(f_tepe, f_dip)
        mae = max(mae, -kotu)
        mfe = max(mfe, iyi)
        son_kapanis = kapanis
        if stop_yuzde and kotu <= -stop_yuzde:
            neden, cikis = "stop", fiyat(-stop_yuzde)
            break
        if tetik_yuzde is not None and mesafe_yuzde is not None and en_iyi_onceki >= tetik_yuzde:
            seviye = en_iyi_onceki - mesafe_yuzde
            if kotu <= seviye:
                neden, cikis = "iz", fiyat(seviye)
                break
        en_iyi_onceki = max(en_iyi_onceki, iyi)
    if cikis is None:
        cikis = son_kapanis
    kz = fav(cikis) - 2.0 * komisyon
    return {"cikis_fiyati": cikis, "neden": neden, "kz_yuzde": kz, "mae": mae, "mfe": mfe}


def senaryo_kurallari(kural: dict) -> dict:
    """Botun kendi çıkış ayarları: stop, tetik, mesafe (yoksa None)."""
    cikis = kural["cikis"]
    iz = cikis.get("iz_suren_stop") or {}
    return {"stop": cikis.get("zarar_durdur_yuzde"),
            "tetik": iz.get("tetik_yuzde"), "mesafe": iz.get("mesafe_yuzde")}


# --------------------------------------------------------------------------
# Mumlar ve işlem başına satır
# --------------------------------------------------------------------------


def _mumlar(islem: dict, kural: dict, getir=ig.mum_getir) -> list[tuple] | None:
    """İşlemin giriş anından çıkışa kadar 5 dakikalık (kuralın taban dilimi) mumları; alınamazsa None."""
    aralik = kural["zaman_dilimi"]
    dk = g.dilim_dakika(aralik)
    bas = islem["giris_zamani"].replace(second=0, microsecond=0)
    bas -= timedelta(minutes=bas.minute % dk)
    bit = islem["cikis_zamani"] + timedelta(minutes=dk)
    anahtar = (islem["bot"], islem["kimlik"], aralik, bas.isoformat(), bit.isoformat())
    try:
        mumlar = MUM_ONBELLEK.al(anahtar, False, lambda: getir(islem["parite"], islem["piyasa"], aralik, bas, bit))
    except Exception:  # noqa: BLE001 - ağ hatası tek işlemi düşürmesin
        return None
    return [m for m in mumlar if m[0] + timedelta(minutes=dk) > islem["giris_zamani"]] or None


def islem_satiri(islem: dict, kural: dict, getir=ig.mum_getir) -> dict:
    """Bir kapanmış işlemin tablo satırı (gerçek sonuç + simülasyonlar). Mum yoksa simülasyon alanları None."""
    kur = senaryo_kurallari(kural)
    giris = float(islem.get("ilk_giris_fiyati") or islem["giris_fiyati"])
    satir = {
        "kimlik": islem["kimlik"], "parite": islem["parite"], "yon": islem["yon"],
        "giris_zamani": islem["giris_zamani"], "giris": giris,
        "gercek_yuzde": islem["net_yuzde"], "gercek_usdt": islem["net_tutar"],
        "neden": islem["neden"], "stop_oldu": islem["neden"] == "stop",
        "mae": None, "mae_olan": None, "bot_kurali": None, "m06": None, "t2m05": None,
    }
    mumlar = _mumlar(islem, kural, getir)
    if not mumlar or not kur["stop"]:
        return satir
    bot = simule(mumlar, giris, islem["yon"], kur["stop"], kur["tetik"], kur["mesafe"])
    satir["mae"] = bot["mae"]
    satir["bot_kurali"] = bot["kz_yuzde"]
    if kur["tetik"] is not None:
        satir["m06"] = simule(mumlar, giris, islem["yon"], kur["stop"], kur["tetik"], SENARYO_M06)["kz_yuzde"]
        satir["t2m05"] = simule(mumlar, giris, islem["yon"], kur["stop"], SENARYO_T2[0], SENARYO_T2[1])["kz_yuzde"]
    return satir


# --------------------------------------------------------------------------
# Oranlar
# --------------------------------------------------------------------------


def oranlar(satirlar: list[dict]) -> dict:
    """100 işlem başına oranlar ve senaryo toplamları. satirlar: islem_satiri çıktıları."""
    n = len(satirlar)
    if not n:
        return {"n": 0}
    kazanan = sum(1 for s in satirlar if s["gercek_yuzde"] > 0)
    stop = sum(1 for s in satirlar if s["stop_oldu"])
    stopsuz = [s["mae"] for s in satirlar if not s["stop_oldu"] and s["mae"] is not None]
    m06 = [s["m06"] for s in satirlar if s["m06"] is not None]
    t2 = [s["t2m05"] for s in satirlar if s["t2m05"] is not None]
    kur_toplam = [s["bot_kurali"] for s in satirlar if s["bot_kurali"] is not None]
    gercek_toplam = [s["gercek_yuzde"] for s in satirlar if s["bot_kurali"] is not None]
    return {
        "n": n,
        "kazanc_yuzde": 100.0 * kazanan / n, "kazanan": kazanan,
        "stop_yuzde": 100.0 * stop / n, "stop": stop,
        "per100_kazanan": 100.0 * kazanan / n, "per100_stop": 100.0 * stop / n,
        "stopsuz_ort_mae": (sum(stopsuz) / len(stopsuz)) if stopsuz else None,
        "stopsuz_adet": len(stopsuz),
        "veri_olan": len(kur_toplam),
        "gercek_toplam_yuzde": sum(gercek_toplam) if gercek_toplam else None,
        "kural_toplam_yuzde": sum(kur_toplam) if kur_toplam else None,
        "m06_toplam_yuzde": sum(m06) if m06 else None,
        "t2m05_toplam_yuzde": sum(t2) if t2 else None,
    }


# --------------------------------------------------------------------------
# Günlük kullanım (mum gerekmez)
# --------------------------------------------------------------------------


def gunluk_kullanim(kapali: list[dict], butce: float = BUTCE) -> list[dict]:
    """Her UTC günü için: o günün herhangi bir anında açık olan teminatların en büyük toplamı ve
    kullanılmayan (bütçe eksi en büyük kullanım) kısım. Yalnız işlem olan günler."""
    if not kapali:
        return []
    olaylar = []
    for i in kapali:
        olaylar.append((i["giris_zamani"], +float(i.get("tutar") or 0.0)))
        olaylar.append((i["cikis_zamani"], -float(i.get("tutar") or 0.0)))
    olaylar.sort(key=lambda o: (o[0], o[1]))   # aynı anda çıkış ve giriş: önce çıkış
    gunler = sorted({i["giris_zamani"].date() for i in kapali} | {i["cikis_zamani"].date() for i in kapali})
    sonuc = []
    for gun in gunler:
        bas = datetime(gun.year, gun.month, gun.day, tzinfo=timezone.utc)
        bit = bas + timedelta(days=1)
        # gün başındaki açık teminat: giriş < bas ve çıkış ≥ bas
        acik = sum(float(i.get("tutar") or 0.0) for i in kapali
                   if i["giris_zamani"] < bas <= i["cikis_zamani"])
        en_cok = acik
        for z, t in olaylar:
            if bas <= z < bit:
                acik += t
                en_cok = max(en_cok, acik)
        sonuc.append({"gun": gun, "en_cok": en_cok, "dokunulmadi": max(0.0, butce - en_cok)})
    return sonuc


# --------------------------------------------------------------------------
# Sayfa
# --------------------------------------------------------------------------


def _usd(x) -> str:
    return "–" if x is None else f"{x:+.2f}".replace(".", ",")


def _yuzde(x) -> str:
    return "–" if x is None else f"{x:+.2f}%".replace(".", ",")


def _mesafe(x) -> str:
    return "–" if x is None else f"−{x:.2f}%".replace(".", ",")


def _sinif(x) -> str:
    if x is None:
        return ""
    return "arti" if x > 0 else "eksi" if x < 0 else ""


DETAY_STIL = """
.dt-bot{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
.dt-bot a{min-height:40px;display:inline-flex;align-items:center;padding:0 12px;border-radius:999px;border:1px solid var(--cizgi);font-size:.8125rem;text-decoration:none}
.dt-bot a.secili{border-color:var(--holo);color:var(--holo)}
.dt-kart{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}
.dt-kart div{border:1px solid var(--cizgi);border-radius:10px;padding:8px 10px;background:var(--cam);font-size:.8125rem}
.dt-kart b{display:block;font-size:1.125rem;margin-top:2px}
.dt-tablo{width:100%;border-collapse:collapse;font-size:.75rem;overflow-x:auto}
.dt-tablo th,.dt-tablo td{padding:5px 4px;text-align:left;border-bottom:1px solid var(--cizgi);white-space:nowrap}
.dt-kaydir{overflow-x:auto;-webkit-overflow-scrolling:touch}
.dt-not{font-size:.75rem;color:var(--soluk);line-height:1.45}
.dt-h{margin:18px 0 6px;font-size:1rem}
.dt-sim{color:var(--altin)}
"""


def sayfa_uret(bot: str, veri_klasoru: Path, getir=ig.mum_getir, simdi: datetime | None = None) -> str:
    from .sayfa import STIL, _tarih_saat

    simdi = simdi or datetime.now(timezone.utc)
    satir_bot = next((b for b in _botlar.BOTLAR if b[0] == bot), None)
    botlar_html = "".join(
        f'<a href="/detay?bot={escape(b[0])}"{" class=secili" if b[0] == bot else ""}>{escape(b[2])}</a>'
        for b in _botlar.BOTLAR)
    govde = [f'<div class="dt-bot">{botlar_html}</div>']
    if satir_bot is None:
        govde.append('<p class="bos">Böyle bir bot yok.</p>')
    else:
        kayit = islemleri_oku(veri_klasoru / "db" / f"{bot}.sqlite")
        kural = kural_yukle(satir_bot[2])
        kapali = sorted(kayit["kapali"], key=lambda i: i["giris_zamani"])
        if kayit["hata"]:
            govde.append(f'<p class="bos">{escape(kayit["hata"])}</p>')
        son = kapali[-SON_N_ISLEM:]
        for i in son:
            i["bot"] = bot
            i["piyasa"] = satir_bot[3]
        with cf.ThreadPoolExecutor(max_workers=ISCI) as havuz:
            satirlar = list(havuz.map(lambda i: islem_satiri(i, kural, getir), son))
        o = oranlar(satirlar)
        if o.get("n"):
            govde.append(
                f'<h2 class="dt-h">Oranlar (son {o["n"]} kapanmış işlem)</h2>'
                '<div class="dt-kart">'
                f'<div>Kazanç<b>{o["kazanan"]} / {o["n"]}</b><span>100 işlemde ≈ {o["per100_kazanan"]:.0f}</span></div>'
                f'<div>Stop<b>{o["stop"]} / {o["n"]}</b><span>100 işlemde ≈ {o["per100_stop"]:.0f}</span></div>'
                f'<div>Stop olmayanların ort. max düşüşü<b>{_mesafe(o["stopsuz_ort_mae"])}</b>'
                f'<span>{o["stopsuz_adet"]} işlemde (girişin ters yönü)</span></div>'
                f'<div>Gerçek toplam (bot)<b class="{_sinif(o["gercek_toplam_yuzde"])}">{_yuzde(o["gercek_toplam_yuzde"])}</b>'
                f'<span>veritabanı, komisyon sonrası</span></div>'
                f'<div>Trailing 0,6 olsaydı<b class="{_sinif(o["m06_toplam_yuzde"])}">{_yuzde(o["m06_toplam_yuzde"])}</b>'
                f'<span>tetik botun, mesafe 0,6 (aynı girişler)</span></div>'
                f'<div>Tetik %2 + trailing 0,5<b class="{_sinif(o["t2m05_toplam_yuzde"])}">{_yuzde(o["t2m05_toplam_yuzde"])}</b>'
                f'<span>stop botun, aynı girişler</span></div>'
                '</div>'
                f'<p class="dt-not dt-sim">Simülasyon toplamları yüzde olarak, ilk girişe göre; bot kuralı yeniden oynatılınca '
                f'{_yuzde(o["kural_toplam_yuzde"])} çıkıyor, gerçek {_yuzde(o["gercek_toplam_yuzde"])}. Aradaki fark mum '
                'yaklaşıklığından ve ek girişlerden gelir.</p>')
        satir_html = []
        for s in reversed(satirlar):
            mae = s["mae"]
            ters = "–" if mae is None else ("Evet, " + _mesafe(mae)) if mae > 0 else "Hayır"
            stopsuz = "stop oldu" if s["stop_oldu"] else ("–" if mae is None else _mesafe(mae))
            satir_html.append(
                f'<tr><td>{escape(s["parite"].split("/")[0])}</td>'
                f'<td>{_tarih_saat(s["giris_zamani"], "Europe/Bucharest")}<br>{s["giris"]:.4g}</td>'
                f'<td>{"Alım" if s["yon"] == "alim" else "Açığa satış"}</td>'
                f'<td class="{_sinif(s["gercek_yuzde"])}">{_yuzde(s["gercek_yuzde"])}<br>'
                f'<span class="dt-not">{_usd(s["gercek_usdt"])} USDT · {escape(str(s["neden"]))}</span></td>'
                f'<td>{ters}</td><td>{stopsuz}</td>'
                f'<td class="{_sinif(s["m06"])}">{_yuzde(s["m06"])}</td></tr>')
        govde.append(
            '<h2 class="dt-h">İşlemler (en yeni üstte)</h2>'
            '<p class="dt-not">Ters yön: alımda girişin altına inen en büyük mesafe, açığa satışta üstüne çıkan. '
            '"Stop olmayanlarda max düşüş" yalnız stopa gitmeyen işlemlerde gösterilir.</p>'
            '<div class="dt-kaydir"><table class="dt-tablo"><thead><tr><th>Coin</th><th>Giriş</th><th>Yön</th>'
            '<th>Gerçek K/Z</th><th>Ters yöne indi mi</th><th>Stop olmayanda max düşüş</th>'
            '<th>Trailing 0,6 olsaydı</th></tr></thead><tbody>'
            + "".join(satir_html) + '</tbody></table></div>' if satirlar else
            '<p class="bos">Kapanmış işlem yok.</p>')
        gun = gunluk_kullanim(kapali)[-GUN_TABLO:]
        if gun:
            govde.append(
                f'<h2 class="dt-h">Günlük bütçe kullanımı (bütçe {BUTCE:.0f} USDT, UTC günü)</h2>'
                '<div class="dt-kaydir"><table class="dt-tablo"><thead><tr><th>Gün</th><th>En çok kullanılan</th>'
                '<th>Hiç dokunulmayan</th></tr></thead><tbody>'
                + "".join(f'<tr><td>{r["gun"].strftime("%d.%m")}</td><td>{r["en_cok"]:.0f} USDT</td>'
                          f'<td>{r["dokunulmadi"]:.0f} USDT</td></tr>' for r in reversed(gun))
                + '</tbody></table></div>'
                '<p class="dt-not">En çok kullanılan: o gün açık olan teminatların aynı anda en büyük toplamı. '
                'Hiç dokunulmayan: bütçe eksi bu.</p>')
    from .islem_grafik import ISLEM_STIL
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#04070d"><meta name="robots" content="noindex">
<title>Karabasan · Bot detayı</title><style>{STIL}{ISLEM_STIL}{DETAY_STIL}</style></head>
<body>{site_gezinti.serit("detay")}<div class="sayfa">
<header class="ust baslik-cubugu"><a class="marka" href="/">KARABASAN</a>
<a class="ig-geri" href="/#sonuc-islemler" style="margin-left:auto">← Pano</a></header>
<main><h2 class="ekran-baslik">Bot detayı</h2>
<p class="dt-not">Simülasyonlar bu sayfa için mum verisinden yapılır (Binance vadeli 5 dakikalık, anahtarsız). Sanal işlemdir; borsaya emir gitmez.</p>
{"".join(govde)}
</main></div></body></html>"""
