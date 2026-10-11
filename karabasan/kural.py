"""Kural dosyası motoru.

Bir strateji kod değil, bir kural dosyasıdır (JSON). Bu modül dosyayı okur,
doğrular, göstergeleri hesaplar ve giriş sinyalini üretir.

Kural dosyasının biçimi için: karabasan/stratejiler/ klasöründeki örneklere
ve README.md içindeki "Strateji dosyası" bölümüne bakın.
"""

from __future__ import annotations

import json
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
)
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
        # Emekli kurallar koduyla da okunur (eski raporlar, karşılaştırmalar, testler);
        # hangi botların çalıştığını yalnız botlar.BOTLAR belirler.
        if not yol.exists() and (STRATEJI_KLASORU / "emekli" / yol.name).exists():
            yol = STRATEJI_KLASORU / "emekli" / yol.name
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


def ek_veri_topla(kural: dict, yukle) -> tuple[dict, list[str]]:
    """Kuralın borsadan ayrıca istediği dilimlerin mumlarını toplar.

    yukle(dilim) bir mum tablosu ya da None döndürür. Dönen ikili:
    ({dilim: tablo}, bulunamayan dilimler). Bulunamayan dilim sözlükte yer almaz,
    yani taban mumlardan toplanır (bkz. gosterge_ekle); sonuç o zaman motorunkiyle
    birebir tutmaz, çünkü motor verisi olmayan dilimde hiç sinyal üretmez.
    """
    ek, eksik = {}, []
    for dilim in borsa_dilimleri(kural):
        tablo = yukle(dilim)
        if tablo is None or len(tablo) == 0:
            eksik.append(dilim)
        else:
            ek[dilim] = tablo
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
    # Her üst dilimin kendi sütunları: bir gösterge yalnız kendi dilimindeki bir kaynağı kullanabilir.
    dilim_bilinen: dict[str | None, set] = {None: bilinen}
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
        elif tur != "vwap":
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
        gecerli = dilim_bilinen.setdefault(dilim, set(fiyatlar))
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
    for alan in ("kar_hedefi_yuzde", "zarar_durdur_yuzde", "sure_asimi_dakika"):
        if alan not in cikis:
            raise KuralHatasi(f"'cikis' içinde zorunlu alan eksik: '{alan}'")
        _sinir_denetle(alan, cikis[alan])
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

    for durum in kural.get("izinli_durumlar", []):
        if durum not in DURUMLAR:
            raise KuralHatasi(f"'izinli_durumlar' içinde tanınmayan durum: {durum!r}")

    ihtiyac = gereken_mum(kural, sinirla=False)
    if ihtiyac > EN_FAZLA_BASLANGIC_MUMU:
        raise KuralHatasi(
            f"Bu kural {ihtiyac} başlangıç mumu istiyor; sınır {EN_FAZLA_BASLANGIC_MUMU}. "
            "Üst dilimdeki göstergelerin periyodunu küçültün ya da taban dilimi büyütün."
        )


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


def _mum_ihtiyaclari(kural: dict) -> tuple[int, dict[str, int]]:
    """(taban dilimde gereken mum, borsadan istenen her dilim için o dilimde gereken mum)."""
    taban_dk = g.dilim_dakika(kural["zaman_dilimi"])
    borsadan = set(borsa_dilimleri(kural))
    ihtiyaclar: dict[str, int] = {}      # sütun -> kendi hesaplandığı ölçüde ihtiyaç
    taban_ihtiyac, ek_ihtiyac = [50], {}
    for ad, tanim in kural["gostergeler"].items():
        periyot = int(tanim.get("periyot", 0))
        # Üstel ortalamalar yaklaşık üç periyotta oturur.
        kat = 3 if tanim["tur"] in ("ema", "rsi", "atr_yuzde") else 1
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
        if tanim["tur"] == "uyumsuzluk":
            # En eski karşılaştırılan nokta + göstergelerin (MACD, RSI...) oturması.
            ihtiyac = g.UYUMSUZLUK_EN_FAZLA_MUM + periyot + (26 + 9) * 3
        if tanim["tur"] == "yapi":
            # Yapı, veri nereden başlarsa başlasın aynı yere otursun: salınımların ve yönün
            # yeniden kurulması, üstüne en eski geçerli bloğun ömrü.
            ihtiyac = max(30 * periyot, _yapi_omru(tanim) + 10 * periyot)
        dilim = gosterge_dilimi(kural, tanim)
        borsadan_mi = dilim in borsadan
        if dilim and not borsadan_mi:
            ihtiyac *= g.dilim_dakika(dilim) // taban_dk
        # Başka bir göstergeden türeyen gösterge, kaynağının ihtiyacını da taşır.
        ihtiyac += ihtiyaclar.get(tanim.get("kaynak"), 0)
        for sutun in _gosterge_sutunlari(ad, tanim):
            ihtiyaclar[sutun] = ihtiyac
        if borsadan_mi:
            ek_ihtiyac[dilim] = max(ek_ihtiyac.get(dilim, 0), ihtiyac + 10)
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


