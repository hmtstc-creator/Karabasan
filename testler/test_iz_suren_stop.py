"""İz süren stop (12 Ekim 2026, Ahmet'in isteği): %1,2 kârda devreye girer, en iyi fiyatın
%0,3 gerisini izler; stop %3; sabit kâr hedefi ve süre sınırı yok."""

import unittest

import pandas as pd

from karabasan import benzetim as b
from karabasan import kural as k
from testler.veri import duz_mumlar

KOMISYON = 0.05


def kural(yon="alim", **cikis):
    alim = yon == "alim"
    return {
        "kod": "T", "ad": "Deneme kuralı", "yon": yon, "zaman_dilimi": "5m",
        "gostergeler": {"k1": {"tur": "sma", "periyot": 1}},
        "giris": {"sol": "kapanis", "islem": "yukari_keser" if alim else "asagi_keser",
                  "sag": 100.5 if alim else 99.5},
        "cikis": cikis or {"zarar_durdur_yuzde": 3.0,
                           "iz_suren_stop": {"tetik_yuzde": 1.2, "mesafe_yuzde": 0.3}},
    }


def mumlar(fiyatlar):
    """20 sakin mum, sinyal mumu (20., kapanış 100,6), sonra verilenler (21. mumdan). Giriş 21. mumun açılışı = 100."""
    return duz_mumlar([(100, 100.2, 99.8, 100)] * 20 + [(100, 100.7, 99.9, 100.6)] + fiyatlar)


class Benzetim(unittest.TestCase):
    def test_tetikten_sonra_geri_cekilince_kapanir(self):
        # Giriş 100. 21. mum: tepe 101,5 (kâr %1,5 - %0,1 = %1,4 >= %1,2) -> seviye 101,5 x 0,997 = 101,1955.
        df = mumlar([(100, 101.5, 99.9, 101.4), (101.4, 101.45, 101.0, 101.1), (101.1, 101.2, 101.0, 101.1)])
        islemler = b.benzet(df, kural(), komisyon_yuzde=KOMISYON)
        self.assertEqual(len(islemler), 1)
        i = islemler[0]
        self.assertEqual(i["neden"], "iz_suren_stop")
        self.assertAlmostEqual(i["giris_fiyati"], 100.0)
        self.assertAlmostEqual(i["cikis_fiyati"], 101.5 * 0.997)
        self.assertAlmostEqual(i["net_yuzde"], 1.1955 - 0.1, places=6)   # Ahmet'in "0,9'a düşünce" eşiğinin biraz üstü
        self.assertEqual(i["cikis_zamani"], df["date"].iloc[22] + pd.Timedelta(minutes=5))

    def test_tetige_ulasmazsa_yalniz_sabit_stop(self):
        # En iyi kâr %1,2 - %0,1 = %1,1 < %1,2: iz süren stop devreye girmez; sonra %3 stop.
        df = mumlar([(100, 101.2, 99.9, 101.0), (101.0, 101.1, 100.0, 100.2), (100.2, 100.3, 96.5, 96.8)])
        i = b.benzet(df, kural(), komisyon_yuzde=KOMISYON)[0]
        self.assertEqual(i["neden"], "zarar_durdur")
        self.assertAlmostEqual(i["cikis_fiyati"], 97.0)

    def test_seviye_yalniz_yukari_tasinir_ve_kar_kosar(self):
        # Fiyat 105'e kadar çıkar: seviye 105 x 0,997 = 104,685; sonra 104,5'e iner -> çıkış.
        yukari = [(100 + n, 101 + n, 99.95 + n, 101 + n) for n in range(5)]
        df = mumlar(yukari + [(105, 105, 104.8, 104.9), (104.9, 104.95, 104.5, 104.6)])
        i = b.benzet(df, kural(), komisyon_yuzde=KOMISYON)[0]
        self.assertEqual(i["neden"], "iz_suren_stop")
        self.assertAlmostEqual(i["cikis_fiyati"], 105 * 0.997)
        self.assertGreater(i["net_yuzde"], 4.5)

    def test_ayni_mumdaki_tepe_stopu_o_mumda_tasimaz(self):
        # 21. mum hem 101,6'ya çıkıp hem 100,9'a iniyor: sıra bilinmez, o mumda çıkış olmaz.
        df = mumlar([(100, 101.6, 100.9, 101.0), (101.0, 101.2, 100.7, 100.8)])
        i = b.benzet(df, kural(), komisyon_yuzde=KOMISYON)[0]
        self.assertEqual(i["cikis_zamani"], df["date"].iloc[22] + pd.Timedelta(minutes=5))
        # Bir sonraki mum seviyenin (101,2952) altında açıldı: açılıştan kapanır (kötümser).
        self.assertAlmostEqual(i["cikis_fiyati"], 101.0)

    def test_suresiz_islem_veri_bitene_kadar_acik(self):
        df = mumlar([(100, 100.5, 99.5, 100.2)] * 200)
        self.assertEqual(b.benzet(df, kural(), komisyon_yuzde=KOMISYON), [])

    def test_aciga_satis_aynasi(self):
        df = duz_mumlar([(100, 100.2, 99.8, 100)] * 20 + [(100, 100.1, 99.3, 99.4),
                        (100, 100.1, 98.5, 98.6), (98.6, 99.0, 98.7, 98.9)])
        i = b.benzet(df, kural(yon="aciga_satis"), komisyon_yuzde=KOMISYON)[0]
        self.assertEqual(i["neden"], "iz_suren_stop")
        self.assertAlmostEqual(i["cikis_fiyati"], 98.5 * 1.003)

    def test_eski_tur_hedefli_kural_degismedi(self):
        df = mumlar([(100, 100.9, 99.9, 100.5)] + [(100.5, 100.6, 100.4, 100.5)] * 3)
        i = b.benzet(df, kural(kar_hedefi_yuzde=0.8, zarar_durdur_yuzde=3.0, sure_asimi_dakika=60))[0]
        self.assertEqual(i["neden"], "kar_hedefi")
        self.assertAlmostEqual(i["cikis_fiyati"], 100.8)


