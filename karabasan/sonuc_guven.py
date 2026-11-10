"""Güven ekranının verisi: sanal sonuçlara ne kadar güvenilebilir? (10 Kasım 2026)

Yalnız okur; hiçbir ayar, kural ya da bot dosyası yazmaz. Yalnız standart kütüphane.

Yeniden kullanılanlar (kopyalanmaz):
- Gün bazında t değeri ve etiketi: botlardaki `guven` alanı (sonuc.guven_etiketi); toplam için
  sonuc.guven_etiketi(sonuc.gunluk_topla(...)).
- Başa baş oranı: botlardaki `basabas_orani` (karne).
- Coin sonuçları: botlardaki `pariteler` (sonuc.parite_ozeti) ve işlemler.
- Sınav işlem eşiği: botların 1. ölçütünün eşiği; yoksa karne.SINAV_ESIKLERI["en_az_islem"].

Not: sonuc.py ve karne.py şu an karne'nin dosya başındaki `import pandas` yüzünden pandas'sız
içe aktarılamaz. Bu modül onları bu yüzden işlev içinde (tembel) içe aktarır; hesapla() yalnız
sonuc.genel_ozet içinden çağrıldığı için o anda ikisi zaten yüklüdür.

Geleceğe bakmamak için: işlemlerden türetilen her sayı yalnız `simdi`ye kadar kapanmış işlemlerle hesaplanır.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

Z95 = 1.959963984540054          # %95 iki yönlü normal kritik değeri
YESIL_EN_AZ_ISLEM = 100          # yeşil rozet için en az işlem (sınav ölçütüyle aynı; aşağıda okunur)
YESIL_EN_FAZLA_P = 0.01          # yeşil rozet için p en fazla bu (t >= 2,5 ile birlikte)
BOT_BASI_OLCU = 4                # bot başına bakılan ölçü: t, kazanma aralığı, coin, en iyi gün
YAKLASIM = ("p değeri gün bazında t değerinden Student t dağılımıyla (serbestlik = gün − 1) hesaplanır; "
            "günlerin birbirinden bağımsız ve kabaca çan eğrisi gibi dağıldığı varsayılır, büyük tek günler "
            "bu varsayımı bozar.")


# --------------------------------------------------------------------------
# Saf istatistik işlevleri
# --------------------------------------------------------------------------

def _betacf(a: float, b: float, x: float) -> float:
    """Eksik beta işlevinin sürekli kesir açılımı (Lentz yöntemi)."""
    kucuk = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > kucuk else kucuk)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > kucuk else kucuk)
        c = 1.0 + aa / c
        c = c if abs(c) > kucuk else kucuk
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > kucuk else kucuk)
        c = 1.0 + aa / c
        c = c if abs(c) > kucuk else kucuk
        degisim = d * c
        h *= degisim
        if abs(degisim - 1.0) < 1e-14:
            break
    return h


def eksik_beta(a: float, b: float, x: float) -> float:
    """Düzenlenmiş eksik beta işlevi I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    on = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return on * _betacf(a, b, x) / a
    return 1.0 - on * _betacf(b, a, 1.0 - x) / b


def p_degeri(t: float | None, serbestlik: float | None) -> float | None:
    """t değerinin iki yönlü p değeri. Serbestlik yoksa (ya da çok büyükse) normal yaklaşım (math.erfc)."""
    if t is None or (isinstance(t, float) and math.isnan(t)):
        return None
    if serbestlik is None or serbestlik > 1e6:
        return math.erfc(abs(t) / math.sqrt(2.0))
    if serbestlik <= 0:
        return None
    return eksik_beta(serbestlik / 2.0, 0.5, serbestlik / (serbestlik + t * t))


