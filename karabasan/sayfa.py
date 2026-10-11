"""Sonuç sayfası: karabasan.sonuc özetini tek bir Türkçe HTML sayfasına çevirir.

Beş ekran vardır: ana ekran (gösterge halkası), botlar, işlemler, dersler
(stop sonrası izleme), sınav.
Dış kaynak (yazı tipi, resim, dış betik) kullanmaz; sayfa sunucudan tek dosya
olarak gelir ve önce telefon için tasarlanmıştır.

Sayfanın iki hali vardır:

- Sunucudan açılan hali küçük bir satır içi betik taşır. Betik ekranlar
  arasında geçiş yaptırır ve veriyi dakikada bir, sayfayı yeniden yüklemeden
  tazeler. Sunucuya ulaşamazsa bunu ekranın üstünde söyler.
- Telegram'dan dosya olarak gönderilen hali (yenile_saniye=0) betik taşımaz;
  ekranlar alt alta tek sayfa olarak görünür. Betiği kapalı bir tarayıcıda
  da sayfa böyle görünür.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from html import escape

from .stop_sonrasi import KARAR_ADI, carpan_metni

OLCUT_ACIKLAMALARI = [
    "En az 100 sanal işlem yapmış olmak.",
    "Komisyon ve işlem başına ek kayma payı düşüldükten sonra toplam sonucun artıda olması.",
    "Kâr faktörünün (toplam kazanç bölü toplam kayıp) en az 1,3 olması.",
    "En büyük düşüşün sanal bakiyenin %5'ini aşmamış olması.",
    "Dört haftanın en az üçünün artıda kapanması.",
    "Kazanma oranının, zarar etmemek için gereken orandan en az 5 puan yüksek olması.",
    "Sonucun 12 aylık geçmiş testiyle aynı yönde olması.",
]

DURUM_ADLARI = {"YESIL": "Yeşil", "SARI": "Sarı", "KIRMIZI": "Kırmızı", "SIYAH": "Siyah"}

EKRANLAR = [
    ("ana", "Ana ekran"),
    ("botlar", "Botlar"),
    ("islemler", "İşlemler"),
    ("dersler", "Dersler"),
    ("sinav", "Sınav"),
]


# --------------------------------------------------------------------------
# Biçimlendirme (Türkçe: ondalık virgül, binlik nokta)
# --------------------------------------------------------------------------


def sayi(deger, basamak: int = 2) -> str:
    if deger is None:
        return "–"
    if deger in (float("inf"), float("-inf")):
        return "sonsuz"
    metin = f"{abs(deger):,.{basamak}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if deger < 0 else "") + metin


def isaretli(deger, basamak: int = 2) -> str:
    if deger is None:
        return "–"
    if abs(deger) < 0.5 * 10 ** (-basamak):
        return sayi(0.0, basamak)
    return ("+" if deger > 0 else "") + sayi(deger, basamak)


def yuzde(deger, basamak: int = 1) -> str:
    return "–" if deger is None else "%" + sayi(deger, basamak)


def isaretli_yuzde(deger, basamak: int = 2) -> str:
    """+%1,05 ya da −%1,14: işaret önde, yüzde işareti sayının başında."""
    if deger is None:
        return "–"
    if abs(deger) < 0.5 * 10 ** (-basamak):
        return "%" + sayi(0.0, basamak)
    return ("+" if deger > 0 else "−") + "%" + sayi(abs(deger), basamak)


def kisa_yuzde(deger) -> str:
    """Kural dosyasındaki oranı gereksiz sıfır olmadan yazar: %1,2 ya da %0,75."""
    if deger is None:
        return "–"
    metin = sayi(deger, 2).rstrip("0").rstrip(",")
    return "%" + metin


def yerel_zaman(zaman: datetime | None, saat_dilimi: str = "Europe/Bucharest"):
    """UTC zamanı yerel saate çevirir; saat dilimi verisi yoksa UTC döner."""
    if zaman is None:
        return None, "UTC"
    try:
        from zoneinfo import ZoneInfo

        return zaman.astimezone(ZoneInfo(saat_dilimi)), "Bükreş saati"
    except Exception:  # noqa: BLE001 - saat dilimi verisi yoksa UTC ile devam
        return zaman.astimezone(timezone.utc), "UTC"


def _tarih_saat(zaman, saat_dilimi) -> str:
    yerel, _ = yerel_zaman(zaman, saat_dilimi)
    return yerel.strftime("%d.%m %H:%M") if yerel else "–"


def _yon(yon: str) -> str:
    return "açığa satış" if yon == "aciga_satis" else "alım"


def _sure(dakika: float) -> str:
    """Süreyi okunur yazar: 20 dakika, 3 saat, 2 gün."""
    if dakika < 90:
        return f"{int(round(dakika))} dakika"
    if dakika < 48 * 60:
        return f"{int(round(dakika / 60))} saat"
    return f"{int(round(dakika / 1440))} gün"


def _parite(parite) -> str:
    """Vadeli paritelerdeki ':USDT' ekini atar (SOL/USDT:USDT yerine SOL/USDT)."""
    return escape(str(parite).split(":", 1)[0])


def _isaret_sinifi(deger) -> str:
    if deger is None or abs(deger) < 0.005:
        return "notr"
    return "arti" if deger > 0 else "eksi"


def selam(saat: int) -> str:
    """Günün saatine göre karşılama."""
    if 5 <= saat < 11:
        return "Günaydın efendim."
    if 11 <= saat < 18:
        return "İyi günler efendim."
    if 18 <= saat < 23:
        return "İyi akşamlar efendim."
    return "İyi geceler efendim."


# --------------------------------------------------------------------------
# Dönem cümleleri
# --------------------------------------------------------------------------


def _durum_cumlesi(ozet: dict) -> tuple[str, str]:
    """(başlık cümlesi, açıklama cümlesi)"""
    donem, gun = ozet["donem"], ozet["gun"]
    if donem == "kurulmadi":
        return (
            "Botlar henüz kurulmadı.",
            "Sunucu kurulumu bittiğinde bu sayfa kendiliğinden dolmaya başlar.",
        )
    if donem == "isinma":
        return (
            f"Isınma dönemi, {gun}. gün.",
            "Botlar sanal işlem yapıyor. Bu işlemler sınava sayılmıyor; "
            "30 günlük sınavın saati henüz başlatılmadı.",
        )
    if donem == "sinav":
        kalan = ozet["sinav_gun"] - gun
        return (
            f"Sınavın {gun}. günü.",
            f"{kalan} gün kaldı. Ölçütler ara durumdur; karar 30. günde verilir."
            if kalan > 0
            else "Son gün. Karar bu günün sonunda verilir.",
        )
    gecen = [b for b in ozet["botlar"] if b.get("karar") == "gecti"]
    if gecen:
        adlar = ", ".join(b["bot"] for b in gecen)
        return (
            "Sınav bitti.",
            f"{len(gecen)} bot yedi ölçütün hepsini geçti: {adlar}. "
            "Gerçek paraya geçip geçmemek senin kararın.",
        )
    return (
        "Sınav bitti.",
        "Hiçbir bot yedi ölçütün hepsini geçemedi. Gerçek paraya geçilmiyor; "
        "stratejiler gözden geçirilip sınav tekrarlanır.",
    )


def _bot_cumlesi(ozet: dict) -> str:
    t = ozet["toplam"]
    if ozet["donem"] == "kurulmadi":
        return ""
    if t["calisan_bot"] == t["bot_sayisi"]:
        return f"{t['bot_sayisi']} botun hepsi görevde."
    sessiz = t["bot_sayisi"] - t["calisan_bot"]
    return f"{t['bot_sayisi']} bottan {t['calisan_bot']} tanesi görevde, {sessiz} tanesinden ses yok."


# --------------------------------------------------------------------------
# Ana ekran: gösterge halkası
# --------------------------------------------------------------------------

MERKEZ = 200.0


def _nokta(yaricap: float, aci: float) -> tuple[float, float]:
    """Açı derece cinsinden, tepeden başlar ve saat yönünde artar."""
    radyan = math.radians(aci - 90.0)
    return MERKEZ + yaricap * math.cos(radyan), MERKEZ + yaricap * math.sin(radyan)


def _yay(yaricap: float, bas: float, son: float) -> str:
    x0, y0 = _nokta(yaricap, bas)
    x1, y1 = _nokta(yaricap, son)
    buyuk = 1 if (son - bas) > 180 else 0
    return f"M{x0:.1f} {y0:.1f}A{yaricap:g} {yaricap:g} 0 {buyuk} 1 {x1:.1f} {y1:.1f}"


def _bot_halka_sinifi(bot: dict) -> tuple[str, str]:
    """(çizim sınıfı, durum sözü)"""
    if bot["hata"]:
        return "yok", "kayıt yok"
    if not bot.get("calisiyor"):
        return "sessiz", "ses yok"
    if bot["islem_sayisi"] == 0:
        return "notr", "çalışıyor, henüz işlem yok"
    return _isaret_sinifi(bot["net_tutar"]), "çalışıyor"


def _halka(ozet: dict) -> str:
    """Ana ekranın ortasındaki gösterge: dışta botlar, içte sınavın 30 günü."""
    botlar = ozet["botlar"]
    toplam = ozet["toplam"]
    kurulu = ozet["donem"] != "kurulmadi"
    parcalar = []

    # Sabit ölçek: 5 derecede bir çentik, 30 derecede bir uzun çentik.
    centik = []
    for k in range(72):
        aci = k * 5.0
        ic = 184.0 if k % 6 == 0 else 188.0
        x0, y0 = _nokta(ic, aci)
        x1, y1 = _nokta(193.0, aci)
        centik.append(f"M{x0:.1f} {y0:.1f}L{x1:.1f} {y1:.1f}")
    parcalar.append(f'<g class="r-kat k1"><path class="r-olcek" d="{"".join(centik)}"/></g>')

    # Dış halka: her bot bir dilim.
    dilimler = []
    adet = max(1, len(botlar))
    genislik = 360.0 / adet
    for sira, bot in enumerate(botlar):
        bas, son = sira * genislik + 2.2, (sira + 1) * genislik - 2.2
        sinif, soz = _bot_halka_sinifi(bot)
        ex, ey = _nokta(141.0, (bas + son) / 2)
        baslik = f"{bot['ad']}: {isaretli(bot['net_tutar'])} USDT, {soz}"
        dilimler.append(
            f'<a href="#bot-{escape(bot["bot"])}" tabindex="-1"><title>{escape(baslik)}</title>'
            f'<path class="r-dokun" d="{_yay(152.0, bas, son)}"/>'
            f'<path class="r-bot {sinif}" d="{_yay(166.0, bas, son)}"/>'
            f'<text class="r-etiket {sinif}" x="{ex:.1f}" y="{ey:.1f}">{escape(bot["kod"])}</text></a>'
        )
    parcalar.append(f'<g class="r-kat k2">{"".join(dilimler)}</g>')

    # Dönen ince halkalar (yalnız süs).
    parcalar.append(
        '<g class="r-kat k3"><circle class="r-nokta r-don" cx="200" cy="200" r="124"/>'
        f'<path class="r-ince r-don ters" d="{_yay(96.0, 10, 80)}{_yay(96.0, 130, 200)}{_yay(96.0, 250, 320)}"/></g>'
    )

    # İç halka: sınavın günleri.
    gunler = []
    gun_sayisi = ozet["sinav_gun"]
    if ozet["donem"] == "sinav":
        dolu, bugun = ozet["gun"] - 1, ozet["gun"]
    elif ozet["donem"] == "bitti":
        dolu, bugun = gun_sayisi, 0
    else:
        dolu, bugun = 0, 0
    adim = 360.0 / gun_sayisi
    for g in range(1, gun_sayisi + 1):
        sinif = "r-gun"
        if g <= dolu:
            sinif += " gecti"
        elif g == bugun:
            sinif += " bugun"
        gunler.append(f'<path class="{sinif}" d="{_yay(110.0, (g - 1) * adim + 1.3, g * adim - 1.3)}"/>')
    parcalar.append(f'<g class="r-kat k4">{"".join(gunler)}</g>')

    # Çekirdek: toplam sanal sonuç.
    if kurulu:
        net = toplam["net_tutar"]
        metin = isaretli(net)
        sinif = _isaret_sinifi(net)
    else:
        metin, sinif = "–", "notr"
    # Sayı çekirdeğe sığmalı; geniş yazı tipli telefonlarda da taşmasın diye
    # uzadıkça küçülür.
    boyut = 46 if len(metin) <= 6 else 38 if len(metin) <= 8 else 30
    parcalar.append(
        '<g class="r-kat k5"><circle class="r-cekirdek" cx="200" cy="200" r="88"/>'
        '<text class="r-ad" x="200" y="166">Toplam sanal sonuç</text>'
        f'<text class="r-sayi {sinif}" x="200" y="{203 + boyut * 0.34:.0f}" font-size="{boyut}">{metin}</text>'
        '<text class="r-ad" x="200" y="243">USDT</text></g>'
    )

    if not kurulu:
        etiket = "Botlar henüz kurulmadı."
    else:
        etiket = (
            f"Toplam sanal sonuç {isaretli(toplam['net_tutar'])} USDT. "
            f"{toplam['bot_sayisi']} bottan {toplam['calisan_bot']} tanesi çalışıyor."
        )
    return (
        f'<div class="reaktor"><svg viewBox="0 0 400 400" role="img" aria-label="{escape(etiket)}">'
        f'{"".join(parcalar)}</svg>'
        '<p class="reaktor-not">Dış halkadaki her dilim bir bottur: yeşil artıda, kırmızı ekside. '
        "İç halka sınavın 30 günüdür.</p></div>"
    )


def _okumalar(ozet: dict) -> str:
    t = ozet["toplam"]
    if ozet["donem"] in ("sinav", "bitti"):
        gun_deger = f'{ozet["gun"]}<small> / {ozet["sinav_gun"]}</small>'
        gun_alt = "sınavın günü"
    elif ozet["donem"] == "isinma":
        gun_deger = f'{ozet["gun"]}<small>. gün</small>'
        gun_alt = "ısınma; sınav saati başlamadı"
    else:
        gun_deger, gun_alt = "–", "kurulum bekleniyor"
    son24 = t["son_24s_net_tutar"]
    hucreler = [
        (
            "Görevdeki bot",
            f'{t["calisan_bot"]}<small> / {t["bot_sayisi"]}</small>',
            "son 15 dakikada kayıt yazan",
            "" if t["calisan_bot"] == t["bot_sayisi"] else "uyari",
        ),
        ("Dönem", gun_deger, gun_alt, ""),
        (
            "Kapanan işlem",
            str(t["islem_sayisi"]),
            f'{t["acik_pozisyon"]} pozisyon şu an açık',
            "",
        ),
        (
            "Son 24 saat",
            f'{isaretli(son24)}<small> USDT</small>',
            f'{t["son_24s_islem"]} işlem kapandı',
            _isaret_sinifi(son24),
        ),
    ]
    return '<div class="okumalar kose">' + "".join(
        f'<div class="okuma"><span class="okuma-ad">{ad}</span>'
        f'<span class="okuma-deger {sinif}">{deger}</span>'
        f'<span class="okuma-alt">{alt}</span></div>'
        for ad, deger, alt, sinif in hucreler
    ) + "</div>"


def _seyir(ozet: dict) -> str:
    """Toplam sanal sonucun işlemler kapandıkça nasıl biriktiğini çizer."""
    egri = [float(v) for v in ozet.get("egri") or []]
    baslik = '<h2 class="kucuk-baslik">Toplam sanal sonucun seyri</h2>'
    if len(egri) < 3:
        return (
            f'<div class="seyir">{baslik}<p class="bos">İşlemler kapandıkça toplam sonucun '
            "nasıl değiştiği burada çizilir.</p></div>"
        )
    genislik, yukseklik, bosluk = 600.0, 120.0, 8.0
    alt, ust = min(egri), max(egri)
    aralik = (ust - alt) or 1.0

    def y(deger: float) -> float:
        return bosluk + (ust - deger) / aralik * (yukseklik - 2 * bosluk)

    adim = genislik / (len(egri) - 1)
    noktalar = " ".join(f"{k * adim:.1f},{y(v):.1f}" for k, v in enumerate(egri))
    son = egri[-1]
    sinif = _isaret_sinifi(son)
    return (
        f'<div class="seyir">{baslik}'
        f'<svg viewBox="0 0 {genislik:g} {yukseklik:g}" role="img" '
        f'aria-label="Toplam sanal sonuç sıfırdan başlayıp {isaretli(son)} USDT oldu.">'
        f'<line class="s-sifir" x1="0" x2="{genislik:g}" y1="{y(0.0):.1f}" y2="{y(0.0):.1f}"/>'
        f'<polyline class="s-cizgi {sinif}" points="{noktalar}"/>'
        f'<circle class="s-uc {sinif}" cx="{genislik:g}" cy="{y(son):.1f}" r="4.5"/></svg>'
        f'<p class="seyir-alt"><span>En düşük {isaretli(alt)}</span>'
        f'<span>En yüksek {isaretli(ust)}</span><span>Kesik çizgi sıfır</span></p></div>'
    )


def _siralama(ozet: dict) -> str:
    """Botlar net sonuca göre, en iyiden en kötüye."""
    botlar = sorted(ozet["botlar"], key=lambda b: b["net_tutar"], reverse=True)
    en_buyuk = max((abs(b["net_tutar"]) for b in botlar), default=0.0) or 1.0
    satirlar = []
    for b in botlar:
        net = b["net_tutar"]
        sinif = _isaret_sinifi(net)
        oran = min(50.0, abs(net) / en_buyuk * 50.0)
        _halka_sinifi, soz = _bot_halka_sinifi(b)
        piyasa = "spot" if b["piyasa"] == "spot" else "vadeli"
        cubuk = f'<i class="{sinif}" style="width:{oran:.1f}%"></i>' if sinif != "notr" else ""
        satirlar.append(
            f'<li><a class="sira" href="#bot-{escape(b["bot"])}">'
            f'<span class="kod">{escape(b["kod"])}</span>'
            f'<span class="sira-ad">{escape(b["ad"])}'
            f'<span class="alt">{piyasa}, {_yon(b["yon"])}, {b["islem_sayisi"]} işlem, {soz}</span></span>'
            f'<span class="sira-net {sinif}">{isaretli(net)}</span>'
            f'<span class="cubuk" aria-hidden="true">{cubuk}</span></a></li>'
        )
    return f'<ol class="siralama">{"".join(satirlar)}</ol>'


def _islem_satiri(i: dict, saat_dilimi: str) -> str:
    ayrinti = f'{_yon(i["yon"])}, {escape(str(i["neden"]))}, {_sure(i["sure_dakika"])}'
    if i.get("stop_sonrasi"):
        ayrinti += f'</span><span class="alt sonra">Sonrası: {escape(i["stop_sonrasi"])}'
    return (
        "<li>"
        f'<span class="islem-zaman">{_tarih_saat(i["cikis_zamani"], saat_dilimi)}</span>'
        f'<span class="kod">{escape(str(i.get("kod") or i["bot"]))}</span>'
        f'<span class="islem-parite">{_parite(i["parite"])}<span class="alt">{ayrinti}</span></span>'
        f'<span class="islem-net {_isaret_sinifi(i["net_yuzde"])}">{isaretli(i["net_tutar"])}'
        f'<span class="alt">{isaretli_yuzde(i["net_yuzde"])}</span></span>'
        "</li>"
    )


def _kapananlar(islemler: list, saat_dilimi: str) -> str:
    if not islemler:
        return '<p class="bos">Henüz kapanmış işlem yok. İlk işlem kapandığında burada görünür.</p>'
    return f'<ul class="islemler">{"".join(_islem_satiri(i, saat_dilimi) for i in islemler)}</ul>'


def _aciklar(ozet: dict, saat_dilimi: str) -> str:
    aciklar = ozet.get("acik_islemler") or []
    if not aciklar:
        return '<p class="bos">Şu an açık pozisyon yok.</p>'
    satirlar = []
    for i in aciklar:
        gecen = max(0.0, (ozet["uretildi"] - i["giris_zamani"]).total_seconds() / 60.0)
        satirlar.append(
            "<li>"
            f'<span class="islem-zaman">{_tarih_saat(i["giris_zamani"], saat_dilimi)}</span>'
            f'<span class="kod">{escape(str(i.get("kod") or i["bot"]))}</span>'
            f'<span class="islem-parite">{_parite(i["parite"])}'
            f'<span class="alt">{_yon(i["yon"])}, {sayi(i["tutar"], 0)} USDT</span></span>'
            f'<span class="islem-sure">{_sure(gecen)}<span class="alt">önce açıldı</span></span>'
            "</li>"
        )
    return f'<ul class="islemler">{"".join(satirlar)}</ul>'


def _son_ders_seridi(ozet: dict, saat_dilimi: str) -> str:
    dersler = ozet.get("dersler") or []
    if not dersler:
        return ""
    d = dersler[0]
    return (
        f'<p class="serit ders"><strong>Son ders, {_tarih_saat(d["zaman"], saat_dilimi)}:</strong> '
        f'{escape(str(d.get("kod", "")))} {escape(str(d.get("ad", "")))}. {escape(str(d.get("metin", "")))} '
        '<a href="#dersler">Bütün dersler</a></p>'
    )


def _ana_ekran(ozet: dict, saat_dilimi: str) -> str:
    baslik, aciklama = _durum_cumlesi(ozet)
    yerel, _ad = yerel_zaman(ozet["uretildi"], saat_dilimi)
    bot_cumlesi = _bot_cumlesi(ozet)
    return f"""<section id="ana" class="ekran">
