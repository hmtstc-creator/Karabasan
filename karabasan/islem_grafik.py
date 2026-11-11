"""Tek bir sanal işlemin fiyat grafiği (6 Kasım 2026, Ahmet'in isteği).

Sonuç sayfasının "İşlem grafiği" ekranında bir işleme dokununca açılan sayfa:
o coinin mum grafiği, girişin ve çıkışın yeri, giriş fiyatı ve stop seviyesi.

Mumlar Binance'in herkese açık, anahtarsız fiyat adresinden gelir (stop sonrası
izlemenin kullandığı adres). Yalnız okur; hiçbir emir ya da ayar yoktur.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from . import botlar as _botlar
from . import site_gezinti
from .kural import kural_yukle
from .sonuc import islemleri_oku
from .stop_sonrasi import SPOT_ADRESI, VADELI_ADRESI, sembol

# Binance mum aralıkları (dakika) ve grafikte en çok mum sayısı.
ARALIKLAR = [("1m", 1), ("5m", 5), ("15m", 15), ("1h", 60), ("4h", 240), ("1d", 1440)]
EN_FAZLA_MUM = 240
EN_AZ_MUM = 40
ONBELLEK_ACIK_SN = 60


def bot_bul(bot: str):
    """BOTLAR'daki satır (ad, sınıf, kural kodu, piyasa) ya da None. Yalnız bilinen bot adları kabul edilir."""
    for satir in _botlar.BOTLAR:
        if satir[0] == bot:
            return satir
    return None


def islem_bul(veri_klasoru: Path, bot: str, kimlik: int) -> tuple[dict | None, dict | None, str | None]:
    """(işlem, kural, hata). İşlem açık ya da kapanmış olabilir."""
    satir = bot_bul(bot)
    if satir is None:
        return None, None, "Böyle bir bot yok."
    kayit = islemleri_oku(veri_klasoru / "db" / f"{bot}.sqlite")
    if kayit["hata"]:
        return None, None, kayit["hata"]
    for durum in ("kapali", "acik"):
        for i in kayit[durum]:
            if i.get("kimlik") == kimlik:
                return {**i, "acik": durum == "acik", "bot": bot, "kod": satir[2], "piyasa": satir[3]}, \
                    kural_yukle(satir[2]), None
    return None, None, "Bu işlem bulunamadı; kayıttan silinmiş ya da kimliği yanlış olabilir."


def aralik_sec(baslangic: datetime, bitis: datetime) -> tuple[str, int, datetime, datetime]:
    """İşlemin süresine göre mum aralığı ve grafiğin başı / sonu (işlemin iki yanında pay)."""
    sure = max((bitis - baslangic).total_seconds() / 60.0, 1.0)
    for ad, dakika in ARALIKLAR:
        pay = max(sure * 0.35, dakika * 12)
        if (sure + 2 * pay) / dakika <= EN_FAZLA_MUM:
            break
    pay = max(sure * 0.35, dakika * 12)
    # Çok kısa işlemde de en az EN_AZ_MUM mum görünsün.
    eksik = max(0.0, EN_AZ_MUM * dakika - (sure + 2 * pay)) / 2
    return ad, dakika, baslangic - timedelta(minutes=pay + eksik), bitis + timedelta(minutes=pay + eksik)


def mum_getir(parite: str, piyasa: str, aralik: str, baslangic: datetime, bitis: datetime,
              zaman_asimi: int = 10) -> list[tuple]:
    """[(zaman, açılış, tepe, dip, kapanış), ...]"""
    taban = (os.environ.get("KARABASAN_BINANCE_VADELI", VADELI_ADRESI) if piyasa == "vadeli"
             else os.environ.get("KARABASAN_BINANCE_SPOT", SPOT_ADRESI))
    sorgu = urllib.parse.urlencode({
        "symbol": sembol(parite), "interval": aralik,
        "startTime": int(baslangic.timestamp() * 1000), "endTime": int(bitis.timestamp() * 1000), "limit": 1000,
    })
    istek = urllib.request.Request(f"{taban}?{sorgu}", headers={"User-Agent": "karabasan-bot"})
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
        satirlar = json.loads(yanit.read().decode("utf-8"))
    return [(datetime.fromtimestamp(int(s[0]) / 1000.0, tz=timezone.utc),
             float(s[1]), float(s[2]), float(s[3]), float(s[4])) for s in satirlar]


