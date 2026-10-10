"""Gösterge blokları.

Tüm fonksiyonlar "geleceğe bakmaz": bir mumun değeri yalnız o mum ve
öncesindeki veriden hesaplanır. Sütun adları hazır motorun (Freqtrade)
kullandığı adlardır: date, open, high, low, close, volume.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FIYAT_SUTUNLARI = ("open", "high", "low", "close", "volume")

# Kural dosyalarında Türkçe ad da yazılabilsin.
TURKCE_SUTUN = {
    "acilis": "open",
    "yuksek": "high",
    "dusuk": "low",
    "kapanis": "close",
    "hacim": "volume",
}


def dilim_dakika(dilim: str) -> int:
    """'5m', '1h', '4h', '1d' gibi bir zaman dilimini dakikaya çevirir."""
    dilim = dilim.strip().lower()
    birim = dilim[-1]
    try:
        sayi = int(dilim[:-1])
    except ValueError as hata:
        raise ValueError(f"Zaman dilimi anlaşılamadı: {dilim!r}") from hata
    carpan = {"m": 1, "h": 60, "d": 1440}.get(birim)
    if carpan is None or sayi <= 0:
        raise ValueError(f"Zaman dilimi anlaşılamadı: {dilim!r}")
    return sayi * carpan


def ema(seri: pd.Series, periyot: int) -> pd.Series:
    """Üstel hareketli ortalama."""
    return seri.ewm(span=periyot, adjust=False, min_periods=periyot).mean()


def sma(seri: pd.Series, periyot: int) -> pd.Series:
    """Basit hareketli ortalama."""
    return seri.rolling(periyot, min_periods=periyot).mean()


def rsi(kapanis: pd.Series, periyot: int = 14) -> pd.Series:
    """Göreli güç endeksi (Wilder yumuşatması). 0 ile 100 arasındadır."""
    fark = kapanis.diff()
    kazanc = fark.clip(lower=0.0)
    kayip = -fark.clip(upper=0.0)
    ort_kazanc = kazanc.ewm(alpha=1.0 / periyot, adjust=False, min_periods=periyot).mean()
    ort_kayip = kayip.ewm(alpha=1.0 / periyot, adjust=False, min_periods=periyot).mean()
    oran = ort_kazanc / ort_kayip.replace(0.0, np.nan)
    sonuc = 100.0 - 100.0 / (1.0 + oran)
    # Hiç kayıp yoksa RSI 100'dür.
    sonuc = sonuc.where(~((ort_kayip == 0.0) & ort_kazanc.notna()), 100.0)
    return sonuc


def macd(seri: pd.Series, hizli: int = 12, yavas: int = 26, sinyal: int = 9):
    """MACD: (çizgi, sinyal çizgisi, fark).

    çizgi  = hızlı EMA - yavaş EMA
    sinyal = çizginin EMA'sı
    fark   = çizgi - sinyal (histogram); sıfırın üstüne çıkması yukarı ivme demektir.
    """
    cizgi = ema(seri, hizli) - ema(seri, yavas)
    sinyal_cizgisi = cizgi.ewm(span=sinyal, adjust=False, min_periods=sinyal).mean()
    return cizgi, sinyal_cizgisi, cizgi - sinyal_cizgisi


def bollinger(kapanis: pd.Series, periyot: int = 20, sapma: float = 2.0):
    """Bollinger bandı: (üst, orta, alt)."""
    orta = sma(kapanis, periyot)
    std = kapanis.rolling(periyot, min_periods=periyot).std(ddof=0)
    return orta + sapma * std, orta, orta - sapma * std


def atr(df: pd.DataFrame, periyot: int = 14) -> pd.Series:
    """Ortalama gerçek aralık (Wilder yumuşatması)."""
    onceki = df["close"].shift(1)
    gercek_aralik = pd.concat(
        [df["high"] - df["low"], (df["high"] - onceki).abs(), (df["low"] - onceki).abs()],
        axis=1,
    ).max(axis=1)
    return gercek_aralik.ewm(alpha=1.0 / periyot, adjust=False, min_periods=periyot).mean()


def atr_yuzde(df: pd.DataFrame, periyot: int = 14) -> pd.Series:
    """ATR'nin kapanış fiyatına oranı, yüzde olarak."""
    return atr(df, periyot) / df["close"] * 100.0


def vwap_gunluk(df: pd.DataFrame) -> pd.Series:
    """Gün içi hacim ağırlıklı ortalama fiyat. Her UTC gününde sıfırlanır."""
    gun = pd.to_datetime(df["date"], utc=True).dt.floor("D")
    tipik = (df["high"] + df["low"] + df["close"]) / 3.0
    pay = (tipik * df["volume"]).groupby(gun).cumsum()
    payda = df["volume"].groupby(gun).cumsum()
    return pay / payda.replace(0.0, np.nan)


def en_yuksek(seri: pd.Series, periyot: int) -> pd.Series:
    """Son N mumun en yükseği (bu mum dahil)."""
    return seri.rolling(periyot, min_periods=periyot).max()


def en_dusuk(seri: pd.Series, periyot: int) -> pd.Series:
    """Son N mumun en düşüğü (bu mum dahil)."""
    return seri.rolling(periyot, min_periods=periyot).min()


def degisim_yuzde(seri: pd.Series, periyot: int) -> pd.Series:
    """N mum önceye göre yüzde değişim."""
    return (seri / seri.shift(periyot) - 1.0) * 100.0


def ust_dilime_cevir(df: pd.DataFrame, taban_dilim: str, ust_dilim: str) -> pd.DataFrame:
    """Taban zaman dilimindeki mumları daha büyük bir dilime toplar.

    Dönen tablonun 'date' sütunu, üst dilim mumunun AÇILIŞ zamanıdır.
    """
    taban_dk = dilim_dakika(taban_dilim)
    ust_dk = dilim_dakika(ust_dilim)
    if ust_dk <= taban_dk or ust_dk % taban_dk != 0:
        raise ValueError(
            f"Üst dilim ({ust_dilim}) taban dilimin ({taban_dilim}) tam katı ve ondan büyük olmalı."
        )
    gecici = df[["date", "open", "high", "low", "close", "volume"]].copy()
    gecici["date"] = pd.to_datetime(gecici["date"], utc=True)
    toplu = (
        gecici.set_index("date")
        .resample(f"{ust_dk}min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
        .reset_index()
    )
    return toplu


def ust_dilimden_hizala(
    ust_seri: pd.Series,
    ust_tarih: pd.Series,
    taban_tarih: pd.Series,
    taban_dilim: str,
    ust_dilim: str,
) -> pd.Series:
    """Üst dilimde hesaplanmış bir göstergeyi taban dilime taşır.

    Geleceğe bakmamak için, saat 10:00'da açılan 1 saatlik mumun değeri ancak
    o mum kapandığında, yani 10:55'te açılan 5 dakikalık mumda kullanılabilir.
    """
    kayma = pd.Timedelta(minutes=dilim_dakika(ust_dilim) - dilim_dakika(taban_dilim))
    hazir = pd.Series(
        ust_seri.to_numpy(),
        index=pd.to_datetime(ust_tarih, utc=True) + kayma,
    )
    hedef = pd.to_datetime(taban_tarih, utc=True)
    hizali = hazir.reindex(pd.DatetimeIndex(hedef), method="ffill")
    return pd.Series(hizali.to_numpy(), index=taban_tarih.index)