<div class="pano">
<div class="selam">
<p class="selam-ust">{selam(yerel.hour)} {escape(bot_cumlesi)}</p>
<h1>{escape(baslik)}</h1>
<p class="aciklama">{escape(aciklama)}</p>
</div>
{_halka(ozet)}
{_okumalar(ozet)}
{_seyir(ozet)}
</div>
<p class="serit"><strong>Karabasan piyasa durumu</strong> henüz canlı ölçülmüyor. Ölçüm kurulunca
Yeşil, Sarı, Kırmızı ya da Siyah durumu burada görünecek. Botlar şimdilik her piyasa durumunda işlem açıyor.</p>
{_son_ders_seridi(ozet, saat_dilimi)}
<h2>Botların sıralaması</h2>
<p class="not">Net sanal sonuca göre, en iyiden en kötüye. Bir bota dokunursan ayrıntısı açılır.</p>
{_siralama(ozet)}
<h2>Son kapananlar</h2>
{_kapananlar(ozet["son_islemler"][:5], saat_dilimi)}
<p class="devam"><a href="#islemler">Bütün işlemleri gör</a></p>
</section>"""


# --------------------------------------------------------------------------
# Botlar ekranı
# --------------------------------------------------------------------------


def _olcut_isaretleri(bot: dict) -> str:
    if not bot["olcutler"]:
        return ""
    parcalar = []
    for o in bot["olcutler"]:
        durum = o["durum"]
        metin = {"saglandi": "sağlanıyor", "saglanmadi": "sağlanmıyor", "veri_yok": "veri yok"}[durum]
        simge = {"saglandi": "✓", "saglanmadi": "✗", "veri_yok": "·"}[durum]
        baslik = f"{o['no']}. {o['ad']}: {metin}"
        parcalar.append(
            f'<span class="isaret {durum}" title="{escape(baslik)}" aria-label="{escape(baslik)}">'
            f'<span class="isaret-no">{o["no"]}</span>{simge}</span>'
        )
    return f'<span class="isaretler">{"".join(parcalar)}</span>'


def _bot_durumu(bot: dict) -> str:
    if bot["hata"]:
        return f'<span class="durum sorun">kayıt yok</span><span class="alt">{escape(bot["hata"])}</span>'
    if bot.get("karar") == "gecti":
        return '<span class="durum gecti">Geçti</span>'
    if bot.get("karar") == "kaldi":
        return '<span class="durum kaldi">Kaldı</span>'
    if not bot.get("calisiyor"):
        yas = bot.get("gunluk_yasi_dakika")
        ne_zaman = "hiç kayıt yazmadı" if yas is None else f"son kayıt {_sure(yas)} önce"
        return f'<span class="durum sorun">ses yok</span><span class="alt">{ne_zaman}</span>'
    return f'<span class="durum">çalışıyor</span><span class="alt">{bot["acik_pozisyon"]} açık pozisyon</span>'


def _bot_karti(bot: dict) -> str:
    piyasa = "Spot piyasada" if bot["piyasa"] == "spot" else "Vadeli piyasada, 1 kat kaldıraçla"
    net = bot["net_tutar"]
    kazanma = yuzde(bot["kazanma_orani"])
    basabas = (
        f'<span class="alt">başabaş {yuzde(bot["basabas_orani"])}</span>'
        if bot["basabas_orani"] is not None
        else ""
    )
    olculer = [
        ("Kâr hedefi", kisa_yuzde(bot.get("hedef_yuzde")), ""),
        ("Stop", kisa_yuzde(bot.get("stop_yuzde")), ""),
        (
            "En uzun süre",
            _sure(bot["sure_asimi_dakika"]) if bot.get("sure_asimi_dakika") else "–",
            "",
        ),
    ]
    sonuclar = [
        ("İşlem", str(bot["islem_sayisi"]), ""),
        ("Kazanma", kazanma + basabas, ""),
        ("Net (USDT)", f'<span class="{_isaret_sinifi(net)}">{isaretli(net)}</span>', ""),
        ("En büyük düşüş", yuzde(bot["en_buyuk_dusus_yuzde"], 2), ""),
    ]

    def liste(ogeler, sinif):
        return f'<dl class="olcu {sinif}">' + "".join(
            f"<div><dt>{ad}</dt><dd>{deger}</dd></div>" for ad, deger, _ in ogeler
        ) + "</dl>"

    notlar = []
    if bot.get("nedenler"):
        sirali = sorted(bot["nedenler"].items(), key=lambda n: n[1], reverse=True)
        notlar.append("Çıkışlar: " + ", ".join(f"{adet} {escape(neden)}" for neden, adet in sirali) + ".")
    if bot.get("izinli_durumlar"):
        durumlar = ", ".join(DURUM_ADLARI.get(d, d) for d in bot["izinli_durumlar"])
        notlar.append(f"Tasarlandığı piyasa durumu: {escape(durumlar)}.")
    izleme = bot.get("stop_sonrasi") or {}
    if izleme.get("stop_sayisi"):
        notlar.append(
            f'Stop sonrası: izlenen {izleme["stop_sayisi"]} stopun {izleme["hedefi_goren"]} tanesinde fiyat '
            f'süre dolmadan hedefi gördü. {KARAR_ADI[izleme["karar"]["kod"]]}. <a href="#dersler">Ayrıntı</a>'
        )
    isaretler = _olcut_isaretleri(bot)
    return (
        f'<article class="kart kose" id="bot-{escape(bot["bot"])}">'
        f'<div class="kart-ust"><span class="kod">{escape(bot["kod"])}</span>'
        f'<h3>{escape(bot["ad"])}</h3></div>'
        f'<p class="alt">{piyasa} {_yon(bot["yon"])} yapar. Bot adı {escape(bot["bot"])}.</p>'
        f'<p class="kart-aciklama">{escape(bot.get("aciklama") or "")}</p>'
        f'{liste(olculer, "kural")}{liste(sonuclar, "sonuc")}'
        + "".join(f'<p class="alt">{n}</p>' for n in notlar)
        + (f'<div class="kart-olcut">{isaretler}</div>' if isaretler else "")
        + f'<div class="kart-durum">{_bot_durumu(bot)}</div></article>'
    )


def _botlar_ekrani(ozet: dict) -> str:
    kartlar = "".join(_bot_karti(b) for b in ozet["botlar"])
    return f"""<section id="botlar" class="ekran">
