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


# --------------------------------------------------------------------------
# Hazır motorun işlem kayıt dosyasının (SQLite) sahte kopyası
# --------------------------------------------------------------------------

ISLEM_TABLOSU = """
CREATE TABLE trades (
    id INTEGER PRIMARY KEY, exchange VARCHAR, pair VARCHAR, is_open BOOLEAN,
    fee_open FLOAT, fee_close FLOAT, open_rate FLOAT, close_rate FLOAT,
    close_profit FLOAT, close_profit_abs FLOAT, stake_amount FLOAT, amount FLOAT,
    open_date DATETIME, close_date DATETIME, exit_reason VARCHAR, strategy VARCHAR,
    enter_tag VARCHAR, timeframe INTEGER, is_short BOOLEAN, leverage FLOAT
)
"""


def sahte_islem_db(yol, islemler):
    """Verilen işlemlerle hazır motorunkine benzeyen bir kayıt dosyası üretir.

    Her işlem: (parite, açılış zamanı, kapanış zamanı ya da None, net yüzde, çıkış nedeni, açığa satış mı)
    Zamanlar hazır motorun yazdığı gibi saat dilimi bilgisi olmayan UTC metnidir.
    """
    import sqlite3
    from pathlib import Path

    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    baglanti = sqlite3.connect(yol)
    baglanti.execute(ISLEM_TABLOSU)
    for parite, acilis, kapanis, net_yuzde, neden, aciga in islemler:
        acik = kapanis is None
        baglanti.execute(
            "INSERT INTO trades (exchange, pair, is_open, open_rate, close_rate, close_profit,"
            " close_profit_abs, stake_amount, open_date, close_date, exit_reason, enter_tag, is_short)"
            " VALUES ('binance', ?, ?, 100.0, ?, ?, ?, 50.0, ?, ?, ?, 'S1', ?)",
            (
                parite,
                1 if acik else 0,
                None if acik else 100.0 * (1 + net_yuzde / 100.0),
                None if acik else net_yuzde / 100.0,
                None if acik else net_yuzde / 100.0 * 50.0,
                acilis.strftime("%Y-%m-%d %H:%M:%S.%f"),
                None if acik else kapanis.strftime("%Y-%m-%d %H:%M:%S.%f"),
                None if acik else neden,
                1 if aciga else 0,
            ),
        )
    baglanti.commit()
    baglanti.close()
    return yol


def sahte_sinav_klasoru(klasor, simdi, sinav_gunu=12, isinma_gunu=7):
    """On botun kayıtlarıyla dolu bir user_data kopyası üretir (sınavın ortasında).

    Botların sonuçları bilerek farklıdır: iyi, kötü, işlemsiz ve kaydı olmayan.
    """
    import random
    from datetime import timedelta
    from pathlib import Path

    from karabasan.botlar import BOTLAR

    klasor = Path(klasor)
    sinav = simdi - timedelta(days=sinav_gunu - 1, hours=3)
    isinma = sinav - timedelta(days=isinma_gunu)
    klasor.mkdir(parents=True, exist_ok=True)
    (klasor / "isinma_baslangici.txt").write_text(isinma.strftime("%Y-%m-%dT%H:%M:%SZ\n"))
    (klasor / "sinav_baslangici.txt").write_text(sinav.strftime("%Y-%m-%dT%H:%M:%SZ\n"))
    # (kazanma olasılığı, işlem sayısı); None = kayıt dosyası yok
    davranis = [(0.62, 130), (0.48, 90), (0.55, 60), (0.40, 110), (0.58, 75),
                (0.45, 40), (0.60, 0), None, (0.52, 55), (0.35, 20)]
    coinler = ["SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "SUI", "NEAR"]
    rastgele = random.Random(7)
    for (bot, _sinif, _kural, piyasa), d in zip(BOTLAR, davranis):
        if d is None:
            continue
        olasilik, adet = d
        ek = ":USDT" if piyasa == "vadeli" else ""
        islemler = []
        # Isınma döneminden kalan, sınava sayılmaması gereken iki işlem.
        for k in range(2):
            a = isinma + timedelta(hours=5 + k)
            islemler.append((f"BTC/USDT{ek}", a, a + timedelta(minutes=40), 1.05, "roi", False))
        for k in range(adet):
            a = sinav + (simdi - sinav) * (k + 0.5) / (adet + 1)
            kazandi = rastgele.random() < olasilik
            if kazandi:
                net, neden = 1.05, "roi"
            elif rastgele.random() < 0.8:
                net, neden = -1.15, "stop_loss"
            else:
                net, neden = rastgele.uniform(-0.6, 0.4), "sure_asimi"
            islemler.append(
                (f"{rastgele.choice(coinler)}/USDT{ek}", a,
                 a + timedelta(minutes=rastgele.randint(15, 200)), net, neden, "k-" in bot)
            )
        for k in range(rastgele.randint(0, 3)):
            islemler.append((f"{coinler[k]}/USDT{ek}", simdi - timedelta(minutes=30 * (k + 1)), None, 0.0, None, False))
        sahte_islem_db(klasor / "db" / f"{bot}.sqlite", islemler)
    return klasor
