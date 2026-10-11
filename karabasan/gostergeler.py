"""Gösterge blokları.

Tüm fonksiyonlar "geleceğe bakmaz": bir mumun değeri yalnız o mum ve
öncesindeki veriden hesaplanır. Sütun adları hazır motorun (Freqtrade)
kullandığı adlardır: date, open, high, low, close, volume.
"""

from __future__ import annotations

import bisect
import math

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


# --------------------------------------------------------------------------
# Uyumsuzluk (divergence)
# --------------------------------------------------------------------------
#
# Kavram, Ahmet'in gönderdiği TradingView göstergesinden ("Divergence for Many
# Indicators v4", LonesomeTheBlue, MPL 2.0) alındı; kod kopyalanmadı, aynı fikir
# burada baştan yazıldı. Fiyat yeni bir dip yaparken göstergenin dip yapmaması
# (ya da tersi) uyumsuzluktur:
#
#   normal boğa:  fiyat daha düşük dip, gösterge daha yüksek dip (dönüş işareti)
#   gizli boğa:   fiyat daha yüksek dip, gösterge daha düşük dip (trendin sürmesi)
#   ayı tarafı:   aynısı tepelerle, ters yönde.
#
# Dipler / tepeler kapanış fiyatının salınım noktalarıdır (her iki yanında 'uzunluk'
# mum). Bir salınım noktası ancak 'uzunluk' mum sonra kesinleşir; bir mumdaki sonuç
# yalnız o mumda kesinleşmiş noktaları kullanır (geleceğe bakmaz). Karşılaştırma bir
# önceki mumla yapılır, son mum gösterge ya da fiyatın o yöne dönmesiyle onaylar.
# İki nokta arasında ne fiyat ne gösterge, iki noktayı birleştiren doğrunun öbür
# yanına geçmemelidir (aradaki hareket "temiz" olmalı).

UYUMSUZLUK_GOSTERGELERI = ("macd", "macd_fark", "rsi", "stokastik", "cci", "momentum",
                           "obv", "hacimli_macd", "cmf", "mfi")
UYUMSUZLUK_EN_FAZLA_MUM = 100      # en eski salınım noktası bu kadar mum geride olabilir
UYUMSUZLUK_EN_FAZLA_NOKTA = 10     # en yeni kaç salınım noktasına bakılır
UYUMSUZLUK_EN_AZ_MUM = 5           # iki nokta arası en az bu kadar mum


def _uyumsuzluk_gostergeleri(df: pd.DataFrame) -> dict[str, np.ndarray]:
    k, y, d, h = df["close"], df["high"], df["low"], df["volume"]
    cizgi, _sinyal, fark = macd(k, 12, 26, 9)
    en_dusuk14, en_yuksek14 = d.rolling(14).min(), y.rolling(14).max()
    stok = (100.0 * (k - en_dusuk14) / (en_yuksek14 - en_dusuk14).replace(0, np.nan)).rolling(3).mean()
    tipik = (y + d + k) / 3.0
    sapma = tipik.rolling(10).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    cci = (tipik - tipik.rolling(10).mean()) / (0.015 * sapma.replace(0, np.nan))
    yon = np.sign(k.diff().fillna(0.0))
    obv = (yon * h).cumsum()
    hacimli = (k * h).rolling(12).sum() / h.rolling(12).sum() - (k * h).rolling(26).sum() / h.rolling(26).sum()
    aralik = (y - d).replace(0, np.nan)
    cmf_carpan = (((k - d) - (y - k)) / aralik).fillna(0.0)
    cmf = (cmf_carpan * h).rolling(21).sum() / h.rolling(21).sum().replace(0, np.nan)
    para = tipik * h
    artan = para.where(tipik > tipik.shift(1), 0.0).rolling(14).sum()
    azalan = para.where(tipik < tipik.shift(1), 0.0).rolling(14).sum()
    mfi = 100.0 - 100.0 / (1.0 + artan / azalan.replace(0, np.nan))
    seriler = {"macd": cizgi, "macd_fark": fark, "rsi": rsi(k, 14), "stokastik": stok, "cci": cci,
               "momentum": k - k.shift(10), "obv": obv, "hacimli_macd": hacimli, "cmf": cmf, "mfi": mfi}
    return {ad: seriler[ad].to_numpy(dtype=float) for ad in UYUMSUZLUK_GOSTERGELERI}


def _salinim_noktalari(kapanis: np.ndarray, uzunluk: int) -> tuple[list[int], list[int]]:
    """Kapanışın dip ve tepe noktaları (sıra numaraları). Nokta p, p + uzunluk mumunda kesinleşir."""
    dipler, tepeler = [], []
    for p in range(uzunluk, len(kapanis) - uzunluk):
        sol = kapanis[p - uzunluk:p]
        sag = kapanis[p + 1:p + uzunluk + 1]
        deger = kapanis[p]
        if deger < sol.min() and deger <= sag.min():
            dipler.append(p)
        if deger > sol.max() and deger >= sag.max():
            tepeler.append(p)
    return dipler, tepeler


