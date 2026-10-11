import unittest

from karabasan.benzetim import benzet
from testler.veri import duz_mumlar


def kural(yon="alim", hedef=1.0, stop=1.0, sure=60, bekleme=0):
    # Sinyal: hacim 1000'i aşınca. Testte hangi mumda sinyal olacağını hacimle belirleriz.
    return {
        "kod": "T", "ad": "Test", "yon": yon, "zaman_dilimi": "5m", "gostergeler": {},
        "giris": {"sol": "hacim", "islem": ">", "sag": 1000},
        "cikis": {"kar_hedefi_yuzde": hedef, "zarar_durdur_yuzde": stop, "sure_asimi_dakika": sure},
        "bekleme_dakika": bekleme,
    }


def tablo(mumlar, sinyal_mumlari):
    df = duz_mumlar(mumlar)
    for i in sinyal_mumlari:
        df.loc[i, "volume"] = 5000.0
    return df


DUZ = (100, 100.2, 99.8, 100)


class BenzetimTestleri(unittest.TestCase):
    def test_giris_sonraki_mumun_acilisinda(self):
        df = tablo([DUZ, (101, 101.2, 100.8, 101), (101, 103, 100.9, 102.5), DUZ], [0])
        islemler = benzet(df, kural(), komisyon_yuzde=0.0)
        self.assertEqual(len(islemler), 1)
        self.assertAlmostEqual(islemler[0]["giris_fiyati"], 101.0)
        self.assertEqual(islemler[0]["giris_zamani"], df["date"].iloc[1])

    def test_kar_hedefi(self):
        df = tablo([DUZ, DUZ, (100, 101.5, 99.9, 101.2), DUZ], [0])
        i = benzet(df, kural(), komisyon_yuzde=0.075)[0]
        self.assertEqual(i["neden"], "kar_hedefi")
        self.assertAlmostEqual(i["cikis_fiyati"], 101.0)
        self.assertAlmostEqual(i["brut_yuzde"], 1.0)
        self.assertAlmostEqual(i["net_yuzde"], 1.0 - 0.15)

    def test_zarar_durdur(self):
        df = tablo([DUZ, DUZ, (100, 100.1, 98.5, 98.8), DUZ], [0])
        i = benzet(df, kural(), komisyon_yuzde=0.075)[0]
        self.assertEqual(i["neden"], "zarar_durdur")
        self.assertAlmostEqual(i["brut_yuzde"], -1.0)
        self.assertAlmostEqual(i["net_yuzde"], -1.15)

    def test_ayni_mumda_ikisi_de_olursa_stop_sayilir(self):
        df = tablo([DUZ, (100, 101.5, 98.5, 100), DUZ], [0])
        i = benzet(df, kural(), komisyon_yuzde=0.0)[0]
        self.assertEqual(i["neden"], "zarar_durdur")

    def test_sure_asimi(self):
        mumlar = [DUZ] * 20
        mumlar[13] = (100, 100.4, 99.9, 100.3)
        df = tablo(mumlar, [0])
        i = benzet(df, kural(sure=60), komisyon_yuzde=0.0)[0]
        self.assertEqual(i["neden"], "sure_asimi")
        self.assertAlmostEqual(i["sure_dakika"], 60.0)
        # Giriş 1. mumun açılışı (00:05); 60 dakika 12. mumun kapanışında dolar
        self.assertEqual(i["cikis_zamani"], df["date"].iloc[13])

    def test_aciga_satis_ayna(self):
        df = tablo([DUZ, DUZ, (100, 100.1, 98.5, 98.8), DUZ], [0])
        i = benzet(df, kural(yon="aciga_satis"), komisyon_yuzde=0.075)[0]
        self.assertEqual(i["neden"], "kar_hedefi")
        self.assertAlmostEqual(i["cikis_fiyati"], 99.0)
        self.assertAlmostEqual(i["net_yuzde"], 1.0 - 0.15)
        df = tablo([DUZ, DUZ, (100, 101.5, 99.9, 101.2), DUZ], [0])
        i = benzet(df, kural(yon="aciga_satis"), komisyon_yuzde=0.0)[0]
        self.assertEqual(i["neden"], "zarar_durdur")
        self.assertAlmostEqual(i["brut_yuzde"], -1.0)

    def test_kayma_aleyhe_isler(self):
        df = tablo([DUZ, DUZ, (100, 100.1, 98.5, 98.8), DUZ], [0])
        kaymasiz = benzet(df, kural(), komisyon_yuzde=0.0, kayma_yuzde=0.0)[0]
        kaymali = benzet(df, kural(), komisyon_yuzde=0.0, kayma_yuzde=0.05)[0]
        self.assertGreater(kaymali["giris_fiyati"], kaymasiz["giris_fiyati"])
        self.assertLess(kaymali["net_yuzde"], kaymasiz["net_yuzde"])

    def test_ayni_anda_tek_islem(self):
        # Art arda üç sinyal; ilk işlem açıkken gelenler yok sayılır
        mumlar = [DUZ] * 8
        mumlar[5] = (100, 101.5, 99.9, 101.2)
        df = tablo(mumlar, [0, 1, 2])
        islemler = benzet(df, kural(sure=600), komisyon_yuzde=0.0)
        self.assertEqual(len(islemler), 1)

    def test_hedef_mumundaki_sinyal_sonraki_mumda_islem_acar(self):
        """Hazır motor gibi: hedef mumun içinde gerçekleşir, o mumun sinyali hemen kullanılır."""
        df = tablo([DUZ, DUZ, (100, 101.5, 99.9, 101.2), (101.2, 101.3, 101.1, 101.2), DUZ, DUZ],
                   [0, 2])
        islemler = benzet(df, kural(), komisyon_yuzde=0.0)
        self.assertEqual([i["neden"] for i in islemler[:1]], ["kar_hedefi"])
        self.assertEqual(len(islemler), 2)
        self.assertEqual(islemler[1]["giris_zamani"], df["date"].iloc[3])

    def test_sure_asimi_mumundaki_sinyal_bir_mum_bekler(self):
        """Süre aşımı mumun kapanışında; motor bir sonraki mumun açılışında kapatır, o mumda girmez."""
        df = tablo([DUZ] * 8, [0, 2, 3])
        islemler = benzet(df, kural(sure=10), komisyon_yuzde=0.0)
        self.assertEqual(islemler[0]["neden"], "sure_asimi")
        self.assertEqual(islemler[0]["cikis_zamani"], df["date"].iloc[3])   # 2. mumun kapanışı
        self.assertEqual(islemler[1]["giris_zamani"], df["date"].iloc[4])   # 2'nin değil, 3'ün sinyali

    def test_stop_sonrasi_bekleme(self):
        mumlar = [DUZ] * 30
        mumlar[2] = (100, 100.1, 98.5, 100)   # ilk işlem stop olur
        mumlar[6] = (100, 101.5, 99.9, 100)   # ikinci sinyalden sonra hedef
        df = tablo(mumlar, [0, 4])
        beklemesiz = benzet(df, kural(bekleme=0), komisyon_yuzde=0.0)
        beklemeli = benzet(df, kural(bekleme=120), komisyon_yuzde=0.0)
        self.assertEqual(len(beklemesiz), 2)
        self.assertEqual(len(beklemeli), 1)

    def test_acik_kalan_islem_sayilmaz(self):
        df = tablo([DUZ, DUZ, DUZ], [0])
        self.assertEqual(benzet(df, kural(sure=600)), [])

    def test_son_mumdaki_sinyal_islem_acmaz(self):
        df = tablo([DUZ, DUZ, DUZ], [2])
        self.assertEqual(benzet(df, kural()), [])


if __name__ == "__main__":
    unittest.main()