class MumOnbellegi:
    """Kapanmış işlemin mumları değişmez: bir kez indirilir. Açık işlemde 60 sn saklanır."""

    def __init__(self, en_fazla: int = 200):
        self._kilit = threading.Lock()
        self._veri: dict = {}
        self.en_fazla = en_fazla

    def al(self, anahtar, acik: bool, uret):
        with self._kilit:
            kayit = self._veri.get(anahtar)
            if kayit and (not acik or time.monotonic() - kayit[0] < ONBELLEK_ACIK_SN):
                return kayit[1]
        deger = uret()
        with self._kilit:
            if len(self._veri) >= self.en_fazla:
                self._veri.pop(next(iter(self._veri)))
            self._veri[anahtar] = (time.monotonic(), deger)
        return deger


def seviyeler(islem: dict, kural: dict) -> dict:
    """Giriş fiyatları ve çıkış seviyeleri.

    'giris' ilk girişin gerçek fiyatıdır (grafikte mumların üstünde durduğu yer); stop ona göre kurulur.
    Zararda ek giriş yapıldıysa 'ortalama' ayrı bir çizgidir; iz süren stop tetiği ve kâr hedefi ortalamadan hesaplanır.
    """
    ort = float(islem.get("giris_fiyati") or 0.0)
    ilk = float(islem.get("ilk_giris_fiyati") or ort or 0.0)
    if not ilk:
        return {}
    yon = 1.0 if islem["yon"] == "aciga_satis" else -1.0   # stop, açığa satışta yukarıda
    cikis = kural.get("cikis", {})
    sonuc = {"giris": ilk}
    if ort and abs(ort - ilk) > ilk * 1e-6:
        sonuc["ortalama"] = ort
    taban = ort or ilk
    if cikis.get("zarar_durdur_yuzde"):
        sonuc["stop"] = ilk * (1 + yon * cikis["zarar_durdur_yuzde"] / 100.0)
    iz = cikis.get("iz_suren_stop")
    if iz:
        sonuc["tetik"] = taban * (1 - yon * iz["tetik_yuzde"] / 100.0)
    if cikis.get("kar_hedefi_yuzde") and cikis["kar_hedefi_yuzde"] < 100:
        sonuc["hedef"] = taban * (1 - yon * cikis["kar_hedefi_yuzde"] / 100.0)
    return sonuc


# --------------------------------------------------------------------------
# Çizim
# --------------------------------------------------------------------------


def _fiyat(f: float) -> str:
    from .sayfa import fiyat_metni

    return fiyat_metni(f)