def _tek_gosterge(cerceve: pd.DataFrame, ad: str, tanim: dict) -> dict:
    """Tek bir göstergeyi verilen çerçevede hesaplar; sütun adı -> seri döndürür."""
    tur = tanim["tur"]
    periyot = tanim.get("periyot")
    if tur == "vwap":
        return {ad: g.vwap_gunluk(cerceve)}
    if tur == "atr_yuzde":
        return {ad: g.atr_yuzde(cerceve, periyot)}
    if tur == "hacim_ort":
        return {ad: g.sma(cerceve["volume"], periyot)}
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


def gosterge_ekle(df: pd.DataFrame, kural: dict, ek_veri: dict | None = None) -> pd.DataFrame:
    """Kuraldaki tüm göstergeleri hesaplayıp tabloya sütun olarak ekler.

    ek_veri: {dilim: mum tablosu}. 'borsa_dilimleri' içindeki bir dilimin borsadan
    gelen mumları buradan verilir (örnek: {"1d": günlük mumlar}). Sözlükte hiç yer
    almayan dilim taban mumlardan toplanır (geçmiş veriyle çalışan araçlar ve testler
    için; eldeki taban veri kısaysa göstergeler boş kalır). Boş tablo verilen dilim
    toplanmaz: göstergeleri boş kalır ve kural sinyal üretmez.

    Girdi tablosu değiştirilmez; yeni bir tablo döner.
    """
    sonuc = df.copy()
    taban = kural["zaman_dilimi"]
    gost = kural["gostergeler"]

    # 1) Üst dilim göstergeleri: kendi dilimlerinin tablosunda hesaplanır, sonra hizalanır.
    gruplar: dict[str, dict] = {}
    for ad, tanim in gost.items():
        dilim = gosterge_dilimi(kural, tanim)
        if dilim:
            gruplar.setdefault(dilim, {})[ad] = tanim
    for dilim, tanimlar in gruplar.items():
        ust_tablo = _ust_tablo(df, taban, dilim, ek_veri)
        for ad, tanim in tanimlar.items():
            for sutun, seri in _tek_gosterge(ust_tablo, ad, tanim).items():
                ust_tablo[sutun] = seri
                sonuc[sutun] = g.ust_dilimden_hizala(
                    seri, ust_tablo["date"], df["date"], taban, dilim
                )

    # 2) Taban dilim göstergeleri.
    for ad, tanim in gost.items():
        if gosterge_dilimi(kural, tanim):
            continue
        for sutun, seri in _tek_gosterge(sonuc, ad, tanim).items():
            sonuc[sutun] = seri
    return sonuc


def _islenen(df: pd.DataFrame, islenen) -> pd.Series:
    if isinstance(islenen, (int, float)):
        return pd.Series(float(islenen), index=df.index)
    if isinstance(islenen, str):
        return df[_sutun_adi(islenen)].astype(float)
    seri = df[_sutun_adi(islenen["ad"])].astype(float)
    kaydir = int(islenen.get("kaydir", 0))
    if kaydir:
        seri = seri.shift(kaydir)
    return seri * float(islenen.get("carpan", 1.0))


def _kosul(df: pd.DataFrame, kosul: dict) -> pd.Series:
    if "hepsi" in kosul:
        sonuc = pd.Series(True, index=df.index)
        for parca in kosul["hepsi"]:
            sonuc &= _kosul(df, parca)
        return sonuc
    if "herhangi" in kosul:
        sonuc = pd.Series(False, index=df.index)
        for parca in kosul["herhangi"]:
            sonuc |= _kosul(df, parca)
        return sonuc

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

    son_n = int(kosul.get("son_n_mumda", 1))
    if son_n > 1:
        dogru = dogru.astype(float).rolling(son_n, min_periods=1).max() > 0
    return dogru.astype(bool)


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
    """Kısa yol: göstergeleri ekler, 'sinyal' ve 'cikis_sinyal' sütunlarını koyar."""
    tablo = gosterge_ekle(df, kural, ek_veri)
    tablo["sinyal"] = giris_sinyali(tablo, kural)
    tablo["cikis_sinyal"] = cikis_sinyali(tablo, kural)
    tablo["giris_limit_yuzde"] = giris_limit_yuzde(tablo, kural)
    return tablo


def ozet(kural: dict) -> str:
    """Stratejinin tek satırlık Türkçe özeti (panel ve kayıtlar için)."""
    c = kural["cikis"]
    yon = "alım" if kural["yon"] == "alim" else "açığa satış"
    return (
        f"{kural['kod']} {kural['ad']} ({yon}, {kural['zaman_dilimi']}): "
        f"hedef %{c['kar_hedefi_yuzde']:g}, stop %{c['zarar_durdur_yuzde']:g}, "
        f"süre {c['sure_asimi_dakika']} dk"
    )


def basabas_orani(kural: dict, gidis_donus_maliyet_yuzde: float) -> float:
    """Zarar etmemek için gereken kazanma oranı, yüzde olarak.

    Formül: (stop + maliyet) / (hedef + stop)
    """
    c = kural["cikis"]
    hedef = float(c["kar_hedefi_yuzde"])
    stop = float(c["zarar_durdur_yuzde"])
    return float(np.round((stop + gidis_donus_maliyet_yuzde) / (hedef + stop) * 100.0, 2))
