"""Sonuç özeti: sanal botların işlem kayıtlarını okuyup tek bir özet çıkarır.

Hazır motor her botun işlemlerini ayrı bir SQLite dosyasına yazar
(user_data/db/<bot>.sqlite). Bu modül o dosyaları SALT OKUNUR açar, botun
çalışmasına dokunmaz, ve sonuç sayfasının göstereceği özeti üretir.

Yalnız Python standart kütüphanesi ile karabasan.karne kullanılır.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import karne as kr
from . import stop_sonrasi as ss
from .botlar import BOTLAR, ayarlari_yukle
from .kural import kural_yukle

SINAV_GUN = 30

CIKIS_NEDENI = {
    "roi": "kâr hedefi",
    "stop_loss": "stop",
    "stoploss_on_exchange": "stop",
    "trailing_stop_loss": "iz süren stop",
    "sure_asimi": "süre aşımı",
    "force_exit": "elle kapatma",
    "emergency_exit": "acil çıkış",
    "liquidation": "tasfiye",
    "exit_signal": "çıkış sinyali",
}

GEREKLI_SUTUNLAR = ("pair", "is_open", "open_date", "close_date", "stake_amount")


def zaman_coz(metin) -> datetime | None:
    """'2026-10-10 12:00:00.123' ya da '2026-10-10T12:00:00Z' biçimini UTC zamana çevirir."""
    if metin is None:
        return None
    metin = str(metin).strip()
    if not metin:
        return None
    if metin.endswith("Z"):
        metin = metin[:-1] + "+00:00"
    try:
        zaman = datetime.fromisoformat(metin)
    except ValueError:
        return None
    if zaman.tzinfo is None:
        zaman = zaman.replace(tzinfo=timezone.utc)
    return zaman.astimezone(timezone.utc)


def zaman_dosyasi_oku(yol: Path) -> datetime | None:
    """sinav_baslangici.txt gibi tek satırlık zaman dosyasını okur."""
    try:
        return zaman_coz(yol.read_text(encoding="utf-8"))
    except OSError:
        return None


def islemleri_oku(db_yolu: Path) -> dict:
    """Bir botun işlem kayıtlarını okur.

    Dönen sözlük: {"kapali": [işlem...], "acik": [işlem...], "hata": metin ya da None}
    """
    bos = {"kapali": [], "acik": [], "hata": None}
    if not db_yolu.exists():
        return {**bos, "hata": "Kayıt dosyası henüz yok; bot hiç çalışmamış olabilir."}
    try:
        baglanti = sqlite3.connect(f"file:{db_yolu}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as hata:
        return {**bos, "hata": f"Kayıt dosyası açılamadı: {hata}"}
    try:
        baglanti.row_factory = sqlite3.Row
        sutunlar = {s["name"] for s in baglanti.execute("PRAGMA table_info(trades)")}
        if not sutunlar:
            return {**bos, "hata": "Kayıt dosyasında işlem tablosu yok."}
        eksik = [s for s in GEREKLI_SUTUNLAR if s not in sutunlar]
        if eksik:
            return {**bos, "hata": f"İşlem tablosunda beklenen sütunlar yok: {', '.join(eksik)}"}
        satirlar = baglanti.execute("SELECT * FROM trades ORDER BY id").fetchall()
    except sqlite3.Error as hata:
        return {**bos, "hata": f"Kayıt dosyası okunamadı: {hata}"}
    finally:
        baglanti.close()

    kapali, acik = [], []
    for s in satirlar:
        satir = dict(s)
        giris = zaman_coz(satir.get("open_date"))
        if giris is None:
            continue
        tutar = float(satir.get("stake_amount") or 0.0)
        islem = {
            "kimlik": satir.get("id"),
            "parite": satir.get("pair"),
            "yon": "aciga_satis" if satir.get("is_short") else "alim",
            "giris_zamani": giris,
            "giris_fiyati": satir.get("open_rate"),
            "tutar": tutar,
            "etiket": satir.get("enter_tag"),
        }
        if satir.get("is_open"):
            acik.append(islem)
            continue
        cikis = zaman_coz(satir.get("close_date"))
        if cikis is None:
            continue
        # Komisyon sonrası sonuç: önce mutlak kârdan, yoksa oran sütunundan.
        mutlak = satir.get("close_profit_abs")
        if mutlak is not None and tutar > 0:
            net_yuzde = float(mutlak) / tutar * 100.0
        elif satir.get("close_profit") is not None:
            net_yuzde = float(satir["close_profit"]) * 100.0
        else:
            continue
        neden_ham = satir.get("exit_reason") or ""
        kapali.append(
            {
                **islem,
                "cikis_zamani": cikis,
                "cikis_fiyati": satir.get("close_rate"),
                "net_yuzde": net_yuzde,
                "net_tutar": float(mutlak) if mutlak is not None else net_yuzde / 100.0 * tutar,
                "neden": CIKIS_NEDENI.get(neden_ham, neden_ham or "bilinmiyor"),
                "sure_dakika": (cikis - giris).total_seconds() / 60.0,
            }
        )
    return {"kapali": kapali, "acik": acik, "hata": None}


SESSIZLIK_DAKIKA = 15


def gunluk_yasi_dakika(veri_klasoru: Path, bot: str, simdi: datetime) -> float | None:
    """Botun günlük dosyasına en son kaç dakika önce yazıldı (dosya yoksa None).

    Hazır motor çalışırken dakikada bir "yaşıyorum" satırı yazar; dosya uzun
    süredir değişmediyse bot durmuş ya da takılmış demektir.
    """
    try:
        degisim = (veri_klasoru / "logs" / f"{bot}.log").stat().st_mtime
    except OSError:
        return None
    return max(0.0, simdi.timestamp() - degisim) / 60.0


def donem_bilgisi(simdi: datetime, isinma: datetime | None, sinav: datetime | None) -> dict:
    """Hangi dönemdeyiz: kurulmadı, ısınma, sınav ya da sınav bitti."""
    if sinav is not None and simdi >= sinav:
        gecen = (simdi - sinav) / timedelta(days=1)
        if gecen >= SINAV_GUN:
            return {"donem": "bitti", "gun": SINAV_GUN, "baslangic": sinav,
                    "bitis": sinav + timedelta(days=SINAV_GUN)}
        return {"donem": "sinav", "gun": int(gecen) + 1, "baslangic": sinav,
                "bitis": sinav + timedelta(days=SINAV_GUN)}
    if isinma is not None:
        gecen = max(0.0, (simdi - isinma) / timedelta(days=1))
        return {"donem": "isinma", "gun": int(gecen) + 1, "baslangic": isinma, "bitis": None}
    return {"donem": "kurulmadi", "gun": 0, "baslangic": None, "bitis": None}


def _olcut_durumu(olcut: dict, sira: int) -> dict:
    """Bir ölçütün sayfada gösterilecek durumu: saglandi, saglanmadi ya da veri_yok."""
    deger = olcut["deger"]
    if deger is None:
        durum = "veri_yok"
    elif olcut["gecti"]:
        durum = "saglandi"
    else:
        durum = "saglanmadi"
    return {"no": sira, "ad": olcut["olcut"], "durum": durum, "deger": deger, "esik": olcut["esik"]}


def bot_ozeti(
    bot: str,
    kural_kodu: str,
    piyasa: str,
    kayit: dict,
    donem: dict,
    ayar: dict,
    gecmis_test: dict | None = None,
) -> dict:
    """Tek bir botun sayfada gösterilecek özeti."""
    kural = kural_yukle(kural_kodu)
    baslangic = donem["baslangic"]
    bitis = donem["bitis"]
    islemler = [
        i for i in kayit["kapali"]
        if (baslangic is None or i["giris_zamani"] >= baslangic)
        and (bitis is None or i["cikis_zamani"] <= bitis)
    ]
    tutar = float(ayar["islem_tutari"])
    bakiye = float(ayar["sanal_bakiye"])
    ham = kr.karne(islemler, tutar, bakiye)

    nedenler: dict[str, int] = {}
    for i in islemler:
        nedenler[i["neden"]] = nedenler.get(i["neden"], 0) + 1

    ozet = {
        "bot": bot,
        "kod": kural_kodu,
        "ad": kural["ad"],
        "piyasa": piyasa,
        "yon": kural["yon"],
        "aciklama": kural.get("aciklama", ""),
        "hedef_yuzde": kural["cikis"].get("kar_hedefi_yuzde"),
        "stop_yuzde": kural["cikis"].get("zarar_durdur_yuzde"),
        "sure_asimi_dakika": kural["cikis"].get("sure_asimi_dakika"),
        "izinli_durumlar": list(kural.get("izinli_durumlar", [])),
        "hata": kayit["hata"],
        "gunluk_yasi_dakika": None,
        "calisiyor": None,
        "acik_pozisyon": len(kayit["acik"]),
        "islem_sayisi": ham["islem_sayisi"],
        "kazanma_orani": ham["kazanma_orani"],
        "basabas_orani": ham["basabas_orani"],
        "net_beklenti": ham["net_beklenti"],
        "kar_faktoru": ham["kar_faktoru"],
        "net_tutar": ham["net_tutar"],
        "en_buyuk_dusus_yuzde": ham["en_buyuk_dusus_yuzde"],
        "ort_sure_dakika": ham["ort_sure_dakika"],
        "son_islem": max((i["cikis_zamani"] for i in islemler), default=None),
        "nedenler": nedenler,
        "olcutler": [],
        "karar": None,
    }
    if donem["donem"] in ("sinav", "bitti"):
        beklenti = (gecmis_test or {}).get(bot)
        karar = kr.sinav_karari(islemler, baslangic, beklenti, tutar, bakiye)
        ozet["olcutler"] = [
            _olcut_durumu(o, sira) for sira, o in enumerate(karar["olcutler"], 1)
        ]
        ozet["net_tutar_ek_kaymali"] = karar["karne_ek_kaymali"]["net_tutar"]
        ozet["haftalik_net"] = karar["haftalik_net"]
        if donem["donem"] == "bitti":
            ozet["karar"] = "gecti" if karar["gecti"] else "kaldi"
    return ozet


def genel_ozet(veri_klasoru: Path, simdi: datetime | None = None) -> dict:
    """Sonuç sayfasının tüm verisi. JSON'a çevrilebilir bir sözlük döner."""
    simdi = simdi or datetime.now(timezone.utc)
    ayar = ayarlari_yukle(veri_klasoru / "ayarlar.json")
    donem = donem_bilgisi(
        simdi,
        zaman_dosyasi_oku(veri_klasoru / "isinma_baslangici.txt"),
        zaman_dosyasi_oku(veri_klasoru / "sinav_baslangici.txt"),
    )
    gecmis_test = _gecmis_test_oku(veri_klasoru / "gecmis_test.json")
    izleme = ss.dosya_oku(ss.dosya_yolu(veri_klasoru))

    botlar, son_islemler, acik_islemler = [], [], []
    for bot, _sinif, kural_kodu, piyasa in BOTLAR:
        kayit = islemleri_oku(veri_klasoru / "db" / f"{bot}.sqlite")
        ozet = bot_ozeti(bot, kural_kodu, piyasa, kayit, donem, ayar, gecmis_test)
        # Stop sonrası izleme: stop daha geniş olsaydı ne olurdu (karabasan.stop_sonrasi).
        ozet["stop_sonrasi"] = ss.ozetle(
            ss.donem_kayitlari(izleme, bot, donem["baslangic"], donem["bitis"]),
            ozet["stop_yuzde"], float(ayar["islem_tutari"]),
        )
        # Üç denemede fiyat verisi alınamayan stoplar bir daha denenmez; "bekleyen" sayılmaz.
        izlenemeyen = sum(
            1 for a, deneme in izleme["basarisiz"].items()
            if a.startswith(bot + "#") and deneme >= ss.DENEME_SINIRI
        )
        ozet["stop_sonrasi"]["izlenemeyen"] = izlenemeyen
        ozet["stop_sonrasi"]["izlenmeyi_bekleyen"] = max(
            0, ozet["nedenler"].get("stop", 0) - ozet["stop_sonrasi"]["stop_sayisi"] - izlenemeyen
        )
        yas = gunluk_yasi_dakika(veri_klasoru, bot, simdi)
        ozet["gunluk_yasi_dakika"] = yas
        ozet["calisiyor"] = yas is not None and yas <= SESSIZLIK_DAKIKA
        botlar.append(ozet)
        for i in kayit["kapali"]:
            if donem["baslangic"] is None or i["giris_zamani"] >= donem["baslangic"]:
                izlenen = izleme["islemler"].get(ss.anahtar(bot, i["kimlik"]))
                son_islemler.append(
                    {**i, "bot": bot, "kod": kural_kodu,
                     "stop_sonrasi": ss.islem_cumlesi(izlenen) if izlenen else None}
                )
        for i in kayit["acik"]:
            acik_islemler.append({**i, "bot": bot, "kod": kural_kodu})
    son_islemler.sort(key=lambda i: i["cikis_zamani"], reverse=True)
    acik_islemler.sort(key=lambda i: i["giris_zamani"], reverse=True)

    calisan = [b for b in botlar if b["calisiyor"]]
    bir_gun_once = simdi - timedelta(days=1)
    son_gun = [i for i in son_islemler if i["cikis_zamani"] >= bir_gun_once]
    return {
        "uretildi": simdi,
        "donem": donem["donem"],
        "gun": donem["gun"],
        "sinav_gun": SINAV_GUN,
        "baslangic": donem["baslangic"],
        "bitis": donem["bitis"],
        "sanal_bakiye": float(ayar["sanal_bakiye"]),
        "islem_tutari": float(ayar["islem_tutari"]),
        "komisyon_yuzde": dict(ayar["komisyon_yuzde"]),
        "ek_kayma_yuzde": kr.SINAV_ESIKLERI["ek_kayma_yuzde"],
        "gecmis_test_var": bool(gecmis_test),
        "botlar": botlar,
        "toplam": {
            "bot_sayisi": len(botlar),
            "calisan_bot": len(calisan),
            "islem_sayisi": sum(b["islem_sayisi"] for b in botlar),
            "acik_pozisyon": sum(b["acik_pozisyon"] for b in botlar),
            "net_tutar": sum(b["net_tutar"] for b in botlar),
            "son_24s_islem": len(son_gun),
            "son_24s_net_tutar": sum(i["net_tutar"] for i in son_gun),
        },
        "son_islemler": son_islemler[:SON_ISLEM_SAYISI],
        "acik_islemler": acik_islemler,
        "dersler": [
            {**d, "zaman": zaman_coz(d.get("zaman"))}
            for d in list(reversed(izleme["dersler"]))[:DERS_SAYISI]
            if isinstance(d, dict)
        ],
        "stop_izleme": {
            "son_tur": zaman_coz(izleme.get("son_tur")),
            "carpanlar": list(ss.CARPANLAR),
            "en_az_stop": ss.EN_AZ_STOP,
        },
        "egri": birikimli_egri(
            [i for i in son_islemler if donem["bitis"] is None or i["cikis_zamani"] <= donem["bitis"]]
        ),
    }


