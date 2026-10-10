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
)

# Panelden ya da dosyadan aşılamayan sınırlar. Bir yazım hatası (örneğin
# %1 yerine %100 stop) gerçek paraya ulaşmadan burada durur.
SINIRLAR = {
    "kar_hedefi_yuzde": (0.1, 20.0),
    "zarar_durdur_yuzde": (0.1, 10.0),
    "sure_asimi_dakika": (5, 10080),
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
    return [ad]


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

    # Göstergeler
    gost = kural["gostergeler"]
    if not isinstance(gost, dict):
        raise KuralHatasi("'gostergeler' bir sözlük olmalı.")
    bilinen = set(g.FIYAT_SUTUNLARI) | set(g.TURKCE_SUTUN)
    ust_bilinen = set(bilinen)
    for ad, tanim in gost.items():
        if not ad.isidentifier() or ad in bilinen:
            raise KuralHatasi(f"Gösterge adı uygun değil ya da çakışıyor: {ad!r}")
        if not isinstance(tanim, dict) or tanim.get("tur") not in GOSTERGE_TURLERI:
            raise KuralHatasi(
                f"'{ad}' göstergesinin türü şunlardan biri olmalı: {', '.join(GOSTERGE_TURLERI)}"
            )
        tur = tanim["tur"]
        ust_mu = tanim.get("dilim") == "ust"
        if tanim.get("dilim") not in (None, "ust", "taban"):
            raise KuralHatasi(f"'{ad}': 'dilim' yalnız 'ust' ya da 'taban' olabilir.")
        if ust_mu and ust is None:
            raise KuralHatasi(f"'{ad}' üst dilimde tanımlı ama 'ust_zaman_dilimi' verilmemiş.")
        if tur != "vwap":
            periyot = tanim.get("periyot")
            if not isinstance(periyot, int) or isinstance(periyot, bool) or not 1 <= periyot <= 1000:
                raise KuralHatasi(f"'{ad}': 'periyot' 1 ile 1000 arasında tam sayı olmalı.")
        if tur == "vwap" and ust_mu:
            raise KuralHatasi(f"'{ad}': VWAP yalnız taban dilimde hesaplanır.")
        if tur == "bollinger":
            sapma = tanim.get("sapma", 2.0)
            if not isinstance(sapma, (int, float)) or not 0.1 <= sapma <= 10:
                raise KuralHatasi(f"'{ad}': 'sapma' 0,1 ile 10 arasında olmalı.")
        kaynak = tanim.get("kaynak")
        if kaynak is not None:
            gecerli = ust_bilinen if ust_mu else bilinen
            if kaynak not in gecerli:
                raise KuralHatasi(
                    f"'{ad}': kaynak '{kaynak}' tanımlı değil. Kaynak bir fiyat sütunu ya da "
                    "daha önce tanımlanmış, aynı dilimdeki bir gösterge olmalı."
                )
        for sutun in _gosterge_sutunlari(ad, tanim):
            bilinen.add(sutun)
            if ust_mu:
                ust_bilinen.add(sutun)

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

    for durum in kural.get("izinli_durumlar", []):
        if durum not in DURUMLAR:
            raise KuralHatasi(f"'izinli_durumlar' içinde tanınmayan durum: {durum!r}")

    ihtiyac = gereken_mum(kural, sinirla=False)
    if ihtiyac > EN_FAZLA_BASLANGIC_MUMU:
        raise KuralHatasi(
            f"Bu kural {ihtiyac} başlangıç mumu istiyor; sınır {EN_FAZLA_BASLANGIC_MUMU}. "
            "Üst dilimdeki göstergelerin periyodunu küçültün ya da taban dilimi büyütün."
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


def gereken_mum(kural: dict, sinirla: bool = True) -> int:
    """Göstergelerin oturması için gereken başlangıç mumu sayısı (taban dilimde)."""
    taban_dk = g.dilim_dakika(kural["zaman_dilimi"])
    ust = kural.get("ust_zaman_dilimi")
    oran = g.dilim_dakika(ust) // taban_dk if ust else 1
    ihtiyaclar: dict[str, int] = {}
    for ad, tanim in kural["gostergeler"].items():
        periyot = int(tanim.get("periyot", 0))
        # Üstel ortalamalar yaklaşık üç periyotta oturur.
        kat = 3 if tanim["tur"] in ("ema", "rsi", "atr_yuzde") else 1
        ihtiyac = periyot * kat
        if tanim["tur"] == "vwap":
            ihtiyac = 1440 // taban_dk
        if tanim.get("dilim") == "ust":
            ihtiyac *= oran
        # Başka bir göstergeden türeyen gösterge, kaynağının ihtiyacını da taşır.
        ihtiyac += ihtiyaclar.get(tanim.get("kaynak"), 0)
        sutunlar = _gosterge_sutunlari(ad, tanim)
        for sutun in sutunlar:
            ihtiyaclar[sutun] = ihtiyac
    en_cok = max([50, *ihtiyaclar.values()]) + 10
    return min(en_cok, EN_FAZLA_BASLANGIC_MUMU) if sinirla else en_cok


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
    raise KuralHatasi(f"Tanınmayan gösterge türü: {tur}")


def gosterge_ekle(df: pd.DataFrame, kural: dict) -> pd.DataFrame:
    """Kuraldaki tüm göstergeleri hesaplayıp tabloya sütun olarak ekler.

    Girdi tablosu değiştirilmez; yeni bir tablo döner.
    """
    sonuc = df.copy()
    taban = kural["zaman_dilimi"]
    ust = kural.get("ust_zaman_dilimi")
    gost = kural["gostergeler"]

    # 1) Üst dilim göstergeleri: üst dilim tablosunda hesaplanır, sonra hizalanır.
    ust_tanimlar = {ad: t for ad, t in gost.items() if t.get("dilim") == "ust"}
    if ust_tanimlar:
        ust_tablo = g.ust_dilime_cevir(df, taban, ust)
        for ad, tanim in ust_tanimlar.items():
            for sutun, seri in _tek_gosterge(ust_tablo, ad, tanim).items():
                ust_tablo[sutun] = seri
                sonuc[sutun] = g.ust_dilimden_hizala(
                    seri, ust_tablo["date"], df["date"], taban, ust
                )

    # 2) Taban dilim göstergeleri.
    for ad, tanim in gost.items():
        if tanim.get("dilim") == "ust":
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


def giris_sinyali(df: pd.DataFrame, kural: dict) -> pd.Series:
    """Göstergeleri eklenmiş tabloda giriş koşulunun sağlandığı mumları işaretler."""
    sinyal = _kosul(df, kural["giris"])
    return sinyal.fillna(False).astype(bool)


def sinyal_uret(df: pd.DataFrame, kural: dict) -> pd.DataFrame:
    """Kısa yol: göstergeleri ekler ve 'sinyal' sütununu koyar."""
    tablo = gosterge_ekle(df, kural)
    tablo["sinyal"] = giris_sinyali(tablo, kural)
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
