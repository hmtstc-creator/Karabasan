"""RSI botları (13 Ekim 2026, Ahmet'in isteği): yalnız RSI, 5 dk / 15 dk / 1 saat, aşırı bölgeden dönüş."""

import unittest

from karabasan import benzetim as b
from karabasan import botlar
from karabasan import gostergeler as g
from karabasan import kural as k
from testler.test_motor_baglantisi import strateji_modulu
from testler.veri import yapay_mumlar


class RsiKurallari(unittest.TestCase):
    def test_cikis_ahmetin_istedigi_gibi(self):
        for kod in ("RSI", "RSIK"):
            c = k.kural_yukle(kod)["cikis"]
            with self.subTest(kod=kod):
                self.assertEqual(c["kar_hedefi_yuzde"], 1.5)
                self.assertEqual(c["zarar_durdur_yuzde"], 3.0)
                self.assertEqual(c["iz_suren_stop"], {"tetik_yuzde": 1.2, "mesafe_yuzde": 0.3})
                self.assertNotIn("sure_asimi_dakika", c)
                # 13 Ekim 2026 akşamı (Ahmet): sinyal fiyatının %1 ötesine limit emir, 60 dk bekler.
                self.assertEqual(k.kural_yukle(kod)["giris_limiti"],
                                 {"atr_kat": 0.0, "en_az_yuzde": 1.0, "en_fazla_yuzde": 1.0, "sure_dakika": 60})

    def test_yalniz_rsi_kullanir(self):
        for kod in ("RSI", "RSIK"):
            gost = k.kural_yukle(kod)["gostergeler"]
            self.assertEqual({t["tur"] for t in gost.values()}, {"rsi"})
            self.assertEqual({g_.get("dilim", "5m") for g_ in gost.values()}, {"5m", "15m", "1h"})

    def test_sinyal_aninda_rsi_donmus(self):
        df = yapay_mumlar(20000, tohum=11, oynaklik=0.004)
        for kod, alim in (("RSI", True), ("RSIK", False)):
            t = k.sinyal_uret(df, k.kural_yukle(kod))
            r, r1, r2 = t["rsi14"], t["rsi14"].shift(1), t["rsi14"].shift(2)
            s = t["sinyal"]
            with self.subTest(kod=kod):
                self.assertGreater(int(s.sum()), 0)
                if alim:
                    self.assertTrue(((r1 <= 30) & (r > r1) & (r1 <= r2) & (t["rsi14_15"] <= 40)
                                     & (t["rsi14_1s"] <= 50))[s].all())
                else:
                    self.assertTrue(((r1 >= 70) & (r < r1) & (r1 >= r2) & (t["rsi14_15"] >= 60)
                                     & (t["rsi14_1s"] >= 50))[s].all())

    def test_sinyaller_gelecege_bakmaz(self):
        df = yapay_mumlar(12000, tohum=12, oynaklik=0.004)
        kesim = 8000
        for kod in ("RSI", "RSIK"):
            kural = k.kural_yukle(kod)
            tam = k.sinyal_uret(df, kural)["sinyal"]
            kesik = k.sinyal_uret(df.iloc[:kesim], kural)["sinyal"]
            # Son saat: 1 saatlik mum henüz kapanmamış olabilir.
            n = kesim - 12
            with self.subTest(kod=kod):
                self.assertEqual(tam.iloc[:n].tolist(), kesik.iloc[:n].tolist())

    def test_limit_uzakligi_her_mumda_yuzde_bir(self):
        df = yapay_mumlar(3000, tohum=14, oynaklik=0.004)
        for kod in ("RSI", "RSIK"):
            t = k.sinyal_uret(df, k.kural_yukle(kod))
            self.assertTrue((t["giris_limit_yuzde"] == 1.0).all())
        self.assertAlmostEqual(k.limit_fiyati(100.0, 1.0, True), 99.0)
        self.assertAlmostEqual(k.limit_fiyati(100.0, 1.0, False), 101.0)

    def test_benzetim_hedef_ve_iz_suren_stopla_kapatir(self):
        df = yapay_mumlar(20000, tohum=13, oynaklik=0.004)
        islemler = b.benzet(df, k.kural_yukle("RSI"), komisyon_yuzde=0.05)
        nedenler = {i["neden"] for i in islemler}
        self.assertTrue(nedenler <= {"kar_hedefi", "zarar_durdur", "iz_suren_stop"})
        self.assertTrue(islemler)


class RsiBotlari(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modul = strateji_modulu()

    def test_listenin_sonunda_yeni_kapilarla(self):
        self.assertEqual(botlar.BOTLAR[-2:], [("rsi-vadeli", "RSIVadeli", "RSI", "vadeli"),
                                              ("rsik-vadeli", "RSIKVadeli", "RSIK", "vadeli")])
        self.assertEqual(botlar.ILK_PORT + len(botlar.BOTLAR) - 1, 8087)

    def test_motor_sinifi(self):
        for ad, kisa in (("RSIVadeli", False), ("RSIKVadeli", True)):
            sinif = getattr(self.modul, ad)
            with self.subTest(ad=ad):
                self.assertEqual(sinif.timeframe, "5m")
                self.assertEqual(sinif.can_short, kisa)
                self.assertAlmostEqual(sinif.stoploss, -0.03)
                self.assertTrue(sinif.trailing_stop)
                self.assertAlmostEqual(sinif.trailing_stop_positive, 0.003)
                self.assertAlmostEqual(sinif.trailing_stop_positive_offset, 0.012)
                self.assertLess(sinif.minimal_roi["0"], 0.015)          # %1,5 hedef, komisyon düşülmüş
                self.assertGreater(sinif.minimal_roi["0"], 0.013)
                self.assertEqual(sinif().informative_pairs(), [])        # 15m / 1h taban mumlardan

    def test_motor_sinyali_cekirdekle_ayni(self):
        df = yapay_mumlar(12000, tohum=4, oynaklik=0.004)
        for ad, kod, sutun in (("RSIVadeli", "RSI", "enter_long"), ("RSIKVadeli", "RSIK", "enter_short")):
            s = getattr(self.modul, ad)()
            tablo = s.populate_indicators(df.copy(), {"pair": "ETH/USDT:USDT"})
            tablo = s.populate_entry_trend(tablo, {"pair": "ETH/USDT:USDT"})
            beklenen = k.sinyal_uret(df, k.kural_yukle(kod))["sinyal"]
            with self.subTest(ad=ad):
                self.assertGreater(int(beklenen.sum()), 0)
                self.assertEqual((tablo[sutun] == 1).tolist(), beklenen.tolist())


if __name__ == "__main__":
    unittest.main()
