"""Sniper (12 Ekim 2026): 5 dakikalıkta dip sonrası CHoCH + FVG ile kısa vuruş; FVG göstergesi."""

import copy
import unittest

import numpy as np

from karabasan import benzetim as b
from karabasan import botlar
from karabasan import gostergeler as g
from karabasan import kural as k
from testler.test_motor_baglantisi import strateji_modulu
from testler.veri import duz_mumlar, yapay_mumlar


class FvgTesti(unittest.TestCase):
    def test_boga_boslugu_bulunur_ve_dibe_kapanisla_bozulur(self):
        mumlar = duz_mumlar([
            (100, 101, 99, 100.5),     # 0
            (100.5, 101, 100, 100.8),  # 1: yükseği 101
            (101, 104, 101, 103.5),    # 2: hızlı mum
            (103.5, 105, 102, 104.5),  # 3: düşüğü 102 > 101 -> boşluk [101, 102]
            (104.5, 104.6, 101.5, 102.0),  # 4: boşluğa sarktı, alt sınırın üstünde kapandı
            (102, 102.2, 100.2, 100.5),    # 5: alt sınırın (101) altında kapandı -> bozuldu
        ])
        f = g.fvg(mumlar)
        self.assertEqual(f["boga"].tolist(), [0, 0, 0, 1, 0, 0])
        self.assertEqual(f["ayi"].sum(), 0)
        self.assertTrue(np.isnan(f["boga_ust"].iloc[2]))
        self.assertEqual((f["boga_ust"].iloc[3], f["boga_alt"].iloc[3]), (102.0, 101.0))
        self.assertEqual((f["boga_ust"].iloc[4], f["boga_alt"].iloc[4]), (102.0, 101.0))
        self.assertTrue(np.isnan(f["boga_ust"].iloc[5]))

    def test_ayi_boslugu_ve_omur(self):
        fiyat = [(100, 101, 99, 99.5), (99.5, 100, 99, 99.2), (99, 99, 96, 96.5), (96.5, 97.5, 95, 95.5)]
        fiyat += [(95.5, 96, 95, 95.5)] * 6
        f = g.fvg(duz_mumlar(fiyat), omur=4)
        # 3. mumun yükseği (97,5) 1. mumun düşüğünün (99) altında: boşluk [97,5, 99].
        self.assertEqual(f["ayi"].tolist()[:4], [0, 0, 0, 1])
        self.assertEqual((f["ayi_ust"].iloc[3], f["ayi_alt"].iloc[3]), (99.0, 97.5))
        self.assertEqual(f["ayi_ust"].iloc[7], 99.0)        # 4 mum sonra hâlâ geçerli
        self.assertTrue(np.isnan(f["ayi_ust"].iloc[8]))     # ömrü doldu

    def test_en_kucuk_bosluk_esigi(self):
        mumlar = duz_mumlar([(100, 100.1, 99.9, 100), (100, 100.1, 99.9, 100.05),
                             (100.05, 100.3, 100.05, 100.25), (100.25, 100.4, 100.12, 100.3)])
        self.assertEqual(g.fvg(mumlar)["boga"].iloc[3], 1)                    # boşluk %0,02
        self.assertEqual(g.fvg(mumlar, en_az_yuzde=0.05)["boga"].iloc[3], 0)

    def test_gelecege_bakmaz(self):
        df = yapay_mumlar(3000, tohum=7, oynaklik=0.003)
        tam = g.fvg(df, omur=36, en_az_yuzde=0.05)
        for kesim in (500, 1700, 2999):
            kismi = g.fvg(df.iloc[:kesim], omur=36, en_az_yuzde=0.05)
            for sutun in g.FVG_SUTUNLARI:
                np.testing.assert_array_equal(tam[sutun].to_numpy()[:kesim], kismi[sutun].to_numpy(),
                                              err_msg=f"{sutun} {kesim}")

    def test_kural_dogrulamasi(self):
        def kural(**tanim):
            return {"kod": "T", "ad": "Deneme kuralı", "yon": "alim", "zaman_dilimi": "5m",
                    "gostergeler": {"f": {"tur": "fvg", **tanim}},
                    "giris": {"sol": "dusuk", "islem": "<=", "sag": "f_boga_ust"},
                    "cikis": {"kar_hedefi_yuzde": 1, "zarar_durdur_yuzde": 1, "sure_asimi_dakika": 60}}

        k.kural_dogrula(kural())
        k.kural_dogrula(kural(omur=20, en_az_yuzde=0.1))
        for hatali in ({"omur": 2}, {"omur": 501}, {"omur": 5.5}, {"en_az_yuzde": -1},
                       {"en_az_yuzde": "0.1"}, {"kaynak": "kapanis"}):
            with self.subTest(hatali=hatali), self.assertRaises(k.KuralHatasi):
                k.kural_dogrula(kural(**hatali))
        self.assertEqual(k.gereken_mum(kural(omur=100)), 113)


