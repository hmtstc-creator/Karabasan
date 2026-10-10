import copy
import unittest

import numpy as np
import pandas as pd

from karabasan import gostergeler as g
from karabasan import kural as k
from testler.veri import yapay_mumlar


def basit_kural(**ek):
    kural = {
        "kod": "T1", "ad": "Test", "yon": "alim", "zaman_dilimi": "5m",
        "gostergeler": {"ema3": {"tur": "ema", "kaynak": "kapanis", "periyot": 3}},
        "giris": {"sol": "kapanis", "islem": ">", "sag": "ema3"},
        "cikis": {"kar_hedefi_yuzde": 1.0, "zarar_durdur_yuzde": 1.0, "sure_asimi_dakika": 60},
    }
    kural.update(ek)
    return kural


class KuralDosyalari(unittest.TestCase):
    def test_alti_strateji_yuklenir(self):
        kurallar = k.tum_kurallar()
        self.assertEqual(sorted(kurallar), ["S1", "S1K", "S2", "S2K", "S3", "S4"])
        for kod, kural in kurallar.items():
            with self.subTest(kod=kod):
                self.assertEqual(kural["kod"], kod)
                self.assertLessEqual(k.gereken_mum(kural), k.EN_FAZLA_BASLANGIC_MUMU)

    def test_ters_yonluler_aciga_satis(self):
        kurallar = k.tum_kurallar()
        self.assertEqual(kurallar["S1K"]["yon"], "aciga_satis")
        self.assertEqual(kurallar["S2K"]["yon"], "aciga_satis")
        for kod in ("S1", "S2", "S3", "S4"):
            self.assertEqual(kurallar[kod]["yon"], "alim")

    def test_basabas_oranlari_raporla_ayni(self):
        kurallar = k.tum_kurallar()
        beklenen = {"S1": 54.55, "S2": 48.0, "S3": 60.0, "S4": 55.56}
        for kod, oran in beklenen.items():
            self.assertAlmostEqual(k.basabas_orani(kurallar[kod], 0.20), oran, places=2)

    def test_tum_stratejiler_yapay_veride_calisir(self):
        df5 = yapay_mumlar(6000, dilim_dk=5, tohum=3)
        df15 = yapay_mumlar(3000, dilim_dk=15, tohum=3)
        for kod, kural in k.tum_kurallar().items():
            with self.subTest(kod=kod):
                df = df15 if kural["zaman_dilimi"] == "15m" else df5
                tablo = k.sinyal_uret(df, kural)
                self.assertEqual(len(tablo), len(df))
                self.assertEqual(tablo["sinyal"].dtype, bool)
                # Başlangıç mumları dolmadan sinyal üretilmemeli
                self.assertFalse(tablo["sinyal"].iloc[:50].any())


class Dogrulama(unittest.TestCase):
    def test_gecerli_kural(self):
        k.kural_dogrula(basit_kural())

    def hata_bekle(self, kural, parca):
        with self.assertRaises(k.KuralHatasi) as baglam:
            k.kural_dogrula(kural)
        self.assertIn(parca, str(baglam.exception))

    def test_eksik_alan(self):
        kural = basit_kural()
        del kural["cikis"]
        self.hata_bekle(kural, "cikis")

    def test_yanlis_yon(self):
        self.hata_bekle(basit_kural(yon="yukari"), "yon")

    def test_stop_siniri(self):
        kural = basit_kural()
        kural["cikis"]["zarar_durdur_yuzde"] = 100  # yazım hatası: %1 yerine %100
        self.hata_bekle(kural, "zarar_durdur_yuzde")

    def test_hedef_siniri(self):
        kural = basit_kural()
        kural["cikis"]["kar_hedefi_yuzde"] = 0
        self.hata_bekle(kural, "kar_hedefi_yuzde")

    def test_tanimsiz_gosterge(self):
        self.hata_bekle(basit_kural(giris={"sol": "kapanis", "islem": ">", "sag": "yok"}), "yok")

    def test_tanimsiz_islem(self):
        self.hata_bekle(basit_kural(giris={"sol": "kapanis", "islem": "==", "sag": 1}), "işlem")

    def test_negatif_kaydirma_gelecege_bakar(self):
        giris = {"sol": "kapanis", "islem": ">", "sag": {"ad": "ema3", "kaydir": -1}}
        self.hata_bekle(basit_kural(giris=giris), "kaydir")

    def test_ust_dilim_tanimsiz(self):
        kural = basit_kural()
        kural["gostergeler"]["e"] = {"tur": "ema", "periyot": 5, "dilim": "ust"}
        self.hata_bekle(kural, "ust_zaman_dilimi")

    def test_ust_dilim_kat_degil(self):
        self.hata_bekle(basit_kural(ust_zaman_dilimi="7m"), "ust_zaman_dilimi")

    def test_cok_fazla_baslangic_mumu(self):
        kural = basit_kural(ust_zaman_dilimi="1d")
        kural["gostergeler"]["e"] = {"tur": "ema", "periyot": 200, "dilim": "ust"}
        self.hata_bekle(kural, "başlangıç mumu")

    def test_cakisan_gosterge_adi(self):
        kural = basit_kural()
        kural["gostergeler"]["close"] = {"tur": "ema", "periyot": 5}
        self.hata_bekle(kural, "close")

    def test_bos_baglac(self):
        self.hata_bekle(basit_kural(giris={"hepsi": []}), "hepsi")


