"""Testler için yapay mum verisi üretir. Gerçek piyasa verisi değildir."""

import numpy as np
import pandas as pd


def yapay_mumlar(adet=3000, dilim_dk=5, tohum=1, baslangic="2026-01-01", fiyat=100.0,
                 oynaklik=0.002, egim=0.0):
    """Rastgele yürüyüşle mum üretir. Aynı tohum her zaman aynı veriyi verir."""
    rng = np.random.default_rng(tohum)
    getiri = rng.normal(egim, oynaklik, adet)
    kapanis = fiyat * np.exp(np.cumsum(getiri))
    acilis = np.concatenate([[fiyat], kapanis[:-1]])
    fitil = np.abs(rng.normal(0, oynaklik / 2, adet))
    yuksek = np.maximum(acilis, kapanis) * (1 + fitil)
    dusuk = np.minimum(acilis, kapanis) * (1 - fitil)
    hacim = rng.lognormal(mean=6.0, sigma=0.6, size=adet)
    tarih = pd.date_range(baslangic, periods=adet, freq=f"{dilim_dk}min", tz="UTC")
    return pd.DataFrame({"date": tarih, "open": acilis, "high": yuksek, "low": dusuk,
                         "close": kapanis, "volume": hacim})


def duz_mumlar(fiyatlar, dilim_dk=5, baslangic="2026-01-01", hacim=100.0):
    """Verilen (açılış, yüksek, düşük, kapanış) dörtlülerinden mum tablosu kurar."""
    tarih = pd.date_range(baslangic, periods=len(fiyatlar), freq=f"{dilim_dk}min", tz="UTC")
    tablo = pd.DataFrame(fiyatlar, columns=["open", "high", "low", "close"]).astype(float)
    tablo.insert(0, "date", tarih)
    tablo["volume"] = hacim
    return tablo