class Dogrulama(unittest.TestCase):
    def test_gecerli(self):
        k.kural_dogrula(kural())
        k.kural_dogrula(kural(kar_hedefi_yuzde=1.0, zarar_durdur_yuzde=1.0))
        k.kural_dogrula(kural(zarar_durdur_yuzde=1.0, sure_asimi_dakika=60))

    def test_hatali(self):
        for cikis in ({"zarar_durdur_yuzde": 3.0},                                  # stoptan başka çıkış yok
                      {"iz_suren_stop": {"tetik_yuzde": 1.2, "mesafe_yuzde": 0.3}},  # stop yok
                      {"zarar_durdur_yuzde": 3.0, "iz_suren_stop": {"tetik_yuzde": 0.3, "mesafe_yuzde": 0.3}},
                      {"zarar_durdur_yuzde": 3.0, "iz_suren_stop": {"tetik_yuzde": 1.2}},
                      {"zarar_durdur_yuzde": 3.0, "iz_suren_stop": {"tetik_yuzde": 25, "mesafe_yuzde": 0.3}},
                      {"zarar_durdur_yuzde": 3.0, "iz_suren_stop": 1.2}):
            with self.subTest(cikis=cikis), self.assertRaises(k.KuralHatasi):
                k.kural_dogrula(kural(**cikis))

    def test_cikis_metni(self):
        self.assertEqual(k.cikis_metni(k.kural_yukle("SM")["cikis"]),
                         "iz süren stop %1,2 kârda başlar, tepeden %0,3 geride, stop %3, süre sınırı yok")
        self.assertEqual(k.cikis_metni(k.kural_yukle("S1")["cikis"]), "hedef %0,8, stop %3, süre 240 dk")


if __name__ == "__main__":
    unittest.main()
