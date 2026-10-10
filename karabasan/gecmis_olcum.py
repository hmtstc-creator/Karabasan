"""Karabasan'ın geçmişe dönük ölçümü.

Canlı ölçüm servisi yazılana kadar şu soruyu eldeki geçmiş mum verisiyle
yanıtlar: stratejiler yalnız izinli oldukları Karabasan durumunda çalışsaydı
sonuç ne olurdu?

Puanın kendisi karabasan.puan modülündeki aynı fonksiyonlarla hesaplanır.
Canlı tasarımdan farkları, hepsi veri eksikliğinden:

- Altcoin akışı (A): BTC dominansı ve TOTAL2'nin geçmişi elde yok. Yerine
  eldeki altcoinlerin eşit ağırlıklı getirisi kullanılır: altcoinler 24 saatte
  BTC'den iyi gittiyse dominans "düşüyor" sayılır; TOTAL2 yerine altcoinlerin
  eşit ağırlıklı endeksi kendi 4 saatlik EMA50'siyle karşılaştırılır.
- Piyasa genişliği (G): yalnız eldeki coinler üzerinden (uyum denemesinde 5).
- Makro (M): yok; ağırlığı diğer bileşenlere dağıtılır.
- Vetolardan yalnız "BTC ani düşüşü" uygulanır.
- BTC trendi ve sakinliği (T, S) kapanmış saatlik mumlarla, saatte bir yenilenir.

Geleceğe bakmaz: t anındaki puan yalnız kapanışı t ya da öncesinde olan
mumlardan hesaplanır. Bunu sınayan test: test_gecmis_olcum.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import gostergeler as g
from . import karne as kr
from . import puan as p

ADIM_DAKIKA = 5
GUN_ADIM = 24 * 60 // ADIM_DAKIKA  # 24 saatteki 5 dakikalık mum sayısı


def _np_zaman(seri) -> np.ndarray:
    """Zaman sütununu saat dilimsiz (UTC) numpy zamanlarına çevirir; aramalar bununla yapılır."""
    return pd.DatetimeIndex(pd.to_datetime(seri, utc=True)).tz_localize(None).to_numpy()


def _np_an(an) -> np.datetime64:
    damga = pd.Timestamp(an)
    damga = damga.tz_localize("UTC") if damga.tzinfo is None else damga.tz_convert("UTC")
    return damga.tz_localize(None).to_datetime64()


def _hazirla(df: pd.DataFrame) -> pd.DataFrame:
    tablo = df[["date", "open", "high", "low", "close", "volume"]].copy()
    tablo["date"] = pd.to_datetime(tablo["date"], utc=True)
    return tablo.sort_values("date").drop_duplicates("date").reset_index(drop=True)


def _kapanmis_ust_dilim(df5: pd.DataFrame, dilim: str) -> pd.DataFrame:
    """5 dakikalık mumlardan üst dilim mumları; yalnız TAMAMLANMIŞ olanlar.

    'kapanis_zamani' sütunu mumun bittiği andır. Son mum, içindeki 5 dakikalık
    mumların hepsi gelmediyse atılır.
    """
    ust = g.ust_dilime_cevir(df5, "5m", dilim)
    sure = pd.Timedelta(minutes=g.dilim_dakika(dilim))
    ust["kapanis_zamani"] = ust["date"] + sure
    son_veri = df5["date"].iloc[-1] + pd.Timedelta(minutes=ADIM_DAKIKA)
    return ust[ust["kapanis_zamani"] <= son_veri].reset_index(drop=True)


def _saatlik_t_ve_s(btc5: pd.DataFrame) -> pd.DataFrame:
    """Her kapanan saatlik mumda BTC trendi (T) ve sakinliği (S)."""
    bir = _kapanmis_ust_dilim(btc5, "1h")
    dort = _kapanmis_ust_dilim(btc5, "4h")
    dort_kapanis = _np_zaman(dort["kapanis_zamani"])
    satirlar = []
    for i in range(len(bir)):
        an = bir["kapanis_zamani"].iloc[i]
        k1 = bir.iloc[: i + 1]
        k4 = dort.iloc[: int(np.searchsorted(dort_kapanis, _np_an(an), side="right"))]
        satirlar.append(
            {
                "zaman": an,
                "T": p.btc_trend_puani(k4["close"], k1["close"]),
                "S": p.btc_sakinlik_puani(k1),
            }
        )
    return pd.DataFrame(satirlar, columns=["zaman", "T", "S"])


def _asof(kaynak_zaman: pd.Series, kaynak_deger: pd.Series, hedef_zaman: pd.Series) -> np.ndarray:
    """Her hedef an için, o anda ya da öncesinde bilinen son değer (yoksa NaN/None)."""
    konum = np.searchsorted(_np_zaman(kaynak_zaman), _np_zaman(hedef_zaman), side="right") - 1
    degerler = kaynak_deger.to_numpy(dtype=object)
    sonuc = np.empty(len(hedef_zaman), dtype=object)
    for i, k in enumerate(konum):
        sonuc[i] = degerler[k] if k >= 0 else None
    return sonuc


def karabasan_gecmisi(mumlar: dict[str, pd.DataFrame], btc: str = "BTC") -> pd.DataFrame:
    """Eldeki 5 dakikalık mumlardan Karabasan puanını ve durumunu geçmişe dönük hesaplar.

    mumlar: {"BTC": tablo, "ETH": tablo, ...}; her tablo 5 dakikalık mumlardır
    (date, open, high, low, close, volume). BTC zorunludur.

    Dönen tablo, her 5 dakikalık mumun KAPANIŞ anı için bir satırdır:
    zaman, puan, durum, T, S, A, G, veto. Puanın hesaplanamadığı baştaki
    dönem (yeterli geçmiş yok) tabloya girmez.
    """
    if btc not in mumlar:
        raise ValueError("Karabasan ölçümü için BTC mumları gerekir.")
    hazir = {ad: _hazirla(df) for ad, df in mumlar.items()}
    btc5 = hazir[btc]
    zaman = btc5["date"] + pd.Timedelta(minutes=ADIM_DAKIKA)  # mumun kapanış anı
    kapanis = btc5["close"]

    saatlik = _saatlik_t_ve_s(btc5)
    t_degeri = _asof(saatlik["zaman"], saatlik["T"], zaman)
    s_degeri = _asof(saatlik["zaman"], saatlik["S"], zaman)

    btc_24s = (kapanis / kapanis.shift(GUN_ADIM) - 1.0) * 100.0
    btc_15dk = (kapanis / kapanis.shift(3) - 1.0) * 100.0
    btc_1s = (kapanis / kapanis.shift(12) - 1.0) * 100.0

    # Altcoinler BTC'nin zaman eksenine hizalanır (eksik mum NaN kalır).
    altlar = {}
    for ad, df in hazir.items():
        if ad == btc:
            continue
        altlar[ad] = df.set_index("date")["close"].reindex(btc5["date"]).reset_index(drop=True)

    if altlar:
        alt_tablo = pd.DataFrame(altlar)
        alt_24s = ((alt_tablo / alt_tablo.shift(GUN_ADIM) - 1.0) * 100.0).mean(axis=1, skipna=True)
        # Eşit ağırlıklı endeks: her altcoinin 5 dakikalık getirilerinin ortalaması.
        getiri = alt_tablo.pct_change(fill_method=None).mean(axis=1, skipna=True).fillna(0.0)
        endeks = (1.0 + getiri).cumprod()
        endeks_tablo = pd.DataFrame({"date": btc5["date"], "open": endeks, "high": endeks,
                                     "low": endeks, "close": endeks, "volume": 0.0})
        endeks_4s = _kapanmis_ust_dilim(endeks_tablo, "4h")
        endeks_ema = _asof(endeks_4s["kapanis_zamani"], g.ema(endeks_4s["close"], 50), zaman)
    else:
        alt_24s = pd.Series(np.nan, index=btc5.index)
        endeks = pd.Series(np.nan, index=btc5.index)
        endeks_ema = np.full(len(btc5), None, dtype=object)

    # Genişlik: her coinin son kapanışı, kendi kapanmış 1 saatlik EMA50'sinin üstünde mi?
    ustunde_sayisi = np.zeros(len(btc5), dtype=float)
    olculen_sayisi = np.zeros(len(btc5), dtype=float)
    for ad, df in hazir.items():
        saat = _kapanmis_ust_dilim(df, "1h")
        ema50 = _asof(saat["kapanis_zamani"], g.ema(saat["close"], 50), zaman)
        fiyat = df.set_index("date")["close"].reindex(btc5["date"]).to_numpy(dtype=float)
        ema_sayi = np.array([np.nan if e is None else float(e) for e in ema50], dtype=float)
        gecerli = ~np.isnan(ema_sayi) & ~np.isnan(fiyat)
        olculen_sayisi += gecerli
        ustunde_sayisi += gecerli & (fiyat > ema_sayi)

    makine = p.DurumMakinesi()
    satirlar = []
    for i in range(len(btc5)):
        t = t_degeri[i]
        if t is None or pd.isna(t):
            continue  # yeterli geçmiş yok
        s = s_degeri[i]
        a = None
        if altlar and not pd.isna(btc_24s.iloc[i]) and not pd.isna(alt_24s.iloc[i]):
            ema_i = endeks_ema[i]
            ustunde = None if ema_i is None or pd.isna(ema_i) else bool(endeks.iloc[i] > ema_i)
            a, _ = p.altcoin_akisi_puani(
                float(btc_24s.iloc[i]),
                float(btc_24s.iloc[i] - alt_24s.iloc[i]),  # artı: altcoinler BTC'nin gerisinde
                ustunde,
            )
        gen = p.genislik_puani(int(ustunde_sayisi[i]), int(olculen_sayisi[i])) if olculen_sayisi[i] > 0 else None
        bilesenler = {"T": float(t), "S": None if s is None or pd.isna(s) else float(s),
                      "A": a, "G": gen, "M": None}
        toplam, _ = p.karabasan_puani(bilesenler)
        an = zaman.iloc[i].to_pydatetime()
        girdi = {}
        if not pd.isna(btc_15dk.iloc[i]):
            girdi["btc_15dk_degisim_yuzde"] = float(btc_15dk.iloc[i])
        if not pd.isna(btc_1s.iloc[i]):
            girdi["btc_1s_degisim_yuzde"] = float(btc_1s.iloc[i])
        kayit = makine.guncelle(an, toplam, p.veto_kontrol(an, girdi))
        satirlar.append({"zaman": zaman.iloc[i], "puan": toplam, "durum": kayit["durum"],
                         "T": bilesenler["T"], "S": bilesenler["S"], "A": a, "G": gen,
                         "veto": kayit["veto"]})
    makine.gecmis.clear()
    return pd.DataFrame(satirlar, columns=["zaman", "puan", "durum", "T", "S", "A", "G", "veto"])


def islemleri_etiketle(islemler: list[dict], gecmis: pd.DataFrame) -> list[dict]:
    """Her işleme, açıldığı anda geçerli olan Karabasan durumunu ve puanını yazar.

    İşlem bir mumun açılışında açılır; o an, önceki mumun kapanış anıdır ve
    Karabasan'ın o satırı yalnız o ana kadarki veriden hesaplanmıştır.
    Ölçümün başlamadığı döneme düşen işlemler "BILINMIYOR" olarak etiketlenir.
    """
    if gecmis.empty:
        return [{**i, "karabasan_durumu": "BILINMIYOR", "karabasan_puani": None} for i in islemler]
    zamanlar = _np_zaman(gecmis["zaman"])
    durumlar = gecmis["durum"].to_numpy()
    puanlar = gecmis["puan"].to_numpy()
    etiketli = []
    for i in islemler:
        k = int(np.searchsorted(zamanlar, _np_an(i["giris_zamani"]), side="right")) - 1
        if k < 0:
            etiketli.append({**i, "karabasan_durumu": "BILINMIYOR", "karabasan_puani": None})
        else:
            etiketli.append({**i, "karabasan_durumu": str(durumlar[k]),
                             "karabasan_puani": None if pd.isna(puanlar[k]) else float(puanlar[k])})
    return etiketli


def duruma_gore_karne(islemler: list[dict], islem_tutari: float = 50.0, bakiye: float = 1000.0) -> dict:
    """Etiketli işlemleri duruma göre ayırıp karneler; 'HEPSI' anahtarı toplamdır."""
    sonuc = {"HEPSI": kr.karne(islemler, islem_tutari, bakiye)}
    for durum in ("YESIL", "SARI", "KIRMIZI", "SIYAH", "BILINMIYOR"):
        secilen = [i for i in islemler if i.get("karabasan_durumu") == durum]
        if secilen or durum != "BILINMIYOR":
            sonuc[durum] = kr.karne(secilen, islem_tutari, bakiye)
    return sonuc


def izinli_karne(islemler: list[dict], izinli_durumlar: list[str],
                 islem_tutari: float = 50.0, bakiye: float = 1000.0) -> dict:
    """Yalnız stratejinin izinli olduğu durumlarda açılmış işlemlerin karnesi.

    Bir yaklaşıktır: gerçekte bir işlem atlanınca sonraki işlemlerin sırası da
    değişebilir (aynı coinde aynı anda tek işlem, stop sonrası bekleme).
    """
    secilen = [i for i in islemler if i.get("karabasan_durumu") in izinli_durumlar]
    return kr.karne(secilen, islem_tutari, bakiye)


def sure_dagilimi(gecmis: pd.DataFrame) -> dict:
    """Her durumun ölçüm sayısına göre payı (yüzde)."""
    if gecmis.empty:
        return {}
    sayim = gecmis["durum"].value_counts()
    return {durum: float(sayim.get(durum, 0)) / len(gecmis) * 100.0
            for durum in ("YESIL", "SARI", "KIRMIZI", "SIYAH")}
