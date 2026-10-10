import unittest

import numpy as np
import pandas as pd

from karabasan import gostergeler as g
from testler.veri import yapay_mumlar


class GostergeTestleri(unittest.TestCase):
    def test_dilim_dakika(self):
        self.assertEqual(g.dilim_dakika("5m"), 5)
        self.assertEqual(g.dilim_dakika("1h"), 60)
        self.assertEqual(g.dilim_dakika("4h"), 240)
        self.assertEqual(g.dilim_dakika("1d"), 1440)
        with self.assertRaises(ValueError):
            g.dilim_dakika("5x")

    def test_ema_elle_hesapla_ayni(self):
        seri = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        sonuc = g.ema(seri, 3)
        alfa = 2 / (3 + 1)
        beklenen = [1.0]
        for x in seri[1:]:
            beklenen.append(alfa * x + (1 - alfa) * beklenen[-1])
        self.assertTrue(np.isnan(sonuc.iloc[1]))  # periyot dolmadan değer yok
        np.testing.assert_allclose(sonuc.iloc[2:].to_numpy(), beklenen[2:], rtol=1e-12)

    def test_rsi_sinirlar(self):
        surekli_artan = pd.Series(np.arange(1.0, 60.0))
        self.assertAlmostEqual(g.rsi(surekli_artan, 14).iloc[-1], 100.0)
        surekli_azalan = pd.Series(np.arange(60.0, 1.0, -1.0))
        self.assertAlmostEqual(g.rsi(surekli_azalan, 14).iloc[-1], 0.0)
        karisik = g.rsi(yapay_mumlar(500)["close"], 14).dropna()
        self.assertTrue(((karisik >= 0) & (karisik <= 100)).all())

    def test_bollinger(self):
        kapanis = yapay_mumlar(200)["close"]
        ust, orta, alt = g.bollinger(kapanis, 20, 2.0)
        np.testing.assert_allclose(orta.dropna(), g.sma(kapanis, 20).dropna())
        gecerli = orta.notna()
        self.assertTrue((ust[gecerli] >= orta[gecerli]).all())
        self.assertTrue((alt[gecerli] <= orta[gecerli]).all())
        sabit = pd.Series([5.0] * 30)
        ust, orta, alt = g.bollinger(sabit, 20, 2.0)
        self.assertAlmostEqual(ust.iloc[-1], 5.0)
        self.assertAlmostEqual(alt.iloc[-1], 5.0)

    def test_atr_yuzde_pozitif(self):
        sonuc = g.atr_yuzde(yapay_mumlar(300), 14).dropna()
        self.assertTrue((sonuc > 0).all())

    def test_vwap_gunluk_sifirlanir(self):
        df = yapay_mumlar(600)  # 5 dk mum, iki günden fazla
        vwap = g.vwap_gunluk(df)
        gun_basi = df.index[df["date"].dt.hour.eq(0) & df["date"].dt.minute.eq(0)]
        for i in gun_basi:
            tipik = (df.loc[i, "high"] + df.loc[i, "low"] + df.loc[i, "close"]) / 3
            self.assertAlmostEqual(vwap.loc[i], tipik)

    def test_gelecege_bakmaz(self):
        df = yapay_mumlar(800, tohum=7)
        kisa = df.iloc[:500]
        for ad, fonk in {
            "ema": lambda d: g.ema(d["close"], 20),
            "rsi": lambda d: g.rsi(d["close"], 14),
            "atr": lambda d: g.atr_yuzde(d, 14),
            "vwap": g.vwap_gunluk,
            "tepe": lambda d: g.en_yuksek(d["high"], 48),
        }.items():
            with self.subTest(gosterge=ad):
                np.testing.assert_allclose(
                    fonk(kisa).to_numpy(), fonk(df).iloc[:500].to_numpy(), equal_nan=True
                )

    def test_ust_dilime_cevir(self):
        df = yapay_mumlar(48, dilim_dk=5)  # 4 saat
        ust = g.ust_dilime_cevir(df, "5m", "1h")
        self.assertEqual(len(ust), 4)
        ilk_saat = df.iloc[:12]
        self.assertAlmostEqual(ust.loc[0, "open"], ilk_saat["open"].iloc[0])
        self.assertAlmostEqual(ust.loc[0, "close"], ilk_saat["close"].iloc[-1])
        self.assertAlmostEqual(ust.loc[0, "high"], ilk_saat["high"].max())
        self.assertAlmostEqual(ust.loc[0, "low"], ilk_saat["low"].min())
        self.assertAlmostEqual(ust.loc[0, "volume"], ilk_saat["volume"].sum())
        with self.assertRaises(ValueError):
            g.ust_dilime_cevir(df, "5m", "7m")

    def test_ust_dilim_hizalama_gelecege_bakmaz(self):
        # 3 saatlik 5 dk veri: 00:00 - 02:55
        df = yapay_mumlar(36, dilim_dk=5)
        ust = g.ust_dilime_cevir(df, "5m", "1h")
        hizali = g.ust_dilimden_hizala(ust["close"], ust["date"], df["date"], "5m", "1h")
        # 00:50 mumunda henüz kapanmış bir saatlik mum yok
        self.assertTrue(np.isnan(hizali.iloc[10]))
        # 00:55 mumu kapandığında 00:00 saatlik mumu da kapanmıştır
        self.assertAlmostEqual(hizali.iloc[11], ust.loc[0, "close"])
        # 01:50 mumunda hâlâ 00:00 saatlik mumunun değeri geçerlidir
        self.assertAlmostEqual(hizali.iloc[22], ust.loc[0, "close"])
        # 01:55 mumunda 01:00 saatlik mumunun değeri gelir
        self.assertAlmostEqual(hizali.iloc[23], ust.loc[1, "close"])


if __name__ == "__main__":
    unittest.main()