def mum_grafigi(mumlar: list, aralik_dk: int, islem: dict, sev: dict, simdi: datetime) -> str:
    """Mum grafiği (satır içi SVG): yeşil yükselen, kırmızı düşen mum; giriş / çıkış işaretleri."""
    from .sayfa import _guzel_adimlar, _tarih_saat, sayi

    g, h, sol, sag, ust, alt = 380.0, 260.0, 8.0, 56.0, 12.0, 24.0
    fiyatlar = [m[2] for m in mumlar] + [m[3] for m in mumlar] + [v for v in sev.values()] \
        + [float(e["fiyat"]) for e in islem.get("ek_girisler", [])]
    if islem.get("cikis_fiyati"):
        fiyatlar.append(float(islem["cikis_fiyati"]))
    en_alt, en_ust = min(fiyatlar), max(fiyatlar)
    pay = (en_ust - en_alt) * 0.06 or en_ust * 0.01
    y0, y1 = en_alt - pay, en_ust + pay
    t0 = mumlar[0][0].timestamp()
    t1 = mumlar[-1][0].timestamp() + aralik_dk * 60

    def x(zaman: datetime) -> float:
        return sol + (zaman.timestamp() - t0) / (t1 - t0) * (g - sol - sag)

    def y(f: float) -> float:
        return ust + (y1 - f) / (y1 - y0) * (h - ust - alt)

    genislik = max((g - sol - sag) / len(mumlar) * 0.7, 1.0)
    parca = []
    # Fiyat ızgarası (sağda)
    for f in _guzel_adimlar(y0, y1, 4):
        if y0 <= f <= y1:
            parca.append(f'<line class="g-izgara" x1="{sol:g}" x2="{g - sag:g}" y1="{y(f):.1f}" y2="{y(f):.1f}"/>'
                         f'<text class="g-eksen" x="{g - sag + 4:g}" y="{y(f):.1f}" dominant-baseline="middle">{_fiyat(f)}</text>')
    # İşlemin süresi boyunca hafif bant
    bitis = islem.get("cikis_zamani") or simdi
    parca.append(f'<rect class="ig-bant" x="{x(islem["giris_zamani"]):.1f}" y="{ust:g}" '
                 f'width="{max(x(bitis) - x(islem["giris_zamani"]), 1):.1f}" height="{h - ust - alt:g}"/>')
    # Mumlar
    for zaman, ac, tepe, dip, kap in mumlar:
        orta = x(zaman) + (g - sol - sag) / len(mumlar) / 2
        sinif = "arti" if kap >= ac else "eksi"
        govde_ust, govde_alt = y(max(ac, kap)), y(min(ac, kap))
        parca.append(
            f'<g class="ig-mum {sinif}"><line x1="{orta:.1f}" x2="{orta:.1f}" y1="{y(tepe):.1f}" y2="{y(dip):.1f}"/>'
            f'<rect x="{orta - genislik / 2:.1f}" y="{govde_ust:.1f}" width="{genislik:.1f}" '
            f'height="{max(govde_alt - govde_ust, 0.8):.1f}"/>'
            f'<title>{_tarih_saat(zaman, "Europe/Bucharest")} · A {_fiyat(ac)} T {_fiyat(tepe)} '
            f'D {_fiyat(dip)} K {_fiyat(kap)}</title></g>')
    # Seviyeler
    adlar = {"giris": "İlk giriş", "ortalama": "Ortalama giriş", "stop": "Stop", "tetik": "İz tetiği", "hedef": "Hedef"}
    for ad, f in sev.items():
        if y0 <= f <= y1:
            parca.append(f'<line class="ig-seviye {ad}" x1="{sol:g}" x2="{g - sag:g}" y1="{y(f):.1f}" y2="{y(f):.1f}">'
                         f'<title>{adlar[ad]} {_fiyat(f)}</title></line>')
    # Giriş ve çıkış işaretleri: açığa satışta giriş aşağı ok (satış), alımda yukarı ok.
    satis = islem["yon"] == "aciga_satis"

    def ok(zaman, fiyat, asagi: bool, sinif: str, yazi: str) -> str:
        xx, yy = x(zaman), y(fiyat)
        d = 9.0
        if asagi:   # tepeden aşağı bakan üçgen, noktanın üstünde
            nok = f"{xx - d:.1f},{yy - d * 1.9:.1f} {xx + d:.1f},{yy - d * 1.9:.1f} {xx:.1f},{yy - 3:.1f}"
        else:
            nok = f"{xx - d:.1f},{yy + d * 1.9:.1f} {xx + d:.1f},{yy + d * 1.9:.1f} {xx:.1f},{yy + 3:.1f}"
        return (f'<g class="ig-isaret {sinif}"><polygon points="{nok}"/>'
                f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="3.5"/><title>{escape(yazi)}</title></g>')

    if sev.get("giris"):
        parca.append(ok(islem["giris_zamani"], sev["giris"], satis, "giris",
                        f'İlk giriş {_fiyat(sev["giris"])} · {_tarih_saat(islem["giris_zamani"], "Europe/Bucharest")}'))
    for e in islem.get("ek_girisler", []):
        parca.append(ok(e["zaman"], float(e["fiyat"]), satis, "giris ek",
                        f'Zararda ek giriş {_fiyat(float(e["fiyat"]))} · {_tarih_saat(e["zaman"], "Europe/Bucharest")}'))
    if islem.get("cikis_zamani") and islem.get("cikis_fiyati"):
        parca.append(ok(islem["cikis_zamani"], float(islem["cikis_fiyati"]), not satis, "cikis",
                        f'Çıkış {_fiyat(float(islem["cikis_fiyati"]))} · '
                        f'{_tarih_saat(islem["cikis_zamani"], "Europe/Bucharest")}'))
    # Zaman ekseni
    for k in range(4):
        t = t0 + (t1 - t0) * (0.06 + 0.88 * k / 3)
        z = datetime.fromtimestamp(t, tz=timezone.utc)
        parca.append(f'<text class="g-eksen" x="{x(z):.1f}" y="{h - 7:g}" text-anchor="middle">'
                     f'{escape(_tarih_saat(z, "Europe/Bucharest"))}</text>')
    return (f'<svg class="g-svg ig-svg" viewBox="0 0 {g:g} {h:g}" role="img" '
            f'aria-label="{escape(str(islem["parite"]))} fiyat grafiği, giriş ve çıkış işaretli">{"".join(parca)}</svg>')


ISLEM_STIL = """
.ig-ust{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:14px 0 6px}
.ig-geri{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;border-radius:999px;border:1px solid var(--cizgi);
background:var(--yuzey);color:var(--buz);text-decoration:none;font-weight:600;font-size:.875rem}
.ig-mum line{stroke-width:1;vector-effect:non-scaling-stroke}
.ig-mum.arti line{stroke:var(--arti)}.ig-mum.arti rect{fill:var(--arti)}
.ig-mum.eksi line{stroke:var(--eksi)}.ig-mum.eksi rect{fill:var(--eksi)}
.ig-bant{fill:rgba(214,183,121,.07)}
.ig-seviye{stroke-width:1;stroke-dasharray:5 4;vector-effect:non-scaling-stroke}
.ig-seviye.giris{stroke:var(--holo)}.ig-seviye.ortalama{stroke:#ff9f43}.ig-seviye.stop{stroke:var(--eksi)}.ig-seviye.tetik{stroke:var(--arti)}
.ig-seviye.hedef{stroke:var(--arti)}
.ig-isaret polygon{stroke:#0d111c;stroke-width:1}.ig-isaret circle{stroke:#0d111c;stroke-width:1.5}
.ig-isaret.giris polygon,.ig-isaret.giris circle{fill:var(--holo)}
.ig-isaret.cikis polygon,.ig-isaret.cikis circle{fill:#f2ede2}
.ig-isaret.ek polygon,.ig-isaret.ek circle{fill:#ff9f43}
.ig-anahtar{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:10px;font-size:.8125rem;color:var(--buz)}
.ig-anahtar span{display:inline-flex;align-items:center;gap:6px}
.ig-anahtar i{display:inline-block;width:16px;height:0;border-top:2px dashed}
.ig-anahtar b{display:inline-block;width:10px;height:10px;border-radius:50%}
"""


def sayfa_uret(islem: dict | None, kural: dict | None, mumlar: list | None, aralik: tuple | None,
               hata: str | None, simdi: datetime | None = None) -> str:
    from .sayfa import STIL, _isaret_sinifi, _parite, _sure, _tarih_saat, _yon, isaretli, isaretli_yuzde

    simdi = simdi or datetime.now(timezone.utc)
    if islem is None:
        govde = f'<p class="bos">{escape(hata or "İşlem bulunamadı.")}</p>'
        baslik = "İşlem"
    else:
        sev = seviyeler(islem, kural or {})
        baslik = f'{_parite(islem["parite"])} · {escape(islem["kod"])}'
        if mumlar:
            grafik = mum_grafigi(mumlar, aralik[1], islem, sev, simdi)
            anahtar = ('<div class="ig-anahtar">'
                       '<span><b style="background:var(--holo)"></b>Giriş</span>'
                       '<span><b style="background:#f2ede2"></b>Çıkış</span>'
                       + ('<span><b style="background:#ff9f43"></b>Zararda ek giriş</span>' if islem.get("ek_girisler") else "")
                       + '<span><i style="border-color:var(--holo)"></i>İlk giriş fiyatı</span>'
                       + ('<span><i style="border-color:#ff9f43"></i>Ortalama giriş</span>' if "ortalama" in sev else "")
                       + ('<span><i style="border-color:var(--eksi)"></i>Stop</span>' if "stop" in sev else "")
                       + ('<span><i style="border-color:var(--arti)"></i>İz süren stop tetiği</span>' if "tetik" in sev else "")
                       + ('<span><i style="border-color:var(--arti)"></i>Kâr hedefi</span>' if "hedef" in sev else "")
                       + f'<span>Mum: {escape(aralik[0])}</span></div>')
        else:
            grafik = f'<p class="bos">Fiyat grafiği şu an alınamadı: {escape(hata or "veri yok")}. Biraz sonra yeniden dene.</p>'
            anahtar = ""
        if islem["acik"]:
            durum = '<span class="guven notr">Açık pozisyon</span>'
            sonuc_satiri = (f'<div><dt>Durum</dt><dd>Açık<span class="alt">'
                            f'{_sure((simdi - islem["giris_zamani"]).total_seconds() / 60)} önce açıldı</span></dd></div>')
        else:
            net = islem.get("net_tutar")
            durum = f'<span class="guven {_isaret_sinifi(net)}">{isaretli(net)} USDT</span>'
            sonuc_satiri = (f'<div><dt>Sonuç</dt><dd class="{_isaret_sinifi(net)}">{isaretli(net)} USDT'
                            f'<span class="alt">{isaretli_yuzde(islem.get("net_yuzde"))} · {escape(str(islem.get("neden") or ""))}</span></dd></div>'
                            f'<div><dt>Süre</dt><dd>{_sure(islem.get("sure_dakika") or 0)}</dd></div>')
        cikis_satiri = (f'<div><dt>Çıkış</dt><dd>{_fiyat(float(islem["cikis_fiyati"]))}<span class="alt">'
                        f'{_tarih_saat(islem["cikis_zamani"], "Europe/Bucharest")}</span></dd></div>'
                        if islem.get("cikis_fiyati") else "")
        ek_satiri = "".join(
            f'<div><dt>Zararda ek giriş</dt><dd>{_fiyat(float(e["fiyat"]))}<span class="alt">'
            f'{_tarih_saat(e["zaman"], "Europe/Bucharest")}</span></dd></div>' for e in islem.get("ek_girisler", []))
        if "ortalama" in sev:
            ek_satiri += f'<div><dt>Ortalama giriş</dt><dd>{_fiyat(sev["ortalama"])}</dd></div>'
        stop_satiri = (f'<div><dt>Stop</dt><dd class="eksi">{_fiyat(sev["stop"])}</dd></div>' if "stop" in sev else "")
        govde = f"""<div class="ig-ust"><span class="kod">{escape(islem["kod"])}</span>{durum}</div>
<p class="ekran-ozet">{_yon(islem["yon"]).capitalize()} · {escape(islem["bot"])} · {islem.get("tutar") or 0:.0f} USDT</p>
<div class="kose kart">{grafik}{anahtar}</div>
<dl class="olcu analiz-olcu">
<div><dt>{"İlk giriş" if ek_satiri else "Giriş"}</dt><dd>{_fiyat(sev.get("giris") or 0)}<span class="alt">{_tarih_saat(islem["giris_zamani"], "Europe/Bucharest")}</span></dd></div>
{ek_satiri}{cikis_satiri}{stop_satiri}{sonuc_satiri}
</dl>
<p class="g-not">Grafik Binance'in herkese açık fiyat verisinden çizilir. Sanal işlemdir; borsaya emir gitmez.
Bir muma dokununca açılış, tepe, dip ve kapanış görünür.</p>"""
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#070a12"><meta name="robots" content="noindex">
<title>Karabasan · İşlem</title><style>{STIL}{ISLEM_STIL}</style></head>
<body>{site_gezinti.serit("islem")}<div class="sayfa">
<header class="ust baslik-cubugu"><a class="marka" href="/">KARABASAN</a>
<a class="ig-geri" href="/#sonuc-islemgrafik" style="margin-left:auto">← İşlem listesi</a></header>
<main><h2 class="ekran-baslik">{baslik}</h2>
{govde}</main></div></body></html>"""


def islem_sayfasi(veri_klasoru: Path, bot: str, kimlik: int, onbellek: MumOnbellegi | None = None,
                  getir=mum_getir, simdi: datetime | None = None) -> str:
    simdi = simdi or datetime.now(timezone.utc)
    islem, kural, hata = islem_bul(veri_klasoru, bot, kimlik)
    if islem is None:
        return sayfa_uret(None, None, None, None, hata, simdi)
    bitis = islem.get("cikis_zamani") or simdi
    ad, dakika, bas, son = aralik_sec(islem["giris_zamani"], bitis)
    son = min(son, simdi)

    def uret():
        return getir(islem["parite"], islem["piyasa"], ad, bas, son)

    try:
        anahtar = (bot, kimlik, ad)
        mumlar = onbellek.al(anahtar, islem["acik"], uret) if onbellek else uret()
        hata = None if mumlar else "bu aralıkta mum yok"
    except Exception as e:  # noqa: BLE001 - ağ hatası sayfayı düşürmesin
        mumlar, hata = None, f"{type(e).__name__}"
    return sayfa_uret(islem, kural, mumlar, (ad, dakika), hata, simdi)
