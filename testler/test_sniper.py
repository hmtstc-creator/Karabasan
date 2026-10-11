"""Sniper: çok uzunluklu Donchian kanal topluluğu, çıkış sinyali ve günlük dilim."""

import copy
import unittest

import numpy as np
import pandas as pd

from karabasan import benzetim as b
from karabasan import botlar
from karabasan import gostergeler as g
from karabasan import kural as k
from testler.test_motor_baglantisi import strateji_modulu
from testler.veri import duz_mumlar, yapay_mumlar


def kapanislardan(kapanislar, dilim_dk=1440):
    """Yalnız kapanışı belli günlük mumlar: açılış önceki kapanış, fitil yok."""
    onceki = [kapanislar[0]] + list(kapanislar[:-1])
    return duz_mumlar([(a, max(a, c), min(a, c), c) for a, c in zip(onceki, kapanislar)],
                      dilim_dk=dilim_dk)


class DonchianTopluluk(unittest.TestCase):
    def test_tek_model_kirilimda_girer_orta_cizgi_altinda_cikar(self):
        # 5 gün yatay (100), sonra yükseliş: 6. gün kapanış önceki 5 günün tepesini aşar.
        fiyat = [100.0] * 5 + [101, 102, 103, 104, 105, 106]
        # Orta çizgi son 5 kapanışın ortası; sonra sert düşüş onun altına iner.
        fiyat += [105.5, 103.0]
        sonuc = g.donchian_topluluk(pd.Series(fiyat), [5]).to_numpy()
        self.assertTrue(np.isnan(sonuc[:5]).all())          # ısınma
        self.assertEqual(sonuc[5], 1.0)                       # 101 > 100: kırılım
        self.assertTrue((sonuc[5:11] == 1.0).all())           # trend sürüyor
        # 11. sırada 105,5: son 5 kapanış 102..106, orta 104; stop 104'e taşınmıştı, 105,5 üstünde.
        self.assertEqual(sonuc[11], 1.0)
        # 12. sırada 103 < 104 (taşınmış stop): çıkar; yeni tepe yok, yeniden girmez.
        self.assertEqual(sonuc[12], 0.0)

    def test_stop_her_gun_orta_cizgiye_tasinir(self):
        # Stop, bir önceki günün sonunda hesaplanan orta çizgidir: 9. gün 115'e, 10. gün
        # (pencere 120 119 118 117 116,5) 118,25'e çıkar. 10. gün 116,5 eski stopun (115)
        # üstünde olduğu için işlem sürer; 11. gün 116 yeni stopun altında kalır.
        fiyat = [100.0] * 5 + [110.0, 120.0, 119.0, 118.0, 117.0, 116.5, 116.0]
        sonuc = g.donchian_topluluk(pd.Series(fiyat), [5]).to_numpy()
        self.assertTrue((sonuc[5:11] == 1.0).all())
        self.assertEqual(sonuc[11], 0.0)

    def test_deger_model_payidir(self):
        df = yapay_mumlar(1500, dilim_dk=1440, tohum=5, oynaklik=0.03)
        uzunluklar = [5, 10, 20, 30, 60]
        sonuc = g.donchian_topluluk(df["close"], uzunluklar)
        self.assertTrue(sonuc.iloc[:60].isna().all())
        dolu = sonuc.iloc[60:].to_numpy()
        self.assertTrue(np.isin(np.round(dolu * len(uzunluklar)), np.arange(len(uzunluklar) + 1)).all())
        self.assertGreater(dolu.max(), 0.5)
        self.assertLess(dolu.min(), 0.5)

    def test_sinyaller_gelecege_bakmaz(self):
        df = yapay_mumlar(1500, dilim_dk=1440, tohum=8, oynaklik=0.03)
        kural = k.kural_yukle("SNIPER")
        tam = k.sinyal_uret(df, kural)
        for kesim in (800, 1100, 1400):
            kismi = k.sinyal_uret(df.iloc[:kesim], kural)
            for sutun in ("trend", "sinyal", "cikis_sinyal"):
                np.testing.assert_array_equal(tam[sutun].to_numpy()[:kesim], kismi[sutun].to_numpy(),
                                              err_msg=f"{sutun} {kesim}")


