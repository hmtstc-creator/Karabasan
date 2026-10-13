"""Kural dosyası motoru.

Bir strateji kod değil, bir kural dosyasıdır (JSON). Bu modül dosyayı okur,
doğrular, göstergeleri hesaplar ve giriş sinyalini üretir.

Kural dosyasının biçimi için: karabasan/stratejiler/ klasöründeki örneklere
ve README.md içindeki "Strateji dosyası" bölümüne bakın.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import gostergeler as g

STRATEJI_KLASORU = Path(__file__).parent / "stratejiler"

YONLER = ("alim", "aciga_satis")
DURUMLAR = ("YESIL", "SARI", "KIRMIZI", "SIYAH")
ISLEMLER = (">", "<", ">=", "<=", "yukari_keser", "asagi_keser")
GOSTERGE_TURLERI = (
    "ema",
    "sma",
    "rsi",
    "bollinger",
    "atr_yuzde",
    "vwap",
    "en_yuksek",
    "en_dusuk",
    "hacim_ort",
    "degisim_yuzde",
    "macd",
    "yapi",
    "uyumsuzluk",
    "donchian_topluluk",
    "fvg",
    "hacim_ortanca",
    "fonlama",
    "zaman_araligi",
    "atr",
)
# Bir gösterge başka bir paritenin mumlarında hesaplanabilir ("parite": "BTC"); o mumlar
# ek_veri içinde "<PARİTE>@<dilim>" anahtarıyla gelir (bkz. referans_istekleri).
PARITE_DESENI = re.compile(r"^[A-Z0-9]{2,12}$")
# Fonlama oranı geçmişi ek_veri içinde bu anahtarla gelir: 'date' (ödeme anı, UTC) ve
# 'oran_yuzde' (o ödemenin oranı, yüzde; artıysa alım tarafı öder).
FONLAMA_ANAHTARI = "fonlama"
FONLAMA_EN_FAZLA_ODEME = 30
UYUMSUZLUK_TIPLERI = ("normal", "gizli", "ikisi")
MACD_VARSAYILAN = {"hizli": 12, "yavas": 26, "sinyal": 9}
# Piyasa yapısı (g.piyasa_yapisi): salınım uzunluğunun sınırları.
YAPI_UZUNLUK_SINIRI = (2, 50)

# Panelden ya da dosyadan aşılamayan sınırlar. Bir yazım hatası (örneğin
# %1 yerine %100 stop) gerçek paraya ulaşmadan burada durur.
SINIRLAR = {
    # Trend takibinde (Sniper) hedef pratikte yoktur ve işlem haftalarca sürebilir.
    "kar_hedefi_yuzde": (0.1, 200.0),
    "zarar_durdur_yuzde": (0.1, 10.0),
    "sure_asimi_dakika": (5, 129600),
    "bekleme_dakika": (0, 10080),
}

# Canlıda borsadan bir seferde alınabilen mum sayısı sınırlıdır.
EN_FAZLA_BASLANGIC_MUMU = 2000


class KuralHatasi(ValueError):
    """Kural dosyası hatalı. Mesaj Türkçedir ve panelde aynen gösterilir."""


def kural_yukle(kod_veya_yol) -> dict:
    """Bir stratejiyi koduyla ('S1') ya da dosya yoluyla yükler ve doğrular."""
    yol = Path(str(kod_veya_yol))
    if yol.suffix != ".json":
        yol = STRATEJI_KLASORU / f"{kod_veya_yol}.json"
        # Emekli ve aday kurallar da koduyla okunur (eski raporlar, panel sınaması,
        # testler); hangi botların çalıştığını yalnız botlar.BOTLAR belirler.
        for alt in ("emekli", "aday"):
            if not yol.exists() and (STRATEJI_KLASORU / alt / yol.name).exists():
                yol = STRATEJI_KLASORU / alt / yol.name
    if not yol.exists():
        raise KuralHatasi(f"Strateji dosyası bulunamadı: {yol}")
    try:
        kural = json.loads(yol.read_text(encoding="utf-8"))
    except json.JSONDecodeError as hata:
        raise KuralHatasi(f"{yol.name} okunamadı, JSON biçimi bozuk: {hata}") from hata
    kural_dogrula(kural)
    return kural


def tum_kurallar() -> dict:
    """Klasördeki tüm stratejileri kod -> kural sözlüğü olarak döndürür."""
    return {
        yol.stem: kural_yukle(yol)
        for yol in sorted(STRATEJI_KLASORU.glob("*.json"))
    }


# --------------------------------------------------------------------------
# Doğrulama
# --------------------------------------------------------------------------


def _sutun_adi(ad: str) -> str:
    return g.TURKCE_SUTUN.get(ad, ad)


def _gosterge_sutunlari(ad: str, tanim: dict) -> list[str]:
    if tanim["tur"] == "bollinger":
        return [f"{ad}_ust", f"{ad}_orta", f"{ad}_alt"]
    if tanim["tur"] == "macd":
        return [f"{ad}_cizgi", f"{ad}_sinyal", f"{ad}_fark"]
    if tanim["tur"] == "yapi":
        return [f"{ad}_{sutun}" for sutun in g.YAPI_SUTUNLARI]
    if tanim["tur"] == "uyumsuzluk":
        return [f"{ad}_boga", f"{ad}_ayi"]
    if tanim["tur"] == "fvg":
        return [f"{ad}_{sutun}" for sutun in g.FVG_SUTUNLARI]
    if tanim["tur"] == "zaman_araligi":
        return [f"{ad}_{sutun}" for sutun in g.SEANS_SUTUNLARI]
    return [ad]


def gosterge_dilimi(kural: dict, tanim: dict) -> str | None:
    """Göstergenin hesaplandığı üst zaman dilimi; taban dilimdeyse None.

    'dilim' alanı üç biçimde yazılabilir: yok ya da "taban" (taban dilim),
    "ust" (kuralın 'ust_zaman_dilimi'), ya da doğrudan bir dilim ("15m", "1h", "1d").
    Sonuncusu sayesinde bir kural birden çok üst dilim kullanabilir.
    """
    dilim = tanim.get("dilim")
    if dilim in (None, "taban"):
        return None
    if dilim == "ust":
        return kural.get("ust_zaman_dilimi")
    return dilim


def borsa_dilimleri(kural: dict) -> list[str]:
    """Mumları taban mumlardan toplanmayıp borsadan ayrıca istenen dilimler.

    Günlük gibi büyük dilimler içindir: 5 dakikalık mumlardan 20 günlük bir
    ortalama kurmak için canlıda alınabilenden çok daha fazla mum gerekir.
    """
    return list(kural.get("borsa_dilimleri", []))


def ek_veri_topla(kural: dict, yukle, yukle_referans=None, yukle_fonlama=None) -> tuple[dict, list[str]]:
    """Kuralın borsadan ayrıca istediği verileri toplar.

    yukle(dilim) bir mum tablosu ya da None döndürür. Dönen ikili:
    ({anahtar: tablo}, bulunamayanlar). Bulunamayan dilim sözlükte yer almaz,
    yani taban mumlardan toplanır (bkz. gosterge_ekle); sonuç o zaman motorunkiyle
    birebir tutmaz, çünkü motor verisi olmayan dilimde hiç sinyal üretmez.

    yukle_referans(parite, dilim): başka paritenin mumları ("parite" alanlı göstergeler).
    yukle_fonlama(): paritenin fonlama geçmişi ('date', 'oran_yuzde'). Bu ikisi
    bulunamazsa ilgili göstergeler boş kalır ve kural sinyal üretmez.
    """
    ek, eksik = {}, []
    for dilim in borsa_dilimleri(kural):
        tablo = yukle(dilim)
        if tablo is None or len(tablo) == 0:
            eksik.append(dilim)
        else:
            ek[dilim] = tablo
    for parite, dilim in referans_istekleri(kural):
        anahtar = referans_anahtari(parite, dilim)
        tablo = yukle_referans(parite, dilim) if yukle_referans else None
        if tablo is None or len(tablo) == 0:
            eksik.append(anahtar)
        else:
            ek[anahtar] = tablo
    if fonlama_gerekli(kural):
        tablo = yukle_fonlama() if yukle_fonlama else None
        if tablo is None or len(tablo) == 0:
            eksik.append(FONLAMA_ANAHTARI)
        else:
            ek[FONLAMA_ANAHTARI] = tablo
    return ek, eksik


def _yapi_omru(tanim: dict) -> int:
    return int(tanim.get("blok_omru") or 20 * int(tanim["periyot"]))


def _macd_ayarlari(tanim: dict) -> tuple[int, int, int]:
    return tuple(int(tanim.get(alan, MACD_VARSAYILAN[alan])) for alan in ("hizli", "yavas", "sinyal"))


def kural_dogrula(kural: dict) -> None:
    """Kural dosyasını denetler; hata varsa KuralHatasi fırlatır."""
    if not isinstance(kural, dict):
        raise KuralHatasi("Kural dosyası bir sözlük olmalı.")
    for alan in ("kod", "ad", "yon", "zaman_dilimi", "gostergeler", "giris", "cikis"):
        if alan not in kural:
            raise KuralHatasi(f"Zorunlu alan eksik: '{alan}'")
    kod = str(kural["kod"])
    if not kod.isidentifier():
        raise KuralHatasi(f"Strateji kodu harf ve rakamdan oluşmalı: {kod!r}")
    if kural["yon"] not in YONLER:
        raise KuralHatasi(f"'yon' şunlardan biri olmalı: {', '.join(YONLER)}")

    try:
        taban_dk = g.dilim_dakika(kural["zaman_dilimi"])
    except ValueError as hata:
        raise KuralHatasi(str(hata)) from hata
    ust = kural.get("ust_zaman_dilimi")
    if ust is not None:
        try:
            ust_dk = g.dilim_dakika(ust)
        except ValueError as hata:
            raise KuralHatasi(str(hata)) from hata
        if ust_dk <= taban_dk or ust_dk % taban_dk != 0:
            raise KuralHatasi("'ust_zaman_dilimi' taban dilimin tam katı ve ondan büyük olmalı.")

    borsadan = kural.get("borsa_dilimleri", [])
    if not isinstance(borsadan, list) or len(set(map(str, borsadan))) != len(borsadan):
        raise KuralHatasi("'borsa_dilimleri' birbirinden farklı dilimlerin listesi olmalı.")
    for dilim in borsadan:
        _ust_dilim_denetle(dilim, taban_dk, "'borsa_dilimleri'")

    # Göstergeler
    gost = kural["gostergeler"]
    if not isinstance(gost, dict):
        raise KuralHatasi("'gostergeler' bir sözlük olmalı.")
    fiyatlar = set(g.FIYAT_SUTUNLARI) | set(g.TURKCE_SUTUN)
    bilinen = set(fiyatlar)
    # Her çerçevenin (dilim, parite) kendi sütunları: bir gösterge yalnız kendi çerçevesindeki
    # bir kaynağı kullanabilir.
    dilim_bilinen: dict[tuple, set] = {(None, None): bilinen}
    for ad, tanim in gost.items():
        if not ad.isidentifier() or ad in bilinen:
            raise KuralHatasi(f"Gösterge adı uygun değil ya da çakışıyor: {ad!r}")
        if not isinstance(tanim, dict) or tanim.get("tur") not in GOSTERGE_TURLERI:
            raise KuralHatasi(
                f"'{ad}' göstergesinin türü şunlardan biri olmalı: {', '.join(GOSTERGE_TURLERI)}"
            )
        tur = tanim["tur"]
        if tanim.get("dilim") == "ust" and ust is None:
            raise KuralHatasi(f"'{ad}' üst dilimde tanımlı ama 'ust_zaman_dilimi' verilmemiş.")
        dilim = gosterge_dilimi(kural, tanim)
        ust_mu = dilim is not None
        if ust_mu and tanim.get("dilim") != "ust":
            _ust_dilim_denetle(dilim, taban_dk, f"'{ad}': 'dilim'")
        parite = tanim.get("parite")
        if parite is not None and (not isinstance(parite, str) or not PARITE_DESENI.match(parite)):
            raise KuralHatasi(f"'{ad}': 'parite' büyük harf ve rakamdan oluşan bir coin adı olmalı (örnek: \"BTC\").")
        kaydir = tanim.get("kaydir", 0)
        if not isinstance(kaydir, int) or isinstance(kaydir, bool) or not 0 <= kaydir <= 1000:
            # Negatif kaydırma geleceğe bakmak olur.
            raise KuralHatasi(f"'{ad}': 'kaydir' 0 ile 1000 arasında tam sayı olmalı.")
        if tur == "fonlama":
            if dilim is not None or parite is not None or tanim.get("kaynak") is not None:
                raise KuralHatasi(f"'{ad}': fonlama göstergesi paritenin kendi fonlama geçmişinden "
                                  "hesaplanır; 'dilim', 'parite' ve 'kaynak' almaz.")
            periyot = tanim.get("periyot")
            if (not isinstance(periyot, int) or isinstance(periyot, bool)
                    or not 1 <= periyot <= FONLAMA_EN_FAZLA_ODEME):
                raise KuralHatasi(f"'{ad}': fonlamada 'periyot' (son kaç ödemenin ortalaması) 1 ile "
                                  f"{FONLAMA_EN_FAZLA_ODEME} arasında tam sayı olmalı.")
        if tur == "macd":
            for alan in MACD_VARSAYILAN:
                deger = tanim.get(alan, MACD_VARSAYILAN[alan])
                if not isinstance(deger, int) or isinstance(deger, bool) or not 1 <= deger <= 200:
                    raise KuralHatasi(f"'{ad}': '{alan}' 1 ile 200 arasında tam sayı olmalı.")
            hizli, yavas, _ = _macd_ayarlari(tanim)
            if hizli >= yavas:
                raise KuralHatasi(f"'{ad}': 'hizli' periyot 'yavas' periyottan küçük olmalı.")
        elif tur == "donchian_topluluk":
            uzunluklar = tanim.get("uzunluklar")
            if (not isinstance(uzunluklar, list) or not 1 <= len(uzunluklar) <= 12
                    or len(set(uzunluklar)) != len(uzunluklar)
                    or not all(isinstance(u, int) and not isinstance(u, bool) and 2 <= u <= 400
                               for u in uzunluklar)):
                raise KuralHatasi(f"'{ad}': 'uzunluklar' 2 ile 400 arasında, birbirinden farklı "
                                  "1-12 tam sayının listesi olmalı.")
            if tanim.get("kaynak") is not None:
                raise KuralHatasi(f"'{ad}': Donchian topluluğu kapanıştan hesaplanır, 'kaynak' almaz.")
        elif tur == "fvg":
            omur = tanim.get("omur", 50)
            if not isinstance(omur, int) or isinstance(omur, bool) or not 3 <= omur <= 500:
                raise KuralHatasi(f"'{ad}': 'omur' 3 ile 500 arasında tam sayı olmalı.")
            esik = tanim.get("en_az_yuzde", 0.0)
            if isinstance(esik, bool) or not isinstance(esik, (int, float)) or not 0 <= esik <= 5:
                raise KuralHatasi(f"'{ad}': 'en_az_yuzde' 0 ile 5 arasında sayı olmalı.")
            if tanim.get("kaynak") is not None:
                raise KuralHatasi(f"'{ad}': FVG mumun kendisinden hesaplanır, 'kaynak' almaz.")
        elif tur == "zaman_araligi":
            _zaman_araligi_dogrula(ad, tanim, dilim, parite)
        elif tur not in ("vwap", "fonlama"):
            periyot = tanim.get("periyot")
            if not isinstance(periyot, int) or isinstance(periyot, bool) or not 1 <= periyot <= 1000:
                raise KuralHatasi(f"'{ad}': 'periyot' 1 ile 1000 arasında tam sayı olmalı.")
        if tur == "yapi":
            alt_sinir, ust_sinir = YAPI_UZUNLUK_SINIRI
            if not alt_sinir <= tanim["periyot"] <= ust_sinir:
                raise KuralHatasi(
                    f"'{ad}': piyasa yapısında 'periyot' (salınım uzunluğu) {alt_sinir} ile {ust_sinir} arasında olmalı."
                )
            omur = tanim.get("blok_omru")
            if omur is not None and (
                not isinstance(omur, int) or isinstance(omur, bool) or not 1 <= omur <= 1000
            ):
                raise KuralHatasi(f"'{ad}': 'blok_omru' 1 ile 1000 arasında tam sayı olmalı.")
            if tanim.get("kaynak") is not None:
                raise KuralHatasi(f"'{ad}': piyasa yapısı mumun kendisinden hesaplanır, 'kaynak' almaz.")
        if tur == "uyumsuzluk":
            if not 2 <= tanim["periyot"] <= 20:
                raise KuralHatasi(f"'{ad}': uyumsuzlukta 'periyot' (salınım uzunluğu) 2 ile 20 arasında olmalı.")
            if tanim.get("tip", "ikisi") not in UYUMSUZLUK_TIPLERI:
                raise KuralHatasi(f"'{ad}': 'tip' şunlardan biri olmalı: {', '.join(UYUMSUZLUK_TIPLERI)}")
            if tanim.get("kaynak") is not None:
                raise KuralHatasi(f"'{ad}': uyumsuzluk mumun kendisinden hesaplanır, 'kaynak' almaz.")
        if tur == "vwap" and ust_mu:
            raise KuralHatasi(f"'{ad}': VWAP yalnız taban dilimde hesaplanır.")
        if tur == "bollinger":
            sapma = tanim.get("sapma", 2.0)
            if not isinstance(sapma, (int, float)) or not 0.1 <= sapma <= 10:
                raise KuralHatasi(f"'{ad}': 'sapma' 0,1 ile 10 arasında olmalı.")
        kaynak = tanim.get("kaynak")
        gecerli = dilim_bilinen.setdefault((dilim, parite), set(fiyatlar))
        if kaynak is not None and kaynak not in gecerli:
            raise KuralHatasi(
                f"'{ad}': kaynak '{kaynak}' tanımlı değil. Kaynak bir fiyat sütunu ya da "
                "daha önce tanımlanmış, aynı dilimdeki bir gösterge olmalı."
            )
        for sutun in _gosterge_sutunlari(ad, tanim):
            if sutun in bilinen:
                raise KuralHatasi(f"Gösterge adı uygun değil ya da çakışıyor: {sutun!r}")
            bilinen.add(sutun)
            gecerli.add(sutun)

    # Giriş koşulları
    _kosul_dogrula(kural["giris"], bilinen, "giris")

    # Çıkış
    cikis = kural["cikis"]
    if not isinstance(cikis, dict):
        raise KuralHatasi("'cikis' bir sözlük olmalı.")
    if "zarar_durdur_yuzde" not in cikis:
        raise KuralHatasi("'cikis' içinde zorunlu alan eksik: 'zarar_durdur_yuzde'")
    # Kâr hedefi ve süre sınırı isteğe bağlıdır (12 Ekim 2026: iz süren stoplu, süresiz
    # botlar). Ama stoptan başka en az bir çıkış yolu olmalı.
    for alan in ("kar_hedefi_yuzde", "zarar_durdur_yuzde", "sure_asimi_dakika"):
        if cikis.get(alan) is not None:
            _sinir_denetle(alan, cikis[alan])
    iz = cikis.get("iz_suren_stop")
    if iz is not None:
        _iz_suren_stop_dogrula(iz)
    if cikis.get("stop_atr") is not None:
        _stop_atr_dogrula(cikis["stop_atr"], cikis["zarar_durdur_yuzde"], taban_dk, bilinen)
    if cikis.get("kar_hedefi_r") is not None:
        r = cikis["kar_hedefi_r"]
        if isinstance(r, bool) or not isinstance(r, (int, float)) or not 0.5 <= r <= 5:
            raise KuralHatasi("'kar_hedefi_r' (stopun kaç katı hedef) 0,5 ile 5 arasında olmalı.")
        if cikis.get("kar_hedefi_yuzde") is not None or not cikis.get("stop_atr"):
            raise KuralHatasi("'kar_hedefi_r' yalnız 'stop_atr' ile ve 'kar_hedefi_yuzde' olmadan yazılır.")
    if not any(cikis.get(a) is not None for a in ("kar_hedefi_yuzde", "kar_hedefi_r", "sure_asimi_dakika",
                                                  "iz_suren_stop", "sinyal")):
        raise KuralHatasi("'cikis' içinde stoptan başka en az bir çıkış olmalı: kâr hedefi, "
                          "iz süren stop, süre sınırı ya da çıkış sinyali.")
    _sinir_denetle("bekleme_dakika", kural.get("bekleme_dakika", 0))
    if "sinyal" in cikis:
        _kosul_dogrula(cikis["sinyal"], bilinen, "cikis > sinyal")

    onay = kural.get("defter_onayi")
    if onay is not None:
        esik = onay.get("en_az_dengesizlik") if isinstance(onay, dict) else None
        if isinstance(esik, bool) or not isinstance(esik, (int, float)) or not 0 <= esik < 1:
            raise KuralHatasi("'defter_onayi' içinde 'en_az_dengesizlik' 0 ile 1 arasında olmalı.")

    limit = kural.get("giris_limiti")
    if limit is not None:
        _giris_limiti_dogrula(limit, taban_dk)

    if kural.get("portfoy") is not None:
        _portfoy_dogrula(kural["portfoy"])
    bilgi = kural.get("bilgi", {})
    if not isinstance(bilgi, dict):
        raise KuralHatasi("'bilgi' bir sözlük olmalı: ad -> koşul.")
    for ad, kosul in bilgi.items():
        if not str(ad).isidentifier():
            raise KuralHatasi(f"'bilgi' içindeki ad uygun değil: {ad!r}")
        _kosul_dogrula(kosul, bilinen, f"bilgi > {ad}")

    for durum in kural.get("izinli_durumlar", []):
        if durum not in DURUMLAR:
            raise KuralHatasi(f"'izinli_durumlar' içinde tanınmayan durum: {durum!r}")

    ihtiyac = gereken_mum(kural, sinirla=False)
    if ihtiyac > EN_FAZLA_BASLANGIC_MUMU:
        raise KuralHatasi(
            f"Bu kural {ihtiyac} başlangıç mumu istiyor; sınır {EN_FAZLA_BASLANGIC_MUMU}. "
            "Üst dilimdeki göstergelerin periyodunu küçültün ya da taban dilimi büyütün."
        )


def _tam_sayi(deger, alt: int, ust: int) -> bool:
    return isinstance(deger, int) and not isinstance(deger, bool) and alt <= deger <= ust


def _zaman_araligi_dogrula(ad: str, tanim: dict, dilim, parite) -> None:
    """Seans aralığı: sabit pencere (bas_saat, bit_saat, islem_bas, islem_bit) ya da kayan_saat."""
    if dilim is not None or parite is not None or tanim.get("kaynak") is not None:
        raise KuralHatasi(f"'{ad}': seans aralığı taban dilimin kendi mumlarından hesaplanır; "
                          "'dilim', 'parite' ve 'kaynak' almaz.")
    pay = tanim.get("pay_atr", 0.5)
    if isinstance(pay, bool) or not isinstance(pay, (int, float)) or not 0 <= pay <= 5:
        raise KuralHatasi(f"'{ad}': 'pay_atr' 0 ile 5 arasında sayı olmalı.")
    if tanim.get("kayan_saat") is not None:
        if not _tam_sayi(tanim["kayan_saat"], 1, 24) or any(
                tanim.get(a) is not None for a in ("bas_saat", "bit_saat", "islem_bas", "islem_bit")):
            raise KuralHatasi(f"'{ad}': 'kayan_saat' 1 ile 24 arasında olmalı ve sabit pencere alanlarıyla "
                              "birlikte yazılmamalı.")
        return
    saatler = [tanim.get(a) for a in ("bas_saat", "bit_saat", "islem_bas", "islem_bit")]
    if not all(_tam_sayi(h, 0, 24) for h in saatler):
        raise KuralHatasi(f"'{ad}': 'bas_saat', 'bit_saat', 'islem_bas', 'islem_bit' 0 ile 24 arasında tam sayı olmalı.")
    bas, bit, ibas, ibit = saatler
    if not (bas < bit <= ibas < ibit):
        raise KuralHatasi(f"'{ad}': ölçüm penceresi işlem penceresinden önce bitmeli "
                          "(bas_saat < bit_saat <= islem_bas < islem_bit); yoksa geleceğe bakar.")


def _ust_dilim_denetle(dilim, taban_dk: int, yer: str) -> None:
    """Bir üst dilim, taban dilimin tam katı ve ondan büyük olmalıdır."""
    try:
        dk = g.dilim_dakika(dilim) if isinstance(dilim, str) else 0
    except ValueError:
        dk = 0
    if dk <= taban_dk or dk % taban_dk != 0:
        raise KuralHatasi(
            f"{yer} 'ust', 'taban' ya da taban dilimin tam katı olan daha büyük bir dilim "
            f"(örnek: '15m', '1h', '1d') olmalı; verilen: {dilim!r}"
        )


def _sinir_denetle(alan: str, deger) -> None:
    alt, ust = SINIRLAR[alan]
    if isinstance(deger, bool) or not isinstance(deger, (int, float)) or not alt <= deger <= ust:
        raise KuralHatasi(f"'{alan}' {alt} ile {ust} arasında olmalı; verilen: {deger!r}")


def _islenen_dogrula(islenen, bilinen: set, yer: str) -> None:
    if isinstance(islenen, bool):
        raise KuralHatasi(f"{yer}: doğru/yanlış değeri işlenen olamaz.")
    if isinstance(islenen, (int, float)):
        return
    if isinstance(islenen, str):
        if islenen not in bilinen:
            raise KuralHatasi(f"{yer}: '{islenen}' tanımlı bir sütun ya da gösterge değil.")
        return
    if isinstance(islenen, dict):
        if islenen.get("ad") not in bilinen:
            raise KuralHatasi(f"{yer}: '{islenen.get('ad')}' tanımlı bir sütun ya da gösterge değil.")
        kaydir = islenen.get("kaydir", 0)
        if not isinstance(kaydir, int) or isinstance(kaydir, bool) or not 0 <= kaydir <= 1000:
            # Negatif kaydırma geleceğe bakmak olur; izin verilmez.
            raise KuralHatasi(f"{yer}: 'kaydir' 0 ile 1000 arasında tam sayı olmalı.")
        carpan = islenen.get("carpan", 1.0)
        if isinstance(carpan, bool) or not isinstance(carpan, (int, float)):
            raise KuralHatasi(f"{yer}: 'carpan' sayı olmalı.")
        ekle = islenen.get("ekle")
        if ekle is not None:
            # Seviye + k x başka sütun (örnek: destek + 0,5 x ATR). Aynı mumun değerleri; geleceğe bakmaz.
            if not isinstance(ekle, dict) or ekle.get("ad") not in bilinen or isinstance(
                    ekle.get("carpan", 1.0), bool) or not isinstance(ekle.get("carpan", 1.0), (int, float)):
                raise KuralHatasi(f"{yer}: 'ekle' {{\"ad\": tanımlı sütun, \"carpan\": sayı}} olmalı.")
        return
    raise KuralHatasi(f"{yer}: işlenen anlaşılamadı: {islenen!r}")


def _kosul_dogrula(kosul, bilinen: set, yer: str) -> None:
    if not isinstance(kosul, dict):
        raise KuralHatasi(f"{yer}: koşul bir sözlük olmalı.")
    for baglac in ("hepsi", "herhangi"):
        if baglac in kosul:
            alt = kosul[baglac]
            if not isinstance(alt, list) or not alt:
                raise KuralHatasi(f"{yer}: '{baglac}' boş olmayan bir liste olmalı.")
            for sira, parca in enumerate(alt, 1):
                _kosul_dogrula(parca, bilinen, f"{yer} > {baglac}[{sira}]")
            # Grup da 'son_n_mumda' alabilir: grubun bütün koşulları aynı mumda, son N mumdan birinde.
            if not _tam_sayi(kosul.get("son_n_mumda", 1), 1, 500):
                raise KuralHatasi(f"{yer}: 'son_n_mumda' 1 ile 500 arasında tam sayı olmalı.")
            return
    for alan in ("sol", "islem", "sag"):
        if alan not in kosul:
            raise KuralHatasi(f"{yer}: koşulda '{alan}' eksik.")
    if kosul["islem"] not in ISLEMLER:
        raise KuralHatasi(f"{yer}: işlem şunlardan biri olmalı: {', '.join(ISLEMLER)}")
    _islenen_dogrula(kosul["sol"], bilinen, yer)
    _islenen_dogrula(kosul["sag"], bilinen, yer)
    son_n = kosul.get("son_n_mumda", 1)
    if not isinstance(son_n, int) or isinstance(son_n, bool) or not 1 <= son_n <= 500:
        raise KuralHatasi(f"{yer}: 'son_n_mumda' 1 ile 500 arasında tam sayı olmalı.")


# --------------------------------------------------------------------------
# Hesaplama
# --------------------------------------------------------------------------


def _tum_gostergeler(kural: dict) -> dict:
    """Kuralın göstergeleri ve çıkışın gerektirdiği gizli göstergeler (ATR'ye bağlı stop)."""
    gost = dict(kural["gostergeler"])
    stop_atr = kural["cikis"].get("stop_atr")
    if stop_atr:
        gost[STOP_ATR_SUTUNU] = _stop_atr_gostergesi(stop_atr)
    return gost


def _mum_ihtiyaclari(kural: dict) -> tuple[int, dict[str, int]]:
    """(taban dilimde gereken mum, borsadan istenen her dilim için o dilimde gereken mum).

    Başka paritenin mumları da borsadan ayrıca gelir; onların ihtiyacı "<PARİTE>@<dilim>"
    anahtarıyla yazılır.
    """
    taban = kural["zaman_dilimi"]
    taban_dk = g.dilim_dakika(taban)
    borsadan = set(borsa_dilimleri(kural))
    ihtiyaclar: dict[str, int] = {}      # sütun -> kendi hesaplandığı ölçüde ihtiyaç
    taban_ihtiyac, ek_ihtiyac = [50], {}
    for ad, tanim in _tum_gostergeler(kural).items():
        if tanim["tur"] == "fonlama":
            continue          # mum değil, fonlama geçmişi ister
        periyot = int(tanim.get("periyot", 0))
        # Üstel ortalamalar yaklaşık üç periyotta oturur.
        kat = 3 if tanim["tur"] in ("ema", "rsi", "atr_yuzde", "atr") else 1
        ihtiyac = periyot * kat
        if tanim["tur"] == "vwap":
            ihtiyac = 1440 // taban_dk
        if tanim["tur"] == "macd":
            _, yavas, sinyal = _macd_ayarlari(tanim)
            ihtiyac = (yavas + sinyal) * 3
        if tanim["tur"] == "donchian_topluluk":
            # Modellerin durumu geçmişe bağlıdır; en uzun kanalın iki katı kadar ısınma.
            ihtiyac = 2 * max(tanim["uzunluklar"]) + 5
        if tanim["tur"] == "fvg":
            ihtiyac = int(tanim.get("omur", 50)) + 3
        if tanim["tur"] == "zaman_araligi":
            # Bir günlük pencere (ya da kayan pencere) ve ATR'nin oturması.
            saat = int(tanim.get("kayan_saat") or 24)
            ihtiyac = saat * 60 // taban_dk + g.SEANS_BOSLUGU + 3 * 14
        if tanim["tur"] == "uyumsuzluk":
            # En eski karşılaştırılan nokta + göstergelerin (MACD, RSI...) oturması.
            ihtiyac = g.UYUMSUZLUK_EN_FAZLA_MUM + periyot + (26 + 9) * 3
        if tanim["tur"] == "yapi":
            # Yapı, veri nereden başlarsa başlasın aynı yere otursun: salınımların ve yönün
            # yeniden kurulması, üstüne en eski geçerli bloğun ömrü.
            ihtiyac = max(30 * periyot, _yapi_omru(tanim) + 10 * periyot)
        ihtiyac += int(tanim.get("kaydir", 0))
        dilim = gosterge_dilimi(kural, tanim)
        parite = tanim.get("parite")
        borsadan_mi = dilim in borsadan or parite is not None
        if dilim and not borsadan_mi:
            ihtiyac *= g.dilim_dakika(dilim) // taban_dk
        # Başka bir göstergeden türeyen gösterge, kaynağının ihtiyacını da taşır.
        ihtiyac += ihtiyaclar.get(tanim.get("kaynak"), 0)
        for sutun in _gosterge_sutunlari(ad, tanim):
            ihtiyaclar[sutun] = ihtiyac
        if borsadan_mi:
            anahtar = referans_anahtari(parite, dilim or taban) if parite else dilim
            ek_ihtiyac[anahtar] = max(ek_ihtiyac.get(anahtar, 0), ihtiyac + 10)
        else:
            taban_ihtiyac.append(ihtiyac)
    return max(taban_ihtiyac) + 10, ek_ihtiyac


def gereken_mum(kural: dict, sinirla: bool = True) -> int:
    """Göstergelerin oturması için gereken başlangıç mumu sayısı (taban dilimde).

    'borsa_dilimleri' içindeki dilimler buna katılmaz; onların mumları ayrıca gelir
    (bkz. gereken_ek_mum).
    """
    en_cok, _ek = _mum_ihtiyaclari(kural)
    return min(en_cok, EN_FAZLA_BASLANGIC_MUMU) if sinirla else en_cok


def gereken_ek_mum(kural: dict) -> dict[str, int]:
    """Borsadan ayrıca istenen her dilim için gereken mum sayısı (o dilimin kendi mumuyla)."""
    return _mum_ihtiyaclari(kural)[1]


def referans_anahtari(parite: str, dilim: str) -> str:
    """Başka bir paritenin mumlarının ek_veri içindeki anahtarı: "BTC@15m"."""
    return f"{parite}@{dilim}"


def referans_istekleri(kural: dict) -> list[tuple[str, str]]:
    """Kuralın göstergeleri için gereken (parite, dilim) çiftleri, tanım sırasıyla."""
    istek: list[tuple[str, str]] = []
    for tanim in _tum_gostergeler(kural).values():
        if tanim.get("parite"):
            cift = (tanim["parite"], gosterge_dilimi(kural, tanim) or kural["zaman_dilimi"])
            if cift not in istek:
                istek.append(cift)
    return istek


def fonlama_gerekli(kural: dict) -> bool:
    return any(t["tur"] == "fonlama" for t in kural["gostergeler"].values())


def _tek_gosterge(cerceve: pd.DataFrame, ad: str, tanim: dict) -> dict:
    """Tek bir göstergeyi verilen çerçevede hesaplar; sütun adı -> seri döndürür."""
    tur = tanim["tur"]
    periyot = tanim.get("periyot")
    if tur == "vwap":
        return {ad: g.vwap_gunluk(cerceve)}
    if tur == "atr_yuzde":
        return {ad: g.atr_yuzde(cerceve, periyot)}
    if tur == "atr":
        return {ad: g.atr(cerceve, periyot)}
    if tur == "hacim_ort":
        return {ad: g.sma(cerceve["volume"], periyot)}
    if tur == "zaman_araligi":
        seans = g.zaman_araligi(cerceve, tanim.get("bas_saat"), tanim.get("bit_saat"), tanim.get("islem_bas"),
                                tanim.get("islem_bit"), tanim.get("kayan_saat"), float(tanim.get("pay_atr", 0.5)))
        return {f"{ad}_{sutun}": seans[sutun] for sutun in g.SEANS_SUTUNLARI}
    if tur == "hacim_ortanca":
        return {ad: cerceve["volume"].astype(float).rolling(periyot, min_periods=periyot).median()}
    if tur == "donchian_topluluk":
        return {ad: g.donchian_topluluk(cerceve["close"], list(tanim["uzunluklar"]))}
    if tur == "fvg":
        f = g.fvg(cerceve, int(tanim.get("omur", 50)), float(tanim.get("en_az_yuzde", 0.0)))
        return {f"{ad}_{sutun}": f[sutun] for sutun in g.FVG_SUTUNLARI}
    if tur == "uyumsuzluk":
        u = g.uyumsuzluk(cerceve, periyot, tanim.get("tip", "ikisi"))
        return {f"{ad}_boga": u["boga"], f"{ad}_ayi": u["ayi"]}
    if tur == "yapi":
        yapi = g.piyasa_yapisi(cerceve, periyot, _yapi_omru(tanim))
        return {f"{ad}_{sutun}": yapi[sutun] for sutun in g.YAPI_SUTUNLARI}
    varsayilan = {"en_yuksek": "high", "en_dusuk": "low"}.get(tur, "close")
    kaynak = cerceve[_sutun_adi(tanim.get("kaynak") or varsayilan)]
    if tur == "ema":
        return {ad: g.ema(kaynak, periyot)}
    if tur == "sma":
        return {ad: g.sma(kaynak, periyot)}
    if tur == "rsi":
        return {ad: g.rsi(kaynak, periyot)}
    if tur == "en_yuksek":
        return {ad: g.en_yuksek(kaynak, periyot)}
    if tur == "en_dusuk":
        return {ad: g.en_dusuk(kaynak, periyot)}
    if tur == "degisim_yuzde":
        return {ad: g.degisim_yuzde(kaynak, periyot)}
    if tur == "bollinger":
        ust, orta, alt = g.bollinger(kaynak, periyot, float(tanim.get("sapma", 2.0)))
        return {f"{ad}_ust": ust, f"{ad}_orta": orta, f"{ad}_alt": alt}
    if tur == "macd":
        cizgi, sinyal, fark = g.macd(kaynak, *_macd_ayarlari(tanim))
        return {f"{ad}_cizgi": cizgi, f"{ad}_sinyal": sinyal, f"{ad}_fark": fark}
    raise KuralHatasi(f"Tanınmayan gösterge türü: {tur}")


def _ust_tablo(df: pd.DataFrame, taban: str, dilim: str, ek_veri: dict | None) -> pd.DataFrame:
    """Bir üst dilimin mum tablosu: verildiyse borsadan gelen, yoksa taban mumlardan toplanan.

    Boş bir tablo vermek "bu dilimin verisi yok" demektir: toplamaya gidilmez, o dilimin
    göstergeleri boş kalır. Canlıda borsadan veri alınamadığında işlem açılmasın diye.
    """
    hazir = (ek_veri or {}).get(dilim)
    if hazir is None:
        return g.ust_dilime_cevir(df, taban, dilim)
    fiyatlar = ["open", "high", "low", "close", "volume"]
    tablo = hazir[["date", *fiyatlar]].copy()
    tablo["date"] = pd.to_datetime(tablo["date"], utc=True)
    # Boş tabloda sütun türü belirsiz kalabilir; ortalamalar sayı türü ister.
    tablo[fiyatlar] = tablo[fiyatlar].astype(float)
    return tablo.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


def _bos_mum_tablosu() -> pd.DataFrame:
    tablo = pd.DataFrame({"date": pd.to_datetime([], utc=True)})
    for sutun in g.FIYAT_SUTUNLARI:
        tablo[sutun] = pd.Series([], dtype=float)
    return tablo


def _referans_tablo(anahtar: str, ek_veri: dict | None) -> pd.DataFrame:
    """Başka paritenin mumları; verilmediyse boş tablo (gösterge boş kalır, sinyal olmaz)."""
    hazir = (ek_veri or {}).get(anahtar)
    if hazir is None or len(hazir) == 0:
        return _bos_mum_tablosu()
    fiyatlar = list(g.FIYAT_SUTUNLARI)
    tablo = hazir[["date", *fiyatlar]].copy()
    tablo["date"] = pd.to_datetime(tablo["date"], utc=True)
    tablo[fiyatlar] = tablo[fiyatlar].astype(float)
    return tablo.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


def _fonlama_serisi(df: pd.DataFrame, periyot: int, ek_veri: dict | None) -> pd.Series:
    """Her mumda, mumun açılışından önce kesinleşmiş son 'periyot' fonlama ödemesinin ortalaması.

    Bir ödeme ancak gerçekleştiği andan sonra açılan mumda görülür (geleceğe bakmaz).
    Fonlama geçmişi verilmediyse boş (NaN) seri: koşullar sağlanmaz.
    """
    tablo = (ek_veri or {}).get(FONLAMA_ANAHTARI)
    if tablo is None or len(tablo) == 0:
        return pd.Series(np.nan, index=df.index)
    odeme = pd.Series(tablo["oran_yuzde"].astype(float).to_numpy(),
                      index=pd.to_datetime(tablo["date"], utc=True))
    odeme = odeme[~odeme.index.duplicated(keep="last")].sort_index()
    ortalama = odeme.rolling(periyot, min_periods=periyot).mean()
    hedef = pd.DatetimeIndex(pd.to_datetime(df["date"], utc=True))
    return pd.Series(ortalama.reindex(hedef, method="ffill").to_numpy(), index=df.index)


def _gostergeleri_hesapla(df: pd.DataFrame, kural: dict, tanimlar: dict, ek_veri: dict | None) -> pd.DataFrame:
    """Verilen göstergeleri hesaplayıp df'nin bir kopyasına ekler (bkz. gosterge_ekle)."""
    sonuc = df.copy()
    taban = kural["zaman_dilimi"]

    # 1) Kendi çerçevesinde hesaplanan göstergeler: üst dilim ve / veya başka parite.
    #    Her biri kendi tablosunda hesaplanır, kendi çerçevesinde kaydırılır, sonra hizalanır.
    gruplar: dict[tuple, dict] = {}
    for ad, tanim in tanimlar.items():
        dilim = gosterge_dilimi(kural, tanim)
        parite = tanim.get("parite")
        if (dilim or parite) and tanim["tur"] != "fonlama":
            gruplar.setdefault((dilim, parite), {})[ad] = tanim
    for (dilim, parite), grup in gruplar.items():
        if parite:
            cerceve = _referans_tablo(referans_anahtari(parite, dilim or taban), ek_veri)
        else:
            cerceve = _ust_tablo(df, taban, dilim, ek_veri)
        for ad, tanim in grup.items():
            for sutun, seri in _tek_gosterge(cerceve, ad, tanim).items():
                cerceve[sutun] = seri
                kaydir = int(tanim.get("kaydir", 0))
                sonuc[sutun] = g.ust_dilimden_hizala(
                    seri.shift(kaydir) if kaydir else seri, cerceve["date"], df["date"], taban, dilim or taban
                )

    # 2) Taban dilim göstergeleri ve fonlama.
    for ad, tanim in tanimlar.items():
        if (gosterge_dilimi(kural, tanim) or tanim.get("parite")) and tanim["tur"] != "fonlama":
            continue
        if tanim["tur"] == "fonlama":
            sonuc[ad] = _fonlama_serisi(sonuc, int(tanim["periyot"]), ek_veri)
            continue
        kaydir = int(tanim.get("kaydir", 0))
        for sutun, seri in _tek_gosterge(sonuc, ad, tanim).items():
            sonuc[sutun] = seri.shift(kaydir) if kaydir else seri
    return sonuc


def gosterge_ekle(df: pd.DataFrame, kural: dict, ek_veri: dict | None = None) -> pd.DataFrame:
    """Kuraldaki tüm göstergeleri hesaplayıp tabloya sütun olarak ekler.

    ek_veri: {dilim: mum tablosu}. 'borsa_dilimleri' içindeki bir dilimin borsadan
    gelen mumları buradan verilir (örnek: {"1d": günlük mumlar}). Sözlükte hiç yer
    almayan dilim taban mumlardan toplanır (geçmiş veriyle çalışan araçlar ve testler
    için; eldeki taban veri kısaysa göstergeler boş kalır). Boş tablo verilen dilim
    toplanmaz: göstergeleri boş kalır ve kural sinyal üretmez.

    Başka paritenin göstergeleri ("parite": "BTC") ek_veri["BTC@<dilim>"] mumlarından,
    fonlama göstergesi ek_veri["fonlama"]'dan hesaplanır; verilmezlerse boş kalırlar.
    Göstergenin 'kaydir' alanı kendi çerçevesinde (kendi diliminin mumuyla) kaydırır.

    Girdi tablosu değiştirilmez; yeni bir tablo döner.
    """
    return _gostergeleri_hesapla(df, kural, kural["gostergeler"], ek_veri)


def _islenen(df: pd.DataFrame, islenen) -> pd.Series:
    if isinstance(islenen, (int, float)):
        return pd.Series(float(islenen), index=df.index)
    if isinstance(islenen, str):
        return df[_sutun_adi(islenen)].astype(float)
    seri = df[_sutun_adi(islenen["ad"])].astype(float)
    kaydir = int(islenen.get("kaydir", 0))
    if kaydir:
        seri = seri.shift(kaydir)
    seri = seri * float(islenen.get("carpan", 1.0))
    ekle = islenen.get("ekle")
    if ekle:
        ek = df[_sutun_adi(ekle["ad"])].astype(float)
        seri = seri + (ek.shift(kaydir) if kaydir else ek) * float(ekle.get("carpan", 1.0))
    return seri


def _son_n(dogru: pd.Series, kosul: dict) -> pd.Series:
    son_n = int(kosul.get("son_n_mumda", 1))
    if son_n > 1:
        dogru = dogru.astype(float).rolling(son_n, min_periods=1).max() > 0
    return dogru.astype(bool)


def _kosul(df: pd.DataFrame, kosul: dict) -> pd.Series:
    if "hepsi" in kosul:
        sonuc = pd.Series(True, index=df.index)
        for parca in kosul["hepsi"]:
            sonuc &= _kosul(df, parca)
        return _son_n(sonuc, kosul)
    if "herhangi" in kosul:
        sonuc = pd.Series(False, index=df.index)
        for parca in kosul["herhangi"]:
            sonuc |= _kosul(df, parca)
        return _son_n(sonuc, kosul)

    sol = _islenen(df, kosul["sol"])
    sag = _islenen(df, kosul["sag"])
    islem = kosul["islem"]
    if islem == ">":
        dogru = sol > sag
    elif islem == "<":
        dogru = sol < sag
    elif islem == ">=":
        dogru = sol >= sag
    elif islem == "<=":
        dogru = sol <= sag
    elif islem == "yukari_keser":
        dogru = (sol > sag) & (sol.shift(1) <= sag.shift(1))
    else:  # asagi_keser
        dogru = (sol < sag) & (sol.shift(1) >= sag.shift(1))
    # Eksik veride (NaN) koşul sağlanmamış sayılır.
    dogru = dogru & sol.notna() & sag.notna()
    return _son_n(dogru, kosul)


GIRIS_LIMITI_ATR_PERIYODU = 14


def _giris_limiti_dogrula(limit, taban_dk: int) -> None:
    """'giris_limiti': sinyalden sonra fiyatın biraz altına (açığa satışta üstüne) limit emir.

    {"atr_kat": 0.5, "en_az_yuzde": 0.1, "en_fazla_yuzde": 0.6, "sure_dakika": 15}
    Uzaklık = atr_kat x ATR yüzdesi, [en_az, en_fazla] aralığına kırpılır. Emir
    'sure_dakika' içinde dolmazsa iptal edilir.
    """
    if not isinstance(limit, dict):
        raise KuralHatasi("'giris_limiti' bir sözlük olmalı.")
    sayilar = {}
    for alan, (alt, ust) in {"atr_kat": (0.0, 3.0), "en_az_yuzde": (0.0, 2.0),
                             "en_fazla_yuzde": (0.01, 3.0)}.items():
        deger = limit.get(alan)
        if isinstance(deger, bool) or not isinstance(deger, (int, float)) or not alt <= deger <= ust:
            raise KuralHatasi(f"'giris_limiti' içinde '{alan}' {alt} ile {ust} arasında sayı olmalı.")
        sayilar[alan] = float(deger)
    if sayilar["en_az_yuzde"] > sayilar["en_fazla_yuzde"]:
        raise KuralHatasi("'giris_limiti': 'en_az_yuzde', 'en_fazla_yuzde'den büyük olamaz.")
    sure = limit.get("sure_dakika")
    if (not isinstance(sure, int) or isinstance(sure, bool) or not taban_dk <= sure <= 240
            or sure % taban_dk):
        raise KuralHatasi(f"'giris_limiti' içinde 'sure_dakika' {taban_dk} ile 240 arasında ve "
                          f"{taban_dk}'in katı olmalı.")


def giris_limit_yuzde(df: pd.DataFrame, kural: dict) -> pd.Series:
    """Her mumda, o mumun sinyaline konacak limit emrin fiyattan uzaklığı (yüzde).

    Kural 'giris_limiti' tanımlamıyorsa 0 (piyasa emri). Yalnız o mum ve öncesinden
    hesaplanır; ATR henüz oturmadıysa en küçük uzaklık kullanılır.
    """
    limit = kural.get("giris_limiti")
    if not limit:
        return pd.Series(0.0, index=df.index)
    atr = g.atr_yuzde(df, GIRIS_LIMITI_ATR_PERIYODU)
    uzaklik = (float(limit["atr_kat"]) * atr).clip(float(limit["en_az_yuzde"]), float(limit["en_fazla_yuzde"]))
    return uzaklik.fillna(float(limit["en_az_yuzde"]))


def limit_fiyati(fiyat: float, uzaklik_yuzde: float, alim: bool) -> float:
    """Alımda fiyatın uzaklık kadar altı, açığa satışta üstü."""
    oran = float(uzaklik_yuzde) / 100.0
    return float(fiyat) * (1.0 - oran if alim else 1.0 + oran)


def giris_sinyali(df: pd.DataFrame, kural: dict) -> pd.Series:
    """Göstergeleri eklenmiş tabloda giriş koşulunun sağlandığı mumları işaretler."""
    sinyal = _kosul(df, kural["giris"])
    return sinyal.fillna(False).astype(bool)


def cikis_sinyali(df: pd.DataFrame, kural: dict) -> pd.Series:
    """Kural 'cikis > sinyal' tanımlıyorsa çıkış koşulunun sağlandığı mumlar; yoksa hep yanlış.

    Sinyal mumun kapanışında oluşur; işlem bir sonraki mumun açılışında kapanır
    (hazır motor da böyle yapar).
    """
    kosul = kural["cikis"].get("sinyal")
    if kosul is None:
        return pd.Series(False, index=df.index)
    return _kosul(df, kosul).fillna(False).astype(bool)


def sinyal_uret(df: pd.DataFrame, kural: dict, ek_veri: dict | None = None) -> pd.DataFrame:
    """Kısa yol: göstergeleri ekler, 'sinyal' ve 'cikis_sinyal' sütunlarını koyar.

    Çıkışta ATR'ye bağlı stop varsa 'stop_yuzde' sütunu da eklenir: o mumun sinyaliyle
    açılan işlemin stop uzaklığı (bkz. stop_yuzdesi).
    """
    tablo = gosterge_ekle(df, kural, ek_veri)
    tablo["sinyal"] = giris_sinyali(tablo, kural)
    tablo["cikis_sinyal"] = cikis_sinyali(tablo, kural)
    tablo["giris_limit_yuzde"] = giris_limit_yuzde(tablo, kural)
    if kural["cikis"].get("stop_atr"):
        tablo["stop_yuzde"] = stop_yuzdesi(tablo, kural, ek_veri)
    return tablo


STOP_ATR_SUTUNU = "_stop_atr"


def _stop_atr_gostergesi(stop_atr: dict) -> dict:
    tanim = {"tur": "atr_yuzde", "periyot": int(stop_atr.get("periyot", 14))}
    if stop_atr.get("dilim"):
        tanim["dilim"] = stop_atr["dilim"]
    return tanim


def _stop_atr_dogrula(stop_atr, en_fazla, taban_dk: int, bilinen: set | None = None) -> None:
    """'stop_atr': {"kat": 2, "periyot": 14, "dilim": "1h", "en_az_yuzde": 2}.

    İşlem başına stop = kat x ATR yüzdesi (sinyal mumunda), [en_az_yuzde,
    zarar_durdur_yuzde] aralığına kırpılır. 'zarar_durdur_yuzde' en geniş stoptur.

    'seviye' verilirse (bir sütun adı, örnek: son 5 mumun en düşüğü) stop o seviyenin
    'pay' x ATR ötesine konur; kat x ATR ve en_az_yuzde o zaman alt sınırdır.
    """
    if isinstance(stop_atr, dict) and stop_atr.get("seviye") is not None:
        if bilinen is not None and stop_atr["seviye"] not in bilinen:
            raise KuralHatasi("'stop_atr' içinde 'seviye' tanımlı bir sütun olmalı.")
        pay = stop_atr.get("pay", 0.0)
        if isinstance(pay, bool) or not isinstance(pay, (int, float)) or not 0 <= pay <= 5:
            raise KuralHatasi("'stop_atr' içinde 'pay' 0 ile 5 arasında olmalı.")
    if not isinstance(stop_atr, dict):
        raise KuralHatasi("'stop_atr' bir sözlük olmalı.")
    kat = stop_atr.get("kat")
    if isinstance(kat, bool) or not isinstance(kat, (int, float)) or not 0.1 <= kat <= 10:
        raise KuralHatasi("'stop_atr' içinde 'kat' 0,1 ile 10 arasında sayı olmalı.")
    periyot = stop_atr.get("periyot", 14)
    if not isinstance(periyot, int) or isinstance(periyot, bool) or not 1 <= periyot <= 200:
        raise KuralHatasi("'stop_atr' içinde 'periyot' 1 ile 200 arasında tam sayı olmalı.")
    en_az = stop_atr.get("en_az_yuzde")
    if isinstance(en_az, bool) or not isinstance(en_az, (int, float)) or not 0.1 <= en_az <= en_fazla:
        raise KuralHatasi("'stop_atr' içinde 'en_az_yuzde' 0,1 ile 'zarar_durdur_yuzde' arasında olmalı.")
    if stop_atr.get("dilim") is not None:
        _ust_dilim_denetle(stop_atr["dilim"], taban_dk, "'stop_atr': 'dilim'")


def stop_yuzdesi(df: pd.DataFrame, kural: dict, ek_veri: dict | None = None) -> pd.Series:
    """Her mumda, o mumun sinyaliyle açılacak işlemin stop uzaklığı (yüzde).

    ATR'ye bağlı stop yoksa sabit 'zarar_durdur_yuzde'. ATR henüz oturmadıysa en geniş stop.
    'seviye' varsa df göstergeleri içermelidir (sinyal_uret onu göstergeli tabloyla çağırır).
    """
    cikis = kural["cikis"]
    en_fazla = float(cikis["zarar_durdur_yuzde"])
    stop_atr = cikis.get("stop_atr")
    if not stop_atr:
        return pd.Series(en_fazla, index=df.index)
    tablo = _gostergeleri_hesapla(df, kural, {STOP_ATR_SUTUNU: _stop_atr_gostergesi(stop_atr)}, ek_veri)
    atr_yuzde = tablo[STOP_ATR_SUTUNU]
    stop = float(stop_atr["kat"]) * atr_yuzde
    if stop_atr.get("seviye") is not None:
        kapanis = df["close"].astype(float)
        pay = float(stop_atr.get("pay", 0.0)) * atr_yuzde / 100.0 * kapanis
        seviye = df[_sutun_adi(stop_atr["seviye"])].astype(float)
        if kural["yon"] == "alim":
            uzaklik = (kapanis - (seviye - pay)) / kapanis * 100.0
        else:
            uzaklik = ((seviye + pay) - kapanis) / kapanis * 100.0
        stop = np.maximum(stop, uzaklik)
    stop = stop.clip(float(stop_atr["en_az_yuzde"]), en_fazla)
    return stop.fillna(en_fazla)


PORTFOY_ALANLARI = ("en_fazla_pozisyon", "giris_sinirlari", "seri_stop_muaf", "en_az_kayma_yuzde",
                    "coin_gunde_en_fazla", "kayma_aralik_orani")


def _portfoy_dogrula(portfoy) -> None:
    """'portfoy': botun eşzamanlı pozisyon ve giriş sıklığı sınırları (panel sınaması ve canlı).

    {"en_fazla_pozisyon": 4, "giris_sinirlari": [{"saat": 1, "sayi": 2}],
     "seri_stop_muaf": false, "en_az_kayma_yuzde": 0.05}
    """
    if not isinstance(portfoy, dict):
        raise KuralHatasi("'portfoy' bir sözlük olmalı.")
    for alan in portfoy:
        if alan not in PORTFOY_ALANLARI:
            raise KuralHatasi(f"'portfoy' içinde tanınmayan alan: {alan!r}")
    en_fazla = portfoy.get("en_fazla_pozisyon", 5)
    if not isinstance(en_fazla, int) or isinstance(en_fazla, bool) or not 1 <= en_fazla <= 20:
        raise KuralHatasi("'portfoy' içinde 'en_fazla_pozisyon' 1 ile 20 arasında tam sayı olmalı.")
    sinirlar = portfoy.get("giris_sinirlari", [])
    if not isinstance(sinirlar, list):
        raise KuralHatasi("'portfoy' içinde 'giris_sinirlari' bir liste olmalı.")
    for sinir in sinirlar:
        if (not isinstance(sinir, dict) or set(sinir) != {"saat", "sayi"}
                or not all(isinstance(sinir[a], int) and not isinstance(sinir[a], bool) for a in sinir)
                or not 1 <= sinir["saat"] <= 168 or not 1 <= sinir["sayi"] <= 50):
            raise KuralHatasi("'giris_sinirlari' öğeleri {\"saat\": 1-168, \"sayi\": 1-50} biçiminde olmalı.")
    if not _tam_sayi(portfoy.get("coin_gunde_en_fazla", 1), 1, 100):
        raise KuralHatasi("'portfoy' içinde 'coin_gunde_en_fazla' 1 ile 100 arasında tam sayı olmalı.")
    if not isinstance(portfoy.get("seri_stop_muaf", False), bool):
        raise KuralHatasi("'portfoy' içinde 'seri_stop_muaf' doğru / yanlış olmalı.")
    oran = portfoy.get("kayma_aralik_orani", 0.10)
    if isinstance(oran, bool) or not isinstance(oran, (int, float)) or not 0 <= oran <= 1:
        raise KuralHatasi("'portfoy' içinde 'kayma_aralik_orani' 0 ile 1 arasında olmalı.")
    kayma = portfoy.get("en_az_kayma_yuzde", 0.05)
    if isinstance(kayma, bool) or not isinstance(kayma, (int, float)) or not 0 <= kayma <= 1:
        raise KuralHatasi("'portfoy' içinde 'en_az_kayma_yuzde' 0 ile 1 arasında olmalı.")


def bilgi_sinyalleri(tablo: pd.DataFrame, kural: dict) -> dict[str, pd.Series]:
    """Kuralın 'bilgi' koşulları: işlemleri ayırmak için (seçim için değil), ad -> seri."""
    return {ad: _kosul(tablo, kosul).fillna(False).astype(bool)
            for ad, kosul in kural.get("bilgi", {}).items()}


def cikis_metni(cikis: dict) -> str:
    """Çıkış ayarlarının kısa Türkçe anlatımı: 'iz süren stop %1,2'de, %0,3 geriden; stop %3; süre yok'."""
    parcalar = []
    if cikis.get("kar_hedefi_yuzde") is not None:
        parcalar.append(f"hedef %{cikis['kar_hedefi_yuzde']:g}")
    if cikis.get("kar_hedefi_r") is not None:
        parcalar.append(f"hedef stopun {cikis['kar_hedefi_r']:g} katı")
    iz = cikis.get("iz_suren_stop")
    if iz:
        parcalar.append(f"iz süren stop %{iz['tetik_yuzde']:g} kârda başlar, tepeden %{iz['mesafe_yuzde']:g} geride")
    stop_atr = cikis.get("stop_atr")
    if stop_atr:
        dilim = f" {stop_atr['dilim']}" if stop_atr.get("dilim") else ""
        seviye = f" ya da {stop_atr['seviye']} ötesi" if stop_atr.get("seviye") else ""
        parcalar.append(f"stop {stop_atr['kat']:g} x ATR{dilim}{seviye} (%{stop_atr['en_az_yuzde']:g}-"
                        f"%{cikis['zarar_durdur_yuzde']:g})")
    else:
        parcalar.append(f"stop %{cikis['zarar_durdur_yuzde']:g}")
    sure = cikis.get("sure_asimi_dakika")
    parcalar.append(f"süre {sure} dk" if sure is not None else "süre sınırı yok")
    return ", ".join(parcalar).replace(".", ",")


def ozet(kural: dict) -> str:
    """Stratejinin tek satırlık Türkçe özeti (panel ve kayıtlar için)."""
    yon = "alım" if kural["yon"] == "alim" else "açığa satış"
    return f"{kural['kod']} {kural['ad']} ({yon}, {kural['zaman_dilimi']}): {cikis_metni(kural['cikis'])}"


def _iz_suren_stop_dogrula(iz) -> None:
    """'iz_suren_stop': {"tetik_yuzde": 1.2, "mesafe_yuzde": 0.3}.

    Kâr (komisyon düşülmüş) tetik yüzdesine ulaşınca stop, o ana kadarki en iyi fiyatın
    mesafe kadar gerisine çekilir ve yalnız kâr yönünde ilerler.
    """
    if not isinstance(iz, dict):
        raise KuralHatasi("'iz_suren_stop' bir sözlük olmalı.")
    for alan, (alt, ust) in {"tetik_yuzde": (0.1, 20.0), "mesafe_yuzde": (0.05, 10.0)}.items():
        deger = iz.get(alan)
        if isinstance(deger, bool) or not isinstance(deger, (int, float)) or not alt <= deger <= ust:
            raise KuralHatasi(f"'iz_suren_stop' içinde '{alan}' {alt} ile {ust} arasında sayı olmalı.")
    if iz["mesafe_yuzde"] >= iz["tetik_yuzde"]:
        raise KuralHatasi("'iz_suren_stop': 'mesafe_yuzde', 'tetik_yuzde'den küçük olmalı "
                          "(yoksa stop devreye girdiği anda zarara düşer).")


def basabas_orani(kural: dict, gidis_donus_maliyet_yuzde: float) -> float | None:
    """Zarar etmemek için gereken kazanma oranı, yüzde olarak.

    Formül: (stop + maliyet) / (hedef + stop). Sabit kâr hedefi yoksa (iz süren stop)
    kazancın boyu belli değildir; None döner.
    """
    c = kural["cikis"]
    if c.get("kar_hedefi_yuzde") is None:
        return None
    hedef = float(c["kar_hedefi_yuzde"])
    stop = float(c["zarar_durdur_yuzde"])
    return float(np.round((stop + gidis_donus_maliyet_yuzde) / (hedef + stop) * 100.0, 2))
