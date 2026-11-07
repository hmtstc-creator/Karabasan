"""Sonuç sayfası: karabasan.sonuc özetini tek bir Türkçe HTML sayfasına çevirir.

Altı ekran vardır: ana ekran (gösterge halkası), botlar, işlemler, dersler
(stop sonrası izleme), rapor (bot seçimli günlük kâr / zarar), sınav.
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

from .kriterler import DUZENLEME_ADRESI, metin_degeri
from .kriterler import liste as kriter_listesi
from .stop_sonrasi import KARAR_ADI, carpan_metni, esik_metni, secenek_metni

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
    ("islemgrafik", "İşlem grafiği"),
    ("dersler", "Dersler"),
    ("rapor", "Rapor"),
    ("grafikler", "Grafikler"),
    ("zaman", "Zaman"),
    ("analiz", "Analiz"),
    ("sinav", "Sınav"),
    ("kriterler", "Kriterler"),
]
# Telefondaki alt gezintide görünen kısa adlar (8 sekme 390 px'e sığsın diye).
GEZINTI_ADLARI = {"ana": "Ana", "islemler": "İşlem", "dersler": "Ders", "kriterler": "Kriter", "grafikler": "Grafik",
                  "islemgrafik": "İşlemler"}
# Telefonda alttaki çubukta duran ekranlar; hepsi üstteki menüde.
ALT_CUBUK = ["ana", "botlar", "islemgrafik", "grafikler", "analiz"]
# Menüde ekran adının altındaki kısa açıklama.
MENU_ACIKLAMA = {
    "ana": "Özet ve gösterge halkası", "botlar": "Her botun kartı", "islemler": "Açık ve kapanan işlemler",
    "islemgrafik": "Giriş / çıkış grafikte",
    "dersler": "Stop sonrası izleme", "rapor": "Gün gün kâr / zarar", "grafikler": "Seyir, düşüş, dağılım",
    "zaman": "Saat ve gün bazında", "analiz": "Karneler, coinler, risk", "sinav": "30 günlük sınav",
    "kriterler": "Ahmet Özel kriterleri",
}
# Rapor ekranında seçilebilecek en çok bot sayısı (biçim kuralları bu kadarı için üretilir).
RAPOR_EN_FAZLA = 16
RAPOR_GUN = 30
GUN_ADLARI = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


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


def fiyat_metni(fiyat) -> str:
    """Fiyatı büyüklüğüne göre basamakla yazar: 97,00 · 2,4512 · 0,123456."""
    if fiyat is None:
        return "–"
    basamak = 2 if abs(fiyat) >= 10 else 4 if abs(fiyat) >= 1 else 6
    return sayi(fiyat, basamak)


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
        '<p class="reaktor-not">Dış halkadaki her dilim bir bottur: yeşil artıda, kırmızı ekside, turuncu kesik ses yok. '
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
            f'<span class="alt">{_yon(i["yon"])}, {sayi(i["tutar"], 0)} USDT'
            + (f', stop {fiyat_metni(i["stop_fiyati"])}' if i.get("stop_fiyati") else "")
            + '</span></span>'
            f'<span class="islem-sure">{_sure(gecen)}<span class="alt">önce açıldı</span>'
            + (f'<span class="alt eksi">stopta ≈ {isaretli(i["stopta_kayip"])}</span>'
               if i.get("stopta_kayip") is not None else "")
            + '</span>'
            "</li>"
        )
    toplam = sum(i.get("stopta_kayip") or 0.0 for i in aciklar)
    risk = (f'<p class="serit risk"><strong>{len(aciklar)} açık pozisyon.</strong> Hepsi stopa giderse '
            f'yaklaşık <span class="eksi">{isaretli(toplam)} USDT</span> (komisyon hariç).</p>') if toplam else ""
    return f'{risk}<ul class="islemler">{"".join(satirlar)}</ul>'


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


def _sessiz_seridi(ozet: dict, bot_cumlesi: str) -> str:
    """Bot cümlesi; ses vermeyen bot varsa göze batan bir uyarı şeridi olarak."""
    if not bot_cumlesi:
        return ""
    sessiz = any(b.get("calisiyor") is False and not b.get("hata") for b in ozet["botlar"])
    if sessiz:
        return f'<p class="uyari-serit" role="status">{escape(bot_cumlesi)}</p>'
    return f'<p class="bot-cumlesi">{escape(bot_cumlesi)}</p>'


def _ana_ekran(ozet: dict, saat_dilimi: str) -> str:
    baslik, aciklama = _durum_cumlesi(ozet)
    yerel, _ad = yerel_zaman(ozet["uretildi"], saat_dilimi)
    bot_cumlesi = _bot_cumlesi(ozet)
    return f"""<section id="ana" class="ekran">