class SniperKurali(unittest.TestCase):
    def setUp(self):
        self.kural = copy.deepcopy(k.kural_yukle("SNIPER"))

    def test_kural_gecerli_ve_isinma_motor_sinirinda(self):
        k.kural_dogrula(self.kural)
        self.assertEqual(self.kural["zaman_dilimi"], "1d")
        self.assertEqual(k.gereken_mum(self.kural), 2 * 360 + 5 + 10)
        self.assertLessEqual(k.gereken_mum(self.kural), k.EN_FAZLA_BASLANGIC_MUMU)
        self.assertIn("sinyal", self.kural["cikis"])

    def test_hatali_uzunluklar_reddedilir(self):
        for hatali in ([], [5, 5], [1], [500], [5.0], "20", [True], list(range(2, 15))):
            kural = copy.deepcopy(self.kural)
            kural["gostergeler"]["trend"]["uzunluklar"] = hatali
            with self.subTest(uzunluklar=hatali), self.assertRaises(k.KuralHatasi):
                k.kural_dogrula(kural)
        kural = copy.deepcopy(self.kural)
        kural["gostergeler"]["trend"]["kaynak"] = "acilis"
        with self.assertRaises(k.KuralHatasi):
            k.kural_dogrula(kural)

    def test_cikis_sinyali_dogrulanir(self):
        kural = copy.deepcopy(self.kural)
        kural["cikis"]["sinyal"] = {"sol": "olmayan", "islem": "<", "sag": 0.5}
        with self.assertRaises(k.KuralHatasi):
            k.kural_dogrula(kural)
        kural["cikis"]["sinyal"] = {"sol": "trend", "islem": "garip", "sag": 0.5}
        with self.assertRaises(k.KuralHatasi):
            k.kural_dogrula(kural)

    def test_sinirlar(self):
        for alan, deger in (("kar_hedefi_yuzde", 250.0), ("zarar_durdur_yuzde", 12.0),
                            ("sure_asimi_dakika", 129601)):
            kural = copy.deepcopy(self.kural)
            kural["cikis"][alan] = deger
            with self.subTest(alan=alan), self.assertRaises(k.KuralHatasi):
                k.kural_dogrula(kural)

    def test_cikis_sinyali_olmayan_kuralda_hep_yanlis(self):
        df = yapay_mumlar(3000, tohum=2)
        tablo = k.sinyal_uret(df, k.kural_yukle("SM"), {"1d": g.ust_dilime_cevir(df, "5m", "1d")})
        self.assertFalse(tablo["cikis_sinyal"].any())


class CikisSinyaliBenzetimi(unittest.TestCase):
    """Çıkış sinyali mumun kapanışında oluşur, işlem bir sonraki mumun açılışında kapanır."""

    @staticmethod
    def kural():
        return {
            "kod": "T", "ad": "Deneme kuralı", "yon": "alim", "zaman_dilimi": "1d",
            "gostergeler": {"trend": {"tur": "donchian_topluluk", "uzunluklar": [3]}},
            "giris": {"sol": "trend", "islem": "yukari_keser", "sag": 0.5},
            "cikis": {"kar_hedefi_yuzde": 200.0, "zarar_durdur_yuzde": 10.0,
                      "sure_asimi_dakika": 129600,
                      "sinyal": {"sol": "trend", "islem": "asagi_keser", "sag": 0.5}},
            "bekleme_dakika": 0,
        }

    def test_sinyalle_cikis(self):
        # 5 gün yatay (ilk 3'ü ısınma), yükseliş (kırılım 5. sırada, giriş 6. sıranın
        # açılışında), sonra düşüş.
        fiyat = [100.0] * 5 + [102, 104, 106, 108, 107, 103, 102, 101]
        df = kapanislardan(fiyat)
        kural = self.kural()
        k.kural_dogrula(kural)
        tablo = k.sinyal_uret(df, kural)
        giris_sirasi = int(np.flatnonzero(tablo["sinyal"].to_numpy())[0])
        cikis_sirasi = int(np.flatnonzero(tablo["cikis_sinyal"].to_numpy())[0])
        self.assertEqual(giris_sirasi, 5)
        islemler = b.benzet(df, kural, komisyon_yuzde=0.05)
        self.assertEqual(len(islemler), 1)
        islem = islemler[0]
        self.assertEqual(islem["neden"], "cikis_sinyali")
        self.assertEqual(islem["giris_zamani"], df["date"].iloc[giris_sirasi + 1])
        self.assertEqual(islem["cikis_zamani"], df["date"].iloc[cikis_sirasi + 1])
        self.assertAlmostEqual(islem["giris_fiyati"], df["open"].iloc[giris_sirasi + 1])
        self.assertAlmostEqual(islem["cikis_fiyati"], df["open"].iloc[cikis_sirasi + 1])
        self.assertAlmostEqual(islem["net_yuzde"], islem["brut_yuzde"] - 0.1)

    def test_stop_cikis_sinyalinden_once_gelirse_stop(self):
        # Girişten sonraki ilk mumda %10'dan fazla düşüş: sinyal henüz oluşmadan stop.
        fiyat = [100.0] * 5 + [102, 104, 90, 89, 88]
        islemler = b.benzet(kapanislardan(fiyat), self.kural())
        self.assertEqual(islemler[0]["neden"], "zarar_durdur")

    def test_cikistan_sonra_yeniden_girebilir(self):
        fiyat = [100.0] * 5 + [102, 104, 106, 103, 101, 100, 99]
        fiyat += [103, 105, 107, 104, 100, 99, 98]
        islemler = b.benzet(kapanislardan(fiyat), self.kural())
        self.assertEqual([i["neden"] for i in islemler], ["cikis_sinyali", "cikis_sinyali"])
        self.assertLess(islemler[0]["cikis_zamani"], islemler[1]["giris_zamani"])