class SniperKurali(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kural = k.kural_yukle("SNIPER")
        cls.df = yapay_mumlar(30 * 288, tohum=1, oynaklik=0.003)
        cls.tablo = k.sinyal_uret(cls.df, cls.kural)

    def test_ayarlar(self):
        k.kural_dogrula(self.kural)
        self.assertEqual((self.kural["zaman_dilimi"], self.kural["yon"]), ("5m", "alim"))
        c = self.kural["cikis"]
        self.assertEqual(c, {"zarar_durdur_yuzde": 3.0, "iz_suren_stop": {"tetik_yuzde": 1.2, "mesafe_yuzde": 0.3}})
        self.assertNotIn("sinyal", c)
        self.assertEqual(k.borsa_dilimleri(self.kural), [])
        self.assertLessEqual(k.gereken_mum(self.kural), k.EN_FAZLA_BASLANGIC_MUMU)

    def test_her_sinyal_butun_kosullari_saglar(self):
        t = self.tablo
        s = t["sinyal"]
        self.assertGreater(int(s.sum()), 20, "yapay veride neredeyse hiç sinyal yok")
        son = lambda sutun, n: t[sutun].rolling(n, min_periods=1)  # noqa: E731
        self.assertTrue((son("rsi14_15", 36).min()[s] < 35).all())          # dip görülmüş
        self.assertTrue((son("yapi5_donus", 12).max()[s] > 0).all())        # yukarı CHoCH
        self.assertTrue((t["yapi5_yon"][s] > 0).all())
        fvg_yeni = son("fvg5_boga", 6).max() > 0
        geri_cekilme = (t["low"] <= t["fvg5_boga_ust"]) & (t["close"] > t["fvg5_boga_alt"])
        self.assertTrue((fvg_yeni | geri_cekilme)[s].all())
        self.assertTrue((t["macd5_fark"][s] > 0).all())
        self.assertTrue(t["rsi14"][s].between(50, 70, inclusive="neither").all())
        hacimli = (t["volume"] > 1.5 * t["hacim20"]).astype(float).rolling(3, min_periods=1).max() > 0
        self.assertTrue(hacimli[s].all())

    def test_sinyaller_gelecege_bakmaz(self):
        for kesim in (3000, 6000, 8000):
            kismi = k.sinyal_uret(self.df.iloc[:kesim], self.kural)
            np.testing.assert_array_equal(self.tablo["sinyal"].to_numpy()[:kesim],
                                          kismi["sinyal"].to_numpy(), err_msg=str(kesim))

    def test_yapay_veride_kendiliginden_kar_yok(self):
        """Rastgele yürüyüşte sonuç komisyon kadar kayıp civarında olmalı (kenar yok)."""
        islemler = []
        for tohum in range(1, 4):
            df = yapay_mumlar(30 * 288, tohum=tohum, oynaklik=0.003)
            islemler += b.benzet(df, self.kural, komisyon_yuzde=0.05)
        self.assertGreater(len(islemler), 30)
        ortalama = np.mean([i["net_yuzde"] for i in islemler])
        self.assertLess(abs(ortalama + 0.1), 0.35, ortalama)
        self.assertEqual({i["neden"] for i in islemler} - {"iz_suren_stop", "zarar_durdur"}, set())

    def test_hatali_esik_reddedilir(self):
        kural = copy.deepcopy(self.kural)
        kural["gostergeler"]["fvg5"]["omur"] = 1
        with self.assertRaises(k.KuralHatasi):
            k.kural_dogrula(kural)


class SniperBotu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modul = strateji_modulu()

    def test_bot_listenin_sonunda_kapi_ayni(self):
        sira = botlar.BOTLAR.index(("sniper5-vadeli", "SniperVadeli", "SNIPER", "vadeli"))
        self.assertEqual(botlar.ILK_PORT + sira, 8085)
        self.assertNotIn("sniper-vadeli", [bot for bot, *_ in botlar.BOTLAR])  # eski kayıt karışmasın

    def test_yalniz_smartmoney_gunluk_veri_ister(self):
        self.assertEqual(botlar.ek_dilimler("vadeli"), ["1d"])

    def test_motor_sinifi(self):
        sinif = self.modul.SniperVadeli
        self.assertEqual(sinif.timeframe, "5m")
        self.assertFalse(sinif.can_short)
        self.assertEqual(sinif.startup_candle_count, k.gereken_mum(k.kural_yukle("SNIPER")))
        self.assertAlmostEqual(sinif.stoploss, -0.03)
        self.assertEqual(sinif().informative_pairs(), [])

    def test_motor_sinyali_cekirdekle_ayni(self):
        df = yapay_mumlar(5000, tohum=4, oynaklik=0.003)
        s = self.modul.SniperVadeli()
        tablo = s.populate_indicators(df.copy(), {"pair": "ETH/USDT:USDT"})
        tablo = s.populate_entry_trend(tablo, {"pair": "ETH/USDT:USDT"})
        tablo = s.populate_exit_trend(tablo, {"pair": "ETH/USDT:USDT"})
        beklenen = k.sinyal_uret(df, k.kural_yukle("SNIPER"))["sinyal"]
        self.assertGreater(int(beklenen.sum()), 0)
        self.assertEqual((tablo["enter_long"] == 1).tolist(), beklenen.tolist())
        self.assertEqual(int(tablo["exit_long"].sum()), 0)


if __name__ == "__main__":
    unittest.main()
