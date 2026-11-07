"""/ayar sayfası: bot kriter ayar laboratuvarının ekranı (7 Kasım 2026, Ahmet'in isteği).

Üstte açılır seçim (bot, coin, dönem); yukarıda sabit duran fiyat grafiği (giriş ve çıkışlar işaretli);
altında her kriter bir açılır kutu: sayılar + / − düğmeleriyle değiştirilir ve grafik anında yenilenir
(küçük bir betik formu `/ayar?...&json=1` adresine gönderir, yanıttaki parçaları yerine koyar).
Betik çalışmazsa sayfa düz bir form olarak da çalışır (GET). Hiçbir şey kaydedilmez, canlı bota hiçbir şey gitmez.
Hesap ve açıklamalar için bkz. karabasan.ayar.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from html import escape

import pandas as pd

from . import ayar as a
from . import botlar as _botlar
from .kural import ekleme_fiyati

ONBELLEK = a.VeriOnbellegi()
HESAP_KAPISI = threading.Semaphore(2)   # aynı anda en çok iki hesap; panel öbür işlerini yapabilsin
VARSAYILAN_COIN = "ETH"
VARSAYILAN_GUN = 7
NEDENLER = {"zarar_durdur": "Stop", "iz_suren_stop": "İz süren stop", "kar_hedefi": "Kâr hedefi",
            "sure_asimi": "Süre doldu", "cikis_sinyali": "Çıkış sinyali"}


def sorgu_coz(sorgu: dict[str, list[str]]) -> dict:
    """Adres sorgusunu güvenli bir isteğe çevirir (bilinmeyen değer varsayılana düşer)."""
    def bir(ad: str, varsayilan: str = "") -> str:
        return (sorgu.get(ad) or [varsayilan])[0][:40]

    botlar = [b[0] for b in _botlar.BOTLAR]
    bot = bir("bot") if bir("bot") in botlar else botlar[0]
    coin = bir("coin").upper() if bir("coin").upper() in a.COINLER else VARSAYILAN_COIN

    def tam(ad: str, varsayilan: int, alt: int, ust: int) -> int:
        try:
            return min(max(int(float(bir(ad, str(varsayilan)).replace(",", "."))), alt), ust)
        except ValueError:
            return varsayilan

    istek = {"bot": bot, "bot0": bir("bot0"), "coin": coin,
             "gun": tam("gun", VARSAYILAN_GUN, 1, a.EN_FAZLA_GUN),
             "once": tam("once", 0, 0, a.EN_FAZLA_GERI), "p": {}, "goster": None, "tara": None}
    for ad, deger in sorgu.items():
        if ad[:1] == "p" and ad[1:].isdigit() and len(ad) <= 4 and deger:
            istek["p"][int(ad[1:])] = deger[0][:20]
    for alan in ("goster", "tara"):
        if bir(alan).isdigit() and len(bir(alan)) <= 3:
            istek[alan] = int(bir(alan))
    return istek


def _fiyat(f: float) -> str:
    from .sayfa import fiyat_metni

    return fiyat_metni(f)


def _zaman(z) -> str:
    from .sayfa import _tarih_saat

    return _tarih_saat(z, "Europe/Bucharest")


# --------------------------------------------------------------------------
# Grafik
# --------------------------------------------------------------------------


RENKLER = ["#5fd4ff", "#ffc24a", "#e879f9", "#a78bfa", "#fb923c", "#f472b6", "#38bdf8", "#facc15",
           "#c084fc", "#fdba74", "#67e8f9", "#f9a8d4"]


def renk(sira: int) -> str:
    return RENKLER[sira % len(RENKLER)]


def _ilk(i: dict) -> float:
    """İşlemin İLK giriş fiyatı: zararda ek girişte 'giris_fiyati' ortalamadır, mumların üstünde durmaz."""
    return float(i.get("ilk_giris_fiyati") or i["giris_fiyati"])


def _yollar(x_ler: list[float], y_ler: list) -> list[str]:
    """Çizgi parçaları: boş (NaN) olan yerde çizgi kopar."""
    parcalar, simdiki = [], []
    for xx, yy in zip(x_ler, y_ler):
        if yy is None:
            if len(simdiki) > 1:
                parcalar.append(simdiki)
            simdiki = []
        else:
            simdiki.append((xx, yy))
    if len(simdiki) > 1:
        parcalar.append(simdiki)
    return [" ".join(f"{'M' if k == 0 else 'L'}{xx:.1f},{yy:.1f}" for k, (xx, yy) in enumerate(p)) for p in parcalar]


def _kosular(dizi: list[bool]) -> list[tuple[int, int]]:
    """Art arda True olan aralıklar (başlangıç, bitiş dahil)."""
    sonuc, bas = [], None
    for i, v in enumerate(dizi + [False]):
        if v and bas is None:
            bas = i
        elif not v and bas is not None:
            sonuc.append((bas, i - 1))
            bas = None
    return sonuc


def grafik(df: pd.DataFrame, pencere_bas: pd.Timestamp, yeni: list[dict], eski: list[dict],
           engel: list[datetime], gun: int, satis: bool, katman: dict | None = None,
           kriter_adlari: list[str] | None = None, ek_fiyat=None) -> str:
    """Fiyat grafiği (satır içi SVG): mumlar tek renk; giriş bölgesi yeşil; şartların çizgi ve bantları;
    altta her şart için bir şerit ve en altta hepsinin kesişimi. Genişlik mum sayısıyla büyür; kutu yatay kaydırılır."""
    from .sayfa import _guzel_adimlar

    dk = a.parca_secimi(gun)
    tum_tarih = pd.to_datetime(df["date"], utc=True)
    pencere = df[tum_tarih >= pencere_bas]
    if pencere.empty:
        return '<p class="bos">Bu dönemde mum yok.</p>'
    anahtar = pd.to_datetime(pencere["date"], utc=True).dt.floor(f"{dk}min")
    cubuk = (pencere.assign(_k=anahtar.to_numpy()).groupby("_k")
             .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
             .reset_index().rename(columns={"_k": "date"}))
    n = len(cubuk)
    bw = 6.0 if n < 150 else 4.0
    seritler = katman["kosullar"] if katman else []
    serit_h, serit_ara = 8.0, 2.0
    sol, sag, ust, alt, h = 54.0, 10.0, 10.0, 22.0, 200.0
    serit_ust = h + 4.0
    toplam_h = serit_ust + (len(seritler) + 1) * (serit_h + serit_ara) + 6 if katman else h
    w = max(380.0, sol + sag + n * bw)
    fiyatlar = list(cubuk["high"]) + list(cubuk["low"]) + [_ilk(i) for i in yeni + eski] \
        + [float(i["cikis_fiyati"]) for i in yeni]
    en_alt, en_ust = min(fiyatlar), max(fiyatlar)
    pay = (en_ust - en_alt) * 0.06 or en_ust * 0.01
    y0, y1 = en_alt - pay, en_ust + pay
    t0 = cubuk["date"].iloc[0].timestamp()
    t1 = cubuk["date"].iloc[-1].timestamp() + dk * 60

    def x(z) -> float:
        return sol + (pd.Timestamp(z).timestamp() - t0) / (t1 - t0) * (w - sol - sag)

    def y(f: float) -> float:
        return ust + (y1 - f) / (y1 - y0) * (h - ust - alt)

    parca = []
    # Pencere içi her 5 dakikalık satırı çizim çubuğuna eşle (şeritler, çizgiler, giriş bölgesi).
    if katman:
        ts = pd.DatetimeIndex(katman["tarih"]).floor(f"{dk}min")
        bar_zamanlari = list(cubuk["date"])

        def gruplu(dizi, nasil: str):
            seri = pd.Series(list(dizi), index=ts)
            g = seri.groupby(level=0)
            sonuc = g.max() if nasil == "any" else g.last()
            return sonuc.reindex(bar_zamanlari)

    # 1) Giriş bölgesi (yeşil): hepsi doğru olan çubuklar, grafiğin ve şeritlerin tüm yüksekliğinde.
    if katman:
        hepsi = gruplu(katman["hepsi"], "any").fillna(False).astype(bool).tolist()
        kapat = toplam_h - 4
        for i, v in enumerate(hepsi):
            if v:
                xx = x(bar_zamanlari[i])
                parca.append(f'<rect class="ay-bolge" x="{xx - 1:.1f}" y="{ust:g}" width="{max(bw, 5):.1f}" '
                             f'height="{kapat - ust:.1f}"><title>Tüm şartlar aynı anda doğru · '
                             f'{_zaman(bar_zamanlari[i])}</title></rect>')
    # İşlemin açık kaldığı süre: hafif yeşil bant (fiyat alanında).
    for i in yeni:
        gx, cx = x(i["giris_zamani"]), x(i["cikis_zamani"])
        parca.append(f'<rect class="ay-sure" x="{gx:.1f}" y="{ust:g}" width="{max(cx - gx, 1):.1f}" height="{h - ust - alt:g}"/>')
    for f in _guzel_adimlar(y0, y1, 5):
        if y0 <= f <= y1:
            parca.append(f'<line class="g-izgara" x1="{sol:g}" x2="{w - sag:g}" y1="{y(f):.1f}" y2="{y(f):.1f}"/>'
                         f'<text class="g-eksen" x="4" y="{y(f):.1f}" dominant-baseline="middle">{_fiyat(f)}</text>')
    # 2) Şartların fiyat üstü çizgi ve bantları (kriter rengiyle).
    if katman:
        merkez = [x(z) + bw / 2 for z in bar_zamanlari]

        def kes(deger):   # grafiğin fiyat aralığı dışındaki değer çizilmez
            return None if (deger != deger or deger < y0 or deger > y1) else y(deger)

        for k in katman["cizgiler"]:
            c = renk(k["sira"])
            alt_d = gruplu(k["deger"], "last").tolist()
            if k["tur"] == "bant":
                ust_d = gruplu(k["ust"], "last").tolist()
                for bas_i, son_i in _kosular([(kes(u) is not None and kes(a_) is not None)
                                              for a_, u in zip(alt_d, ust_d)]):
                    ust_n = [(merkez[i], kes(ust_d[i])) for i in range(bas_i, son_i + 1)]
                    alt_n = [(merkez[i], kes(alt_d[i])) for i in range(son_i, bas_i - 1, -1)]
                    noktalar = " ".join(f"{xx:.1f},{yy:.1f}" for xx, yy in ust_n + alt_n)
                    parca.append(f'<polygon class="ay-bant" points="{noktalar}" fill="{c}" stroke="{c}">'
                                 f'<title>{k["sira"] + 1}. şart · {escape(k["ad"])}</title></polygon>')
            else:
                for d in _yollar(merkez, [kes(v) for v in alt_d]):
                    parca.append(f'<path class="ay-cizgi" d="{d}" stroke="{c}"><title>{k["sira"] + 1}. şart · '
                                 f'{escape(k["ad"])}</title></path>')
    # 3) Mumlar: tek renk (yön rengi yok).
    for _, m in cubuk.iterrows():
        orta = x(m["date"]) + bw / 2
        ustk, altk = y(max(m["open"], m["close"])), y(min(m["open"], m["close"]))
        parca.append(
            f'<g class="ay-mum"><line x1="{orta:.1f}" x2="{orta:.1f}" y1="{y(m["high"]):.1f}" y2="{y(m["low"]):.1f}"/>'
            f'<rect x="{orta - bw * 0.35:.1f}" y="{ustk:.1f}" width="{bw * 0.7:.1f}" height="{max(altk - ustk, 0.8):.1f}"/>'
            f'<title>{_zaman(m["date"])} · A {_fiyat(m["open"])} T {_fiyat(m["high"])} D {_fiyat(m["low"])} '
            f'K {_fiyat(m["close"])}</title></g>')
    gorulen = set()
    for z in engel:
        k = int(pd.Timestamp(z).timestamp() // (dk * 60))
        if k in gorulen:
            continue
        gorulen.add(k)
        parca.append(f'<polygon class="ay-engel" points="{x(z) + bw / 2:.1f},{h - alt - 9:.1f} {x(z) + bw / 2 + 4:.1f},{h - alt - 3:.1f} '
                     f'{x(z) + bw / 2 - 4:.1f},{h - alt - 3:.1f}"><title>Yalnız seçtiğin şart yüzünden giriş olmadı · {_zaman(z)}</title></polygon>')
    for i in eski:
        parca.append(f'<circle class="ay-eski" cx="{x(i["giris_zamani"]):.1f}" cy="{y(_ilk(i)):.1f}" r="6">'
                     f'<title>Canlı ayarın girişi · {_fiyat(_ilk(i))} · {_zaman(i["giris_zamani"])}</title></circle>')
    for i in yeni:
        gx, gy = x(i["giris_zamani"]), y(_ilk(i))
        cx, cy = x(i["cikis_zamani"]), y(float(i["cikis_fiyati"]))
        sinif = "arti" if float(i["net_yuzde"]) > 0 else "eksi"
        parca.append(f'<line class="ay-yol {sinif}" x1="{gx:.1f}" y1="{gy:.1f}" x2="{cx:.1f}" y2="{cy:.1f}"/>')
        d = 8.0
        nok = (f"{gx - d:.1f},{gy - d * 1.8:.1f} {gx + d:.1f},{gy - d * 1.8:.1f} {gx:.1f},{gy - 3:.1f}" if satis
               else f"{gx - d:.1f},{gy + d * 1.8:.1f} {gx + d:.1f},{gy + d * 1.8:.1f} {gx:.1f},{gy + 3:.1f}")
        parca.append(f'<g class="ig-isaret giris"><polygon points="{nok}"/><circle cx="{gx:.1f}" cy="{gy:.1f}" r="3.2"/>'
                     f'<title>Giriş {_fiyat(_ilk(i))} · {_zaman(i["giris_zamani"])}</title></g>')
        if ek_fiyat and i.get("ekleme_zamani") is not None:
            ef = ek_fiyat(_ilk(i))
            ex, ey = x(i["ekleme_zamani"]), y(ef)
            nok2 = (f"{ex - 6:.1f},{ey - 11:.1f} {ex + 6:.1f},{ey - 11:.1f} {ex:.1f},{ey - 2:.1f}" if satis
                    else f"{ex - 6:.1f},{ey + 11:.1f} {ex + 6:.1f},{ey + 11:.1f} {ex:.1f},{ey + 2:.1f}")
            parca.append(f'<g class="ig-isaret ek"><polygon points="{nok2}" fill="#ff9f43"/>'
                         f'<title>Zararda ek giriş ~{_fiyat(ef)} · {_zaman(i["ekleme_zamani"])}</title></g>')
        parca.append(f'<g class="ig-isaret cikis"><circle cx="{cx:.1f}" cy="{cy:.1f}" r="4"/>'
                     f'<title>Çıkış {_fiyat(float(i["cikis_fiyati"]))} · {_zaman(i["cikis_zamani"])} · '
                     f'{NEDENLER.get(i["neden"], i["neden"])} · {float(i["net_yuzde"]):+.2f}%</title></g>')
    for k in range(0, 6):
        t = t0 + (t1 - t0) * (0.03 + 0.94 * k / 5)
        z = datetime.fromtimestamp(t, tz=timezone.utc)
        parca.append(f'<text class="g-eksen" x="{x(z):.1f}" y="{h - 8:g}" text-anchor="middle">{escape(_zaman(z))}</text>')
    # 4) Şeritler: her şart bir satır (doğru olduğu yerler boyalı), en altta kesişim (yeşil).
    if katman:
        satirlar = [(f"{i + 1}", renk(i), gruplu(d, "any").fillna(False).astype(bool).tolist(),
                     (kriter_adlari[i] if kriter_adlari and i < len(kriter_adlari) else f"{i + 1}. şart"))
                    for i, d in enumerate(seritler)]
        satirlar.append(("✓", "#5af0b2", hepsi, "Hepsi aynı anda doğru: giriş sinyali"))
        for r, (etiket, c, dizi, ad) in enumerate(satirlar):
            yy = serit_ust + r * (serit_h + serit_ara)
            parca.append(f'<rect class="ay-serit" x="{sol:g}" y="{yy:g}" width="{w - sol - sag:g}" height="{serit_h:g}"/>')
            parca.append(f'<text class="ay-serit-no" x="{sol - 6:g}" y="{yy + serit_h / 2 + 0.5:g}" text-anchor="end" '
                         f'dominant-baseline="middle" fill="{c}">{etiket}</text>')
            for bas_i, son_i in _kosular(dizi):
                xx = x(bar_zamanlari[bas_i])
                ww = max(x(bar_zamanlari[son_i]) + bw - xx, 2)
                parca.append(f'<rect class="ay-serit-dolu" x="{xx:.1f}" y="{yy:g}" width="{ww:.1f}" height="{serit_h:g}" '
                             f'fill="{c}"><title>{escape(ad)} · doğru ({_zaman(bar_zamanlari[bas_i])})</title></rect>')
    return (f'<div class="ay-kaydir"><svg class="g-svg ig-svg" style="width:{w:g}px;min-width:100%" '
            f'viewBox="0 0 {w:g} {toplam_h:g}" role="img" aria-label="Fiyat grafiği: giriş bölgesi yeşil, şartların çizgileri ve şeritleri">'
            f'{"".join(parca)}</svg></div>')


# --------------------------------------------------------------------------
# Parçalar
# --------------------------------------------------------------------------


def _deger_yazisi(x) -> str:
    return f"{x:g}".replace(".", ",")


def _ozet_kutusu(ad: str, o: dict, sinyal: int, vurgu: bool) -> str:
    net = o["net_toplam"]
    sinif = "arti" if net > 0 else "eksi" if net < 0 else ""
    kazanma = f"%{100 * o['kazanan'] / o['islem']:.0f}" if o["islem"] else "–"
    kisa = "Senin" if ad.startswith("Senin") else "Canlı"
    return (f'<div class="ay-ozet{" vurgu" if vurgu else ""}" title="{escape(ad)} · sinyal sayısı {sinyal} · '
            f'{kazanma} kazanan"><b>{kisa}</b><span>{o["islem"]} işlem</span><span>{kazanma}</span>'
            f'<span class="{sinif}">{net:+.2f}%</span></div>')


def _adim(deger) -> float:
    """+ / − düğmesinin bir basışta değiştirdiği miktar."""
    if isinstance(deger, int) and not isinstance(deger, bool):
        return 1 if abs(deger) < 50 else 5
    d = abs(float(deger))
    return 0.05 if d < 0.5 else 0.1 if d < 5 else 0.5


def _girdi(idx: int, ad: str, deger, ilk, ipucu: str = "") -> str:
    tam = isinstance(ilk, int) and not isinstance(ilk, bool)
    adim = _adim(ilk)
    degisti = abs(float(deger) - float(ilk)) > 1e-9
    aciklama = f'<small class="ay-ipucu">{escape(ipucu)}</small>' if ipucu else ""
    return (f'<div class="ay-satir{" degisti" if degisti else ""}"><label for="p{idx}">{escape(ad)}</label>{aciklama}'
            f'<span class="ay-girdi"><button type="button" class="ay-b ay-ek" data-adim="-{adim:g}" data-hedef="p{idx}" '
            f'aria-label="Azalt">−</button>'
            f'<input id="p{idx}" name="p{idx}" type="text" inputmode="decimal" autocomplete="off" '
            f'value="{escape(_deger_yazisi(deger))}" data-ilk="{escape(_deger_yazisi(ilk))}" data-tam="{1 if tam else 0}" '
            f'data-min="{0 if float(ilk) > 0 else ""}">'
            f'<button type="button" class="ay-b ay-ek" data-adim="{adim:g}" data-hedef="p{idx}" aria-label="Artır">+</button>'
            f'<button class="ay-kucuk" type="submit" name="tara" value="{idx}" '
            f'title="Bu sayının çevresindeki değerleri dene">Tara</button></span>'
            f'<div class="ay-tara" id="tara{idx}"></div></div>')


def _rozet(olcum: dict | None) -> str:
    """Kriter başlığının sağındaki canlı özet: kaç mumda doğru, kaç girişi tek başına engelliyor."""
    if not olcum:
        return ""
    engel = olcum["engel_sayisi"]
    return (f'<span class="ay-r">%{100 * olcum["dogru_oran"]:.0f}</span>'
            + (f'<span class="ay-r engel" title="Yalnız bu şart yüzünden giriş olmayan mum sayısı">{engel} engel</span>'
               if engel else ""))


def _kriter_listesi(kural, simdiki: dict, ilkler: dict, olc: list[dict] | None, istek: dict) -> tuple[str, int]:
    kartlar, idx = [], 0
    for k in a.kriterler(kural):
        girdiler = []
        for yol, ad, _eski in k["sayilar"]:
            girdiler.append(_girdi(idx, ad, simdiki[yol], ilkler[yol], a.sayi_aciklamasi(kural, yol)))
            idx += 1
        bilgi = a.kriter_bilgisi(kural, k["sira"])
        sozluk = "".join(f"<li>{escape(x)}</li>" for x in bilgi["sozluk"])
        ne = (f'<div class="ay-bilgi"><p><b>Bu şart ne diyor?</b> {escape(bilgi["anlam"])}</p>'
              f'{"<ul>" + sozluk + "</ul>" if sozluk else ""}</div>')
        goster = (f'<button class="ay-kucuk{" secili" if istek["goster"] == k["sira"] else ""}" type="submit" '
                  f'name="goster" value="{k["sira"]}" data-goster="{k["sira"]}">Girişi engellediği yerleri grafikte göster</button>')
        ipucu = ("" if girdiler else "<p class=alt>Bu şartın kendi sayısı yok; ilgili göstergenin periyodunu "
                 "aşağıdaki Göstergeler bölümünden değiştirebilirsin.</p>")
        kartlar.append(
            f'<details class="ay-ac" id="k{k["sira"]}"><summary>'
            f'<span class="ay-no" style="background:{renk(k["sira"])}">{k["sira"] + 1}</span>'
            f'<span class="ay-ad">{escape(k["yazi"])}</span>'
            f'<span class="ay-rozet" id="rozet{k["sira"]}">{_rozet(olc[k["sira"]] if olc else None)}</span></summary>'
            f'<div class="ay-ic">{ne}{ipucu}{"".join(girdiler)}{goster}</div></details>')
    return "".join(kartlar), idx


def _grup(baslik: str, aciklama: str, sayilar, bas: int, simdiki: dict, ilkler: dict, kural=None) -> str:
    satirlar = "".join(_girdi(bas + j, ad, simdiki[yol], ilkler[yol], a.sayi_aciklamasi(kural, yol) if kural else "")
                       for j, (yol, ad, _e) in enumerate(sayilar))
    if not satirlar:
        return ""
    return (f'<details class="ay-ac"><summary><span class="ay-ad">{escape(baslik)}</span></summary>'
            f'<div class="ay-ic"><p class="alt">{escape(aciklama)}</p>{satirlar}</div></details>')


def _islem_tablosu(islemler: list[dict]) -> str:
    if not islemler:
        return '<p class="bos">Bu ayarla bu dönemde işlem açılmadı.</p>'
    satirlar = "".join(
        f'<tr><td>{_zaman(i["giris_zamani"])}</td><td>{_fiyat(_ilk(i))}</td>'
        f'<td>{_fiyat(float(i["cikis_fiyati"]))}</td><td>{escape(NEDENLER.get(i["neden"], i["neden"]))}</td>'
        f'<td class="{"arti" if float(i["net_yuzde"]) > 0 else "eksi"}">{float(i["net_yuzde"]):+.2f}%</td></tr>'
        for i in islemler[-40:])
    return ('<table class="ay-tablo"><thead><tr><th>Giriş</th><th>Fiyat</th><th>Çıkış</th><th>Neden</th><th>Net</th></tr></thead>'
            f'<tbody>{satirlar}</tbody></table>')


def _tarama_tablosu(satirlar: list[dict], simdiki) -> str:
    govde = "".join(
        f'<tr class="{"secili" if abs(s["deger"] - simdiki) < 1e-9 else ""}"><td>{_deger_yazisi(s["deger"])}</td>'
        + (f'<td colspan="3" class="alt">{escape(s["hata"])}</td></tr>' if s.get("hata") else
           f'<td>{s["ozet"]["islem"]}</td><td>{s["ozet"]["kazanan"]}</td>'
           f'<td class="{"arti" if s["ozet"]["net_toplam"] > 0 else "eksi" if s["ozet"]["net_toplam"] < 0 else ""}">'
           f'{s["ozet"]["net_toplam"]:+.2f}%</td></tr>')
        for s in satirlar)
    return ('<p class="alt">Yalnız bu sayı değişir. Çok değer denedikçe birinin geçmişte şans eseri iyi görünmesi '
            'kolaylaşır: en iyi görüneni seçmek ayar değil, ezberdir.</p>'
            '<table class="ay-tablo"><thead><tr><th>Değer</th><th>İşlem</th><th>Kazanan</th><th>Net</th></tr></thead>'
            f'<tbody>{govde}</tbody></table>')


AYAR_STIL = """
.ay-form{display:block}
.ay-giris{margin:4px 0 8px;font-size:.8125rem;color:var(--soluk)}
.ay-secim{border:1px solid var(--cizgi);border-radius:12px;background:var(--cam);margin:0 0 8px}
.ay-secim>summary{list-style:none;cursor:pointer;min-height:44px;display:flex;align-items:center;gap:8px;padding:0 12px;font-weight:600}
.ay-secim>summary::-webkit-details-marker,.ay-ac>summary::-webkit-details-marker{display:none}
.ay-secim>summary::after,.ay-ac>summary::after{content:"▾";margin-left:auto;color:var(--soluk)}
.ay-secim[open]>summary::after,.ay-ac[open]>summary::after{content:"▴"}
.ay-ust{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:0 12px 12px}
.ay-ust label,.ay-satir label{display:block;font-size:.8125rem;color:var(--soluk);margin-bottom:4px}
.ay-ust select,.ay-ust input,.ay-girdi input{width:100%;min-height:44px;box-sizing:border-box;padding:0 12px;border-radius:12px;
border:1px solid var(--cizgi);background:var(--cam);color:var(--buz);font:inherit;font-size:1rem}
.ay-ust .tam{grid-column:1/-1}
.ay-dugme{min-height:44px;padding:0 20px;border-radius:999px;border:1px solid var(--holo);background:var(--holo);color:#04141c;
font:700 1rem/1 inherit;cursor:pointer}
.ay-bag{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;border-radius:999px;border:1px solid var(--cizgi);
text-decoration:none;font-size:.875rem}
.ay-sabitust{position:sticky;top:var(--ay-ust,60px);z-index:6;background:var(--gece);padding:4px 0 6px;
border-bottom:1px solid var(--cizgi)}
.ay-sabitust .kose{margin:0;padding:6px 4px}
.ay-durum{position:absolute;right:8px;top:8px;font-size:.6875rem;color:var(--altin);pointer-events:none}
.ay-kaydir{overflow-x:auto;-webkit-overflow-scrolling:touch}
.ay-yol{stroke-width:1.5;stroke-dasharray:3 3;vector-effect:non-scaling-stroke}
.ay-yol.arti{stroke:var(--arti)}.ay-yol.eksi{stroke:var(--eksi)}
.ay-bolge{fill:rgba(90,240,178,.22);stroke:rgba(90,240,178,.55);stroke-width:1;vector-effect:non-scaling-stroke}
.ay-sure{fill:rgba(90,240,178,.06)}
.ay-mum line{stroke:#9fb3c8;stroke-width:1;vector-effect:non-scaling-stroke}
.ay-mum rect{fill:rgba(159,179,200,.28);stroke:#9fb3c8;stroke-width:.8;vector-effect:non-scaling-stroke}
.ay-cizgi{fill:none;stroke-width:1.6;vector-effect:non-scaling-stroke}
.ay-bant{fill-opacity:.16;stroke-opacity:.8;stroke-width:1;vector-effect:non-scaling-stroke}
.ay-serit{fill:rgba(159,179,200,.08)}.ay-serit-dolu{fill-opacity:.7}
.ay-serit-no{font:600 8px var(--rakam,monospace)}
.ay-eski{fill:none;stroke:var(--soluk);stroke-width:1.5}
.ay-engel{fill:var(--altin)}
.ay-ozetler{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:6px 0 0}
.ay-ozet{display:flex;gap:10px;align-items:baseline;border:1px solid var(--cizgi);border-radius:10px;
padding:4px 8px;background:var(--cam);font-size:.6875rem;white-space:nowrap}
.ay-ozet.vurgu{border-color:var(--holo)}.ay-ozet b{font-size:.75rem}
.ay-uyari{margin:4px 0 0;font-size:.6875rem;color:var(--altin)}
.ay-hata{border:1px solid var(--eksi);border-radius:10px;padding:6px 10px;margin:4px 0;font-size:.8125rem;color:var(--eksi)}
.ay-liste{margin-top:10px}
.ay-ac{border:1px solid var(--cizgi);border-radius:12px;background:var(--cam);margin:8px 0}
.ay-ac>summary{list-style:none;cursor:pointer;min-height:48px;display:flex;align-items:center;gap:8px;padding:6px 12px;font-size:.875rem}
.ay-ad{flex:1;line-height:1.3}
.ay-no{display:inline-flex;flex:none;width:22px;height:22px;border-radius:50%;color:#04141c;font-size:.75rem;
font-weight:700;align-items:center;justify-content:center}
.ay-rozet{display:flex;flex:none;gap:4px}
.ay-r{font-size:.6875rem;border:1px solid var(--cizgi);border-radius:999px;padding:1px 7px;color:var(--soluk)}
.ay-r.engel{border-color:var(--altin);color:var(--altin)}
.ay-ic{padding:0 12px 12px}
.ay-bilgi{background:rgba(95,212,255,.06);border-radius:10px;padding:8px 10px;margin:0 0 10px;font-size:.8125rem;line-height:1.45}
.ay-bilgi p{margin:0 0 4px}.ay-bilgi ul{margin:4px 0 0;padding-left:18px;color:var(--soluk)}.ay-bilgi li{margin:3px 0}
.ay-ipucu{display:block;font-size:.75rem;line-height:1.35;color:var(--soluk);margin:-2px 0 6px}
.ay-satir{margin:8px 0}.ay-satir.degisti input{border-color:var(--altin)}
.ay-girdi{display:flex;gap:6px}.ay-girdi input{text-align:center;min-width:0;flex:1}
.ay-b{display:none;flex:none;width:44px;min-height:44px;align-items:center;justify-content:center;border-radius:12px;
border:1px solid var(--holo);background:transparent;color:var(--holo);font:700 1.25rem/1 inherit;cursor:pointer;touch-action:manipulation}
.js .ay-b{display:inline-flex}
.ay-kucuk{min-height:44px;padding:0 12px;border-radius:12px;border:1px solid var(--cizgi);background:transparent;color:var(--holo);
font:inherit;font-size:.8125rem;cursor:pointer}
.ay-ic>.ay-kucuk{margin-top:6px}
.ay-kucuk.secili{border-color:var(--altin);color:var(--altin)}
.ay-tablo{width:100%;border-collapse:collapse;font-size:.8125rem}
.ay-tablo th,.ay-tablo td{padding:6px 4px;text-align:left;border-bottom:1px solid var(--cizgi)}
.ay-tablo tr.secili td{background:rgba(95,212,255,.08)}
.ay-tara:not(:empty){margin-top:8px;border-top:1px dashed var(--cizgi);padding-top:6px}
.ay-aciklama{margin:6px 0}
.ay-aciklama>summary{cursor:pointer;min-height:44px;display:flex;align-items:center;font-size:.8125rem;color:var(--soluk)}
"""

BETIK = r"""
(function(){
var f=document.getElementById('ay-form');
if(!f||!window.fetch||!window.URLSearchParams)return;
document.documentElement.classList.add('js');
var bar=document.querySelector('.baslik-cubugu');
if(bar)document.documentElement.style.setProperty('--ay-ust',bar.offsetHeight+'px');
var bekle=null,kontrol=null,durum=document.getElementById('ay-durum');
function d(m){if(durum)durum.textContent=m||'';}
function koy(id,h){var e=document.getElementById(id);if(e&&h!=null)e.innerHTML=h;}
function sorgu(ek){
  var p=new URLSearchParams(new FormData(f));
  if(ek)for(var k in ek)p.set(k,ek[k]);
  return p;
}
function uygula(v,taraId){
  if(v.grafik!=null){
    var k=document.querySelector('#ay-grafik .ay-kaydir'),sol=k?k.scrollLeft:0;
    koy('ay-grafik',v.grafik);
    var y=document.querySelector('#ay-grafik .ay-kaydir');if(y)y.scrollLeft=sol;
  }
  koy('ay-ozet',v.ozet);koy('ay-mesaj',v.mesaj);koy('ay-anahtar',v.anahtar);koy('ay-islemler',v.islemler);
  if(v.secim!=null){var s=document.getElementById('ay-secim-yazi');if(s)s.textContent=v.secim;}
  if(v.rozet)for(var i=0;i<v.rozet.length;i++)koy('rozet'+i,v.rozet[i]);
  if(taraId!=null)koy('tara'+taraId,v.tara||'');
  d('');
}
function calistir(ek,taraId){
  if(kontrol)kontrol.abort();
  kontrol=new AbortController();
  var p=sorgu(ek);p.set('json','1');d('Hesaplanıyor…');
  fetch('/ayar?'+p.toString(),{signal:kontrol.signal,headers:{'Accept':'application/json'}})
   .then(function(r){if(!r.ok)throw new Error('http '+r.status);return r.json();})
   .then(function(v){uygula(v,taraId);})
   .catch(function(e){if(e&&e.name==='AbortError')return;d('Bağlantı hatası: yeniden dene');});
}
function sonra(){
  document.querySelectorAll('.ay-tara').forEach(function(e){e.innerHTML='';});
  clearTimeout(bekle);bekle=setTimeout(function(){calistir();},350);
}
function isaretle(i){
  var s=i.closest('.ay-satir');if(!s)return;
  var a=parseFloat(String(i.value).replace(',','.')),b=parseFloat(String(i.dataset.ilk).replace(',','.'));
  s.classList.toggle('degisti',!(Math.abs(a-b)<1e-9));
}
f.addEventListener('submit',function(e){e.preventDefault();clearTimeout(bekle);calistir();});
f.addEventListener('input',function(e){
  var t=e.target;
  if(t.matches('.ay-girdi input')){isaretle(t);sonra();}
  else if(t.id==='gun'||t.id==='once'){sonra();}
});
f.addEventListener('change',function(e){
  var t=e.target;
  if(t.id==='bot'){f.submit();}      // bot değişince alanlar da değişir: sayfa yenilenir (submit olayı tetiklenmez)
  else if(t.id==='coin'){sonra();}
});
f.addEventListener('click',function(e){
  var b=e.target.closest('button');if(!b||!f.contains(b))return;
  if(b.dataset.adim){
    e.preventDefault();
    var i=document.getElementById(b.dataset.hedef);
    var v=parseFloat(String(i.value).replace(',','.'));if(isNaN(v))return;
    v=Math.round((v+parseFloat(b.dataset.adim))*10000)/10000;
    if(i.dataset.min!==''&&i.dataset.min!=null&&v<parseFloat(i.dataset.min))v=parseFloat(i.dataset.min);
    if(i.dataset.tam==='1')v=Math.round(v);
    i.value=String(v).replace('.',',');isaretle(i);sonra();
  }else if(b.name==='tara'){
    e.preventDefault();
    document.querySelectorAll('.ay-tara').forEach(function(x){x.innerHTML='';});
    clearTimeout(bekle);
    var t=document.getElementById('tara'+b.value);if(t)t.textContent='Deneniyor…';
    calistir({tara:b.value},b.value);
  }else if(b.name==='goster'){
    e.preventDefault();
    var h=f.elements['goster'],acik=b.classList.contains('secili');
    document.querySelectorAll('[data-goster]').forEach(function(x){x.classList.remove('secili');});
    if(!acik)b.classList.add('secili');
    if(h)h.value=acik?'':b.value;
    clearTimeout(bekle);calistir();
  }
});
})();
"""


def guvenlik_basligi() -> str:
    """Sayfa tek bir satır içi betik çalıştırır (özetiyle sınırlı); yalnız kendi adresine veri çeker ve form gönderir."""
    ozet = base64.b64encode(hashlib.sha256(BETIK.encode("utf-8")).digest()).decode("ascii")
    return ("default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
            f"script-src 'sha256-{ozet}'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")


def _kabuk(govde: str) -> str:
    from .islem_grafik import ISLEM_STIL
    from .sayfa import STIL

    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#04070d"><meta name="robots" content="noindex">
<title>Karabasan · Kriter ayarı</title><style>{STIL}{ISLEM_STIL}{AYAR_STIL}</style></head>
<body><div class="sayfa">
<header class="ust baslik-cubugu"><a class="marka" href="/#ana">KARABASAN</a>
<a class="ig-geri" href="/#kriterler" style="margin-left:auto">← Ana sayfa</a></header>
<main><h2 class="ekran-baslik">Kriter ayarı</h2>{govde}</main></div><script>{BETIK}</script></body></html>"""


# Baz (canlı ayar) sonucu: aynı bot, coin ve dönem için her + / − basışında yeniden hesaplanmasın.
_TEMEL: dict = {}
_TEMEL_KILIT = threading.Lock()


def _temel_sonuc(anahtar, uret):
    with _TEMEL_KILIT:
        if anahtar in _TEMEL:
            return _TEMEL[anahtar]
    deger = uret()
    with _TEMEL_KILIT:
        if len(_TEMEL) >= 16:
            _TEMEL.pop(next(iter(_TEMEL)))
        _TEMEL[anahtar] = deger
    return deger


def hesapla(istek: dict, onbellek: a.VeriOnbellegi | None = None, getir=None,
            simdi: datetime | None = None) -> dict:
    """İsteği hesaplar; sayfa ve canlı yanıt (JSON) aynı sonucu kullanır."""
    onbellek = onbellek or ONBELLEK
    getir = getir or a.binance_getir
    simdi = (simdi or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    simdi -= timedelta(minutes=simdi.minute % 5)
    bot, coin, gun, once = istek["bot"], istek["coin"], istek["gun"], istek["once"]
    kural = a.kural_hazirla(bot)
    sayilar = a.tum_sayilar(kural)
    mesajlar: list[str] = []

    degisim: dict[str, float] = {}
    if istek["bot0"] == bot:
        for idx, (yol, ad, eski) in enumerate(sayilar):
            if idx in istek["p"]:
                try:
                    yeni_deger = a.sayi_oku(istek["p"][idx])
                except a.AyarHatasi as hata:
                    mesajlar.append(f"{ad}: {hata}")
                    continue
                if abs(yeni_deger - float(eski)) > 1e-9:
                    degisim[yol] = yeni_deger
    kopya = kural
    if degisim:
        try:
            kopya = a.uygula(kural, degisim)
        except a.AyarHatasi as hata:
            mesajlar.append(str(hata) + " Canlı ayar gösteriliyor.")
            degisim = {}
    ctx = {"istek": istek, "kural": kural, "kopya": kopya, "sayilar": sayilar, "degisim": degisim, "mesajlar": mesajlar,
           "simdiki": {yol: a._al(kopya, yol) for yol, _ad, _e in sayilar},
           "ilkler": {yol: eski for yol, _ad, eski in sayilar}, "hata": None, "tarama": None}
    bitis = simdi - timedelta(days=once)
    pencere_bas = pd.Timestamp(bitis - timedelta(days=gun))
    ctx.update(bitis=bitis, pencere_bas=pencere_bas)
    try:
        with HESAP_KAPISI:
            df, ek = a.veri_topla(kural, coin, "vadeli", bitis, gun, getir, onbellek, diger=kopya if degisim else None)
            if df.empty or not len(df[pd.to_datetime(df["date"], utc=True) >= pencere_bas]):
                raise a.AyarHatasi("Bu coin için bu dönemde mum bulunamadı.")
            temel = _temel_sonuc((bot, coin, gun, once, int(bitis.timestamp()),
                                  hashlib.sha1(json.dumps(kural, sort_keys=True).encode()).hexdigest()),
                                 lambda: a.calistir(kural, df, ek, pencere_bas, kriter_olc=True))
            yeni = a.calistir(kopya, df, ek, pencere_bas, kriter_olc=True) if degisim else temel
            ctx.update(df=df, yeni=yeni, eski=temel)
            if istek["tara"] is not None and 0 <= istek["tara"] < len(sayilar):
                yol = sayilar[istek["tara"]][0]
                satirlar = []
                for v in a.tarama_degerleri(ctx["simdiki"][yol]):
                    try:
                        k2 = a.uygula(kopya, {yol: v})
                        satirlar.append({"deger": v, "ozet": a.calistir(k2, df, ek, pencere_bas)["ozet"]})
                    except a.AyarHatasi as hata:
                        satirlar.append({"deger": v, "hata": str(hata)[:90]})
                ctx["tarama"] = (satirlar, ctx["simdiki"][yol])
    except a.AyarHatasi as hata:
        ctx["hata"] = str(hata)
    except Exception as hata:  # noqa: BLE001 - ağ hatası sayfayı düşürmesin
        ctx["hata"] = f"Fiyat verisi şu an alınamadı ({type(hata).__name__}). Biraz sonra yeniden dene."
    return ctx


def parcalar(ctx: dict) -> dict:
    """Canlı güncellenen parçalar (HTML metni). Hata varsa grafik None: ekrandaki son grafik kalır."""
    istek, kural, kopya, degisim = ctx["istek"], ctx["kural"], ctx["kopya"], ctx["degisim"]
    coin, gun = istek["coin"], istek["gun"]
    sonuc = {"secim": f'{[b[2] for b in _botlar.BOTLAR if b[0] == istek["bot"]][0]} · {coin} · {gun} gün'
                      + (f' · {istek["once"]} gün geri' if istek["once"] else ""),
             "mesaj": "".join(f'<p class="ay-hata">{escape(m)}</p>' for m in ctx["mesajlar"])}
    if ctx["hata"]:
        sonuc["mesaj"] += f'<p class="ay-hata">{escape(ctx["hata"])}</p>'
        sonuc.update(grafik=None, ozet=None, anahtar=None, islemler=None, rozet=None)
        return sonuc
    yeni, eski, df = ctx["yeni"], ctx["eski"], ctx["df"]
    satis = kural["yon"] == "aciga_satis"
    engel = []
    if istek["goster"] is not None and istek["goster"] < len(yeni["kriterler"]):
        engel = yeni["kriterler"][istek["goster"]]["engel_zamanlari"]
    katman = yeni["katman"]
    adlar = [k["yazi"] for k in a.kriterler(kopya)]
    ek_fn = (lambda ilk: ekleme_fiyati(kopya, ilk)) if kopya.get("zararda_ekleme") else None
    sonuc["grafik"] = (f'<div class="kose kart">{grafik(df, ctx["pencere_bas"], yeni["islemler"], eski["islemler"] if degisim else [], engel, gun, satis, katman, adlar, ek_fn)}</div>')
    katman_anahtari = "".join(
        f'<span><i style="border-color:{renk(k["sira"])}{";border-top-width:6px;opacity:.7" if k["tur"] == "bant" else ""}"></i>'
        f'{k["sira"] + 1}. şart: {escape(k["ad"])} ({"bölge" if k["tur"] == "bant" else "çizgi"})</span>'
        for k in katman["cizgiler"])
    sonuc["anahtar"] = (
        '<div class="ig-anahtar"><span><b style="background:rgba(90,240,178,.55);border-radius:2px"></b>'
        'Giriş bölgesi: tüm şartlar aynı anda doğru</span>'
        '<span><b style="background:var(--holo)"></b>Giriş</span><span><b style="background:#f2ede2"></b>Çıkış</span>'
        + katman_anahtari
        + ('<span><b style="background:transparent;border:1.5px solid var(--soluk)"></b>Canlı ayarın girişi</span>' if degisim else "")
        + ('<span><b style="background:var(--altin);border-radius:2px"></b>Seçili şart yüzünden olmayan giriş</span>' if engel else "")
        + f'<span>{escape(coin)}/USDT · {_zaman(ctx["pencere_bas"])} → {_zaman(pd.Timestamp(ctx["bitis"]))}</span></div>')
    kutular = _ozet_kutusu("Senin ayarın" if degisim else "Canlı ayar", yeni["ozet"], yeni["sinyal_sayisi"], True)
    if degisim:
        kutular += _ozet_kutusu("Canlı ayar", eski["ozet"], eski["sinyal_sayisi"], False)
    uyari = ('<p class="ay-uyari">30\'dan az işlem: sonuç şans olabilir.</p>'
             if yeni["ozet"]["islem"] < 30 else "")
    sonuc["ozet"] = f'<div class="ay-ozetler">{kutular}</div>{uyari}'
    sonuc["rozet"] = [_rozet(o) for o in yeni["kriterler"]]
    sonuc["islemler"] = _islem_tablosu(yeni["islemler"])
    sonuc["tara"] = _tarama_tablosu(*ctx["tarama"]) if ctx["tarama"] else ""
    return sonuc


def ayar_json(istek: dict, onbellek=None, getir=None, simdi=None) -> str:
    ctx = hesapla(istek, onbellek, getir, simdi)
    return json.dumps(parcalar(ctx), ensure_ascii=False)


def ayar_sayfasi(istek: dict, onbellek: a.VeriOnbellegi | None = None, getir=None,
                 simdi: datetime | None = None) -> str:
    ctx = hesapla(istek, onbellek, getir, simdi)
    p = parcalar(ctx)
    bot, coin, gun, once = istek["bot"], istek["coin"], istek["gun"], istek["once"]
    kopya, kural = ctx["kopya"], ctx["kural"]
    botlar = "".join(f'<option value="{escape(b[0])}"{" selected" if b[0] == bot else ""}>{escape(b[2])}</option>'
                     for b in _botlar.BOTLAR)
    coinler = "".join(f'<option{" selected" if c == coin else ""}>{c}</option>' for c in a.COINLER)
    secim = f"""<details class="ay-secim"><summary><span id="ay-secim-yazi">{escape(p["secim"])}</span></summary>
<div class="ay-ust">
<div class="tam"><label for="bot">Bot</label><select id="bot" name="bot">{botlar}</select></div>
<div><label for="coin">Coin</label><select id="coin" name="coin">{coinler}</select></div>
<div><label for="gun">Kaç gün bak (1–{a.EN_FAZLA_GUN})</label><input id="gun" name="gun" type="number" inputmode="numeric" min="1" max="{a.EN_FAZLA_GUN}" value="{gun}"></div>
<div class="tam"><label for="once">Geri sar: dönem kaç gün önce bitsin (0 = bugün)</label><input id="once" name="once" type="number" inputmode="numeric" min="0" max="{a.EN_FAZLA_GERI}" value="{once}"></div>
<div class="tam"><noscript><button class="ay-dugme" type="submit">Çalıştır</button> </noscript>
<a class="ay-bag" href="/ayar?bot={escape(bot)}&amp;coin={coin}&amp;gun={gun}&amp;once={once}">Canlı ayara dön</a></div>
</div></details>"""
    if ctx["hata"]:
        govde = (f'<form id="ay-form" class="ay-form" method="get" action="/ayar"><input type="hidden" name="bot0" value="{escape(bot)}">'
                 f'<input type="hidden" name="goster" value="">{secim}<div id="ay-mesaj">{p["mesaj"]}</div>'
                 '<div id="ay-grafik"></div><div id="ay-ozet"></div></form>')
        return _kabuk(govde)
    istek_g = istek
    kriter_html, nk = _kriter_listesi(kopya, ctx["simdiki"], ctx["ilkler"], ctx["yeni"]["kriterler"], istek_g)
    kriter_say = sum(len(k["sayilar"]) for k in a.kriterler(kural))
    gosterge = a.gosterge_sayilari(kural)
    cikis = a.cikis_sayilari(kural)
    govde = f"""<form id="ay-form" class="ay-form" method="get" action="/ayar">
<input type="hidden" name="bot0" value="{escape(bot)}">
<input type="hidden" name="goster" value="{istek['goster'] if istek['goster'] is not None else ''}">
<p class="ay-giris">Sayıyı değiştir ya da + / − bas: grafik anında yenilenir. Canlı botlar değişmez, hiçbir şey kaydedilmez.</p>
{secim}
<div class="ay-sabitust" id="ay-sabit"><span class="ay-durum" id="ay-durum"></span>
<div id="ay-mesaj">{p["mesaj"]}</div>
<div id="ay-grafik">{p["grafik"]}</div>
<div id="ay-ozet">{p["ozet"]}</div></div>
<details class="ay-aciklama"><summary>Renkler ve işaretler ne demek?</summary><div id="ay-anahtar">{p["anahtar"]}</div></details>
<div class="ay-liste">
<p class="ay-giris"><b>Giriş şartları:</b> hepsi aynı anda doğru olunca bot girer. Bir şartı açınca ne dediğini ve her sayının ne işe yaradığını görürsün.</p>
{kriter_html}
{_grup("Göstergeler", "Göstergenin kaç muma baktığı. Aynı gösterge birkaç şartta kullanılır; değiştirmek hepsini etkiler. Ne olduğu ilgili şartın içinde yazıyor.", gosterge, kriter_say, ctx["simdiki"], ctx["ilkler"], kopya)}
{_grup("Giriş emri ve çıkış", "Girişin nasıl konduğu ve işlemin nasıl kapandığı.", cikis, kriter_say + len(gosterge), ctx["simdiki"], ctx["ilkler"], kopya)}
</div>
<details class="ay-ac"><summary><span class="ay-ad">Bu ayarla açılan işlemler</span></summary>
<div class="ay-ic" id="ay-islemler">{p["islemler"]}</div></details>
<p class="g-not">Hesap, bağımsız mum benzetimidir (hazır motor değil); Binance’in herkese açık fiyat verisinden.
Karabasan durum süzgeci ve (SMDK’da) emir defteri onayı uygulanmaz, o yüzden canlı botun gerçek işlemlerinden
farklı çıkabilir. Güzel görünen bir ayar bir öneridir: denenmesi yeni bir sanal bot ve kendi 30 günüdür.</p>
</form>"""
    return _kabuk(govde)
