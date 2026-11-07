"""/ayar sayfası: bot kriter ayar laboratuvarının ekranı (7 Kasım 2026, Ahmet'in isteği).

Üstte bot, coin ve dönem seçimi; ortada fiyat grafiği (giriş ve çıkışlar işaretli); altında her
kriterin sayıları. Sayılar değiştirilip "Çalıştır"a basılır: sayfa aynı adrese yeni değerlerle
yeniden açılır (düz form, GET; betik yok). Hiçbir şey kaydedilmez, canlı bota hiçbir şey gitmez.
Hesap ve açıklamalar için bkz. karabasan.ayar.
"""

from __future__ import annotations

import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from html import escape

import pandas as pd

from . import ayar as a
from . import botlar as _botlar

ONBELLEK = a.VeriOnbellegi()
HESAP_KAPISI = threading.Semaphore(2)   # aynı anda en çok iki hesap; panel öbür işlerini yapabilsin
VARSAYILAN_COIN = "ETH"
VARSAYILAN_GUN = 7
NEDENLER = {"zarar_durdur": "Stop", "iz_suren_stop": "İz süren stop", "kar_hedefi": "Kâr hedefi",
            "sure_asimi": "Süre doldu", "cikis_sinyali": "Çıkış sinyali"}


def guvenlik_basligi() -> str:
    """Bu sayfa betiksizdir; yalnız kendi adresine form gönderebilir."""
    return ("default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
            "base-uri 'none'; frame-ancestors 'none'")


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