def _temiz_mi(seri: list, p: int, s: int, boga: bool) -> bool:
    """p ile s arasındaki mumlar, iki noktayı birleştiren doğrunun öbür yanına geçmiyor mu?"""
    egim = (seri[s] - seri[p]) / (s - p)
    for i in range(p + 1, s):
        dogru = seri[p] + egim * (i - p)
        if (seri[i] < dogru) if boga else (seri[i] > dogru):
            return False
    return True


def uyumsuzluk(df: pd.DataFrame, uzunluk: int = 5, tip: str = "ikisi") -> pd.DataFrame:
    """Her mum için boğa ve ayı uyumsuzluğu gösteren gösterge sayısı (0-10).

    tip: "normal", "gizli" ya da "ikisi".
    Dönen tablo: 'boga', 'ayi' sütunları.
    """
    kapanis_dizi = df["close"].to_numpy(dtype=float)
    n = len(kapanis_dizi)
    dipler, tepeler = _salinim_noktalari(kapanis_dizi, uzunluk)
    # Mum mum döngüde düz liste numpy dizisinden çok daha hızlı.
    kapanis = kapanis_dizi.tolist()
    gostergeler = {ad: seri.tolist() for ad, seri in _uyumsuzluk_gostergeleri(df).items()}
    normal = tip in ("normal", "ikisi")
    gizli = tip in ("gizli", "ikisi")
    boga = np.zeros(n, dtype=int)
    ayi = np.zeros(n, dtype=int)

    def ara(noktalar: list[int], t: int, seri: np.ndarray, boga_mi: bool) -> bool:
        s = t - 1
        # Onay: son mumda gösterge ya da fiyat beklenen yöne dönmüş olmalı.
        if boga_mi and not (seri[t] > seri[s] or kapanis[t] > kapanis[s]):
            return False
        if not boga_mi and not (seri[t] < seri[s] or kapanis[t] < kapanis[s]):
            return False
        # En yeni kesinleşmiş noktadan (p + uzunluk <= t) geriye.
        son = bisect.bisect_right(noktalar, t - uzunluk)
        for p in noktalar[max(0, son - UYUMSUZLUK_EN_FAZLA_NOKTA):son][::-1]:
            if t - p > UYUMSUZLUK_EN_FAZLA_MUM:
                break
            if t - p <= UYUMSUZLUK_EN_AZ_MUM or math.isnan(seri[p]) or math.isnan(seri[s]):
                continue
            if boga_mi:
                eslesti = (normal and seri[s] > seri[p] and kapanis[s] < kapanis[p]) or \
                          (gizli and seri[s] < seri[p] and kapanis[s] > kapanis[p])
            else:
                eslesti = (normal and seri[s] < seri[p] and kapanis[s] > kapanis[p]) or \
                          (gizli and seri[s] > seri[p] and kapanis[s] < kapanis[p])
            if eslesti and _temiz_mi(seri, p, s, boga_mi) and _temiz_mi(kapanis, p, s, boga_mi):
                return True
        return False

    for t in range(2, n):
        for seri in gostergeler.values():
            if math.isnan(seri[t]) or math.isnan(seri[t - 1]):
                continue
            if ara(dipler, t, seri, True):
                boga[t] += 1
            if ara(tepeler, t, seri, False):
                ayi[t] += 1
    return pd.DataFrame({"boga": boga, "ayi": ayi}, index=df.index)


# --------------------------------------------------------------------------
# Donchian topluluğu (Sniper)
# --------------------------------------------------------------------------
#
# Zarattini, Pagani ve Barbon, "Catching Crypto Trends" (2025, SSRN 5209907):
# günlük kapanışlarla, farklı uzunluklarda (5 ... 360 gün) birçok Donchian kanal
# modeli birlikte. Her model, kapanış son L günün en yüksek kapanışını aşınca
# "içeride" olur; izleyen stop, önceki stop ile son L günün en yüksek ve en düşük
# kapanışlarının ortası arasındaki büyük olandır; kapanış stopun altına inince
# model "dışarıda" olur. Topluluk değeri içerideki modellerin oranıdır (0-1).
# Makaledeki oynaklığa göre pozisyon büyüklüğü burada yok (sabit işlem tutarı).


def donchian_topluluk(kapanis: pd.Series, uzunluklar: list[int]) -> pd.Series:
    """İçeride olan Donchian modellerinin oranı (0 ile 1 arası). Yalnız geçmişe bakar."""
    k = kapanis.to_numpy(dtype=float)
    n = len(k)
    toplam = np.zeros(n)
    for L in uzunluklar:
        onceki_tepe = kapanis.rolling(L).max().shift(1).to_numpy()       # bugün hariç son L gün
        orta = ((kapanis.rolling(L).max() + kapanis.rolling(L).min()) / 2.0).to_numpy()
        icerde = False
        stop = -np.inf
        durum = np.zeros(n)
        for t in range(n):
            if np.isnan(onceki_tepe[t]):
                continue
            if icerde:
                if k[t] < stop:
                    icerde = False
                else:
                    stop = max(stop, orta[t])
            if not icerde and k[t] > onceki_tepe[t]:
                icerde = True
                stop = orta[t]
            durum[t] = 1.0 if icerde else 0.0
        toplam += durum
    sonuc = pd.Series(toplam / len(uzunluklar), index=kapanis.index)
    # En uzun model hazır olana kadar oran eksik sayılır.
    sonuc.iloc[:max(uzunluklar)] = np.nan
    return sonuc