class SniperBotu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modul = strateji_modulu()

    def test_bot_listenin_sonunda(self):
        self.assertEqual(botlar.BOTLAR[-1], ("sniper-vadeli", "SniperVadeli", "SNIPER", "vadeli"))
        self.assertEqual(botlar.ILK_PORT + len(botlar.BOTLAR) - 1, 8085)

    def test_gunluk_veri_indirilir(self):
        self.assertEqual(botlar.ek_dilimler("vadeli"), ["1d"])

    def test_motor_sinifi(self):
        sinif = self.modul.SniperVadeli
        self.assertEqual(sinif.timeframe, "1d")
        self.assertFalse(sinif.can_short)
        self.assertEqual(sinif.startup_candle_count, 735)
        self.assertAlmostEqual(sinif.stoploss, -0.10)
        s = sinif()
        self.assertEqual(s.informative_pairs(), [])    # kendi dilimi zaten 1d; ek veri istemez

    def test_motor_cikis_sutunu_cekirdekle_ayni(self):
        df = yapay_mumlar(1500, dilim_dk=1440, tohum=13, oynaklik=0.03)
        s = self.modul.SniperVadeli()
        tablo = s.populate_indicators(df.copy(), {"pair": "ETH/USDT:USDT"})
        tablo = s.populate_entry_trend(tablo, {"pair": "ETH/USDT:USDT"})
        tablo = s.populate_exit_trend(tablo, {"pair": "ETH/USDT:USDT"})
        cekirdek = k.sinyal_uret(df, k.kural_yukle("SNIPER"))
        self.assertGreater(int(cekirdek["cikis_sinyal"].sum()), 0)
        self.assertEqual((tablo["enter_long"] == 1).tolist(), cekirdek["sinyal"].tolist())
        self.assertEqual((tablo["exit_long"] == 1).tolist(), cekirdek["cikis_sinyal"].tolist())
        self.assertNotIn("exit_short", tablo.columns)


class SniperStopSonrasi(unittest.TestCase):
    def test_sniper_stoplari_izlenmez(self):
        import tempfile
        from datetime import datetime, timedelta, timezone
        from pathlib import Path
        from unittest import mock

        from karabasan import stop_sonrasi as ss
        from testler.veri import sahte_islem_db

        t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
        istekler = []
        with tempfile.TemporaryDirectory() as gecici, \
                mock.patch("karabasan.botlar.BOTLAR", [("sniper-vadeli", "SniperVadeli", "SNIPER", "vadeli")]):
            klasor = Path(gecici)
            sahte_islem_db(klasor / "db" / "sniper-vadeli.sqlite",
                           [("SOL/USDT:USDT", t0, t0 + timedelta(days=2), -10.1, "stop_loss", False)])
            sayim = ss.bir_tur(klasor, t0 + timedelta(days=200),
                               getir=lambda *a: istekler.append(a), ara=0)
        self.assertEqual(istekler, [])
        self.assertEqual(sayim["izlenen"] + sayim["bekleyen"] + sayim["basarisiz"], 0)


class SniperYillikRaporu(unittest.TestCase):
    """12 aylık test raporu hedefsiz, sinyalle çıkan kuralı doğru anlatır."""

    def test_rapor(self):
        from unittest import mock

        from karabasan import yillik as y

        def yukle(coin, dilim, piyasa):
            tohum = sum(map(ord, coin))
            if dilim == "1d":
                return yapay_mumlar(1200, dilim_dk=1440, tohum=tohum, baslangic="2023-01-01",
                                    oynaklik=0.04)
            return yapay_mumlar(130 * 288, dilim_dk=5, tohum=tohum, baslangic="2026-01-01")

        ayar = {"islem_tutari": 50.0, "sanal_bakiye": 1000.0,
                "komisyon_yuzde": {"spot": 0.075, "vadeli": 0.05}}
        with mock.patch.object(y, "BOTLAR", [("sniper-vadeli", "SniperVadeli", "SNIPER", "vadeli")]):
            metin, sonuc, eksik = y.rapor_uret(yukle, gun=100, ayar=ayar)
        self.assertEqual(eksik, 0)
        self.assertIn("hedef yok (çıkış kanal sinyaliyle), stop %10,0", metin)
        self.assertIn("(başa baş %-)", metin)
        self.assertIn("kanal sinyali", metin)
        self.assertIn("1 botun toplamı", metin)
        self.assertIn("sniper-vadeli", sonuc)
        # "Stop = hedef" karşılaştırması bu kuralda anlamsız; tabloda satırı yok.
        bilgi = metin.split("BİLGİ İÇİN", 1)[1]
        self.assertNotIn("sniper-vadeli", bilgi)


if __name__ == "__main__":
    unittest.main()