def grafik(df: pd.DataFrame, pencere_bas: pd.Timestamp, yeni: list[dict], eski: list[dict],
           engel: list[datetime], gun: int, satis: bool) -> str:
    """Mum grafiği (satır içi SVG). Genişlik mum sayısıyla büyür; kutu yatay kaydırılır."""
    from .sayfa import _guzel_adimlar

    dk = a.parca_secimi(gun)
    pencere = df[pd.to_datetime(df["date"], utc=True) >= pencere_bas]
    if pencere.empty:
        return '<p class="bos">Bu dönemde mum yok.</p>'
    cubuk = (pencere.set_index(pd.to_datetime(pencere["date"], utc=True))
             .resample(f"{dk}min").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
             .dropna().reset_index())
    n = len(cubuk)
    bw = 6.0 if n < 150 else 4.0
    sol, sag, ust, alt, h = 54.0, 10.0, 14.0, 26.0, 300.0
    w = max(380.0, sol + sag + n * bw)
    fiyatlar = list(cubuk["high"]) + list(cubuk["low"]) + [float(i["giris_fiyati"]) for i in yeni + eski] \
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
    for f in _guzel_adimlar(y0, y1, 5):
        if y0 <= f <= y1:
            parca.append(f'<line class="g-izgara" x1="{sol:g}" x2="{w - sag:g}" y1="{y(f):.1f}" y2="{y(f):.1f}"/>'
                         f'<text class="g-eksen" x="4" y="{y(f):.1f}" dominant-baseline="middle">{_fiyat(f)}</text>')
    for _, m in cubuk.iterrows():
        orta = x(m["date"]) + bw / 2
        sinif = "arti" if m["close"] >= m["open"] else "eksi"
        ustk, altk = y(max(m["open"], m["close"])), y(min(m["open"], m["close"]))
        parca.append(
            f'<g class="ig-mum {sinif}"><line x1="{orta:.1f}" x2="{orta:.1f}" y1="{y(m["high"]):.1f}" y2="{y(m["low"]):.1f}"/>'
            f'<rect x="{orta - bw * 0.35:.1f}" y="{ustk:.1f}" width="{bw * 0.7:.1f}" height="{max(altk - ustk, 0.8):.1f}"/>'
            f'<title>{_zaman(m["date"])} · A {_fiyat(m["open"])} T {_fiyat(m["high"])} D {_fiyat(m["low"])} '
            f'K {_fiyat(m["close"])}</title></g>')
    # "Bu şart olmasaydı burada da girerdik" işaretleri (seçilen kriter).
    gorulen = set()
    for z in engel:
        k = int(pd.Timestamp(z).timestamp() // (dk * 60))
        if k in gorulen:
            continue
        gorulen.add(k)
        parca.append(f'<polygon class="ay-engel" points="{x(z) + bw / 2:.1f},{h - alt - 9:.1f} {x(z) + bw / 2 + 4:.1f},{h - alt - 3:.1f} '
                     f'{x(z) + bw / 2 - 4:.1f},{h - alt - 3:.1f}"><title>Yalnız seçtiğin şart yüzünden giriş olmadı · {_zaman(z)}</title></polygon>')
    # Eski (canlı ayar) girişleri: içi boş halka.
    for i in eski:
        parca.append(f'<circle class="ay-eski" cx="{x(i["giris_zamani"]):.1f}" cy="{y(float(i["giris_fiyati"])):.1f}" r="6">'
                     f'<title>Canlı ayarın girişi · {_fiyat(float(i["giris_fiyati"]))} · {_zaman(i["giris_zamani"])}</title></circle>')
    for i in yeni:
        gx, gy = x(i["giris_zamani"]), y(float(i["giris_fiyati"]))
        cx, cy = x(i["cikis_zamani"]), y(float(i["cikis_fiyati"]))
        sinif = "arti" if float(i["net_yuzde"]) > 0 else "eksi"
        parca.append(f'<line class="ay-yol {sinif}" x1="{gx:.1f}" y1="{gy:.1f}" x2="{cx:.1f}" y2="{cy:.1f}"/>')
        d = 8.0
        nok = (f"{gx - d:.1f},{gy - d * 1.8:.1f} {gx + d:.1f},{gy - d * 1.8:.1f} {gx:.1f},{gy - 3:.1f}" if satis
               else f"{gx - d:.1f},{gy + d * 1.8:.1f} {gx + d:.1f},{gy + d * 1.8:.1f} {gx:.1f},{gy + 3:.1f}")
        parca.append(f'<g class="ig-isaret giris"><polygon points="{nok}"/><circle cx="{gx:.1f}" cy="{gy:.1f}" r="3.2"/>'
                     f'<title>Giriş {_fiyat(float(i["giris_fiyati"]))} · {_zaman(i["giris_zamani"])}</title></g>')
        parca.append(f'<g class="ig-isaret cikis"><circle cx="{cx:.1f}" cy="{cy:.1f}" r="4"/>'
                     f'<title>Çıkış {_fiyat(float(i["cikis_fiyati"]))} · {_zaman(i["cikis_zamani"])} · '
                     f'{NEDENLER.get(i["neden"], i["neden"])} · {float(i["net_yuzde"]):+.2f}%</title></g>')
    for k in range(0, 6):
        t = t0 + (t1 - t0) * (0.03 + 0.94 * k / 5)
        z = datetime.fromtimestamp(t, tz=timezone.utc)
        parca.append(f'<text class="g-eksen" x="{x(z):.1f}" y="{h - 8:g}" text-anchor="middle">{escape(_zaman(z))}</text>')
    return (f'<div class="ay-kaydir"><svg class="g-svg ig-svg" style="width:{w:g}px;min-width:100%" '
            f'viewBox="0 0 {w:g} {h:g}" role="img" aria-label="Fiyat grafiği, giriş ve çıkışlar işaretli">'
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
    return (f'<div class="ay-ozet{" vurgu" if vurgu else ""}"><h3>{escape(ad)}</h3>'
            f'<p class="ay-buyuk">{o["islem"]} işlem</p>'
            f'<p>Kazanan: {kazanma} · Sinyal: {sinyal}</p>'
            f'<p class="{sinif}">Net: {net:+.2f}% <span class="alt">(ilk tutara göre, komisyon dahil)</span></p></div>')


def _girdi(idx: int, ad: str, deger, degisti: bool, tara_secili: bool) -> str:
    return (f'<div class="ay-satir{" degisti" if degisti else ""}"><label for="p{idx}">{escape(ad)}</label>'
            f'<span class="ay-girdi"><input id="p{idx}" name="p{idx}" type="text" inputmode="decimal" '
            f'autocomplete="off" value="{escape(_deger_yazisi(deger))}">'
            f'<button class="ay-kucuk{" secili" if tara_secili else ""}" type="submit" name="tara" value="{idx}" '
            f'title="Bu sayının çevresindeki değerleri dene">Tara</button></span></div>')


def _kriter_kartlari(kural, simdiki: dict, olc: list[dict] | None, istek: dict, degisenler: set) -> tuple[str, int]:
    kartlar, idx = [], 0
    for k in a.kriterler(kural):
        girdiler = []
        for yol, ad, _eski in k["sayilar"]:
            girdiler.append(_girdi(idx, ad, simdiki[yol], yol in degisenler, istek["tara"] == idx))
            idx += 1
        olcum = olc[k["sira"]] if olc else None
        if olcum:
            dogru = f'%{100 * olcum["dogru_oran"]:.0f} mumda doğru'
            engel = olcum["engel_sayisi"]
            engel_yazi = (f'Tek başına <b>{engel}</b> mumda girişi engelledi' if engel
                          else 'Tek başına hiçbir girişi engellemedi')
            dugme = (f'<button class="ay-kucuk{" secili" if istek["goster"] == k["sira"] else ""}" type="submit" '
                     f'name="goster" value="{k["sira"]}">Grafikte göster</button>' if engel else "")
            rozet = f'<p class="ay-olcum"><span>{dogru}</span><span>{engel_yazi}</span>{dugme}</p>'
        else:
            rozet = ""
        kartlar.append(f'<section class="ay-kart"><h3><span class="ay-no">{k["sira"] + 1}</span>{escape(k["yazi"])}</h3>'
                       f'{rozet}{"".join(girdiler)}'
                       f'{"" if girdiler else "<p class=alt>Bu şartın kendi sayısı yok; ilgili göstergenin periyodunu aşağıdaki Göstergeler bölümünden değiştirebilirsin.</p>"}</section>')
    return "".join(kartlar), idx


def _grup(baslik: str, aciklama: str, sayilar, bas: int, simdiki: dict, degisenler: set, istek: dict) -> str:
    satirlar = "".join(_girdi(bas + j, ad, simdiki[yol], yol in degisenler, istek["tara"] == bas + j)
                       for j, (yol, ad, _e) in enumerate(sayilar))
    if not satirlar:
        return ""
    return (f'<section class="ay-kart"><h3>{escape(baslik)}</h3><p class="alt">{escape(aciklama)}</p>{satirlar}</section>')


def _islem_tablosu(islemler: list[dict]) -> str:
    if not islemler:
        return '<p class="bos">Bu ayarla bu dönemde işlem açılmadı.</p>'
    satirlar = "".join(
        f'<tr><td>{_zaman(i["giris_zamani"])}</td><td>{_fiyat(float(i["giris_fiyati"]))}</td>'
        f'<td>{_fiyat(float(i["cikis_fiyati"]))}</td><td>{escape(NEDENLER.get(i["neden"], i["neden"]))}</td>'
        f'<td class="{"arti" if float(i["net_yuzde"]) > 0 else "eksi"}">{float(i["net_yuzde"]):+.2f}%</td></tr>'
        for i in islemler[-40:])
    return ('<table class="ay-tablo"><thead><tr><th>Giriş</th><th>Fiyat</th><th>Çıkış</th><th>Neden</th><th>Net</th></tr></thead>'
            f'<tbody>{satirlar}</tbody></table>')


def _tarama_tablosu(ad: str, satirlar: list[dict], simdiki) -> str:
    govde = "".join(
        f'<tr class="{"secili" if abs(s["deger"] - simdiki) < 1e-9 else ""}"><td>{_deger_yazisi(s["deger"])}</td>'
        + (f'<td colspan="3" class="alt">{escape(s["hata"])}</td></tr>' if s.get("hata") else
           f'<td>{s["ozet"]["islem"]}</td><td>{s["ozet"]["kazanan"]}</td>'
           f'<td class="{"arti" if s["ozet"]["net_toplam"] > 0 else "eksi" if s["ozet"]["net_toplam"] < 0 else ""}">'
           f'{s["ozet"]["net_toplam"]:+.2f}%</td></tr>')
        for s in satirlar)
    return (f'<section class="ay-kart"><h3>Tarama: {escape(ad)}</h3>'
            '<p class="alt">Yalnız bu sayı değişir, öbürleri ekrandaki gibi kalır. Çok değer denedikçe birinin '
            'geçmişte şans eseri iyi görünmesi kolaylaşır: tabloda en iyi görüneni seçmek ayar değil, ezberdir.</p>'
            '<table class="ay-tablo"><thead><tr><th>Değer</th><th>İşlem</th><th>Kazanan</th><th>Net</th></tr></thead>'
            f'<tbody>{govde}</tbody></table></section>')


AYAR_STIL = """
.ay-form{display:block}
.ay-ust{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}
.ay-ust label,.ay-satir label{display:block;font-size:.8125rem;color:var(--soluk);margin-bottom:4px}
.ay-ust select,.ay-ust input,.ay-girdi input{width:100%;min-height:44px;box-sizing:border-box;padding:0 12px;border-radius:12px;
border:1px solid var(--cizgi);background:var(--cam);color:var(--buz);font:inherit;font-size:1rem}
.ay-ust .tam{grid-column:1/-1}
.ay-calistir{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.ay-dugme{min-height:48px;padding:0 24px;border-radius:999px;border:1px solid var(--holo);background:var(--holo);color:#04141c;
font:700 1rem/1 inherit;cursor:pointer}
.ay-bag{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;border-radius:999px;border:1px solid var(--cizgi);
text-decoration:none;font-size:.875rem}
.ay-kaydir{overflow-x:auto;-webkit-overflow-scrolling:touch}
.ay-yol{stroke-width:1.5;stroke-dasharray:3 3;vector-effect:non-scaling-stroke}
.ay-yol.arti{stroke:var(--arti)}.ay-yol.eksi{stroke:var(--eksi)}
.ay-eski{fill:none;stroke:var(--soluk);stroke-width:1.5}
.ay-engel{fill:var(--altin)}
.ay-ozetler{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}
.ay-ozet{border:1px solid var(--cizgi);border-radius:12px;padding:10px 12px;background:var(--cam)}
.ay-ozet.vurgu{border-color:var(--holo)}
.ay-ozet h3{margin:0 0 4px;font-size:.8125rem;color:var(--soluk);font-weight:600}
.ay-ozet p{margin:2px 0;font-size:.875rem}.ay-buyuk{font-size:1.25rem !important;font-weight:700}
.ay-kart{border:1px solid var(--cizgi);border-radius:12px;padding:12px;margin:12px 0;background:var(--cam)}
.ay-kart h3{margin:0 0 8px;font-size:.9375rem;line-height:1.35}
.ay-no{display:inline-flex;width:22px;height:22px;border-radius:50%;background:var(--holo);color:#04141c;font-size:.75rem;
font-weight:700;align-items:center;justify-content:center;margin-right:8px}
.ay-olcum{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:.8125rem;color:var(--soluk);margin:0 0 8px}
.ay-satir{margin:8px 0}.ay-satir.degisti input{border-color:var(--altin)}
.ay-girdi{display:flex;gap:8px}
.ay-kucuk{min-height:44px;padding:0 12px;border-radius:12px;border:1px solid var(--cizgi);background:transparent;color:var(--holo);
font:inherit;font-size:.8125rem;cursor:pointer}
.ay-kucuk.secili{border-color:var(--altin);color:var(--altin)}
.ay-tablo{width:100%;border-collapse:collapse;font-size:.8125rem}
.ay-tablo th,.ay-tablo td{padding:6px 4px;text-align:left;border-bottom:1px solid var(--cizgi)}
.ay-tablo tr.secili td{background:rgba(95,212,255,.08)}
.ay-uyari{border:1px solid var(--altin);border-radius:12px;padding:10px 12px;margin:12px 0;font-size:.875rem}
.ay-hata{border:1px solid var(--eksi);border-radius:12px;padding:10px 12px;margin:12px 0;font-size:.875rem;color:var(--eksi)}
.ay-sabit{position:sticky;bottom:0;padding:10px 0 calc(10px + env(safe-area-inset-bottom));background:var(--gece);z-index:5}
"""


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
<main><h2 class="ekran-baslik">Kriter ayarı</h2>{govde}</main></div></body></html>"""


def ayar_sayfasi(istek: dict, onbellek: a.VeriOnbellegi | None = None, getir=a.binance_getir,
                 simdi: datetime | None = None) -> str:
    onbellek = onbellek or ONBELLEK
    simdi = (simdi or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    simdi -= timedelta(minutes=simdi.minute % 5)
    bot, coin, gun, once = istek["bot"], istek["coin"], istek["gun"], istek["once"]
    kural = a.kural_hazirla(bot)
    sayilar = a.tum_sayilar(kural)
    mesajlar: list[str] = []

    # Formdan gelen sayılar (aynı botun alanlarıysa).
    degisim: dict[str, float] = {}
    if istek["bot0"] == bot:
        for idx, (yol, ad, eski) in enumerate(sayilar):
            if idx in istek["p"]:
                try:
                    yeni = a.sayi_oku(istek["p"][idx])
                except a.AyarHatasi as hata:
                    mesajlar.append(f'{ad}: {hata}')
                    continue
                if abs(yeni - float(eski)) > 1e-9:
                    degisim[yol] = yeni
    kopya = kural
    if degisim:
        try:
            kopya = a.uygula(kural, degisim)
        except a.AyarHatasi as hata:
            mesajlar.append(str(hata) + " Canlı ayar gösteriliyor.")
            degisim = {}
    simdiki = {yol: (a._al(kopya, yol)) for yol, _ad, _e in sayilar}

    bitis = simdi - timedelta(days=once)
    pencere_bas = pd.Timestamp(bitis - timedelta(days=gun))
    govde_parcalari = []
    veri_hatasi = None
    try:
        with HESAP_KAPISI:
            df, ek = a.veri_topla(kopya, coin, "vadeli", bitis, gun, getir, onbellek)
            if df.empty or not len(df[pd.to_datetime(df["date"], utc=True) >= pencere_bas]):
                raise a.AyarHatasi("Bu coin için bu dönemde mum bulunamadı.")
            yeni = a.calistir(kopya, df, ek, pencere_bas, kriter_olc=True)
            eski = a.calistir(kural, df, ek, pencere_bas) if degisim else yeni
            tarama = None
            if istek["tara"] is not None and 0 <= istek["tara"] < len(sayilar):
                yol, ad, _e = sayilar[istek["tara"]]
                satirlar = []
                for v in a.tarama_degerleri(simdiki[yol]):
                    try:
                        k2 = a.uygula(kopya, {yol: v})
                        satirlar.append({"deger": v, "ozet": a.calistir(k2, df, ek, pencere_bas)["ozet"]})
                    except a.AyarHatasi as hata:
                        satirlar.append({"deger": v, "hata": str(hata)[:90]})
                tarama = (ad, satirlar, simdiki[yol])
    except a.AyarHatasi as hata:
        veri_hatasi = str(hata)
    except Exception as hata:  # noqa: BLE001 - ağ hatası sayfayı düşürmesin
        veri_hatasi = f"Fiyat verisi şu an alınamadı ({type(hata).__name__}). Biraz sonra yeniden dene."

    # Üst form
    botlar = "".join(f'<option value="{escape(b[0])}"{" selected" if b[0] == bot else ""}>{escape(b[2])}</option>'
                     for b in _botlar.BOTLAR)
    coinler = "".join(f'<option{" selected" if c == coin else ""}>{c}</option>' for c in a.COINLER)
    ust = f"""<form class="ay-form" method="get" action="/ayar">
<input type="hidden" name="bot0" value="{escape(bot)}">
<p class="not">Bir bot ve coin seç, geçmişe sar, her kriterin sayısını değiştir; giriş ve çıkışların nereye
düştüğünü gör. <b>Canlı botlar değişmez</b>: burada yaptığın hiçbir şey kaydedilmez.</p>
<div class="ay-ust">
<div class="tam"><label for="bot">Bot</label><select id="bot" name="bot">{botlar}</select></div>
<div><label for="coin">Coin</label><select id="coin" name="coin">{coinler}</select></div>
<div><label for="gun">Kaç gün bak (1–{a.EN_FAZLA_GUN})</label><input id="gun" name="gun" type="number" inputmode="numeric" min="1" max="{a.EN_FAZLA_GUN}" value="{gun}"></div>
<div class="tam"><label for="once">Geri sar: dönem kaç gün önce bitsin (0 = bugün)</label><input id="once" name="once" type="number" inputmode="numeric" min="0" max="{a.EN_FAZLA_GERI}" value="{once}"></div>
</div>
<div class="ay-calistir"><button class="ay-dugme" type="submit">Çalıştır</button>
<a class="ay-bag" href="/ayar?bot={escape(bot)}&amp;coin={coin}&amp;gun={gun}&amp;once={once}">Canlı ayara dön</a></div>"""
    govde_parcalari.append(ust)
    for m in mesajlar:
        govde_parcalari.append(f'<p class="ay-hata">{escape(m)}</p>')
    if veri_hatasi:
        govde_parcalari.append(f'<p class="ay-hata">{escape(veri_hatasi)}</p></form>')
        return _kabuk("".join(govde_parcalari))

    satis = kural["yon"] == "aciga_satis"
    engel_zamanlari = []
    if istek["goster"] is not None and istek["goster"] < len(yeni["kriterler"]):
        engel_zamanlari = yeni["kriterler"][istek["goster"]]["engel_zamanlari"]
    cizim = grafik(df, pencere_bas, yeni["islemler"], eski["islemler"] if degisim else [], engel_zamanlari, gun, satis)
    anahtar = ('<div class="ig-anahtar"><span><b style="background:var(--holo)"></b>Giriş</span>'
               '<span><b style="background:#f2ede2"></b>Çıkış</span>'
               + ('<span><b style="background:transparent;border:1.5px solid var(--soluk)"></b>Canlı ayarın girişi</span>'
                  if degisim else "")
               + ('<span><b style="background:var(--altin);border-radius:2px"></b>Seçili şart yüzünden olmayan giriş</span>'
                  if engel_zamanlari else "")
               + f'<span>{escape(coin)}/USDT · {_zaman(pencere_bas)} → {_zaman(pd.Timestamp(bitis))}</span></div>')
    govde_parcalari.append(f'<div class="kose kart">{cizim}{anahtar}</div>')

    # Sonuç kutuları ve uyarılar
    kutular = _ozet_kutusu("Senin ayarın" if degisim else "Canlı ayar", yeni["ozet"], yeni["sinyal_sayisi"], True)
    if degisim:
        kutular += _ozet_kutusu("Canlı ayar", eski["ozet"], eski["sinyal_sayisi"], False)
    govde_parcalari.append(f'<div class="ay-ozetler">{kutular}</div>')
    if yeni["ozet"]["islem"] < 30:
        govde_parcalari.append('<p class="ay-uyari">Az işlem var (30\'dan az): bu sonuç şans olabilir. '
                               'Sayılar hangi girişlerin değiştiğini görmek içindir; kâr kanıtı değildir.</p>')

    # Kriter kartları
    kartlar, bitis_idx = _kriter_kartlari(kopya, simdiki, yeni["kriterler"], istek, set(degisim))
    kriter_say = sum(len(k["sayilar"]) for k in a.kriterler(kural))
    gosterge = a.gosterge_sayilari(kural)
    cikis = a.cikis_sayilari(kural)
    govde_parcalari.append('<h3 class="ay-baslik">Giriş şartları <span class="alt">(hepsi aynı anda doğru olmalı)</span></h3>')
    govde_parcalari.append(kartlar)
    if istek["tara"] is not None and tarama:
        govde_parcalari.append(_tarama_tablosu(*tarama))
    govde_parcalari.append(_grup("Göstergeler", "Bir gösterge birkaç şartta kullanılır; periyodu değiştirmek hepsini etkiler.",
                                 gosterge, kriter_say, simdiki, set(degisim), istek))
    govde_parcalari.append(_grup("Giriş emri ve çıkış", "Girişin nasıl konduğu ve işlemin nasıl kapandığı.",
                                 cikis, kriter_say + len(gosterge), simdiki, set(degisim), istek))
    govde_parcalari.append('<div class="ay-sabit"><button class="ay-dugme" type="submit">Çalıştır</button></div></form>')
    govde_parcalari.append('<h3 class="ay-baslik">Bu ayarla açılan işlemler</h3>' + _islem_tablosu(yeni["islemler"]))
    govde_parcalari.append(
        '<p class="g-not">Hesap, bağımsız mum benzetimidir (hazır motor değil); Binance’in herkese açık fiyat verisinden. '
        'Karabasan durum süzgeci ve (SMDK’da) emir defteri onayı uygulanmaz, o yüzden canlı botun gerçek işlemlerinden '
        'farklı çıkabilir. Hiçbir ayar kaydedilmez ve canlı bota gitmez. Güzel görünen bir ayar bir öneridir: '
        'denenmesi yeni bir sanal bot ve kendi 30 günüdür.</p>')
    return _kabuk("".join(govde_parcalari))