<h2 class="ekran-baslik">Botlar</h2>
<p class="not">Her botun {sayi(ozet["sanal_bakiye"], 0)} USDT sanal bakiyesi var ve işlem başına
{sayi(ozet["islem_tutari"], 0)} USDT kullanıyor. Net sonuç, komisyon düşülmüş sanal kâr ya da zarardır.
Başabaş, zarar etmemek için gereken kazanma oranıdır; kazanma oranı bunun üstünde olmalıdır.</p>
<p class="not">Piyasa durumu süzgeci (Karabasan) henüz canlı bağlı değil; botlar şimdilik her
piyasa durumunda işlem açıyor.</p>
<div class="kartlar">{kartlar}</div>
</section>"""


# --------------------------------------------------------------------------
# İşlemler ekranı
# --------------------------------------------------------------------------


def _islemler_ekrani(ozet: dict, saat_dilimi: str) -> str:
    kapanan = ozet["son_islemler"]
    return f"""<section id="islemler" class="ekran">
<h2 class="ekran-baslik">İşlemler</h2>
<h3>Açık pozisyonlar</h3>
{_aciklar(ozet, saat_dilimi)}
<h3>Son kapanan {len(kapanan) if kapanan else ""} işlem</h3>
{_kapananlar(kapanan, saat_dilimi)}
<p class="not">Sağdaki sayı işlemin komisyon düşülmüş sanal sonucudur (USDT); altında yüzdesi yazar.
Hiçbir emir borsaya gitmez.</p>
</section>"""


# --------------------------------------------------------------------------
# Dersler ekranı: stop sonrası izleme
# --------------------------------------------------------------------------


def _ders_karti(bot: dict) -> str:
    izleme = bot["stop_sonrasi"]
    adet = izleme["stop_sayisi"]
    karar = izleme["karar"]
    bekleyen = izleme.get("izlenmeyi_bekleyen") or 0
    cumle = (
        f'{adet} stop izlendi; {izleme["hedefi_goren"]} tanesinde fiyat, işlemin süresi dolmadan '
        "kâr hedefini gördü."
    )
    if bekleyen:
        cumle += f" {bekleyen} stop daha izlenmeyi bekliyor."
    if izleme.get("izlenemeyen"):
        cumle += f' {izleme["izlenemeyen"]} stop için fiyat verisi alınamadı; hesaba girmiyor.'
    # Karar için yeterli stop yokken farklar renklendirilmez: az veriyle büyük görünen
    # bir artı, sonuç gibi okunmasın.
    yeterli = karar["kod"] != "yetersiz"
    secenekler = []
    for s in izleme["carpanlar"]:
        etiket = f'Stop {carpan_metni(s["carpan"])} kat geniş olsaydı'
        if s.get("stop_yuzde") is not None:
            etiket += f' ({kisa_yuzde(s["stop_yuzde"])})'
        secenekler.append(
            f'<li><span>{etiket}<span class="alt">{s["hedef"]} tanesi hedefe ulaşır, {s["stop"]} tanesi '
            f'yine stop olur, {s["sure"]} tanesinde süre dolardı</span></span>'
            f'<span class="secenek-net {_isaret_sinifi(s["fark_tutar"]) if yeterli else "erken"}">'
            f'{isaretli(s["fark_tutar"])}'
            '<span class="alt">USDT fark</span></span></li>'
        )
    return (
        f'<article class="ders-kart kose"><div class="kart-ust"><span class="kod">{escape(bot["kod"])}</span>'
        f'<h4>{escape(bot["ad"])}</h4><span class="karar {karar["kod"]}">{KARAR_ADI[karar["kod"]]}</span></div>'
        f'<p class="ders-cumle">{cumle}</p><ul class="secenekler">{"".join(secenekler)}</ul>'
        f'<p class="alt">{escape(karar["metin"])}</p></article>'
    )


def _dersler_ekrani(ozet: dict, saat_dilimi: str) -> str:
    izlenen = [b for b in ozet["botlar"] if b.get("stop_sonrasi", {}).get("stop_sayisi")]
    izleme = ozet.get("stop_izleme") or {}
    en_az = izleme.get("en_az_stop", 30)
    if izlenen:
        bos_botlar = [b["kod"] for b in ozet["botlar"] if b not in izlenen]
        kartlar = f'<div class="ders-kartlar">{"".join(_ders_karti(b) for b in izlenen)}</div>'
        if bos_botlar:
            kartlar += f'<p class="not">Henüz izlenmiş stopu olmayan botlar: {escape(", ".join(bos_botlar))}.</p>'
    else:
        bekleyen = sum((b.get("stop_sonrasi") or {}).get("izlenmeyi_bekleyen") or 0 for b in ozet["botlar"])
        ek = f" Şu an {bekleyen} stop sırada." if bekleyen else ""
        kartlar = (
            '<p class="bos">Henüz izlenmiş stop yok. Bir işlem stop olduktan sonra, o işlemin süresi '
            f"dolunca (stratejiye göre 1 ile 6 saat) sonucu burada görünür.{ek}</p>"
        )

    dersler = ozet.get("dersler") or []
    if dersler:
        ders_listesi = '<ul class="ders-listesi">' + "".join(
            f'<li><div class="ders-ust"><span class="islem-zaman">{_tarih_saat(d["zaman"], saat_dilimi)}</span>'
            f'<span class="kod">{escape(str(d.get("kod", "")))}</span><strong>{escape(str(d.get("ad", "")))}</strong></div>'
            f'{escape(str(d.get("metin", "")))}</li>'
            for d in dersler
        ) + "</ul>"
    else:
        ders_listesi = (
            f'<p class="bos">Henüz ders yok. Bir botun {en_az} stopu izlenince ilk karar buraya yazılır; '
            "karar sonradan değişirse yenisi eklenir.</p>"
        )
    son_tur = izleme.get("son_tur")
    tur_notu = (
        f"Son izleme turu: {_tarih_saat(son_tur, saat_dilimi)}."
        if son_tur
        else "İzleme henüz ilk turunu tamamlamadı."
    )
    return f"""<section id="dersler" class="ekran">