class Degerlendirme(unittest.TestCase):
    def setUp(self):
        self.df = yapay_mumlar(400, tohum=11)

    def test_basit_karsilastirma(self):
        tablo = k.sinyal_uret(self.df, basit_kural())
        ema3 = g.ema(self.df["close"], 3)
        beklenen = (self.df["close"] > ema3) & ema3.notna()
        pd.testing.assert_series_equal(tablo["sinyal"], beklenen.astype(bool), check_names=False)

    def test_yukari_keser(self):
        kural = basit_kural(giris={"sol": "kapanis", "islem": "yukari_keser", "sag": "ema3"})
        sinyal = k.sinyal_uret(self.df, kural)["sinyal"]
        ema3 = g.ema(self.df["close"], 3)
        c = self.df["close"]
        beklenen = (c > ema3) & (c.shift(1) <= ema3.shift(1))
        pd.testing.assert_series_equal(sinyal, beklenen.astype(bool), check_names=False)
        # Kesişim mumlarından hemen önce fiyat ortalamanın üstünde olamaz
        onceki = (c.shift(1) > ema3.shift(1))[sinyal]
        self.assertFalse(onceki.any())

    def test_hepsi_ve_herhangi(self):
        a = {"sol": "kapanis", "islem": ">", "sag": "ema3"}
        b = {"sol": "kapanis", "islem": ">", "sag": "acilis"}
        sa = k.sinyal_uret(self.df, basit_kural(giris=a))["sinyal"]
        sb = k.sinyal_uret(self.df, basit_kural(giris=b))["sinyal"]
        ve = k.sinyal_uret(self.df, basit_kural(giris={"hepsi": [a, b]}))["sinyal"]
        veya = k.sinyal_uret(self.df, basit_kural(giris={"herhangi": [a, b]}))["sinyal"]
        pd.testing.assert_series_equal(ve, sa & sb, check_names=False)
        pd.testing.assert_series_equal(veya, sa | sb, check_names=False)

    def test_kaydir_ve_carpan(self):
        giris = {"sol": "hacim", "islem": ">", "sag": {"ad": "hacim", "kaydir": 1, "carpan": 2.0}}
        sinyal = k.sinyal_uret(self.df, basit_kural(giris=giris))["sinyal"]
        v = self.df["volume"]
        beklenen = (v > v.shift(1) * 2.0).fillna(False)
        pd.testing.assert_series_equal(sinyal, beklenen.astype(bool), check_names=False)

    def test_son_n_mumda(self):
        tek = {"sol": "kapanis", "islem": "yukari_keser", "sag": "ema3"}
        genis = {**tek, "son_n_mumda": 3}
        s1 = k.sinyal_uret(self.df, basit_kural(giris=tek))["sinyal"]
        s3 = k.sinyal_uret(self.df, basit_kural(giris=genis))["sinyal"]
        beklenen = s1 | s1.shift(1, fill_value=False) | s1.shift(2, fill_value=False)
        pd.testing.assert_series_equal(s3, beklenen.astype(bool), check_names=False)

    def test_girdi_tablosu_degismez(self):
        kopya = self.df.copy()
        k.sinyal_uret(self.df, basit_kural())
        pd.testing.assert_frame_equal(self.df, kopya)

    def test_sinyaller_gelecege_bakmaz(self):
        """Sonradan gelen veri, geçmişteki sinyali değiştirmemeli."""
        df5 = yapay_mumlar(5000, dilim_dk=5, tohum=5)
        df15 = yapay_mumlar(2500, dilim_dk=15, tohum=5)
        for kod, kural in k.tum_kurallar().items():
            with self.subTest(kod=kod):
                df = df15 if kural["zaman_dilimi"] == "15m" else df5
                kesim = len(df) - 700
                tam = k.sinyal_uret(df, kural)["sinyal"].iloc[:kesim]
                kismi = k.sinyal_uret(df.iloc[:kesim], kural)["sinyal"]
                np.testing.assert_array_equal(tam.to_numpy(), kismi.to_numpy())

    def test_ust_dilim_gostergesi_gecikmeli_gelir(self):
        kural = basit_kural(ust_zaman_dilimi="1h")
        kural["gostergeler"] = {"k1s": {"tur": "sma", "kaynak": "kapanis", "periyot": 1, "dilim": "ust"}}
        kural["giris"] = {"sol": "kapanis", "islem": ">", "sag": "k1s"}
        tablo = k.gosterge_ekle(self.df, kural)
        # 01:50 mumu (indeks 22): geçerli saatlik kapanış 00:55 mumunun kapanışıdır
        self.assertAlmostEqual(tablo["k1s"].iloc[22], self.df["close"].iloc[11])
        # 01:55 mumu (indeks 23): artık 01:00 saatlik mumu kapanmıştır
        self.assertAlmostEqual(tablo["k1s"].iloc[23], self.df["close"].iloc[23])


if __name__ == "__main__":
    unittest.main()