<div class="pano">
<div class="selam">
<p class="selam-ust">{selam(yerel.hour)}</p>
{_sessiz_seridi(ozet, bot_cumlesi)}
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
    kaldirac = bot.get("kaldirac") or 1
    piyasa = "Spot piyasada" if bot["piyasa"] == "spot" else f"Vadeli piyasada, {kaldirac:g} kat kaldıraçla"
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
        ("Ort. kazanç", f'<span class="arti">{isaretli(bot.get("ort_kazanc_usdt"))}</span>', ""),
        ("Ort. kayıp", f'<span class="eksi">{isaretli(bot.get("ort_kayip_usdt"))}</span>', ""),
        ("En kötü işlem", f'<span class="eksi">{isaretli(bot.get("en_buyuk_kayip_usdt"))}</span>', ""),
        ("Kayıp serisi", f'{bot.get("en_uzun_kayip_serisi") or 0} işlem', ""),
    ]

    def liste(ogeler, sinif):
        return f'<dl class="olcu {sinif}">' + "".join(
            f"<div><dt>{ad}</dt><dd>{deger}</dd></div>" for ad, deger, _ in ogeler
        ) + "</dl>"

    notlar = []
    if bot.get("nedenler"):
        sirali = sorted(bot["nedenler"].items(), key=lambda n: n[1], reverse=True)
        notlar.append("Çıkışlar: " + ", ".join(f"{adet} {escape(neden)}" for neden, adet in sirali) + ".")
    if bot.get("ekleme_metni"):
        notlar.append(f"Pozisyon: {escape(bot['ekleme_metni'])}; stop ilk girişe göre kalır.")
    if bot.get("izinli_durumlar"):
        durumlar = ", ".join(DURUM_ADLARI.get(d, d) for d in bot["izinli_durumlar"])
        notlar.append(f"Tasarlandığı piyasa durumu: {escape(durumlar)}.")
    izleme = bot.get("stop_sonrasi") or {}
    if izleme.get("stop_sayisi"):
        notlar.append(
            f'Stop sonrası: izlenen {izleme["stop_sayisi"]} stopun {izleme["hedefi_goren"]} tanesinde fiyat '
            f'{esik_metni(izleme.get("esik", "hedef"))}. {KARAR_ADI[izleme["karar"]["kod"]]}. '
            '<a href="#dersler">Ayrıntı</a>'
        )
    isaretler = _olcut_isaretleri(bot)
    return (
        f'<article class="kart kose" id="bot-{escape(bot["bot"])}">'
        f'<div class="kart-ust"><span class="kod">{escape(bot["kod"])}</span>'
        f'<h3>{escape(bot["ad"])}</h3></div>'
        f'<div class="kart-guven">{_guven_rozeti(bot)}</div>'
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
# İşlem grafiği ekranı: bot seç, işleme dokun, /islem sayfasında grafiği aç.
# Bot seçimi betiksiz (gizli seçim düğmeleri + biçim kuralları; Rapor ekranı gibi).
# --------------------------------------------------------------------------

IG_EN_FAZLA = 16


def _ig_satiri(i: dict, bot: str, saat_dilimi: str, acik: bool) -> str:
    adres = f"/islem?bot={escape(bot)}&amp;id={int(i['kimlik'])}"
    if acik:
        sag = '<span class="ig-sonuc notr">açık<span class="alt">şu an</span></span>'
        zaman = _tarih_saat(i["giris_zamani"], saat_dilimi)
    else:
        net = i.get("net_tutar")
        sag = (f'<span class="ig-sonuc {_isaret_sinifi(net)}">{isaretli(net)}'
               f'<span class="alt">{escape(str(i.get("neden") or ""))}</span></span>')
        zaman = _tarih_saat(i["cikis_zamani"], saat_dilimi)
    return (f'<li><a class="ig-satir" href="{adres}"><span class="islem-zaman">{zaman}</span>'
            f'<span class="islem-parite">{_parite(i["parite"])}<span class="alt">{_yon(i["yon"])}</span></span>'
            f'{sag}<span class="ig-ok" aria-hidden="true">›</span></a></li>')


def _islem_grafigi_ekrani(ozet: dict, saat_dilimi: str) -> str:
    liste = (ozet.get("islem_listesi") or [])[:IG_EN_FAZLA]
    if not liste:
        govde = '<p class="bos">Henüz bot yok.</p>'
    else:
        dugmeler = "".join(
            f'<input type="radio" name="ig-bot" id="ig-{k}" class="rapor-radyo"{" checked" if k == 0 else ""}>'
            for k in range(len(liste)))
        etiketler = "".join(f'<label for="ig-{k}">{escape(b["kod"])}</label>' for k, b in enumerate(liste))
        paneller = []
        for k, b in enumerate(liste):
            satirlar = ([_ig_satiri(i, b["bot"], saat_dilimi, True) for i in b["acik"]]
                        + [_ig_satiri(i, b["bot"], saat_dilimi, False) for i in b["kapali"]])
            icerik = (f'<ul class="ig-liste">{"".join(satirlar)}</ul>' if satirlar
                      else '<p class="bos">Bu botun henüz işlemi yok.</p>')
            paneller.append(f'<div class="ig-panel ig-p-{k}"><h3>{escape(b["kod"])} · {escape(b["ad"])}</h3>{icerik}</div>')
        govde = (f'{dugmeler}<div class="rapor-secim ig-secim" role="group" aria-label="Bot seç">{etiketler}</div>'
                 f'<div class="ig-paneller">{"".join(paneller)}</div>')
    return f"""<section id="islemgrafik" class="ekran">
<h2 class="ekran-baslik">İşlem grafiği</h2>
<p class="ekran-ozet">Bir bot seç, sonra bir işleme dokun: o coinin grafiğinde nerede girip nerede çıktığını görürsün.</p>
<p class="g-not">Açık pozisyonlar üstte. Grafik ayrı bir sayfada açılır; bu sayfaya dönmek için "İşlem listesi" düğmesine dokun.
Telegram'dan gelen dosyada bu bağlantılar çalışmaz, yalnız sitede çalışır.</p>
{govde}
</section>"""


# --------------------------------------------------------------------------
# Rapor ekranı: her botun günlük kâr / zararı
# --------------------------------------------------------------------------


def _gun_metni(gun: str) -> str:
    """'2026-10-12' -> '12.10 Pzt'."""
    tarih = datetime.strptime(gun, "%Y-%m-%d")
    return f"{tarih:%d.%m} {GUN_ADLARI[tarih.weekday()]}"


def _gunluk_cubuklar(gunluk: list, bugun: str, gun_sayisi: int = RAPOR_GUN) -> str:
    """Son günlerin net sonucu, gün başına bir çubuk (işlem olmayan gün boş kalır)."""
    from datetime import date, timedelta

    son = date.fromisoformat(bugun)
    ilk_kayit = date.fromisoformat(gunluk[0]["gun"])
    bas = max(ilk_kayit, son - timedelta(days=gun_sayisi - 1))
    gunler = [(bas + timedelta(days=k)).isoformat() for k in range((son - bas).days + 1)]
    netler = {g["gun"]: float(g["net_tutar"]) for g in gunluk}
    gorunen = [netler[g] for g in gunler if g in netler]
    ust = max([0.0, *gorunen])
    alt = -min([0.0, *gorunen])
    en_buyuk = max(ust, alt) or 1.0
    genislik, bosluk = 600.0, 4.0
    # Sıfır çizgisi artı ve eksi günlerin büyüklüğüne göre yerleşir; boş yarım alan kalmaz.
    olcek = 120.0 / ((ust + alt) or 1.0)
    orta = bosluk + ust * olcek
    yukseklik = orta + alt * olcek + bosluk
    adim = genislik / len(gunler)
    cubuk = max(2.0, min(28.0, adim * 0.7))
    parcalar = []
    for k, g in enumerate(gunler):
        if g not in netler:
            continue
        net = netler[g]
        boy = max(1.0, abs(net) * olcek)
        y = orta - boy if net > 0 else orta
        parcalar.append(
            f'<rect class="g-cubuk {_isaret_sinifi(net)}" x="{k * adim + (adim - cubuk) / 2:.1f}" '
            f'y="{y:.1f}" width="{cubuk:.1f}" height="{boy:.1f}"><title>{_gun_metni(g)}: '
            f"{isaretli(net)} USDT</title></rect>"
        )
    return (
        f'<svg class="g-grafik" viewBox="0 0 {genislik:g} {yukseklik:.1f}" role="img" '
        f'aria-label="Son {len(gunler)} günün günlük sonucu">'
        f'<line class="s-sifir" x1="0" x2="{genislik:g}" y1="{orta:.1f}" y2="{orta:.1f}"/>{"".join(parcalar)}</svg>'
        f'<p class="seyir-alt"><span>{_gun_metni(gunler[0])}</span><span>En büyük gün ±{sayi(en_buyuk)} USDT</span>'
        f'<span>{_gun_metni(gunler[-1])}</span></p>'
    )


def _rapor_paneli(sira: int, baslik: str, gunluk: list, bugun: str) -> str:
    if not gunluk:
        govde = '<p class="bos">Henüz kapanmış işlem yok. İşlemler kapandıkça günlük sonuç burada birikir.</p>'
    else:
        toplam = sum(g["net_tutar"] for g in gunluk)
        islem = sum(g["islem"] for g in gunluk)
        kazanan = sum(g["kazanan"] for g in gunluk)
        arti_gun = sum(1 for g in gunluk if g["net_tutar"] > 0.005)
        en_iyi = max(gunluk, key=lambda g: g["net_tutar"])
        en_kotu = min(gunluk, key=lambda g: g["net_tutar"])
        satirlar = "".join(
            f'<tr><th scope="row">{_gun_metni(g["gun"])}</th><td>{g["islem"]}'
            f'<span class="alt">{g["kazanan"]} kazanan</span></td>'
            f'<td class="{_isaret_sinifi(g["net_tutar"])}">{isaretli(g["net_tutar"])}</td>'
            f'<td class="{_isaret_sinifi(g["birikimli"])}">{isaretli(g["birikimli"])}</td></tr>'
            for g in reversed(gunluk)
        )
        govde = (
            f'<dl class="olcu sonuc">'
            f'<div><dt>Toplam net</dt><dd class="{_isaret_sinifi(toplam)}">{isaretli(toplam)} '
            f'<span class="alt">USDT</span></dd></div>'
            f'<div><dt>Artıda biten gün</dt><dd>{arti_gun} / {len(gunluk)}</dd></div>'
            f'<div><dt>İşlem</dt><dd>{islem} <span class="alt">%{sayi(kazanan / islem * 100, 0)} kazanan</span></dd></div>'
            f'<div><dt>En iyi / en kötü gün</dt><dd><span class="{_isaret_sinifi(en_iyi["net_tutar"])}">'
            f'{isaretli(en_iyi["net_tutar"])}</span> / <span class="{_isaret_sinifi(en_kotu["net_tutar"])}">'
            f'{isaretli(en_kotu["net_tutar"])}</span></dd></div></dl>'
            f'{_gunluk_cubuklar(gunluk, bugun)}'
            f'<table class="cizelge gunluk"><thead><tr><th>Gün</th><th>İşlem</th><th>Net USDT</th>'
            f'<th>Birikimli</th></tr></thead><tbody>{satirlar}</tbody></table>'
        )
    return f'<div class="rapor-panel rp-{sira}"><h3>{escape(baslik)}</h3>{govde}</div>'


def _rapor_ekrani(ozet: dict, saat_dilimi: str) -> str:
    """Bot seçimli günlük kâr / zarar raporu.

    Seçim betiksiz çalışır (gizli seçim düğmeleri ve biçim kuralları); Telegram'dan
    gönderilen dosyada da kullanılabilir.
    """
    yerel, dilim_adi = yerel_zaman(ozet["uretildi"], saat_dilimi)
    bugun = yerel.strftime("%Y-%m-%d")
    secenekler = [("Bütün botlar", "Bütün botlar", ozet.get("gunluk_toplam") or [])]
    secenekler += [(b["kod"], f'{b["kod"]} · {b["ad"]}', b.get("gunluk") or [])
                   for b in ozet["botlar"]][:RAPOR_EN_FAZLA - 1]
    dugmeler = "".join(
        f'<input type="radio" name="rapor-bot" id="rb-{k}" class="rapor-radyo"{" checked" if k == 0 else ""}>'
        for k in range(len(secenekler))
    )
    etiketler = "".join(f'<label for="rb-{k}">{escape(kisa)}</label>' for k, (kisa, _, _) in enumerate(secenekler))
    paneller = "".join(_rapor_paneli(k, uzun, gunluk, bugun) for k, (_, uzun, gunluk) in enumerate(secenekler))
    return f"""<section id="rapor" class="ekran">
<h2 class="ekran-baslik">Rapor</h2>
<p class="not">Her botun gün gün sanal kâr ya da zararı (komisyon düşülmüş, USDT). Bir işlem
kapandığı güne sayılır; açık pozisyonlar kapanınca eklenir. Gün sınırı gece yarısıdır
({escape(dilim_adi)}).</p>
{dugmeler}
<div class="rapor-secim" role="group" aria-label="Bot seç">{etiketler}</div>
<div class="rapor-paneller">{paneller}</div>
</section>"""


# --------------------------------------------------------------------------
# Analiz ekranı: yalnız okuma. Bot karşılaştırması, kazanma oranı, çıkış nedenleri, süre.
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Grafik yardımcıları (satır içi SVG; dış kütüphane yok, betiksiz de çizilir).
# İpuçları <title> ile: dokununca / üstüne gelince değer görünür.
# --------------------------------------------------------------------------

SERI_RENKLERI = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
SERI_EN_FAZLA = len(SERI_RENKLERI)


def _guzel_adimlar(alt: float, ust: float, adet: int = 4) -> list[float]:
    """Eksen için okunur değerler (1, 2, 2,5, 5 × 10^n)."""
    if ust - alt < 1e-12:
        ust = alt + 1.0
    ham = (ust - alt) / max(adet, 1)
    us = 10 ** math.floor(math.log10(ham))
    adim = next(k * us for k in (1, 2, 2.5, 5, 10) if k * us >= ham)
    bas = math.floor(alt / adim) * adim
    cikti, v = [], bas
    while v <= ust + adim * 0.001:
        cikti.append(round(v, 10))
        v += adim
    if cikti[-1] < ust - 1e-12:
        cikti.append(round(cikti[-1] + adim, 10))
    return cikti


def _tarih_kisa(zaman_sn: float) -> str:
    yerel, _ = yerel_zaman(datetime.fromtimestamp(zaman_sn, tz=timezone.utc))
    return yerel.strftime("%d.%m")


class _Cerceve:
    """Grafik alanı: kenar boşlukları ve ölçekler."""

    def __init__(self, x0, x1, y0, y1, genislik=380.0, yukseklik=220.0, sol=40.0, sag=10.0, ust=12.0, alt=24.0):
        self.g, self.h = genislik, yukseklik
        self.sol, self.sag, self.ust, self.alt = sol, sag, ust, alt
        self.x0, self.x1 = x0, (x1 if x1 > x0 else x0 + 1)
        self.y0, self.y1 = y0, (y1 if y1 > y0 else y0 + 1)

    def x(self, v):
        return self.sol + (v - self.x0) / (self.x1 - self.x0) * (self.g - self.sol - self.sag)

    def y(self, v):
        return self.ust + (self.y1 - v) / (self.y1 - self.y0) * (self.h - self.ust - self.alt)

    def y_ekseni(self, adimlar, bicim=lambda v: sayi(v, 2)) -> str:
        parca = []
        for v in adimlar:
            yy = self.y(v)
            sinif = "g-sifir" if abs(v) < 1e-12 else "g-izgara"
            parca.append(f'<line class="{sinif}" x1="{self.sol:g}" x2="{self.g - self.sag:g}" y1="{yy:.1f}" y2="{yy:.1f}"/>'
                         f'<text class="g-eksen" x="{self.sol - 6:g}" y="{yy:.1f}" text-anchor="end" dominant-baseline="middle">{bicim(v)}</text>')
        return "".join(parca)

    def x_etiketleri(self, ciftler) -> str:
        return "".join(f'<text class="g-eksen" x="{self.x(v):.1f}" y="{self.h - 8:g}" text-anchor="middle">{escape(m)}</text>'
                       for v, m in ciftler)

    def svg(self, icerik: str, etiket: str) -> str:
        return (f'<svg class="g-svg" viewBox="0 0 {self.g:g} {self.h:g}" role="img" aria-label="{escape(etiket)}">'
                f"{icerik}</svg>")


def _zaman_etiketleri(c: _Cerceve, adet: int = 4) -> str:
    if c.x1 - c.x0 < 1:
        return ""
    return c.x_etiketleri([(c.x0 + (c.x1 - c.x0) * k / (adet - 1), _tarih_kisa(c.x0 + (c.x1 - c.x0) * k / (adet - 1)))
                           for k in range(adet)])


def _cizgi_grafigi(seriler: list) -> str:
    """seriler: (ad, renk, [(zaman, değer)]). Bot başına birikimli sonuç; aynı eksen, aynı birim."""
    tum = [p for _, _, nok in seriler for p in nok]
    if len(tum) < 2:
        return '<p class="bos">Grafik için henüz yeterli kapanmış işlem yok.</p>'
    xs, ys = [p[0] for p in tum], [p[1] for p in tum] + [0.0]
    adimlar = _guzel_adimlar(min(ys), max(ys))
    c = _Cerceve(min(xs), max(xs), adimlar[0], adimlar[-1], sag=44.0 if len(seriler) <= 4 else 10.0)
    parca = [c.y_ekseni(adimlar), _zaman_etiketleri(c)]
    for ad, renk, nok in seriler:
        if len(nok) < 2:
            continue
        cizgi = " ".join(f"{c.x(t):.1f},{c.y(v):.1f}" for t, v in nok)
        son_t, son_v = nok[-1]
        parca.append(f'<polyline class="g-cizgi" style="stroke:{renk}" points="{cizgi}"><title>{escape(ad)}: '
                     f'{isaretli(son_v)} USDT</title></polyline>'
                     f'<circle class="g-uc" style="fill:{renk}" cx="{c.x(son_t):.1f}" cy="{c.y(son_v):.1f}" r="4">'
                     f'<title>{escape(ad)}: {isaretli(son_v)} USDT</title></circle>')
        if len(seriler) <= 4:
            parca.append(f'<text class="g-etiket" x="{c.x(son_t) + 8:.1f}" y="{c.y(son_v):.1f}" dominant-baseline="middle">'
                         f'{escape(ad)}</text>')
    gosterge = "".join(f'<span class="g-gosterge-oge"><i style="background:{renk}"></i>{escape(ad)}</span>'
                       for ad, renk, _ in seriler)
    return (c.svg("".join(parca), "Botların birikimli sanal sonucu")
            + f'<div class="g-gosterge">{gosterge}</div>')


def _dusus_grafigi(dusus: list) -> str:
    if len(dusus) < 2:
        return '<p class="bos">Grafik için henüz yeterli kapanmış işlem yok.</p>'
    en_dip = min(v for _, v in dusus)
    adimlar = _guzel_adimlar(min(en_dip, -0.01), 0.0)
    c = _Cerceve(dusus[0][0], dusus[-1][0], adimlar[0], 0.0, yukseklik=170.0)
    alan = (f"{c.x(dusus[0][0]):.1f},{c.y(0):.1f} "
            + " ".join(f"{c.x(t):.1f},{c.y(v):.1f}" for t, v in dusus)
            + f" {c.x(dusus[-1][0]):.1f},{c.y(0):.1f}")
    cizgi = " ".join(f"{c.x(t):.1f},{c.y(v):.1f}" for t, v in dusus)
    dip_t = next(t for t, v in dusus if v == en_dip)
    icerik = (c.y_ekseni(adimlar) + _zaman_etiketleri(c)
              + f'<polygon class="g-alan-eksi" points="{alan}"/><polyline class="g-cizgi eksi" points="{cizgi}"/>'
              + (f'<circle class="g-uc eksi-dolgu" cx="{c.x(dip_t):.1f}" cy="{c.y(en_dip):.1f}" r="4">'
                 f'<title>En derin düşüş {isaretli(en_dip)} USDT ({_tarih_kisa(dip_t)})</title></circle>' if en_dip < 0 else ""))
    return (c.svg(icerik, f"Tepeden düşüş; en derini {isaretli(en_dip)} USDT")
            + f'<p class="g-not">En derin düşüş <strong class="eksi">{isaretli(en_dip)} USDT</strong>'
            + (f" ({_tarih_kisa(dip_t)})" if en_dip < 0 else "") + ". Sıfır çizgisi yeni tepe demektir.</p>")


def _cubuk_grafigi(cubuklar: list, yukseklik: float = 190.0, etiket_adim: int = 1) -> str:
    """cubuklar: (eksen etiketi, değer, ipucu). Sıfırın iki yanında; artı yeşil, eksi kırmızı."""
    if not cubuklar or all(abs(v) < 1e-12 for _, v, _ in cubuklar):
        return '<p class="bos">Henüz yeterli kapanmış işlem yok.</p>'
    degerler = [v for _, v, _ in cubuklar] + [0.0]
    adimlar = _guzel_adimlar(min(degerler), max(degerler))
    n = len(cubuklar)
    c = _Cerceve(0, n, adimlar[0], adimlar[-1], yukseklik=yukseklik)
    genislik = (c.x(1) - c.x(0))
    cubuk_g = max(genislik - 3.0, 2.0)
    parca = [c.y_ekseni(adimlar)]
    for k, (et, v, ipucu) in enumerate(cubuklar):
        x = c.x(k) + (genislik - cubuk_g) / 2
        y_ust, y_alt = sorted((c.y(v), c.y(0)))
        sinif = _isaret_sinifi(v)
        parca.append(f'<rect class="g-cubuk {sinif}" x="{x:.1f}" y="{y_ust:.1f}" width="{cubuk_g:.1f}" '
                     f'height="{max(y_alt - y_ust, 0.8):.1f}" rx="2"><title>{escape(ipucu)}</title></rect>')
        if k % etiket_adim == 0:
            parca.append(f'<text class="g-eksen" x="{x + cubuk_g / 2:.1f}" y="{c.h - 8:g}" text-anchor="middle">{escape(et)}</text>')
    return c.svg("".join(parca), "Çubuk grafik")


def _histogram(kutular: list) -> str:
    if not kutular:
        return '<p class="bos">Henüz kapanmış işlem yok.</p>'
    en_cok = max(k["adet"] for k in kutular) or 1
    adimlar = _guzel_adimlar(0, en_cok)
    c = _Cerceve(kutular[0]["alt"], kutular[-1]["ust"], 0, adimlar[-1], yukseklik=180.0)
    parca = [c.y_ekseni(adimlar, bicim=lambda v: str(int(v)))]
    for k in kutular:
        x0, x1 = c.x(k["alt"]) + 1, c.x(k["ust"]) - 1
        sinif = "eksi" if k["ust"] <= 0 else "arti" if k["alt"] >= 0 else "notr"
        parca.append(f'<rect class="g-cubuk {sinif}" x="{x0:.1f}" y="{c.y(k["adet"]):.1f}" width="{max(x1 - x0, 1):.1f}" '
                     f'height="{max(c.y(0) - c.y(k["adet"]), 0):.1f}" rx="2"><title>{k["adet"]} işlem: '
                     f'{isaretli(k["alt"])} ile {isaretli(k["ust"])} USDT arası</title></rect>')
    parca.append(c.x_etiketleri([(k["alt"], sayi(k["alt"], 1)) for k in kutular[:: max(len(kutular) // 4, 1)]]))
    if c.x0 < 0 < c.x1:
        parca.append(f'<line class="g-sifir" x1="{c.x(0):.1f}" x2="{c.x(0):.1f}" y1="{c.ust:g}" y2="{c.y(0):.1f}"/>')
    return c.svg("".join(parca), "İşlem sonuçlarının dağılımı")


def _sacilim(noktalar: list) -> str:
    if len(noktalar) < 3:
        return '<p class="bos">Henüz yeterli kapanmış işlem yok.</p>'
    saatler = [d / 60 for d, _ in noktalar]
    netler = [v for _, v in noktalar] + [0.0]
    y_ad = _guzel_adimlar(min(netler), max(netler))
    x_ad = _guzel_adimlar(0, max(saatler) or 1)
    c = _Cerceve(0, x_ad[-1], y_ad[0], y_ad[-1], yukseklik=220.0)
    parca = [c.y_ekseni(y_ad), c.x_etiketleri([(v, f"{sayi(v, 0)} sa") for v in x_ad])]
    for (d, v), sa in zip(noktalar, saatler):
        parca.append(f'<circle class="g-nokta {_isaret_sinifi(v)}" cx="{c.x(sa):.1f}" cy="{c.y(v):.1f}" r="3.2">'
                     f'<title>{_sure(d)}: {isaretli(v)} USDT</title></circle>')
    return c.svg("".join(parca), "İşlem süresi ve sonucu")


def _grafikler_ekrani(ozet: dict) -> str:
    g = ozet.get("grafik") or {}
    botlar = ozet["botlar"]
    egriler = g.get("egriler") or {}
    kodlar = [b["kod"] for b in botlar if b["kod"] in egriler]
    # Renk bota bağlıdır (sıra BOTLAR'dan), sonuca göre değişmez. 8'den fazlaysa en büyük 8.
    if len(kodlar) > SERI_EN_FAZLA:
        nets = {b["kod"]: abs(b["net_tutar"]) for b in botlar}
        secilen = set(sorted(kodlar, key=lambda k: nets.get(k, 0), reverse=True)[:SERI_EN_FAZLA])
        kodlar = [k for k in kodlar if k in secilen]
        not_metni = f'<p class="g-not">Grafik en büyük {SERI_EN_FAZLA} botu gösteriyor.</p>'
    else:
        not_metni = ""
    seriler = [(k, SERI_RENKLERI[i], egriler[k]) for i, k in enumerate(kodlar)]
    dagilim = g.get("dagilim") or []
    toplam_islem = sum(k["adet"] for k in dagilim)
    kazanan = sum(k["adet"] for k in dagilim if k["alt"] >= 0)
    return f"""<section id="grafikler" class="ekran">
<h2 class="ekran-baslik">Grafikler</h2>
<p class="ekran-ozet">{toplam_islem} kapanmış işlem · toplam <span class="{_isaret_sinifi(ozet["toplam"]["net_tutar"])}">{isaretli(ozet["toplam"]["net_tutar"])} USDT</span></p>
<details class="aciklama-kutu"><summary>Bu grafikler nasıl okunur?</summary>
<p>Hepsi sanal işlemlerden çizilir; tutarlar komisyon düşülmüş USDT'dir. Bir çizgiye, çubuğa ya da noktaya dokununca değeri görünür.
Kısa dönemde iyi görünen bir eğri şans olabilir; Analiz ekranındaki güven etiketine de bak.</p></details>
<div class="g-kartlar">
<div class="kose kart"><h3>Botların seyri</h3><p class="alt">Her bot için kapanan işlemlerle biriken net sonuç.</p>
{_cizgi_grafigi(seriler)}{not_metni}</div>
<div class="kose kart"><h3>Tepeden düşüş</h3><p class="alt">Bütün botlar birlikte: ulaşılan en yüksek noktadan ne kadar geride.</p>
{_dusus_grafigi(g.get("dusus") or [])}</div>
<div class="kose kart"><h3>İşlem sonuçlarının dağılımı</h3><p class="alt">Kaç işlem hangi kâr / zarar aralığında kapandı.
Sağda yeşil kazananlar, solda kırmızı kaybedenler{f" ({kazanan} / {toplam_islem} işlem sıfırın sağında)" if toplam_islem else ""}.</p>
{_histogram(dagilim)}</div>
<div class="kose kart"><h3>Süre ve sonuç</h3><p class="alt">Her nokta bir işlem: ne kadar açık kaldı, nasıl kapandı.</p>
{_sacilim(g.get("sure_sonuc") or [])}</div>
</div>
</section>"""


def _zaman_ekrani(ozet: dict, saat_dilimi: str) -> str:
    z = (ozet.get("grafik") or {}).get("zaman") or {"saat": [], "gun": []}
    _yerel, dilim_adi = yerel_zaman(ozet["uretildi"], saat_dilimi)

    def ipucu(ad, k):
        if not k["islem"]:
            return f"{ad}: işlem yok"
        return f'{ad}: {k["islem"]} işlem, %{sayi(k["kazanan"] / k["islem"] * 100, 0)} kazanma, {isaretli(k["net"])} USDT'

    saat = [(f"{h:02d}", k["net"], ipucu(f"{h:02d}:00", k)) for h, k in enumerate(z["saat"])]
    gun = [(ad, k["net"], ipucu(ad, k)) for ad, k in zip(GUN_ADLARI, z["gun"])]
    dolu_saat = [(h, k) for h, k in enumerate(z["saat"]) if k["islem"] >= 3]
    if dolu_saat:
        en_iyi = max(dolu_saat, key=lambda hk: hk[1]["net"])
        en_kotu = min(dolu_saat, key=lambda hk: hk[1]["net"])
        satir = (f'En iyi saat <strong class="arti">{en_iyi[0]:02d}:00</strong> ({isaretli(en_iyi[1]["net"])} USDT), '
                 f'en kötü <strong class="eksi">{en_kotu[0]:02d}:00</strong> ({isaretli(en_kotu[1]["net"])} USDT). '
                 "Az işlemli saatler şansa çok açıktır; bunu ayar değiştirmek için kullanma.")
    else:
        satir = "Saatleri karşılaştırmak için henüz yeterli işlem yok."
    return f"""<section id="zaman" class="ekran">
<h2 class="ekran-baslik">Zaman</h2>
<p class="ekran-ozet">İşlemler açıldıkları saate ve güne göre ({escape(dilim_adi)})</p>
<div class="g-kartlar">
<div class="kose kart"><h3>Günün saatine göre</h3><p class="alt">Her çubuk o saatte açılan işlemlerin toplam net sonucu.</p>
{_cubuk_grafigi(saat, etiket_adim=3)}<p class="g-not">{satir}</p></div>
<div class="kose kart"><h3>Haftanın gününe göre</h3>
{_cubuk_grafigi(gun, yukseklik=170.0)}</div>
</div>
</section>"""


# sonuc.CIKIS_NEDENI'nin Türkçe değerleri -> ekrandaki ad (aynı sırayla gösterilir).
NEDEN_ADLARI = {
    "kâr hedefi": "Kâr hedefi", "iz süren stop": "İz süren stop", "stop": "Stop",
    "süre aşımı": "Süre aşımı", "çıkış sinyali": "Çıkış sinyali", "elle kapatma": "Elle kapatma",
    "acil çıkış": "Acil çıkış", "tasfiye": "Tasfiye",
}
NEDEN_SIRASI = list(NEDEN_ADLARI.values())


def _ilk_buyuk(metin: str) -> str:
    """Türkçeye uygun ilk harf büyütme (i -> İ)."""
    if not metin:
        return metin
    ilk = "İ" if metin[0] == "i" else metin[0].upper()
    return ilk + metin[1:]


def _yatay_cubuklar(satirlar: list, en_buyuk: float, tek_yon: bool = False) -> str:
    """satirlar: (etiket, değer, sınıf, yazı). tek_yon: çubuk soldan başlar (süre gibi)."""
    en_buyuk = en_buyuk or 1.0
    cikti = []
    for etiket, deger, sinif, yazi in satirlar:
        if tek_yon:
            sol, genislik = 0.0, min(abs(deger) / en_buyuk, 1.0) * 100
        else:
            genislik = min(abs(deger) / en_buyuk, 1.0) * 50
            sol = 50.0 if deger >= 0 else 50.0 - genislik
        cikti.append(
            f'<li><span class="kriter-ad">{escape(etiket)}</span>'
            f'<span class="cubuk-ic{" tek" if tek_yon else ""}"><i class="{sinif}" '
            f'style="left:{sol:.2f}%;width:{genislik:.2f}%"></i></span>'
            f'<span class="kriter-deger {sinif}">{yazi}</span></li>'
        )
    return '<ul class="yatay">' + "".join(cikti) + "</ul>"


def _guven_rozeti(bot: dict) -> str:
    g = bot.get("guven") or {}
    if not g:
        return ""
    t = f'; t {sayi(g["t"], 1)}' if g.get("t") is not None else ""
    return (f'<span class="guven {g["sinif"]}">{escape(g["etiket"])}'
            f'<span class="guven-alt"> ({g["gun"]} gün{t})</span></span>')


def _analiz_karti(b: dict) -> str:
    """Bir botun analiz kartı: kazanma, beklenti, risk, güven."""
    n = b["islem_sayisi"]
    if n == 0:
        return (f'<article class="analiz-kart bos-kart"><div class="analiz-ust"><span class="kod">{escape(b["kod"])}</span>'
                f'<span class="alt">Henüz kapanmış işlem yok.</span></div></article>')
    kazanma = yuzde(b["kazanma_orani"])
    basabas = b["basabas_orani"]
    yeterli = (b.get("kayip_sayisi") or 0) >= 5
    if basabas is None or not yeterli or b["kazanma_orani"] is None:
        k_sinif = "notr"
    else:
        k_sinif = "arti" if b["kazanma_orani"] >= basabas else "eksi"
    basabas_metni = (f"başa baş {yuzde(basabas)}" if basabas is not None and yeterli
                     else "başa baş için en az 5 kayıp gerekir")
    islem_basi = b["net_tutar"] / n if n else None
    oran = b.get("kayip_kazanc_orani")
    oran_metni = (f"Bir ortalama kayıp {sayi(oran, 1)} ortalama kazancı siler."
                  if oran is not None else "")
    seri = b.get("en_uzun_kayip_serisi") or 0
    return f"""<article class="analiz-kart">
<div class="analiz-ust"><span class="kod">{escape(b["kod"])}</span>{_guven_rozeti(b)}</div>
<dl class="olcu analiz-olcu">
<div><dt>Kazanma</dt><dd class="{k_sinif}">{kazanma}<span class="alt">{escape(basabas_metni)}</span></dd></div>
<div><dt>İşlem başına</dt><dd class="{_isaret_sinifi(islem_basi)}">{isaretli(islem_basi, 3)}
<span class="alt">USDT · {isaretli_yuzde(b["net_beklenti"], 3)}</span></dd></div>
<div><dt>Ort. kazanç / kayıp</dt><dd><span class="arti">{isaretli(b.get("ort_kazanc_usdt"))}</span> /
<span class="eksi">{isaretli(b.get("ort_kayip_usdt"))}</span><span class="alt">USDT</span></dd></div>
<div><dt>En kötü işlem</dt><dd class="eksi">{isaretli(b.get("en_buyuk_kayip_usdt"))}<span class="alt">USDT</span></dd></div>
<div><dt>En uzun kayıp serisi</dt><dd>{seri} işlem<span class="alt">{isaretli(b.get("en_uzun_kayip_toplami")) if seri else "–"} USDT</span></dd></div>
<div><dt>Kâr faktörü</dt><dd>{sayi(b["kar_faktoru"]) if b["kar_faktoru"] not in (None, float("inf")) else "–"}<span class="alt">{n} işlem</span></dd></div>
</dl>
{f'<p class="alt">{escape(oran_metni)}</p>' if oran_metni else ""}
</article>"""


def _analiz_ekrani(ozet: dict) -> str:
    botlar = ozet["botlar"]
    if not botlar:
        return ('<section id="analiz" class="ekran"><h2 class="ekran-baslik">Analiz</h2>'
                '<p class="bos">Henüz bot yok.</p></section>')

    sirali = sorted(botlar, key=lambda b: b["net_tutar"], reverse=True)
    en_buyuk = max((abs(b["net_tutar"]) for b in sirali), default=0.0)
    net_grafik = _yatay_cubuklar(
        [(b["kod"], b["net_tutar"], _isaret_sinifi(b["net_tutar"]), isaretli(b["net_tutar"])) for b in sirali],
        en_buyuk)
    artida = sum(1 for b in botlar if b["net_tutar"] > 0)
    toplam = sum(b["net_tutar"] for b in botlar)

    kartlar = "".join(_analiz_karti(b) for b in botlar)

    neden_satirlar = []
    for b in botlar:
        sayac: dict[str, int] = {}
        for neden, adet in (b.get("nedenler") or {}).items():
            ad = NEDEN_ADLARI.get(neden, _ilk_buyuk(str(neden)))
            sayac[ad] = sayac.get(ad, 0) + adet
        if not sayac:
            parca = '<span class="alt">henüz kapanmış işlem yok</span>'
        else:
            sira = [a for a in NEDEN_SIRASI if a in sayac] + sorted(a for a in sayac if a not in NEDEN_SIRASI)
            parca = " · ".join(f"{escape(a)} {sayac[a]}" for a in sira)
        neden_satirlar.append(f'<li><span class="kriter-ad">{escape(b["kod"])}</span>'
                              f'<span class="analiz-not">{parca}</span></li>')
    nedenler = '<ul class="analiz-liste">' + "".join(neden_satirlar) + "</ul>"

    sureli = sorted((b for b in botlar if b.get("ort_sure_dakika")), key=lambda b: b["ort_sure_dakika"], reverse=True)
    if sureli:
        sure_grafik = _yatay_cubuklar(
            [(b["kod"], b["ort_sure_dakika"], "notr", _sure(b["ort_sure_dakika"])) for b in sureli],
            sureli[0]["ort_sure_dakika"], tek_yon=True)
    else:
        sure_grafik = '<p class="bos">Henüz kapanmış işlem yok.</p>'

    # Coin bazında (bütün botlar birlikte)
    birlesik: dict[str, dict] = {}
    for b in botlar:
        for r in b.get("pariteler") or []:
            d = birlesik.setdefault(r["parite"], {"islem": 0, "kazanan": 0.0, "net": 0.0})
            d["islem"] += r["islem"]
            d["kazanan"] += r["kazanma_orani"] / 100.0 * r["islem"]
            d["net"] += r["net_tutar"]
    if birlesik:
        coinler = sorted(birlesik.items(), key=lambda kv: kv[1]["net"], reverse=True)
        en_iyi = coinler[0]
        pay = (en_iyi[1]["net"] / toplam * 100.0) if toplam > 0 and en_iyi[1]["net"] > 0 else None
        pay_metni = (f"Toplam artının %{sayi(pay, 0)} kadarı tek coinden ({_parite(en_iyi[0])})."
                     if pay is not None else "")
        en_coin = max(abs(v["net"]) for _, v in coinler) or 1.0
        coin_grafik = _yatay_cubuklar(
            [(str(p).split(":", 1)[0], v["net"], _isaret_sinifi(v["net"]),
              f'{isaretli(v["net"])}<span class="alt"> {v["islem"]} işlem</span>') for p, v in coinler],
            en_coin)
    else:
        pay_metni, coin_grafik = "", '<p class="bos">Henüz kapanmış işlem yok.</p>'

    return f"""<section id="analiz" class="ekran">
<h2 class="ekran-baslik">Analiz</h2>
<p class="ekran-ozet">{len(botlar)} bot · {artida} tanesi artıda · toplam <span class="{_isaret_sinifi(toplam)}">{isaretli(toplam)} USDT</span></p>
<details class="aciklama-kutu"><summary>Bu ekran ne gösteriyor?</summary>
<p>Ölçümler yalnız sanal işlemlerden hesaplanır; hiçbir ayarı değiştirmez. Tutarlar komisyon düşülmüş USDT'dir.
Güven etiketi, günlük sonuçların şanstan ayırt edilip edilemediğini söyler (gün bazında t ≥ 2,5 belirgin sayılır).
Az veriyle yüksek kazanma oranı yanıltabilir: bir stop birçok küçük kazancı silebilir.</p></details>
<div class="kose kart">
<h3>Bot başına net sonuç</h3>
{net_grafik}
</div>
<h3>Botların karnesi</h3>
<div class="analiz-kartlar">{kartlar}</div>
<div class="kose kart">
<h3>Coin bazında</h3>
{f'<p class="alt">{pay_metni}</p>' if pay_metni else ""}
{coin_grafik}
</div>
<div class="kose kart">
<h3>Çıkış nedenleri</h3>
{nedenler}
</div>
<div class="kose kart">
<h3>Ortalama işlem süresi</h3>
{sure_grafik}
</div>
</section>"""


# --------------------------------------------------------------------------
# Dersler ekranı: stop sonrası izleme
# --------------------------------------------------------------------------


DERS_EN_FAZLA = 16


def _ders_paneli(k: int, bot: dict, dersler: list[dict], saat_dilimi: str) -> str:
    """Bir botun Dersler paneli: izlenen stop sayısı, stop daha geniş olsaydı sonuç, o botun son dersleri."""
    izleme = bot["stop_sonrasi"]
    karar = izleme["karar"]
    adet = izleme["stop_sayisi"]
    yeterli = karar["kod"] != "yetersiz"
    if adet:
        ozet_satir = (f'{adet} stop izlendi; {izleme["hedefi_goren"]} tanesinde fiyat '
                      f'{esik_metni(izleme.get("esik", "hedef"))}.')
    else:
        ozet_satir = "Henüz izlenmiş stop yok."
    notlar = []
    if izleme.get("izlenmeyi_bekleyen"):
        notlar.append(f'{izleme["izlenmeyi_bekleyen"]} stop sırada')
    if izleme.get("izlenemeyen"):
        notlar.append(f'{izleme["izlenemeyen"]} stopun fiyat verisi alınamadı')
    satirlar = "".join(
        f'<tr><td>Stop {carpan_metni(s["carpan"])} kat</td>'
        f'<td>{("%" + carpan_metni(round(s["stop_yuzde"], 1))) if s.get("stop_yuzde") is not None else "–"}</td>'
        f'<td class="secenek-net {_isaret_sinifi(s["fark_tutar"]) if yeterli else "erken"}">'
        f'{isaretli(s["fark_tutar"])} USDT</td></tr>'
        for s in izleme["carpanlar"])
    ders_satirlari = "".join(
        f'<li><span class="islem-zaman">{_tarih_saat(d["zaman"], saat_dilimi)}</span> '
        f'<strong>{escape(str(d.get("ad", "")))}</strong><span class="alt">{escape(str(d.get("metin", "")))}</span></li>'
        for d in dersler[:5])
    return (
        f'<article class="ders-p ders-p-{k} kose">'
        f'<div class="ders-bas"><span class="kod">{escape(bot["kod"])}</span>'
        f'<span class="karar {karar["kod"]}">{KARAR_ADI[karar["kod"]]}</span></div>'
        f'<h4 class="ders-ad">{escape(bot["ad"])}</h4>'
        f'<p class="ders-cumle">{ozet_satir}'
        + (f' <span class="alt">({"; ".join(notlar)})</span>' if notlar else "") + '</p>'
        + (f'<table class="ders-tablo"><thead><tr><th>Stop daha geniş olsaydı</th><th>Yeni stop</th>'
           f'<th>Fark</th></tr></thead><tbody>{satirlar}</tbody></table>' if adet else "")
        + (f'<h5 class="ders-alt">Son dersler</h5><ul class="ders-mini">{ders_satirlari}</ul>' if ders_satirlari else "")
        + "</article>"
    )


def _dersler_ekrani(ozet: dict, saat_dilimi: str) -> str:
    izleme = ozet.get("stop_izleme") or {}
    en_az = izleme.get("en_az_stop", 30)
    botlar = [b for b in ozet["botlar"] if b.get("stop_sonrasi")][:DERS_EN_FAZLA]
    dersler = ozet.get("dersler") or []
    if not botlar:
        return '<section id="dersler" class="ekran"><h2 class="ekran-baslik">Dersler</h2><p class="bos">Bot yok.</p></section>'
    secim = "".join(
        f'<input type="radio" name="ders-bot" id="dr-{k}" class="ders-radyo"{" checked" if k == 0 else ""}>'
        for k in range(len(botlar)))
    etiketler = "".join(f'<label for="dr-{k}">{escape(b["kod"])}</label>' for k, b in enumerate(botlar))
    paneller = "".join(
        _ders_paneli(k, b, [d for d in dersler if d.get("bot") == b["bot"]], saat_dilimi)
        for k, b in enumerate(botlar))
    if not dersler:
        ders_notu = f'<p class="alt">Henüz ders yok. Bir botun {en_az} stopu izlenince ilk karar yazılır.</p>'
    else:
        ders_notu = ""
    son_tur = izleme.get("son_tur")
    tur_notu = f"Son izleme turu: {_tarih_saat(son_tur, saat_dilimi)}." if son_tur else "İzleme henüz ilk turunu tamamlamadı."
    return f"""<section id="dersler" class="ekran">
<h2 class="ekran-baslik">Dersler</h2>
<p class="not">Stop olan işlemler: stop daha geniş olsaydı ne olurdu? Bot seç.</p>
{secim}
<div class="ders-secim" role="group" aria-label="Bot seç">{etiketler}</div>
<div class="ders-paneller">{paneller}</div>
{ders_notu}
<details class="aciklama-kutu"><summary>Nasıl ölçülüyor?</summary>
<p>Stop olan işlem, süresi dolunca izlenir. Süre sınırı olmayan botlarda girişten 3 gün, stoptan en az 1 gün sonra
sonuç görünür; o anda açık kalan seçenek son fiyattan sayılır. {tur_notu} Karar hiçbir ayarı değiştirmez.</p></details>
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


def _kriter_degeri(k: dict) -> str:
    alim, satis = metin_degeri(k["alim"]), metin_degeri(k["satis"])
    deger = alim if alim == satis else f"{alim} / {satis}"
    birim = f' <span class="alt">{escape(k["birim"])}</span>' if k["birim"] else ""
    return f"{escape(deger)}{birim}"


def _kriterler_ekrani() -> str:
    """Ahmet Özel stratejisinin kriterleri; değerler kural dosyalarından okunur (salt okunur)."""
    try:
        liste = kriter_listesi()
    except (OSError, ValueError, KeyError, StopIteration):
        liste = []
    gruplar: dict[str, list] = {}
    for k in liste:
        gruplar.setdefault(k["grup"], []).append(k)
    bolumler = []
    for grup, ogeler in gruplar.items():
        satirlar = "".join(
            f'<li><span class="kriter-ad">{escape(k["ad"])}<span class="alt">{escape(k["aciklama"])}</span></span>'
            f'<span class="kriter-deger">{_kriter_degeri(k)}</span></li>'
            for k in ogeler
        )
        bolumler.append(f'<h3>{escape(grup)}</h3><ul class="kriter-listesi">{satirlar}</ul>')
    icerik = "".join(bolumler) or '<p class="not">Kriterler okunamadı.</p>'
    return f"""<section id="kriterler" class="ekran">
<h2 class="ekran-baslik">Bot kriterleri</h2>
<p class="not">Ahmet Özel stratejisinin (alım ve açığa satış) bütün sayıları. Değerler sunucudaki kural
dosyalarından okunur; burada gördüğün, sınamanın gerçekte kullandığıdır. İki değer yazıyorsa ilki alım,
ikincisi açığa satış içindir. Bu strateji henüz canlı bot değil; panel sınamasında sınanıyor.</p>
<p><a class="kriter-dugme" href="{escape(DUZENLEME_ADRESI)}">Değerleri değiştir</a></p>
<p><a class="kriter-dugme" href="/ayar">Kriter ayarı: geçmişe sar ve dene</a></p>
<p class="not">Düğme claude.ai'deki Bot Kriterleri sayfasını açar: satıra dokun, yeni değeri yaz, İsteği kaydet'e
bas, sonra Claude'a "kriterleri değiştirdim" yaz. Bu ekran yalnız gösterir; buradan değişiklik yapılmaz.
Her değişiklik yeni bir deneme sayılır.</p>
{icerik}
</section>"""


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

.rapor-radyo,.ders-radyo{position:absolute;opacity:0;pointer-events:none}
.ders-secim{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.ders-secim label{padding:7px 14px;border:1px solid var(--cizgi);color:var(--soluk);font-weight:600;font-size:.875rem;cursor:pointer;background:var(--yuzey);border-radius:999px}
DERS_SECILI{color:var(--holo);border-color:var(--holo);background:rgba(95,212,255,.14)}
.ders-paneller .ders-p{display:none}
DERS_GOSTER{display:block}
.ders-bas{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ders-ad{margin:8px 0 0;font:700 1rem/1.3 var(--rakam);letter-spacing:.02em}
.ders-tablo{width:100%;border-collapse:collapse;font-size:.8125rem;margin:10px 0}
.ders-tablo th,.ders-tablo td{padding:6px 4px;text-align:left;border-bottom:1px solid var(--cizgi)}
.ders-alt{margin:14px 0 4px;font-size:.8125rem;color:var(--soluk)}
.ders-mini{list-style:none;margin:0;padding:0}
.ders-mini li{padding:6px 0;border-bottom:1px solid var(--cizgi);font-size:.8125rem;display:flex;flex-direction:column;gap:2px}
.rapor-secim{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 6px}
.rapor-secim label{padding:7px 12px;border:1px solid var(--cizgi);color:var(--soluk);font-weight:600;
font-size:.875rem;cursor:pointer;background:var(--cam)}
RAPOR_SECILI{color:var(--holo);border-color:var(--holo);background:rgba(95,212,255,.14)}
RAPOR_ODAK{outline:2px solid var(--altin);outline-offset:2px}
.rapor-panel{display:none}
RAPOR_GOSTER{display:block}
.rapor-panel h3{margin-top:18px}
.g-grafik{display:block;width:100%;height:auto;max-width:820px;overflow:visible;margin-top:6px}
.g-cubuk{fill:currentColor}
.g-cubuk.notr{color:var(--soluk)}
.cizelge.gunluk td{font:700 1rem/1.3 var(--rakam);white-space:nowrap}
.cizelge.gunluk td .alt{font-family:var(--govde);font-weight:400}
.cizelge.gunluk th[scope=row]{font-weight:600;white-space:nowrap}

.kriter-listesi{list-style:none;margin:0;padding:0;border-top:1px solid var(--cizgi);max-width:760px}
.kriter-listesi li{display:flex;gap:16px;justify-content:space-between;align-items:baseline;padding:12px 0;
border-bottom:1px solid var(--cizgi)}
.kriter-ad{min-width:0;font-weight:600}
.kriter-ad .alt{display:block;font-weight:400;color:var(--soluk);font-size:.875rem;margin-top:2px}
.kriter-deger{font:700 1.125rem/1.2 var(--rakam);white-space:nowrap;font-variant-numeric:tabular-nums}
.kriter-deger .alt{display:inline;font-size:.8125rem;color:var(--soluk);font-weight:600}
#kriterler a{color:var(--holo)}
.kriter-dugme{display:inline-flex;align-items:center;min-height:44px;padding:0 20px;border:1px solid var(--holo);
font:700 1rem/1 var(--rakam);letter-spacing:.04em;text-decoration:none;background:rgba(95,212,255,.10)}
.gezinti{position:fixed;left:0;right:0;bottom:0;z-index:4;display:flex;overflow-x:auto;scrollbar-width:none;
background:rgba(4,9,17,.9);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);
border-top:1px solid var(--cizgi);padding-bottom:env(safe-area-inset-bottom)}
.gezinti a{flex:1 0 auto;display:flex;align-items:center;justify-content:center;min-height:54px;padding:6px 4px;
color:var(--soluk);text-decoration:none;font-size:.75rem;font-weight:600;border-top:2px solid transparent;margin-top:-1px;
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

/* Premium katman (6 Kasım 2026): yalnız görünüm; ekran yapısı ve sınıf adları aynı. */
:root{--gece:#070a12;--yuzey:rgba(255,255,255,.035);--yuzey2:rgba(255,255,255,.06);
--holo:#d6b779;--cizgi:rgba(255,255,255,.09);--cam:rgba(255,255,255,.03);
--buz:#f2ede2;--soluk:#9a9fae;--altin:#e8c36a;--arti:#4fd1a1;--eksi:#f0706b;
--yaricap:18px;--golge:0 18px 48px -20px rgba(0,0,0,.75),0 1px 0 rgba(255,255,255,.05) inset;
--rakam:"Inter","SF Pro Display","Avenir Next","Segoe UI",system-ui,sans-serif}
html{background:radial-gradient(900px 520px at 78% -120px,rgba(214,183,121,.16) 0,rgba(7,10,18,0) 70%),
radial-gradient(760px 520px at 0% 8%,rgba(79,140,209,.12) 0,rgba(7,10,18,0) 70%) no-repeat var(--gece)}
body::before{opacity:.22;background:repeating-linear-gradient(0deg,rgba(255,255,255,.06) 0 1px,transparent 1px 64px),
repeating-linear-gradient(90deg,rgba(255,255,255,.06) 0 1px,transparent 1px 64px)}
::selection{background:rgba(214,183,121,.35)}
.marka{font-weight:600;letter-spacing:.42em;font-size:.9375rem;color:var(--holo);text-shadow:none}
.marka::before{content:"";display:inline-block;width:9px;height:9px;margin-right:12px;border-radius:50%;
background:var(--holo);box-shadow:0 0 0 4px rgba(214,183,121,.16)}
.guncelleme{font-size:.75rem;letter-spacing:.02em}
h1,h2,h3,h4{font-weight:650;letter-spacing:-.015em}
h2.ekran-baslik{font-weight:600;letter-spacing:-.025em}
.selam-ust{color:var(--holo);letter-spacing:.14em;text-transform:uppercase;font-size:.75rem;font-weight:600}
.kose,.kart,.ders-kart,.okumalar{background:linear-gradient(160deg,var(--yuzey2),var(--yuzey));
border:1px solid var(--cizgi);border-radius:var(--yaricap);box-shadow:var(--golge);
-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px)}
.okumalar{overflow:hidden}
.kart.secili{border-color:rgba(214,183,121,.65);box-shadow:var(--golge),0 0 0 1px rgba(214,183,121,.4)}
.kod{border-radius:8px;border-color:rgba(214,183,121,.28);background:rgba(214,183,121,.09);color:var(--holo)}
.serit{border:1px solid var(--cizgi);border-left:3px solid var(--altin);border-radius:12px;background:var(--yuzey)}
.serit.ders{border-left-color:var(--holo)}
.bos{border-radius:14px;border-color:var(--cizgi);background:var(--yuzey)}
.sira{border-radius:12px;transition:background .2s}
.sira:hover{background:var(--yuzey2)}
.cubuk{height:5px;border-radius:5px;overflow:hidden}
.cubuk i{box-shadow:none}
.isaret,.kriter-dugme,.rapor-secim label{border-radius:999px}
.kriter-dugme{background:linear-gradient(180deg,rgba(214,183,121,.22),rgba(214,183,121,.08));
border-color:rgba(214,183,121,.5);color:var(--buz)}
.rapor-secim label{background:var(--yuzey);transition:background .2s,color .2s}
.r-bot,.r-cizgi,.s-cizgi,.r-cekirdek{filter:none}
.r-cekirdek{fill:rgba(255,255,255,.03);stroke:rgba(214,183,121,.5)}
.r-ince,.r-olcek,.r-nokta{stroke:var(--holo)}
.gun{border-radius:5px}
.gun.gecti{background:var(--holo);border-color:var(--holo);box-shadow:none}
.gun.bugun{box-shadow:0 0 0 3px rgba(232,195,106,.2)}
.g-cubuk{rx:3}
.cizelge thead th{letter-spacing:.06em;text-transform:uppercase;font-weight:600;font-size:.6875rem}
.kopuk-uyari{background:#2b2108;border-bottom:1px solid rgba(232,195,106,.35)}
.yatay{list-style:none;margin:12px 0 0;padding:0}
.yatay li{display:grid;grid-template-columns:minmax(64px,140px) minmax(0,1fr) auto;gap:10px;align-items:center;
padding:8px 0;border-bottom:1px solid var(--cizgi)}
.yatay .kriter-ad{font-weight:600}
.cubuk-ic{position:relative;height:10px;background:linear-gradient(var(--soluk),var(--soluk)) 50% 0/1px 100% no-repeat,
var(--yuzey);border-radius:6px;overflow:hidden}
.cubuk-ic i{position:absolute;top:0;bottom:0;background:currentColor;border-radius:6px;opacity:.9}
.cubuk-ic i.arti{background:var(--arti)}.cubuk-ic i.eksi{background:var(--eksi)}.cubuk-ic i.notr{background:var(--holo)}
.yatay .kriter-deger{font:700 1rem var(--rakam);white-space:nowrap}
.analiz-liste{list-style:none;margin:12px 0 0;padding:0}
.analiz-liste li{display:grid;grid-template-columns:minmax(64px,140px) minmax(0,1fr);gap:10px;padding:8px 0;
border-bottom:1px solid var(--cizgi)}
.analiz-not{font-size:.875rem;color:var(--buz)}
.analiz-liste .kriter-ad{font-weight:600}
.gezinti{background:rgba(10,13,22,.82);-webkit-backdrop-filter:blur(22px) saturate(1.4);
backdrop-filter:blur(22px) saturate(1.4);border-top:1px solid var(--cizgi)}
.gezinti a{letter-spacing:.03em}
EKRAN_SECILI{color:var(--holo);border-top-color:var(--holo);
background:linear-gradient(rgba(214,183,121,.16),rgba(214,183,121,0))}
/* Uzman toplantısı kararları (6 Kasım 2026) */
:root{--uyari:#ff9f43;--r-kucuk:8px;--r-orta:12px;--r-buyuk:20px}
.kose,.kart,.ders-kart,.okumalar{-webkit-backdrop-filter:none;backdrop-filter:none;border-radius:var(--r-buyuk);
box-shadow:0 12px 32px -16px rgba(0,0,0,.6),0 1px 0 rgba(255,255,255,.05) inset}
.kod{border-radius:var(--r-kucuk)}
.serit,.bos,.sira{border-radius:var(--r-orta)}
.ekran{scroll-margin-top:96px}
.r-bot.sessiz,.r-etiket.sessiz{color:var(--uyari)}
.uyari-serit{margin:12px 0 4px;padding:12px 14px;border-radius:var(--r-orta);background:rgba(255,159,67,.12);
border:1px solid rgba(255,159,67,.3);border-left:3px solid var(--uyari);color:#ffd2a8;font:600 15px/1.4 var(--govde)}
.bot-cumlesi{margin:8px 0 0;color:var(--soluk);font-size:.9375rem}
.serit.risk{border-left-color:var(--eksi);background:rgba(240,112,107,.07)}
.serit.risk strong{color:var(--buz)}
.ekran-ozet{margin:0 0 14px;font:650 1.125rem/1.35 var(--rakam)}
.aciklama-kutu{margin:0 0 16px;max-width:70ch}
.aciklama-kutu summary{display:flex;align-items:center;min-height:44px;cursor:pointer;color:var(--holo);font-size:.875rem;
font-weight:600;list-style:none}
.aciklama-kutu summary::-webkit-details-marker{display:none}
.aciklama-kutu summary::before{content:"+";display:inline-block;width:1.2em;font-weight:700}
.aciklama-kutu[open] summary::before{content:"−"}
.aciklama-kutu p{margin:0 0 8px;color:var(--soluk);font-size:.875rem}
.guven{display:inline-flex;align-items:center;gap:2px;padding:3px 10px;border-radius:999px;font-size:.75rem;font-weight:700;
border:1px solid currentColor;background:rgba(255,255,255,.03)}
.guven.notr{color:var(--soluk)}.guven-alt{font-weight:500;opacity:.8}
.kart-guven{margin-top:8px}
.analiz-kartlar{display:grid;gap:14px;margin:8px 0 18px}
.analiz-kart{padding:14px 16px;border:1px solid var(--cizgi);border-radius:var(--r-buyuk);
background:linear-gradient(160deg,var(--yuzey2),var(--yuzey))}
.analiz-ust{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.analiz-olcu{grid-template-columns:repeat(2,minmax(0,1fr));margin-top:10px}
.analiz-olcu div{border-top:1px solid var(--cizgi);padding:9px 8px 8px 0}
.analiz-olcu dd .alt{display:block}
.cubuk-ic.tek{background:var(--yuzey)}
.islem-sure .alt.eksi{color:var(--eksi)}
@media (max-width:639px){
.gezinti{display:grid;grid-template-columns:repeat(EKRAN_SAYISI,1fr);overflow:visible}
.gezinti a{min-width:0;padding:6px 1px;font-size:11px;letter-spacing:0}
}
@media (min-width:640px){.analiz-olcu{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (min-width:900px){.analiz-kartlar{grid-template-columns:1fr 1fr}}
@media (min-width:900px){
.gezinti{border-radius:999px;overflow:hidden;box-shadow:0 14px 40px -12px rgba(0,0,0,.8);top:16px}
.sayfa{padding-top:84px}
}
.ig-panel{display:none}
IG_GOSTER{display:block}
IG_SECILI{color:var(--holo);border-color:var(--holo);background:rgba(214,183,121,.14)}
.ig-liste{list-style:none;margin:0;padding:0;border-top:1px solid var(--cizgi)}
.ig-satir{display:grid;grid-template-columns:4.8em minmax(0,1fr) auto 14px;gap:4px 10px;align-items:center;padding:12px 2px;
min-height:56px;border-bottom:1px solid var(--cizgi);color:inherit;text-decoration:none}
.ig-satir:hover,.ig-satir:focus-visible{background:var(--yuzey2)}
.ig-sonuc{font:700 1.0625rem/1.25 var(--rakam);text-align:right;white-space:nowrap}
.ig-sonuc .alt{font-family:var(--govde);font-weight:500}
.ig-ok{color:var(--holo);font-size:1.25rem;font-weight:700}
.ig-panel h3{margin-top:16px}
/* Başlık, menü ve grafikler (6 Kasım 2026, 2. tur) */
.baslik-cubugu{position:sticky;top:0;z-index:6;display:flex;align-items:center;gap:10px;flex-wrap:nowrap;
margin:-16px -16px 0;padding:10px 16px;background:rgba(10,13,22,.86);-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);
border-bottom:1px solid var(--cizgi)}
.baslik-cubugu .marka{text-decoration:none;white-space:nowrap;font-size:.875rem;letter-spacing:.32em}
.canli{display:inline-flex;align-items:center;gap:6px;margin-left:auto;padding:5px 10px;border-radius:999px;
border:1px solid var(--cizgi);background:var(--yuzey);font-size:.75rem;font-weight:600;white-space:nowrap;color:var(--buz)}
.canli i{width:7px;height:7px;border-radius:50%;background:var(--arti);box-shadow:0 0 0 3px rgba(79,209,161,.18)}
.canli.uyari i{background:var(--uyari);box-shadow:0 0 0 3px rgba(255,159,67,.2)}
.canli b{font-weight:700}
.menu{position:relative}
.menu summary{display:flex;align-items:center;justify-content:center;min-height:40px;min-width:64px;padding:0 14px;border-radius:999px;
border:1px solid rgba(214,183,121,.45);background:rgba(214,183,121,.1);color:var(--holo);font-weight:700;font-size:.875rem;
cursor:pointer;list-style:none}
.menu summary::-webkit-details-marker{display:none}
.menu summary::after{content:"";width:7px;height:7px;margin-left:8px;border-right:2px solid currentColor;border-bottom:2px solid currentColor;
transform:translateY(-2px) rotate(45deg);transition:transform .2s}
.menu[open] summary::after{transform:translateY(2px) rotate(-135deg)}
.menu-liste{position:absolute;right:0;top:calc(100% + 8px);width:min(340px,calc(100vw - 32px));display:grid;grid-template-columns:1fr 1fr;
gap:6px;padding:8px;border-radius:var(--r-buyuk);border:1px solid var(--cizgi);background:#0d111c;
box-shadow:0 24px 48px -16px rgba(0,0,0,.85)}
.menu-liste a{display:flex;flex-direction:column;gap:2px;min-height:56px;justify-content:center;padding:8px 12px;border-radius:var(--r-orta);
text-decoration:none;color:var(--buz);border:1px solid transparent}
.menu-liste a:hover,.menu-liste a:focus-visible{background:var(--yuzey2)}
.menu-liste a[aria-current]{border-color:rgba(214,183,121,.5);background:rgba(214,183,121,.1)}
.menu-ad{font-weight:700;font-size:.9375rem}.menu-alt{font-size:.75rem;color:var(--soluk);line-height:1.3}
p.guncelleme{margin:10px 0 0;font-size:.75rem;color:var(--soluk)}
.g-svg{display:block;width:100%;height:auto;margin-top:10px;overflow:visible}
.g-izgara{stroke:rgba(255,255,255,.07);stroke-width:1}
.g-sifir{stroke:var(--soluk);stroke-width:1;stroke-dasharray:4 4;opacity:.8}
.g-eksen{fill:var(--soluk);font:500 12px var(--govde)}
.g-etiket{fill:var(--buz);font:700 12px var(--govde)}
.g-kartlar{display:grid;gap:16px}
.g-cizgi,.g-izgara,.g-sifir{vector-effect:non-scaling-stroke}
@media (min-width:900px){.g-kartlar{grid-template-columns:1fr 1fr}.g-eksen,.g-etiket{font-size:10px}}
.g-cizgi{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.g-cizgi.eksi{stroke:var(--eksi)}
.g-uc{stroke:#0d111c;stroke-width:2}.g-uc.eksi-dolgu{fill:var(--eksi)}
.g-alan-eksi{fill:rgba(240,112,107,.18)}
.g-cubuk.arti{fill:var(--arti)}.g-cubuk.eksi{fill:var(--eksi)}.g-cubuk.notr{fill:var(--soluk)}
.g-nokta{stroke:#0d111c;stroke-width:1;opacity:.85}.g-nokta.arti{fill:var(--arti)}.g-nokta.eksi{fill:var(--eksi)}.g-nokta.notr{fill:var(--soluk)}
.g-gosterge{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:8px;font-size:.8125rem;color:var(--buz)}
.g-gosterge-oge{display:inline-flex;align-items:center;gap:6px}
.g-gosterge-oge i{width:14px;height:3px;border-radius:2px}
.g-not{margin:10px 0 0;font-size:.8125rem;color:var(--soluk);max-width:70ch}
.g-not strong{font-weight:700}
.baslik-cubugu{min-width:0;max-width:100vw}
@media (max-width:639px){.gezinti{grid-template-columns:repeat(ALT_SAYISI,1fr)}.gezinti a{font-size:12px}
.baslik-cubugu{gap:8px}.baslik-cubugu .marka{font-size:.75rem;letter-spacing:.18em}
.baslik-cubugu .marka::before{margin-right:8px}
.canli{min-width:0;flex:0 1 auto;overflow:hidden;text-overflow:ellipsis;padding:5px 8px}
.menu summary{min-width:0;padding:0 12px}
.menu-liste{position:fixed;left:16px;right:16px;top:62px;width:auto}}
@media (min-width:900px){
.baslik-cubugu{margin:-84px -24px 0;padding:12px 24px}
.gezinti{display:none}
.sayfa{padding-top:84px}
}
"""
STIL = (
    STIL.replace("KOSE", _KOSE)
    .replace("EKRAN_GOSTER", ",".join(f'.sekmeli[data-ekran="{k}"] #{k}' for k, _ in EKRANLAR))
    .replace("EKRAN_SECILI", ",".join(f'.sekmeli[data-ekran="{k}"] .gezinti a[href="#{k}"]' for k, _ in EKRANLAR))
    .replace("EKRAN_SAYISI", str(len(EKRANLAR)))
    .replace("ALT_SAYISI", str(len(ALT_CUBUK)))
    .replace("IG_GOSTER", ",".join(f"#ig-{k}:checked~.ig-paneller .ig-p-{k}" for k in range(IG_EN_FAZLA)))
    .replace("IG_SECILI", ",".join(f"#ig-{k}:checked~.ig-secim label[for=ig-{k}]" for k in range(IG_EN_FAZLA)))
    .replace("RAPOR_SECILI", ",".join(f"#rb-{k}:checked~.rapor-secim label[for=rb-{k}]" for k in range(RAPOR_EN_FAZLA)))
    .replace("RAPOR_ODAK", ",".join(f"#rb-{k}:focus-visible~.rapor-secim label[for=rb-{k}]" for k in range(RAPOR_EN_FAZLA)))
    .replace("RAPOR_GOSTER", ",".join(f"#rb-{k}:checked~.rapor-paneller .rp-{k}" for k in range(RAPOR_EN_FAZLA)))
    .replace("DERS_SECILI", ",".join(f"#dr-{k}:checked~.ders-secim label[for=dr-{k}]" for k in range(DERS_EN_FAZLA)))
    .replace("DERS_GOSTER", ",".join(f"#dr-{k}:checked~.ders-paneller .ders-p-{k}" for k in range(DERS_EN_FAZLA)))
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
var m=document.querySelector('details.menu');if(m)m.removeAttribute('open');
var b=document.querySelectorAll('.gezinti a,.menu-liste a');
for(var i=0;i<b.length;i++){if(b[i].getAttribute('href')==='#'+ekran)b[i].setAttribute('aria-current','page');else b[i].removeAttribute('aria-current');}
var eski=document.querySelector('.secili');if(eski)eski.classList.remove('secili');
if(hedef&&hedef.id!==ekran){hedef.classList.add('secili');if(kaydir)hedef.scrollIntoView();}
else if(kaydir)window.scrollTo(0,0);
}
var suruyor=false,sonBasari=new Date();
function saat(t){return ('0'+t.getHours()).slice(-2)+':'+('0'+t.getMinutes()).slice(-2);}
function kopuk(metin){var u=document.querySelector('.kopuk-uyari');
if(u)u.textContent=metin+' Ekrandaki sayılar '+saat(sonBasari)+' güncellemesinden.';kok.classList.add('kopuk');}
function yenile(){
if(suruyor||document.hidden)return;suruyor=true;
var iptal=window.AbortController?new AbortController():null,sure=setTimeout(function(){if(iptal)iptal.abort();},15000);
fetch(location.pathname,{cache:'no-cache',signal:iptal?iptal.signal:undefined}).then(function(y){
if(!y.ok)throw y.status;return y.text();}).then(function(m){
var yeni=new DOMParser().parseFromString(m,'text/html').getElementById('govde');
if(!yeni)throw 0;
kok.style.setProperty('--gecen','-'+(performance.now()/1000).toFixed(1)+'s');
kok.classList.add('acildi');
var r=document.querySelectorAll('.rapor-radyo:checked,.ders-radyo:checked'),rid=[];for(var j=0;j<r.length;j++)rid.push(r[j].id);
govde.innerHTML=yeni.innerHTML;
for(var j=0;j<rid.length;j++){var s=document.getElementById(rid[j]);if(s)s.checked=true;}
kok.classList.remove('kopuk');sonBasari=new Date();
goster(false);
}).catch(function(h){
kopuk(typeof h==='number'&&h>=500?'Sunucu çalışıyor ama özet çıkarılamadı.':(typeof h==='number'&&h===401?'Oturum süresi doldu; sayfayı yenile.':'Sunucuya ulaşılamıyor.'));
}).then(function(){clearTimeout(sure);suruyor=false;});
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

    adlar = dict(EKRANLAR)
    gezinti = "".join(
        f'<a href="#{kimlik}">{GEZINTI_ADLARI.get(kimlik, adlar[kimlik])}</a>' for kimlik in ALT_CUBUK if kimlik in adlar
    )
    menu = "".join(
        f'<a href="#{kimlik}"><span class="menu-ad">{ad}</span>'
        f'<span class="menu-alt">{MENU_ACIKLAMA.get(kimlik, "")}</span></a>'
        for kimlik, ad in EKRANLAR
    ) + ('<a href="/ayar"><span class="menu-ad">Kriter ayarı</span>'
         '<span class="menu-alt">Geçmişe sar, kriterleri dene</span></a>' if yenile_saniye else "")
    t = ozet["toplam"]
    canli_sinif = "uyari" if t["calisan_bot"] < t["bot_sayisi"] else "arti"

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
<header class="ust baslik-cubugu">
<a class="marka" href="#ana">KARABASAN</a>
<span class="canli {canli_sinif}" title="Çalışan bot ve toplam sanal sonuç (USDT)"><i></i>{t["calisan_bot"]}/{t["bot_sayisi"]} · <b class="{_isaret_sinifi(t["net_tutar"])}">{isaretli(t["net_tutar"])}</b></span>
<details class="menu"><summary>Menü</summary><nav class="menu-liste" aria-label="Bütün ekranlar">{menu}</nav></details>
</header>
<p class="guncelleme">Son güncelleme {escape(guncelleme)} · sanal işlem, gerçek para yok</p>
<main>
{_ana_ekran(ozet, saat_dilimi)}
{_botlar_ekrani(ozet)}
{_islemler_ekrani(ozet, saat_dilimi)}
{_islem_grafigi_ekrani(ozet, saat_dilimi)}
{_dersler_ekrani(ozet, saat_dilimi)}
{_rapor_ekrani(ozet, saat_dilimi)}
{_grafikler_ekrani(ozet)}
{_zaman_ekrani(ozet, saat_dilimi)}
{_analiz_ekrani(ozet)}
{_sinav_ekrani(ozet, yenileme_notu)}
{_kriterler_ekrani()}
</main>
</div>
<nav class="gezinti" aria-label="Ekranlar">{gezinti}</nav>
{son}
</body>
</html>
"""