SON_ISLEM_SAYISI = 30
DERS_SAYISI = 40
EGRI_NOKTA = 160


def birikimli_egri(islemler: list, en_fazla: int = EGRI_NOKTA) -> list:
    """Toplam sanal sonucun seyri: işlemler kapandıkça biriken net tutar (USDT).

    Sıfırdan başlar, son değeri toplam net sonuca eşittir. Çok işlem varsa
    eşit aralıklı noktalar seçilir; ilk ve son nokta her zaman korunur.
    """
    sirali = sorted(islemler, key=lambda i: i["cikis_zamani"])
    toplam, egri = 0.0, [0.0]
    for i in sirali:
        toplam += float(i["net_tutar"])
        egri.append(toplam)
    if len(egri) <= en_fazla:
        return egri
    adim = (len(egri) - 1) / (en_fazla - 1)
    return [egri[round(k * adim)] for k in range(en_fazla)]


def _gecmis_test_oku(yol: Path) -> dict:
    """12 aylık geçmiş testinin bot başına net beklentisi: {"s1-spot": 0.12, ...}."""
    import json

    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: float(v) for k, v in veri.items() if isinstance(v, (int, float))}


def json_icin(deger):
    """Özeti JSON'a çevirirken zamanları metne, sonsuzu None'a çevirir."""
    if isinstance(deger, datetime):
        return deger.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(deger, float) and deger in (float("inf"), float("-inf")):
        return None
    if isinstance(deger, dict):
        return {k: json_icin(v) for k, v in deger.items()}
    if isinstance(deger, (list, tuple)):
        return [json_icin(v) for v in deger]
    return deger
