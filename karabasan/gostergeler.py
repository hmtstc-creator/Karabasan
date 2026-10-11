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
    birim = dilim[-1:]   # boş metinde de hata "anlaşılamadı" olsun
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


# piyasa_yapisi'nin ürettiği sütunlar (kural dosyasında "<ad>_<sütun>" diye geçer).
YAPI_SUTUNLARI = (
    "yon",        # son kırılımın yönü: +1 yukarı, -1 aşağı, 0 henüz kırılım yok
    "kirilim",    # bu mumda yapı kırıldıysa +1 (yukarı) ya da -1 (aşağı), yoksa 0
    "donus",      # kırılım aynı zamanda yön değişimiyse (CHoCH) +1 ya da -1, yoksa 0
    "tepe",       # son onaylanmış salınım tepesinin fiyatı
    "dip",        # son onaylanmış salınım dibinin fiyatı
    "denge",      # son tepe ile son dip arasındaki aralığın orta noktası
    "blok_ust",   # en yeni geçerli alım bloğunun üst sınırı (yoksa boş)
    "blok_alt",   # en yeni geçerli alım bloğunun alt sınırı
    "sblok_ust",  # en yeni geçerli satış bloğunun üst sınırı
    "sblok_alt",  # en yeni geçerli satış bloğunun alt sınırı
)


def piyasa_yapisi(df: pd.DataFrame, uzunluk: int = 5, blok_omru: int | None = None) -> pd.DataFrame:
    """Piyasa yapısı ("akıllı para" kavramları): salınımlar, yapı kırılımı, emir blokları.

    Yaygın bilinen kavramların (BOS, CHoCH, order block, premium / discount) bu
    depo için yazılmış bağımsız bir uygulamasıdır. Kurallar:

    Salınım:  bir mumun yükseği, kendisinden sonraki `uzunluk` mumun hepsinden
              yüksekse tepe; düşüğü hepsinden düşükse diptir. Tepe ve dip
              sırayla gelir (iki tepe arasında bir dip). Bir salınım ancak
              `uzunluk` mum sonra, yani onaylandığı mumda bilinir.
    Kırılım:  mum, son tepenin üstünde kapanırsa yapı yukarı kırılmıştır; son
              dibin altında kapanırsa aşağı. Her tepe ya da dip bir kez kırılır.
              Kırılım önceki yönle aynıysa devamdır (BOS), tersiyse dönüştür
              (CHoCH); "donus" sütunu yalnız ikincisini işaretler.
    Denge:    son tepeden beri görülen en yüksek ile son dipten beri görülen en
              düşük fiyatın ortası. Fiyat bunun altındaysa "indirimli",
              üstündeyse "pahalı" bölgededir.
    Alım bloğu: yukarı kırılımda, kırılan tepe ile kırılım arasındaki en düşük
              mumun aralığı (hareketin başladığı mum). Fiyat bloğun altına
              sarkarsa ya da blok `blok_omru` mumdan eskiyse geçersiz olur.
              Satış bloğu bunun tersidir. Aşırı geniş mumlar (aralığı son
              `blok_omru` mumun ortalamasının 2 katı ve üstü) blok seçilmez.

    Geleceğe bakmaz: her mumun değeri yalnız o mum ve öncesinden hesaplanır.
    """
    u = int(uzunluk)
    if u < 1:
        raise ValueError("uzunluk en az 1 olmalı.")
    omur = int(blok_omru) if blok_omru else 20 * u
    n = len(df)
    yuksek_s = df["high"].astype(float)
    dusuk_s = df["low"].astype(float)
    yuksek = yuksek_s.tolist()
    dusuk = dusuk_s.tolist()
    kapanis = df["close"].astype(float).tolist()
    # Adaydan sonraki `uzunluk` mumun en yükseği / en düşüğü (bu mum dahil).
    sonraki_tepe = yuksek_s.rolling(u, min_periods=u).max().tolist()
    sonraki_dip = dusuk_s.rolling(u, min_periods=u).min().tolist()
    aralik = yuksek_s - dusuk_s
    ort_aralik = aralik.rolling(omur, min_periods=omur).mean()
    genis = (aralik >= 2.0 * ort_aralik).fillna(False).tolist()

    bos = float("nan")
    cikti = {ad: [bos] * n for ad in YAPI_SUTUNLARI}
    for ad in ("yon", "kirilim", "donus"):
        cikti[ad] = [0.0] * n

    bacak = -1                      # 0 düşüş bacağı, 1 yükseliş bacağı, -1 henüz belli değil
    yon = 0.0
    tepe = dip = ust = alt = bos
    tepe_i = dip_i = -1
    tepe_kirildi = dip_kirildi = True
    alim_bloklari: list[tuple] = []   # (üst, alt, oluştuğu mum)
    satis_bloklari: list[tuple] = []

    for i in range(n):
        # 1) Aralık: son tepeden beri en yüksek, son dipten beri en düşük.
        if ust == ust and yuksek[i] > ust:
            ust = yuksek[i]
        if alt == alt and dusuk[i] < alt:
            alt = dusuk[i]

        # 2) `uzunluk` mum önceki mum bir salınım noktası mıydı?
        if i >= u:
            a = i - u
            yeni = bacak
            if yuksek[a] > sonraki_tepe[i]:
                yeni = 0
            elif dusuk[a] < sonraki_dip[i]:
                yeni = 1
            if yeni != bacak:
                bacak = yeni
                if yeni == 1:
                    dip, dip_i, dip_kirildi = dusuk[a], a, False
                    alt = dusuk[a]
                else:
                    tepe, tepe_i, tepe_kirildi = yuksek[a], a, False
                    ust = yuksek[a]

        # 3) Yapı kırılımı ve kırılımın çıktığı mumdan emir bloğu.
        if not tepe_kirildi and kapanis[i] > tepe:
            cikti["kirilim"][i] = 1.0
            if yon < 0:
                cikti["donus"][i] = 1.0
            tepe_kirildi, yon = True, 1.0
            aday = [j for j in range(tepe_i, i) if not genis[j]]
            if aday:
                j = min(aday, key=dusuk.__getitem__)
                alim_bloklari.append((yuksek[j], dusuk[j], i))
        elif not dip_kirildi and kapanis[i] < dip:
            cikti["kirilim"][i] = -1.0
            if yon > 0:
                cikti["donus"][i] = -1.0
            dip_kirildi, yon = True, -1.0
            aday = [j for j in range(dip_i, i) if not genis[j]]
            if aday:
                j = max(aday, key=yuksek.__getitem__)
                satis_bloklari.append((yuksek[j], dusuk[j], i))

        # 4) Delinen ya da eskiyen bloklar düşer.
        if alim_bloklari:
            alim_bloklari = [b for b in alim_bloklari if dusuk[i] >= b[1] and i - b[2] <= omur]
        if satis_bloklari:
            satis_bloklari = [b for b in satis_bloklari if yuksek[i] <= b[0] and i - b[2] <= omur]

        # 5) Bu mumun değerleri.
        cikti["yon"][i] = yon
        cikti["tepe"][i] = tepe
        cikti["dip"][i] = dip
        if ust == ust and alt == alt:
            cikti["denge"][i] = (ust + alt) / 2.0
        if alim_bloklari:
            cikti["blok_ust"][i], cikti["blok_alt"][i] = alim_bloklari[-1][0], alim_bloklari[-1][1]
        if satis_bloklari:
            cikti["sblok_ust"][i], cikti["sblok_alt"][i] = satis_bloklari[-1][0], satis_bloklari[-1][1]

    return pd.DataFrame(cikti, index=df.index)


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