<h2 class="ekran-baslik">Dersler</h2>
<p class="sinav-durum">Stop olan her işlem, kendi süresi dolana kadar izleniyor. Soru şu: stop daha geniş
olsaydı sonuç daha mı iyi olurdu, yoksa zarar mı büyürdü?</p>
<h3>Stop dar mı?</h3>
{kartlar}
<h3>Ders kaydı</h3>
{ders_listesi}
<h3>Bunu okurken</h3>
<ul class="okuma-notlari">
<li>Fark, yalnız stop olan işlemlerin toplamıdır. Geniş stop bazı işlemleri kurtarır, kurtaramadıklarının
zararını büyütür; önemli olan ikisinin toplamı.</li>
<li>Stop geniş olsaydı işlem daha uzun açık kalır, o sırada gelen başka sinyaller atlanırdı. Bu hesaba girmez.</li>
<li>Bu bir geriye bakıştır. Geçmişte iyi görünen stop gelecekte de iyi olacak demek değildir. Bu yüzden
“stop dar” demek için en az {en_az} stop, şansla açıklanamayacak kadar büyük bir fark ve bu farkın dönemin
iki yarısına da yayılması aranır. {en_az} stoptan önce farklar soluk yazılır.</li>
<li>Karar hiçbir ayarı değiştirmez. “Stop dar” çıkarsa geniş stoplu hal ayrı bir sanal botla denenir.</li>
</ul>
<p class="not">{tur_notu}</p>
</section>"""


# --------------------------------------------------------------------------
# Sınav ekranı
# --------------------------------------------------------------------------


def _cetvel(ozet: dict) -> str:
    """30 günlük sınav cetveli: geçen günler dolu, bugünkü işaretli."""
    toplam = ozet["sinav_gun"]
    if ozet["donem"] in ("sinav", "bitti"):
        dolu = ozet["gun"] if ozet["donem"] == "sinav" else toplam
        etiket = f"30 günlük sınavın {dolu}. günü"
    else:
        dolu = 0
        etiket = "30 günlük sınav henüz başlamadı"
    parcalar = []
    for g in range(1, toplam + 1):
        sinif = "gun"
        if g < dolu or (ozet["donem"] == "bitti" and g <= dolu):
            sinif += " gecti"
        elif g == dolu:
            sinif += " bugun"
        if g % 7 == 0:
            sinif += " hafta-sonu"
        parcalar.append(f'<span class="{sinif}"></span>')
    return (
        f'<div class="cetvel" role="img" aria-label="{escape(etiket)}">{"".join(parcalar)}</div>'
        '<div class="cetvel-alt"><span>1. gün</span><span>7</span><span>14</span>'
        "<span>21</span><span>30. gün</span></div>"
    )


def _olcut_cizelgesi(ozet: dict) -> str:
    if ozet["donem"] not in ("sinav", "bitti"):
        return '<p class="bos">Sınav başlayınca her botun yedi ölçütteki durumu burada görünür.</p>'
    satirlar = []
    for b in ozet["botlar"]:
        hucreler = []
        for o in b["olcutler"]:
            durum = o["durum"]
            metin = {"saglandi": "sağlanıyor", "saglanmadi": "sağlanmıyor", "veri_yok": "veri yok"}[durum]
            simge = {"saglandi": "✓", "saglanmadi": "✗", "veri_yok": "·"}[durum]
            hucreler.append(
                f'<td><span class="im {durum}" aria-label="{o["no"]}. ölçüt {metin}">{simge}</span></td>'
            )
        karar = {"gecti": "Geçti", "kaldi": "Kaldı"}.get(b.get("karar") or "", "")
        satirlar.append(
            f'<tr><th scope="row"><a href="#bot-{escape(b["bot"])}"><span class="kod">{escape(b["kod"])}</span>'
            f'<span class="cizelge-ad">{escape(b["ad"])}</span></a></th>{"".join(hucreler)}'
            f'<td class="cizelge-karar {b.get("karar") or ""}">{karar}</td></tr>'
        )
    basliklar = "".join(f'<th scope="col">{n}</th>' for n in range(1, 8))
    return (
        '<table class="cizelge"><thead><tr><th scope="col">Bot</th>'
        f'{basliklar}<th scope="col"></th></tr></thead><tbody>{"".join(satirlar)}</tbody></table>'
    )


def _sinav_ekrani(ozet: dict, yenileme_notu: str) -> str:
    baslik, aciklama = _durum_cumlesi(ozet)
    olcutler = "".join(f"<li>{escape(a)}</li>" for a in OLCUT_ACIKLAMALARI)
    komisyon = ozet["komisyon_yuzde"]
    gecmis_notu = (
        ""
        if ozet["gecmis_test_var"]
        else " 12 aylık geçmiş testi henüz çalıştırılmadığı için yedinci ölçüt “veri yok” görünür."
    )
    return f"""<section id="sinav" class="ekran">