def wilson(kazanan: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Kazanma oranı için Wilson güven aralığı, yüzde olarak (alt, üst). n = 0 ise None."""
    if n <= 0:
        return None
    p = kazanan / n
    z2 = z * z
    payda = 1.0 + z2 / n
    merkez = (p + z2 / (2 * n)) / payda
    yari = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / payda
    return (max(0.0, merkez - yari) * 100.0, min(1.0, merkez + yari) * 100.0)


def aralik_konumu(aralik: tuple[float, float] | None, basabas: float | None) -> str:
    """Kazanma aralığı başa baş oranının: 'ustunde', 'icinde', 'altinda' ya da 'veri_yok'."""
    if aralik is None or basabas is None:
        return "veri_yok"
    if aralik[0] > basabas:
        return "ustunde"
    if aralik[1] < basabas:
        return "altinda"
    return "icinde"


def coklu_bakis(bakis: int, esik: float = 0.05) -> float:
    """Hiçbir şeyde kenar yokken bile en az bir ölçünün şans eseri 'anlamlı' çıkma olasılığı (bağımsız varsayımıyla)."""
    return 1.0 - (1.0 - esik) ** max(0, bakis)


def coin_bagimliligi(pariteler: list[dict]) -> dict:
    """En iyi ve en kötü coin çıkarılınca net sonuç (USDT). pariteler: sonuc.parite_ozeti çıktısı."""
    toplam = sum(float(p["net_tutar"]) for p in pariteler)
    if len(pariteler) < 2:
        return {"coin_sayisi": len(pariteler), "toplam": toplam, "en_iyi": None, "en_kotu": None,
                "en_iyisiz": None, "en_kotusuz": None, "tek_coine_bagli": None}
    en_iyi = max(pariteler, key=lambda p: p["net_tutar"])
    en_kotu = min(pariteler, key=lambda p: p["net_tutar"])
    en_iyisiz = toplam - float(en_iyi["net_tutar"])
    return {
        "coin_sayisi": len(pariteler), "toplam": toplam,
        "en_iyi": {"parite": str(en_iyi["parite"]), "net_tutar": float(en_iyi["net_tutar"]), "islem": en_iyi["islem"]},
        "en_kotu": {"parite": str(en_kotu["parite"]), "net_tutar": float(en_kotu["net_tutar"]), "islem": en_kotu["islem"]},
        "en_iyisiz": en_iyisiz,
        "en_kotusuz": toplam - float(en_kotu["net_tutar"]),
        # Artıdaki sonuç en iyi coin çıkınca sıfıra ya da eksiye iniyorsa sonuç tek coine bağlıdır.
        "tek_coine_bagli": toplam > 0 and en_iyisiz <= 0,
    }


def en_iyi_gunsuz(gunluk: list[dict]) -> dict:
    """En iyi gün çıkarılınca net sonuç. gunluk: sonuc.gunluk_ozet çıktısı."""
    if not gunluk:
        return {"en_iyi_gun": None, "en_iyi_gun_net": None, "toplam": 0.0, "kalan": None, "tek_gune_bagli": None}
    en_iyi = max(gunluk, key=lambda g: g["net_tutar"])
    toplam = sum(float(g["net_tutar"]) for g in gunluk)
    kalan = toplam - float(en_iyi["net_tutar"])
    return {"en_iyi_gun": en_iyi["gun"], "en_iyi_gun_net": float(en_iyi["net_tutar"]), "toplam": toplam,
            "kalan": kalan if len(gunluk) > 1 else None,
            "tek_gune_bagli": (toplam > 0 and kalan <= 0) if len(gunluk) > 1 else None}


def islem_hizi(islem_sayisi: int, gecen_gun: float, kalan_gun: float | None, hedef: int) -> dict:
    """Mevcut hızla hedef işlem sayısına kaç günde ulaşılır; sınav bitmeden ulaşılır mı?"""
    eksik = max(0, hedef - islem_sayisi)
    hiz = islem_sayisi / gecen_gun if gecen_gun > 0 else None
    if eksik == 0:
        gerek = 0.0
    elif hiz:
        gerek = eksik / hiz
    else:
        gerek = None
    yetisir = None if kalan_gun is None else (gerek is not None and gerek <= kalan_gun)
    return {"hedef": hedef, "eksik": eksik, "gunluk_hiz": hiz, "gereken_gun": gerek, "yetisir": yetisir}


def hukum(t: float | None, p: float | None, islem: int, hedef: int, konum: str,
          tek_coin: bool | None, tek_gun: bool | None, esik_t: float) -> dict:
    """Tek cümlelik hüküm ve sınıfı. Yeşil (arti) için çıta yüksek: hepsi birden sağlanmalı."""
    if islem == 0:
        return {"metin": "Henüz işlem yok", "sinif": "notr", "kod": "islem_yok"}
    if t is None:
        return {"metin": "Veri az", "sinif": "notr", "kod": "veri_az"}
    if t <= -esik_t:
        return {"metin": "Belirgin eksi", "sinif": "eksi", "kod": "eksi"}
    if (t >= esik_t and p is not None and p <= YESIL_EN_FAZLA_P and islem >= hedef
            and konum == "ustunde" and tek_coin is False and tek_gun is False):
        return {"metin": "Belirgin artı, ama tek dönem", "sinif": "arti", "kod": "arti"}
    if t >= esik_t:
        return {"metin": "Artı görünüyor, ama çıta aşılmadı", "sinif": "uyari", "kod": "zayif_arti"}
    if islem < hedef:
        return {"metin": "Veri az, kanıt yok", "sinif": "notr", "kod": "kanit_yok"}
    return {"metin": "Kanıt yok", "sinif": "notr", "kod": "kanit_yok"}


# --------------------------------------------------------------------------
# Ekranın verisi
# --------------------------------------------------------------------------

def _islem_esigi(botlar: list[dict]) -> int:
    for b in botlar:
        for o in b.get("olcutler") or []:
            if o.get("no") == 1 and isinstance(o.get("esik"), (int, float)):
                return int(o["esik"])
    from . import karne

    return int(karne.SINAV_ESIKLERI["en_az_islem"])


def _gunler(a: datetime, b: datetime) -> float:
    return max(0.0, (b - a) / timedelta(days=1))


def hesapla(baglam: dict) -> dict:
    from . import sonuc

    simdi = baglam["simdi"]
    donem = baglam.get("donem") or {}
    botlar = baglam.get("botlar") or []
    bot_islemleri = baglam.get("bot_islemleri") or {}
    gecmis = baglam.get("gecmis_test") or {}
    hedef = _islem_esigi(botlar)
    esik_t = float(sonuc.GUVEN_ESIGI)

    baslangic, bitis = donem.get("baslangic"), donem.get("bitis")
    sinavda = donem.get("donem") in ("sinav", "bitti") and baslangic is not None
    gecen = _gunler(baslangic, min(simdi, bitis) if bitis else simdi) if sinavda else 0.0
    kalan = _gunler(simdi, bitis) if (sinavda and bitis) else None

    satirlar, tum_gunluk = [], []
    for b in botlar:
        islemler = [i for i in bot_islemleri.get(b.get("kod"), []) if i["cikis_zamani"] <= simdi]
        n = len(islemler)
        kazanan = sum(1 for i in islemler if float(i["net_tutar"]) > 0)
        g = b.get("guven") or {}
        t = g.get("t")
        p = p_degeri(t, (g.get("gun") or 0) - 1) if t is not None else None
        aralik = wilson(kazanan, n)
        konum = aralik_konumu(aralik, b.get("basabas_orani"))
        gunluk = sonuc.gunluk_ozet(islemler)
        tum_gunluk.append(gunluk)
        coin = coin_bagimliligi(sonuc.parite_ozeti(islemler))
        gun = en_iyi_gunsuz(gunluk)
        sanal = b.get("net_beklenti")
        gt = gecmis.get(b.get("bot"))
        satirlar.append({
            "bot": b.get("bot"), "kod": b.get("kod"), "ad": b.get("ad"),
            "islem": n, "kazanan": kazanan, "net_tutar": sum(float(i["net_tutar"]) for i in islemler),
            "t": t, "gun": g.get("gun", 0), "etiket": g.get("etiket"), "etiket_sinif": g.get("sinif"),
            "p": p, "wilson": list(aralik) if aralik else None,
            "kazanma_orani": kazanan / n * 100.0 if n else None,
            "basabas": b.get("basabas_orani"), "konum": konum,
            "coin": coin, "en_iyi_gun": gun,
            "sanal_beklenti": sanal, "gecmis_beklenti": gt,
            "beklenti_farki": (sanal - gt) if (sanal is not None and gt is not None) else None,
            "hiz": islem_hizi(n, gecen, kalan, hedef) if sinavda else None,
            "hukum": hukum(t, p, n, hedef, konum, coin["tek_coine_bagli"], gun["tek_gune_bagli"], esik_t),
        })

    toplam_gunluk = sonuc.gunluk_topla(tum_gunluk)
    tg = sonuc.guven_etiketi(toplam_gunluk)
    tp = p_degeri(tg["t"], tg["gun"] - 1) if tg["t"] is not None else None
    toplam_islem = sum(s["islem"] for s in satirlar)
    toplam_kazanan = sum(s["kazanan"] for s in satirlar)
    bakis = len(satirlar) * BOT_BASI_OLCU + 1
    # Toplamın hükmü: yeşil yalnız en az bir bot kendi çıtasını aştıysa ve toplam da belirgin artıysa.
    toplam_hukum = hukum(tg["t"], tp, toplam_islem, hedef, "ustunde" if any(
        s["hukum"]["kod"] == "arti" for s in satirlar) else "icinde", False, en_iyi_gunsuz(toplam_gunluk)["tek_gune_bagli"],
        esik_t)
    return {
        "hedef_islem": hedef,
        "esik_t": esik_t,
        "yesil_p": YESIL_EN_FAZLA_P,
        "sinavda": sinavda,
        "donem": donem.get("donem"),
        "sinav_gunu": donem.get("gun"),
        "gecen_gun": gecen,
        "kalan_gun": kalan,
        "botlar": satirlar,
        "toplam": {
            "islem": toplam_islem, "kazanan": toplam_kazanan,
            "net_tutar": sum(s["net_tutar"] for s in satirlar),
            "t": tg["t"], "gun": tg["gun"], "etiket": tg["etiket"], "etiket_sinif": tg["sinif"], "p": tp,
            "en_iyi_gun": en_iyi_gunsuz(toplam_gunluk),
            "hukum": toplam_hukum,
        },
        "bakis": bakis,
        "coklu_bakis_olasiligi": coklu_bakis(bakis),
        "gecmis_test_var": bool(gecmis),
        "yaklasim": YAKLASIM,
    }
