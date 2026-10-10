"""Sonuç sayfası: karabasan.sonuc özetini tek bir Türkçe HTML sayfasına çevirir.

Dış kaynak (yazı tipi, betik, resim) kullanmaz; sayfa sunucudan tek dosya
olarak gelir. Telefonda da masaüstünde de okunur; açık ve koyu temayı
cihazın ayarından alır.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape

OLCUT_ACIKLAMALARI = [
    "En az 100 sanal işlem yapmış olmak.",
    "Komisyon ve işlem başına ek kayma payı düşüldükten sonra toplam sonucun artıda olması.",
    "Kâr faktörünün (toplam kazanç bölü toplam kayıp) en az 1,3 olması.",
    "En büyük düşüşün sanal bakiyenin %5'ini aşmamış olması.",
    "Dört haftanın en az üçünün artıda kapanması.",
    "Kazanma oranının, zarar etmemek için gereken orandan en az 5 puan yüksek olması.",
    "Sonucun 12 aylık geçmiş testiyle aynı yönde olması.",
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


def _isaret_sinifi(deger) -> str:
    if deger is None or abs(deger) < 0.005:
        return "notr"
    return "arti" if deger > 0 else "eksi"


# --------------------------------------------------------------------------
# Parçalar
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
            f"{kalan} gün kaldı. Aşağıdaki ölçütler ara durumdur; karar 30. günde verilir."
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


def _genel_cumle(ozet: dict) -> str:
    t = ozet["toplam"]
    if ozet["donem"] == "kurulmadi":
        return ""
    calisan = (
        f"{t['bot_sayisi']} bottan {t['calisan_bot']} tanesi çalışıyor."
        if t["calisan_bot"] != t["bot_sayisi"]
        else "On botun hepsi çalışıyor."
    )
    net = t["net_tutar"]
    return (
        f'<p class="genel">{calisan} {t["islem_sayisi"]} işlem kapandı, '
        f'{t["acik_pozisyon"]} pozisyon açık. Toplam sanal sonuç '
        f'<strong class="{_isaret_sinifi(net)}">{isaretli(net)} USDT</strong>.</p>'
    )


def _olcut_isaretleri(bot: dict) -> str:
    if not bot["olcutler"]:
        return '<span class="soluk">sınavda dolar</span>'
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


def _bot_durumu(bot: dict, donem: str) -> str:
    if bot["hata"]:
        ic = f'<span class="durum sorun">kayıt yok</span><span class="alt">{escape(bot["hata"])}</span>'
    elif bot.get("karar") == "gecti":
        ic = '<span class="durum gecti">Geçti</span>'
    elif bot.get("karar") == "kaldi":
        ic = '<span class="durum kaldi">Kaldı</span>'
    elif not bot.get("calisiyor"):
        yas = bot.get("gunluk_yasi_dakika")
        ne_zaman = "hiç kayıt yazmadı" if yas is None else f"son kayıt {_sure(yas)} önce"
        ic = f'<span class="durum sorun">ses yok</span><span class="alt">{ne_zaman}</span>'
    else:
        ic = (
            '<span class="durum">çalışıyor</span>'
            f'<span class="alt">{bot["acik_pozisyon"]} açık pozisyon</span>'
        )
    return f'<span class="durum-ic">{ic}</span>'


def _bot_satiri(bot: dict, donem: str) -> str:
    piyasa = "Spot" if bot["piyasa"] == "spot" else "Vadeli, 1 kat"
    net = bot["net_tutar"]
    hucreler = [
        (
            "Bot",
            f'<span class="bot-kod">{escape(bot["ad"])}</span>'
            f'<span class="alt">{escape(bot["bot"])} · {piyasa}, {_yon(bot["yon"])}</span>',
            "bot",
        ),
        ("İşlem", str(bot["islem_sayisi"]), "sayi"),
        ("Kazanma", yuzde(bot["kazanma_orani"]), "sayi"),
        ("Başabaş", yuzde(bot["basabas_orani"]), "sayi"),
        ("Net (USDT)", f'<span class="{_isaret_sinifi(net)}">{isaretli(net)}</span>', "sayi"),
        ("En büyük düşüş", yuzde(bot["en_buyuk_dusus_yuzde"], 2), "sayi"),
        ("Ölçütler", _olcut_isaretleri(bot), "olcut"),
        ("Durum", _bot_durumu(bot, donem), "durum-hucre"),
    ]
    return "<tr>" + "".join(
        f'<td class="{sinif}" data-etiket="{escape(etiket)}">{icerik}</td>'
        for etiket, icerik, sinif in hucreler
    ) + "</tr>"


def _son_islemler(ozet: dict, saat_dilimi: str) -> str:
    islemler = ozet["son_islemler"]
    if not islemler:
        return '<p class="bos">Henüz kapanmış işlem yok. İlk işlem kapandığında burada görünür.</p>'
    satirlar = []
    for i in islemler:
        satirlar.append(
            "<tr>"
            f'<td data-etiket="Kapanış">{_tarih_saat(i["cikis_zamani"], saat_dilimi)}</td>'
            f'<td data-etiket="Bot">{escape(str(i["bot"]))}</td>'
            f'<td data-etiket="Parite">{escape(str(i["parite"]))}</td>'
            f'<td data-etiket="Yön">{_yon(i["yon"])}</td>'
            f'<td data-etiket="Çıkış nedeni">{escape(str(i["neden"]))}</td>'
            f'<td class="sayi" data-etiket="Net"><span class="{_isaret_sinifi(i["net_yuzde"])}">'
            f'%{isaretli(i["net_yuzde"])}</span></td>'
            "</tr>"
        )
    return (
        '<table class="tablo islemler"><thead><tr><th>Kapanış</th><th>Bot</th><th>Parite</th>'
        '<th>Yön</th><th>Çıkış nedeni</th><th class="sayi">Net</th></tr></thead>'
        f'<tbody>{"".join(satirlar)}</tbody></table>'
    )


STIL = """
:root{--kagit:#eef1f5;--yuzey:#fff;--murekkep:#14213d;--soluk:#5b6780;--cizgi:#cdd5e0;
--vurgu:#3d348b;--arti:#1f7a5c;--eksi:#b3402e;--bekle:#8a6d1b;--arti-zemin:#e2f1ec;--eksi-zemin:#f7e6e2}
@media (prefers-color-scheme:dark){:root{--kagit:#10182b;--yuzey:#172038;--murekkep:#e6eaf2;
--soluk:#9aa6bf;--cizgi:#2b3654;--vurgu:#a9a2f0;--arti:#5cc7a2;--eksi:#f08c7a;--bekle:#d9b95a;
--arti-zemin:#16382f;--eksi-zemin:#43231d}}
*{box-sizing:border-box}
body{margin:0;background:var(--kagit);color:var(--murekkep);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
font-variant-numeric:tabular-nums}
.sayfa{max-width:1120px;margin:0 auto;padding:24px 16px 56px}
.ust{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap;
border-bottom:2px solid var(--murekkep);padding-bottom:10px}
.marka{font:700 1.05rem/1.2 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
letter-spacing:.01em;color:var(--vurgu)}
.guncelleme{color:var(--soluk);font-size:.875rem}
h1{font:700 clamp(1.9rem,6vw,3rem)/1.1 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
margin:28px 0 8px;letter-spacing:-.01em}
.aciklama{max-width:62ch;margin:0 0 20px;font-size:1.0625rem}
.cetvel{display:grid;grid-template-columns:repeat(30,1fr);gap:3px;max-width:720px}
.gun{height:22px;border:1.5px solid var(--cizgi);border-radius:2px;background:transparent}
.gun.hafta-sonu{margin-right:5px}
.gun.gecti{background:var(--vurgu);border-color:var(--vurgu)}
.gun.bugun{border-color:var(--vurgu);border-width:3px}
.cetvel-alt{display:flex;justify-content:space-between;max-width:720px;color:var(--soluk);
font-size:.8125rem;margin-top:4px}
.genel{margin:22px 0 0;max-width:62ch}
h2{font:700 1.375rem/1.2 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;margin:40px 0 12px}
.tablo{width:100%;border-collapse:collapse;background:var(--yuzey);border:1px solid var(--cizgi)}
.tablo th{text-align:left;font-weight:600;font-size:.8125rem;color:var(--soluk);padding:10px 12px;
border-bottom:1px solid var(--cizgi);vertical-align:bottom}
.tablo td{padding:12px;border-bottom:1px solid var(--cizgi);vertical-align:top}
.tablo tr:last-child td{border-bottom:0}
.tablo .sayi{text-align:right;white-space:nowrap}
.bot-kod{font-weight:700;display:block}
.alt{display:block;color:var(--soluk);font-size:.8125rem;line-height:1.35}
.arti{color:var(--arti);font-weight:600}.eksi{color:var(--eksi);font-weight:600}.notr{color:inherit}
.soluk{color:var(--soluk);font-size:.875rem}
.isaretler{display:inline-flex;gap:4px;flex-wrap:nowrap}
.durum-ic{display:block}
.isaret{display:inline-flex;align-items:center;gap:2px;min-width:34px;justify-content:center;
padding:2px 5px;border-radius:3px;font-size:.8125rem;font-weight:700;border:1.5px solid}
.isaret-no{font-weight:500;opacity:.75}
.isaret.saglandi{color:var(--arti);background:var(--arti-zemin);border-color:var(--arti)}
.isaret.saglanmadi{color:var(--eksi);background:var(--eksi-zemin);border-color:var(--eksi)}
.isaret.veri_yok{color:var(--bekle);border-style:dashed;border-color:var(--bekle)}
.durum{font-weight:600;display:block}
.durum.sorun{color:var(--bekle)}.durum.gecti{color:var(--arti)}.durum.kaldi{color:var(--eksi)}
.olcut-listesi{max-width:66ch;padding-left:1.4em;margin:0}
.olcut-listesi li{margin:4px 0}
.anahtar{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0 0;color:var(--soluk);font-size:.875rem}
.anahtar span{display:inline-flex;align-items:center;gap:6px}
.bos{color:var(--soluk);background:var(--yuzey);border:1px dashed var(--cizgi);padding:16px;max-width:62ch}
.not{color:var(--soluk);font-size:.875rem;max-width:70ch;margin:8px 0 0}
a{color:var(--vurgu)}a:focus-visible{outline:3px solid var(--vurgu);outline-offset:2px}
@media (max-width:760px){
.tablo thead{position:absolute;left:-9999px}
.tablo,.tablo tbody,.tablo tr,.tablo td{display:block;width:100%}
.tablo{border:0;background:transparent}
.tablo tr{background:var(--yuzey);border:1px solid var(--cizgi);margin-bottom:12px;padding:6px 0}
.tablo td{border:0;padding:6px 12px;display:flex;justify-content:space-between;gap:16px;text-align:right}
.tablo td::before{content:attr(data-etiket);color:var(--soluk);font-size:.8125rem;text-align:left;flex:none}
.tablo td.bot{display:block;text-align:left;border-bottom:1px solid var(--cizgi);padding-bottom:10px}
.tablo td.bot::before{content:none}
.isaretler{flex-wrap:wrap;justify-content:flex-end}
.tablo .sayi{white-space:normal}
}
"""


def html_uret(ozet: dict, saat_dilimi: str = "Europe/Bucharest", yenile_saniye: int = 60) -> str:
    """Özeti tam bir HTML sayfasına çevirir."""
    baslik, aciklama = _durum_cumlesi(ozet)
    yerel, dilim_adi = yerel_zaman(ozet["uretildi"], saat_dilimi)
    guncelleme = f'{yerel.strftime("%d.%m.%Y %H:%M")} ({dilim_adi})'

    bot_satirlari = "".join(_bot_satiri(b, ozet["donem"]) for b in ozet["botlar"])
    olcutler = "".join(f"<li>{escape(a)}</li>" for a in OLCUT_ACIKLAMALARI)
    komisyon = ozet["komisyon_yuzde"]
    gecmis_notu = (
        ""
        if ozet["gecmis_test_var"]
        else " 12 aylık geçmiş testi henüz çalıştırılmadığı için yedinci ölçüt “veri yok” görünür."
    )

    yenile = f'<meta http-equiv="refresh" content="{int(yenile_saniye)}">' if yenile_saniye else ""
    yenileme_notu = " Sayfa dakikada bir kendini yeniler." if yenile_saniye else ""

    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{yenile}
<meta name="robots" content="noindex">
<title>Karabasan sınav karnesi</title>
<style>{STIL}</style>
</head>
<body>
<div class="sayfa">
<div class="ust">
<span class="marka">Karabasan</span>
<span class="guncelleme">Son güncelleme: {escape(guncelleme)}</span>
</div>

<h1>{escape(baslik)}</h1>
<p class="aciklama">{escape(aciklama)}</p>
{_cetvel(ozet)}
{_genel_cumle(ozet)}

<h2>Botlar</h2>
<table class="tablo botlar">
<thead><tr><th>Bot</th><th class="sayi">İşlem</th><th class="sayi">Kazanma</th>
<th class="sayi">Başabaş</th><th class="sayi">Net (USDT)</th><th class="sayi">En büyük düşüş</th>
<th>Ölçütler</th><th>Durum</th></tr></thead>
<tbody>{bot_satirlari}</tbody>
</table>
<p class="not">Her botun {sayi(ozet["sanal_bakiye"], 0)} USDT sanal bakiyesi var ve işlem başına
{sayi(ozet["islem_tutari"], 0)} USDT kullanıyor. Net sonuç, komisyon düşülmüş sanal kâr ya da zarardır.
Başabaş, zarar etmemek için gereken kazanma oranıdır; kazanma oranı bunun üstünde olmalıdır.</p>

<h2>Yedi ölçüt</h2>
<ol class="olcut-listesi">{olcutler}</ol>
<div class="anahtar">
<span><span class="isaret saglandi">✓</span> sağlanıyor</span>
<span><span class="isaret saglanmadi">✗</span> sağlanmıyor</span>
<span><span class="isaret veri_yok">·</span> veri yok</span>
</div>
<p class="not">Bir bot ancak yedisini birden sağlarsa gerçek para adayı olur.{escape(gecmis_notu)}</p>

<h2>Son kapanan işlemler</h2>
{_son_islemler(ozet, saat_dilimi)}

<h2>Bu sayfa hakkında</h2>
<p class="not">Buradaki bütün işlemler sanaldır; hiçbir emir borsaya gitmez. Komisyon olarak
spot işlemlerde taraf başına {yuzde(komisyon["spot"], 3)}, vadeli işlemlerde
{yuzde(komisyon["vadeli"], 3)} düşülür. Ölçütler hesaplanırken her işlemden ayrıca
{yuzde(ozet["ek_kayma_yuzde"], 2)} kayma payı düşülür, çünkü sanal işlem gerçeğinden biraz
iyimser dolar.{yenileme_notu}</p>
</div>
</body>
</html>
"""