<h2 class="ekran-baslik">Sınav</h2>
<p class="sinav-durum"><strong>{escape(baslik)}</strong> {escape(aciklama)}</p>
{_cetvel(ozet)}
<h3>Yedi ölçüt</h3>
<ol class="olcut-listesi">{olcutler}</ol>
<p class="not">Bir bot ancak yedisini birden sağlarsa gerçek para adayı olur.{escape(gecmis_notu)}</p>
<h3>Botların ölçütlerdeki durumu</h3>
{_olcut_cizelgesi(ozet)}
<div class="anahtar">
<span><span class="im saglandi">✓</span> sağlanıyor</span>
<span><span class="im saglanmadi">✗</span> sağlanmıyor</span>
<span><span class="im veri_yok">·</span> veri yok</span>
</div>
<h3>Bu sayfa hakkında</h3>
<p class="not">Buradaki bütün işlemler sanaldır; hiçbir emir borsaya gitmez. Komisyon olarak
spot işlemlerde taraf başına {yuzde(komisyon["spot"], 3)}, vadeli işlemlerde
{yuzde(komisyon["vadeli"], 3)} düşülür. Ölçütler hesaplanırken her işlemden ayrıca
{yuzde(ozet["ek_kayma_yuzde"], 2)} kayma payı düşülür, çünkü sanal işlem gerçeğinden biraz
iyimser dolar.{yenileme_notu}</p>
</section>"""


# --------------------------------------------------------------------------
# Görünüm
# --------------------------------------------------------------------------

_KOSE = ",".join(
    f"linear-gradient(var(--holo),var(--holo)) {x} {y}/{boyut} no-repeat"
    for x, y in (("0", "0"), ("100%", "0"), ("0", "100%"), ("100%", "100%"))
    for boyut in ("13px 1px", "1px 13px")
)

STIL = """
:root{--gece:#04070d;--holo:#5fd4ff;--cizgi:rgba(95,212,255,.18);--cam:rgba(95,212,255,.045);
--buz:#e2f6ff;--soluk:#86a2ba;--altin:#ffc24a;--arti:#5af0b2;--eksi:#ff7466;--gecen:0s;
--rakam:"DIN Alternate","Bahnschrift","Avenir Next Condensed","Roboto Condensed","Arial Narrow",system-ui,sans-serif;
--govde:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
*{box-sizing:border-box}
html{color-scheme:dark;scroll-padding-top:20px;
background:radial-gradient(95% 620px at 50% -60px,#0d2b46 0,rgba(4,7,13,0) 72%) no-repeat var(--gece)}
body{margin:0;min-height:100vh;color:var(--buz);font:16px/1.5 var(--govde);font-variant-numeric:tabular-nums;
-webkit-text-size-adjust:100%}
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.5;
background:repeating-linear-gradient(0deg,var(--cizgi) 0 1px,transparent 1px 46px),
repeating-linear-gradient(90deg,var(--cizgi) 0 1px,transparent 1px 46px);
-webkit-mask-image:radial-gradient(ellipse 80% 60% at 50% 22%,#000 0,transparent 78%);
mask-image:radial-gradient(ellipse 80% 60% at 50% 22%,#000 0,transparent 78%)}
a{color:var(--holo)}
a:focus-visible{outline:2px solid var(--altin);outline-offset:3px}
.sayfa{max-width:1120px;margin:0 auto;padding:16px 16px 104px}
.ust{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.marka{font:700 1.125rem/1 var(--rakam);letter-spacing:.14em;color:var(--holo);
text-shadow:0 0 14px rgba(95,212,255,.55)}
.guncelleme{color:var(--soluk);font-size:.8125rem}
.kopuk-uyari{display:none;margin:0;padding:10px 16px;background:#3a2a05;color:var(--altin);
font-size:.875rem;text-align:center;position:sticky;top:0;z-index:5}
.kopuk .kopuk-uyari{display:block}

.ekran{padding-top:8px}
.ekran + .ekran{margin-top:56px;border-top:1px solid var(--cizgi);padding-top:28px}
.sekmeli .ekran{display:none;margin-top:0;border-top:0;padding-top:8px}
EKRAN_GOSTER{display:block}

h1{font:700 clamp(1.75rem,7vw,2.75rem)/1.08 var(--rakam);margin:6px 0 10px;letter-spacing:.01em}
h2{font:700 1.25rem/1.2 var(--rakam);letter-spacing:.03em;margin:40px 0 8px}
h2.ekran-baslik{font-size:clamp(1.75rem,7vw,2.5rem);margin:14px 0 14px}
h2.kucuk-baslik{font:600 .8125rem/1.3 var(--govde);letter-spacing:0;color:var(--soluk);margin:0 0 8px}
h3{font:700 1.0625rem/1.25 var(--rakam);letter-spacing:.03em;margin:32px 0 10px}
.alt{display:block;color:var(--soluk);font-size:.8125rem;line-height:1.4;font-weight:400}
.not{color:var(--soluk);font-size:.875rem;max-width:68ch;margin:0 0 10px}
.bos{color:var(--soluk);border:1px dashed var(--cizgi);padding:14px 16px;margin:0;max-width:62ch;font-size:.9375rem}
.arti{color:var(--arti)}.eksi{color:var(--eksi)}.notr{color:var(--buz)}
.uyari{color:var(--altin)}
.kose{background:KOSE,var(--cam);border:1px solid var(--cizgi)}
.kod{display:inline-flex;align-items:center;justify-content:center;min-width:2.6em;padding:2px 6px;
font:700 .8125rem/1.3 var(--rakam);letter-spacing:.04em;color:var(--holo);border:1px solid var(--cizgi);
background:rgba(95,212,255,.08)}

.pano{display:grid;gap:18px}
.selam-ust{margin:14px 0 0;color:var(--holo);font-size:.9375rem}
.aciklama{margin:0;max-width:56ch;color:var(--soluk)}
.reaktor{width:100%;max-width:500px;margin:0 auto}
.reaktor svg{display:block;width:100%;height:auto;overflow:visible}
.reaktor-not{margin:6px auto 0;max-width:40ch;text-align:center;color:var(--soluk);font-size:.8125rem}
.r-kat{transform-origin:200px 200px;animation:acilis .9s cubic-bezier(.2,.8,.2,1) both}
.r-kat.k2{animation-delay:.08s}.r-kat.k3{animation-delay:.16s}.r-kat.k4{animation-delay:.24s}.r-kat.k5{animation-delay:.34s}
.acildi .r-kat{animation:none}
.r-olcek{fill:none;stroke:var(--holo);stroke-width:1;opacity:.5}
.r-don{transform-origin:200px 200px;animation:don 110s linear infinite;animation-delay:var(--gecen)}
.r-don.ters{animation-duration:70s;animation-direction:reverse}
.r-nokta{fill:none;stroke:var(--holo);stroke-width:2;stroke-dasharray:1.5 9;opacity:.6}
.r-ince{fill:none;stroke:var(--holo);stroke-width:1.5;opacity:.75}
.r-dokun{fill:none;stroke:transparent;stroke-width:48;pointer-events:stroke}
.r-bot{fill:none;stroke:currentColor;stroke-width:15;filter:drop-shadow(0 0 5px currentColor)}
.r-bot.notr{color:var(--holo);opacity:.4;filter:none}
.r-bot.sessiz{color:var(--altin);stroke-dasharray:3 5}
.r-bot.yok{color:var(--soluk);opacity:.35;stroke-dasharray:2 6;filter:none}
.r-etiket{font:700 14px var(--rakam);text-anchor:middle;dominant-baseline:central;fill:currentColor;letter-spacing:.03em}
.r-etiket.notr{color:var(--soluk)}.r-etiket.sessiz{color:var(--altin)}.r-etiket.yok{color:var(--soluk)}
.r-gun{fill:none;stroke:var(--holo);stroke-width:5;opacity:.2}
.r-gun.gecti{opacity:.95}
.r-gun.bugun{stroke:var(--altin);opacity:1;stroke-width:8}
.r-cekirdek{fill:rgba(95,212,255,.05);stroke:var(--holo);stroke-opacity:.55;stroke-width:1;
filter:drop-shadow(0 0 18px rgba(95,212,255,.35))}
.r-sayi{font-family:var(--rakam);font-weight:700;text-anchor:middle;fill:currentColor}
.r-ad{font:500 13px var(--govde);text-anchor:middle;fill:var(--soluk)}
@keyframes don{to{transform:rotate(360deg)}}
@keyframes acilis{from{opacity:0;transform:scale(.8) rotate(-28deg)}}

.okumalar{display:grid;grid-template-columns:1fr 1fr}
.okuma{padding:14px 14px 13px;border-top:1px solid var(--cizgi);border-left:1px solid var(--cizgi);min-width:0}
.okuma:nth-child(odd){border-left:0}
.okuma:nth-child(-n+2){border-top:0}
.okuma-ad{display:block;color:var(--soluk);font-size:.8125rem}
.okuma-deger{display:block;font:700 2rem/1.15 var(--rakam);letter-spacing:.01em;white-space:nowrap}
.okuma-deger small{font-size:.5em;font-weight:700;color:var(--soluk)}
.okuma-alt{display:block;color:var(--soluk);font-size:.75rem;line-height:1.35}
.seyir svg{display:block;width:100%;height:auto;overflow:visible}
.s-sifir{stroke:var(--soluk);stroke-width:1;stroke-dasharray:4 5;opacity:.7;vector-effect:non-scaling-stroke}
.s-cizgi{fill:none;stroke:currentColor;stroke-width:2;stroke-linejoin:round;vector-effect:non-scaling-stroke;
filter:drop-shadow(0 0 4px currentColor)}
.s-cizgi.notr,.s-uc.notr{color:var(--holo)}
.s-uc{fill:currentColor}
.seyir-alt{display:flex;flex-wrap:wrap;gap:4px 18px;margin:8px 0 0;color:var(--soluk);font-size:.8125rem}
.serit{margin:26px 0 0;padding:12px 14px;border-left:2px solid var(--altin);background:rgba(255,194,74,.06);
color:var(--soluk);font-size:.875rem;max-width:72ch}
.serit strong{color:var(--altin);font-weight:600}

.siralama{list-style:none;margin:12px 0 0;padding:0;border-top:1px solid var(--cizgi)}
.sira{display:grid;grid-template-columns:3.1em minmax(0,1fr) auto;gap:6px 12px;align-items:center;
padding:12px 2px;border-bottom:1px solid var(--cizgi);color:inherit;text-decoration:none}
.sira:hover{background:var(--cam)}
.sira .kod{min-width:0;justify-self:start}
.sira-ad{font-weight:600;line-height:1.3}
.sira-net{font:700 1.25rem/1 var(--rakam);text-align:right;white-space:nowrap}
.cubuk{grid-column:1/-1;position:relative;height:4px;background:
linear-gradient(var(--soluk),var(--soluk)) 50% 0/1px 100% no-repeat,rgba(95,212,255,.07)}
.cubuk i{position:absolute;top:0;bottom:0;background:currentColor;box-shadow:0 0 8px currentColor}
.cubuk i.arti{left:50%}.cubuk i.eksi{right:50%}

.islemler{list-style:none;margin:0;padding:0;border-top:1px solid var(--cizgi)}
.islemler li{display:grid;grid-template-columns:4.8em 2.9em minmax(0,1fr) auto;gap:4px 10px;align-items:start;
padding:10px 2px;border-bottom:1px solid var(--cizgi)}
.islem-zaman{color:var(--soluk);font-size:.8125rem;white-space:nowrap;padding-top:2px}
.islem-parite{font-weight:600;overflow-wrap:anywhere}
.islem-net{font:700 1.0625rem/1.3 var(--rakam);text-align:right;white-space:nowrap}
.islem-net .alt{font-family:var(--govde)}
.islem-sure{text-align:right;white-space:nowrap;font-weight:600}
.islemler .kod{min-width:0;justify-self:start}
.devam{margin:12px 0 0;font-size:.9375rem}

.kartlar{display:grid;gap:16px;margin-top:18px}
.kart{padding:16px}
.kart.secili{border-color:var(--holo);box-shadow:0 0 0 1px var(--holo),0 0 26px rgba(95,212,255,.25)}
.kart-ust{display:flex;align-items:center;gap:10px}
.kart h3{margin:0;font-size:1.1875rem}
.kart > .alt{margin:6px 0 0}
.kart-aciklama{margin:10px 0 0;max-width:60ch}
.olcu{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;margin:14px 0 0;border-top:1px solid var(--cizgi)}
.olcu.sonuc{grid-template-columns:repeat(2,minmax(0,1fr));margin-top:0;margin-bottom:10px;border-bottom:1px solid var(--cizgi)}
.olcu div{padding:9px 8px 8px 0;min-width:0}
.olcu.sonuc div:nth-child(n+3){border-top:1px solid var(--cizgi)}
.olcu dt{color:var(--soluk);font-size:.75rem}
.olcu dd{margin:0;font:700 1.125rem/1.25 var(--rakam)}
.olcu dd .alt{font-family:var(--govde);font-size:.75rem}
.kart-olcut{margin-top:12px}
.kart-durum{margin-top:12px;padding-top:10px;border-top:1px solid var(--cizgi)}
.durum{font-weight:600;color:var(--arti)}
.durum.sorun{color:var(--altin)}.durum.gecti{color:var(--arti)}.durum.kaldi{color:var(--eksi)}
.isaretler{display:inline-flex;gap:4px;flex-wrap:wrap}
.isaret{display:inline-flex;align-items:center;gap:2px;min-width:34px;justify-content:center;
padding:2px 5px;font-size:.8125rem;font-weight:700;border:1px solid}
.isaret-no{font-weight:500;opacity:.75}
.isaret.saglandi,.im.saglandi{color:var(--arti)}
.isaret.saglanmadi,.im.saglanmadi{color:var(--eksi)}
.isaret.veri_yok{color:var(--altin);border-style:dashed}
.im.veri_yok{color:var(--altin)}
.im{font-weight:700}
.im.veri_yok{font-size:1.5em;line-height:.6}

.serit.ders{border-left-color:var(--holo);background:var(--cam);margin-top:10px}
.serit.ders strong{color:var(--holo)}
.alt.sonra{color:var(--holo);opacity:.85}
.ders-kartlar{display:grid;gap:14px;margin-top:8px}
.ders-kart{padding:16px}
.ders-kart .kart-ust{flex-wrap:wrap}
.ders-kart h4{margin:0;font:700 1.0625rem/1.25 var(--rakam);letter-spacing:.03em}
.karar{margin-left:auto;font-size:.8125rem;font-weight:700;white-space:nowrap;color:var(--soluk)}
.karar.dar{color:var(--altin)}.karar.yerinde{color:var(--holo)}
.ders-cumle{margin:10px 0 0;max-width:60ch}
.secenekler{list-style:none;margin:12px 0 10px;padding:0;border-top:1px solid var(--cizgi)}
.secenekler li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 12px;padding:9px 0;
border-bottom:1px solid var(--cizgi)}
.secenek-net{font:700 1.125rem/1.3 var(--rakam);text-align:right;white-space:nowrap}
.secenek-net .alt{font-family:var(--govde)}
.secenek-net.erken{color:var(--soluk)}
.ders-listesi{list-style:none;margin:0;padding:0;border-top:1px solid var(--cizgi);max-width:76ch}
.ders-listesi li{padding:12px 2px;border-bottom:1px solid var(--cizgi)}
.ders-ust{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:4px}
.okuma-notlari{max-width:68ch;padding-left:1.2em;margin:0 0 12px;color:var(--soluk);font-size:.875rem}
.okuma-notlari li{margin:6px 0}
.sinav-durum{max-width:62ch;margin:0 0 18px;font-size:1.0625rem}
.sinav-durum strong{color:var(--holo)}
.cetvel{display:grid;grid-template-columns:repeat(30,1fr);gap:3px;max-width:720px}
.gun{height:22px;border:1px solid var(--cizgi);background:transparent}
.gun.hafta-sonu{margin-right:5px}
.gun.gecti{background:var(--holo);border-color:var(--holo);box-shadow:0 0 8px rgba(95,212,255,.5)}
.gun.bugun{border-color:var(--altin);border-width:2px;box-shadow:0 0 10px rgba(255,194,74,.5)}
.cetvel-alt{display:flex;justify-content:space-between;max-width:720px;color:var(--soluk);
font-size:.8125rem;margin-top:4px}
.olcut-listesi{max-width:66ch;padding-left:1.4em;margin:0 0 12px}
.olcut-listesi li{margin:4px 0}
.olcut-listesi li::marker{color:var(--holo);font-family:var(--rakam);font-weight:700}
.cizelge{border-collapse:collapse;width:100%;max-width:820px}
.cizelge th,.cizelge td{padding:8px 4px;border-bottom:1px solid var(--cizgi);text-align:center}
.cizelge thead th{color:var(--soluk);font:700 .8125rem var(--rakam)}
.cizelge th[scope=row],.cizelge thead th:first-child{text-align:left}
.cizelge th[scope=row] a{display:flex;align-items:center;gap:10px;color:inherit;text-decoration:none;font-weight:600}
.cizelge-ad{display:none}
.cizelge-karar{font-weight:700;white-space:nowrap}
.cizelge-karar.gecti{color:var(--arti)}.cizelge-karar.kaldi{color:var(--eksi)}
.anahtar{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0 0;color:var(--soluk);font-size:.875rem}

.gezinti{position:fixed;left:0;right:0;bottom:0;z-index:4;display:grid;grid-template-columns:repeat(EKRAN_SAYISI,1fr);
background:rgba(4,9,17,.9);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);
border-top:1px solid var(--cizgi);padding-bottom:env(safe-area-inset-bottom)}
.gezinti a{display:flex;align-items:center;justify-content:center;min-height:54px;padding:6px 4px;
color:var(--soluk);text-decoration:none;font-size:.8125rem;font-weight:600;border-top:2px solid transparent;margin-top:-1px;
white-space:nowrap}
.gezinti a:focus-visible{outline-offset:-4px}
EKRAN_SECILI{
color:var(--holo);border-top-color:var(--holo);background:linear-gradient(rgba(95,212,255,.14),rgba(95,212,255,0))}

@media (min-width:640px){
.cizelge-ad{display:inline}
.okumalar{grid-template-columns:repeat(4,1fr)}
.okuma:nth-child(odd){border-left:1px solid var(--cizgi)}
.okuma:first-child{border-left:0}
.okuma:nth-child(-n+4){border-top:0}
.olcu.sonuc{grid-template-columns:repeat(4,minmax(0,1fr))}
.olcu.sonuc div:nth-child(n+3){border-top:0}
.sira{grid-template-columns:3.1em minmax(0,1fr) minmax(120px,260px) 110px}
.cubuk{grid-column:auto;order:0}
.sira-net{order:1}
}
@media (min-width:900px){
.sayfa{padding:74px 24px 72px}
.ders-kartlar{grid-template-columns:1fr 1fr}
.pano{grid-template-columns:minmax(0,1fr) minmax(0,480px);grid-template-areas:"selam halka" "okumalar halka" "seyir halka";
column-gap:44px;align-items:start;margin-top:26px}
.selam{grid-area:selam}.reaktor{grid-area:halka;align-self:center}.okumalar{grid-area:okumalar}.seyir{grid-area:seyir}
.okumalar{grid-template-columns:1fr 1fr}
.okuma:nth-child(odd){border-left:0}
.okuma:nth-child(even){border-left:1px solid var(--cizgi)}
.okuma:nth-child(-n+4){border-top:1px solid var(--cizgi)}
.okuma:nth-child(-n+2){border-top:0}
.kartlar{grid-template-columns:1fr 1fr}
.kart{scroll-margin-top:56px}
.gezinti{left:50%;right:auto;bottom:auto;top:12px;transform:translateX(-50%);display:flex;
border:1px solid var(--cizgi);padding:0}
.gezinti a{min-height:38px;padding:6px 20px;border-top:0;margin-top:0;font-size:.875rem}
.sekmeli .gezinti a{border-top:0}
}
@media (prefers-reduced-motion:reduce){.r-kat,.r-don{animation:none}}
"""
STIL = (
    STIL.replace("KOSE", _KOSE)
    .replace("EKRAN_GOSTER", ",".join(f'.sekmeli[data-ekran="{k}"] #{k}' for k, _ in EKRANLAR))
    .replace("EKRAN_SECILI", ",".join(f'.sekmeli[data-ekran="{k}"] .gezinti a[href="#{k}"]' for k, _ in EKRANLAR))
    .replace("EKRAN_SAYISI", str(len(EKRANLAR)))
)


# --------------------------------------------------------------------------
# Betik: ekran geçişi ve yerinde tazeleme
# --------------------------------------------------------------------------

_BETIK = """(function(){
var kok=document.documentElement,govde=document.getElementById('govde');
var EKRANLAR=EKRAN_LISTESI;
function goster(kaydir){
var ad=location.hash.slice(1),hedef=ad?document.getElementById(ad):null,ekran='ana';
if(hedef){var e=hedef.closest('.ekran');if(e)ekran=e.id;}
if(EKRANLAR.indexOf(ekran)<0)ekran='ana';
kok.setAttribute('data-ekran',ekran);
var b=document.querySelectorAll('.gezinti a');
for(var i=0;i<b.length;i++){if(b[i].getAttribute('href')==='#'+ekran)b[i].setAttribute('aria-current','page');else b[i].removeAttribute('aria-current');}
var eski=document.querySelector('.secili');if(eski)eski.classList.remove('secili');
if(hedef&&hedef.id!==ekran){hedef.classList.add('secili');if(kaydir)hedef.scrollIntoView();}
else if(kaydir)window.scrollTo(0,0);
}
function yenile(){
fetch(location.pathname,{cache:'no-store'}).then(function(y){if(!y.ok)throw 0;return y.text();}).then(function(m){
var yeni=new DOMParser().parseFromString(m,'text/html').getElementById('govde');
if(!yeni)throw 0;
kok.style.setProperty('--gecen','-'+(performance.now()/1000).toFixed(1)+'s');
kok.classList.add('acildi');
govde.innerHTML=yeni.innerHTML;
kok.classList.remove('kopuk');
goster(false);
}).catch(function(){kok.classList.add('kopuk');});
}
kok.classList.add('sekmeli');
goster(!!location.hash);
window.addEventListener('hashchange',function(){goster(true);});
setInterval(yenile,SURE);
document.addEventListener('visibilitychange',function(){if(!document.hidden)yenile();});
})();"""


def betik(yenile_saniye: int) -> str:
    """Sayfaya gömülen betiğin tam metni. Sunucu, izin başlığını bu metnin özetinden üretir."""
    liste = "[" + ",".join(f"'{k}'" for k, _ in EKRANLAR) + "]"
    return _BETIK.replace("EKRAN_LISTESI", liste).replace("SURE", str(int(yenile_saniye) * 1000))


def html_uret(ozet: dict, saat_dilimi: str = "Europe/Bucharest", yenile_saniye: int = 60) -> str:
    """Özeti tam bir HTML sayfasına çevirir.

    yenile_saniye sıfırsa sayfa betiksiz ve kendini yenilemeyen tek bir dosya
    olur (Telegram'dan gönderilen hali); dört ekran alt alta görünür.
    """
    yerel, dilim_adi = yerel_zaman(ozet["uretildi"], saat_dilimi)
    guncelleme = f'{yerel.strftime("%d.%m.%Y %H:%M")} ({dilim_adi})'

    if yenile_saniye:
        yenile = f'<noscript><meta http-equiv="refresh" content="{int(yenile_saniye)}"></noscript>'
        yenileme_notu = " Sayfa dakikada bir kendini tazeler."
        son = f"<script>{betik(yenile_saniye)}</script>"
    else:
        yenile = ""
        yenileme_notu = " Bu dosya gönderildiği andaki durumu gösterir; kendini tazelemez."
        son = ""

    gezinti = "".join(f'<a href="#{kimlik}">{ad}</a>' for kimlik, ad in EKRANLAR)

    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#04070d">
{yenile}
<meta name="robots" content="noindex">
<title>Karabasan</title>
<style>{STIL}</style>
</head>
<body>
<p class="kopuk-uyari" role="status">Sunucuya ulaşılamıyor. Ekrandaki sayılar son başarılı güncellemeden kalma.</p>
<div id="govde" class="sayfa">
<header class="ust">
<span class="marka">KARABASAN</span>
<span class="guncelleme">Son güncelleme {escape(guncelleme)}</span>
</header>
<main>
{_ana_ekran(ozet, saat_dilimi)}
{_botlar_ekrani(ozet)}
{_islemler_ekrani(ozet, saat_dilimi)}
{_dersler_ekrani(ozet, saat_dilimi)}
{_sinav_ekrani(ozet, yenileme_notu)}
</main>
</div>
<nav class="gezinti" aria-label="Ekranlar">{gezinti}</nav>
{son}
</body>
</html>
"""
