"""Kaldıraç ve zararda ek giriş (22 Ekim 2026, Ahmet'in isteği; SMK2 / SMDK2).

Fiyat ilk girişten (stop - stopa_kala) yüzde aleyhe gidince ilk tutarın 'kat' katı kadar bir
kez daha girilir. Stop fiyatı ilk girişe göre kalır; iz süren stop ortalama girişten hesaplanır.
Sonuç yüzdeleri ilk teminat üzerindendir. Beklenen değerler elle hesaplandı.
"""

import unittest

import pandas as pd

from karabasan import kural as k
from karabasan.benzetim import benzet

KOMISYON = 0.05


def kural(kaldirac=2, ekleme=True, yon="aciga_satis"):
    kr = {
        "kod": "T", "ad": "deneme kuralı", "yon": yon, "zaman_dilimi": "5m",
        "cikis": {"zarar_durdur_yuzde": 9.0, "iz_suren_stop": {"tetik_yuzde": 1.2, "mesafe_yuzde": 0.3}},
        "kaldirac": kaldirac,
    }
    if ekleme:
        kr["zararda_ekleme"] = {"stopa_kala_yuzde": 1.0, "kat": 2.0}
    return kr


def tablo(mumlar):
    """mumlar: (açılış, tepe, dip, kapanış) listesi; ilk mumda giriş sinyali var."""
    n = len(mumlar)
    df = pd.DataFrame(mumlar, columns=["open", "high", "low", "close"])
    df["date"] = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    df["sinyal"] = [True] + [False] * (n - 1)
    df["cikis_sinyal"] = False
    df["giris_limit_yuzde"] = float("nan")
    return df


def calistir(kr, mumlar):
    return benzet(None, kr, komisyon_yuzde=KOMISYON, hazir_tablo=tablo(mumlar))


class BenzetimdeEkleme(unittest.TestCase):
    def test_eklenip_stop_olan_islem(self):
        # Giriş 100 (açığa satış). 108'e değince 2 kat ek giriş, 109'da (ilk girişin %9'u) stop.
        islemler = calistir(kural(), [
            (100, 100, 100, 100),
            (100, 101, 99.5, 100.5),
            (101, 108.5, 100.8, 108.2),
            (108.2, 109.5, 108.0, 109.2),
            (109.2, 109.4, 109.0, 109.1),
        ])
        self.assertEqual(len(islemler), 1)
        i = islemler[0]
        self.assertEqual(i["neden"], "zarar_durdur")
        self.assertAlmostEqual(i["cikis_fiyati"], 109.0)
        self.assertAlmostEqual(i["ilk_giris_fiyati"], 100.0)
        self.assertIsNotNone(i["ekleme_zamani"])
        self.assertAlmostEqual(i["buyukluk"], 6.0)           # 2 kat x (1 + 2)
        # Ortalama giriş: 3 / (1/100 + 2/108)
        self.assertAlmostEqual(i["giris_fiyati"], 3 / (1 / 100 + 2 / 108))
        brut = 2 * ((100 - 109) / 100 + 2 * (108 - 109) / 108) * 100
        self.assertAlmostEqual(i["brut_yuzde"], brut)                       # ≈ -21,70
        self.assertAlmostEqual(i["net_yuzde"], brut - 2 * KOMISYON * 6)     # ≈ -22,30

    def test_eklendikten_sonra_ortalama_giristen_iz_suren_stop(self):
        ort = 3 / (1 / 100 + 2 / 108)                  # ≈ 105,195
        islemler = calistir(kural(), [
            (100, 100, 100, 100),
            (100, 101, 99.5, 100.5),
            (101, 108.5, 100.8, 108.2),               # ek giriş 108
            (108.2, 108.3, 103.0, 103.2),             # en iyi fiyat 103: kâr ortalamadan %2,1 - %0,1
            (103.2, 104.0, 103.1, 103.9),             # iz seviyesi 103 x 1,003 = 103,309
        ])
        i = islemler[0]
        self.assertEqual(i["neden"], "iz_suren_stop")
        self.assertAlmostEqual(i["cikis_fiyati"], 103.309)
        self.assertAlmostEqual(i["giris_fiyati"], ort)
        brut = 2 * ((100 - 103.309) / 100 + 2 * (108 - 103.309) / 108) * 100
        self.assertAlmostEqual(i["brut_yuzde"], brut)                       # ≈ +10,76
        self.assertGreater(i["net_yuzde"], 0)

    def test_mum_ekleme_seviyesinin_otesinde_acilirsa_acilistan_eklenir(self):
        islemler = calistir(kural(), [
            (100, 100, 100, 100),
            (100, 101, 99.5, 100.5),
            (108.6, 108.7, 108.4, 108.5),             # boşlukla açıldı: ek giriş 108,6
            (108.5, 109.5, 108.4, 109.2),
            (109.2, 109.4, 109.0, 109.1),
        ])
        i = islemler[0]
        self.assertAlmostEqual(i["giris_fiyati"], 3 / (1 / 100 + 2 / 108.6))
        self.assertAlmostEqual(i["cikis_fiyati"], 109.0)

    def test_ekleme_seviyesine_gelmeyen_islem_eklemesiz(self):
        islemler = calistir(kural(), [
            (100, 100, 100, 100),
            (100, 107.9, 99.5, 107.0),
            (107.0, 107.5, 98.0, 98.2),                # en iyi 98
            (98.2, 98.5, 98.0, 98.3),                  # iz seviyesi 98 x 1,003 = 98,294
        ])
        i = islemler[0]
        self.assertIsNone(i["ekleme_zamani"])
        self.assertAlmostEqual(i["buyukluk"], 2.0)
        self.assertAlmostEqual(i["giris_fiyati"], 100.0)
        self.assertAlmostEqual(i["brut_yuzde"], 2 * (100 - 98.294) / 100 * 100)

    def test_alim_yonunde_ayna(self):
        islemler = calistir(kural(yon="alim"), [
            (100, 100, 100, 100),
            (100, 100.5, 99, 99.5),
            (99, 99.2, 91.5, 91.8),                    # ek giriş 92
            (91.8, 92.0, 90.5, 90.8),                  # stop 91
            (90.8, 91.0, 90.5, 90.9),
        ])
        i = islemler[0]
        self.assertEqual(i["neden"], "zarar_durdur")
        brut = 2 * ((91 / 100 - 1) + 2 * (91 / 92 - 1)) * 100
        self.assertAlmostEqual(i["brut_yuzde"], brut)

    def test_kaldiracsiz_eklemesiz_kural_eskisiyle_ayni(self):
        mumlar = [
            (100, 100, 100, 100),
            (100, 101, 99.5, 100.5),
            (101, 108.5, 100.8, 108.2),
            (108.2, 109.5, 108.0, 109.2),
            (109.2, 109.4, 109.0, 109.1),
        ]
        kr = kural(kaldirac=1, ekleme=False)
        del kr["kaldirac"]
        i = calistir(kr, mumlar)[0]
        self.assertAlmostEqual(i["brut_yuzde"], (100 - 109) / 100 * 100)
        self.assertAlmostEqual(i["net_yuzde"], -9.0 - 2 * KOMISYON)
        self.assertAlmostEqual(i["buyukluk"], 1.0)
        # Yalnız kaldıraç: sonuç ve komisyon iki kat.
        i2 = calistir(kural(ekleme=False), mumlar)[0]
        self.assertAlmostEqual(i2["net_yuzde"], 2 * (-9.0) - 2 * KOMISYON * 2)


class KuralDogrulama(unittest.TestCase):
    def setUp(self):
        self.temel = k.kural_yukle("SMK2")

    def _hatali(self, degistir):
        import copy

        kr = copy.deepcopy(self.temel)
        degistir(kr)
        with self.assertRaises(k.KuralHatasi):
            k.kural_dogrula(kr)

    def test_canli_kurallar_gecerli(self):
        for kod in ("SMK2", "SMDK2"):
            k.kural_dogrula(k.kural_yukle(kod))

    def test_sinirlar(self):
        self._hatali(lambda kr: kr.__setitem__("kaldirac", 3))
        self._hatali(lambda kr: kr.__setitem__("kaldirac", 0.5))
        self._hatali(lambda kr: kr.__setitem__("kaldirac", True))
        self._hatali(lambda kr: kr["zararda_ekleme"].__setitem__("kat", 5))
        self._hatali(lambda kr: kr["zararda_ekleme"].__setitem__("stopa_kala_yuzde", 9.0))   # stopa eşit
        self._hatali(lambda kr: kr.__setitem__("zararda_ekleme", [1, 2]))

    def test_ozet_anlatir(self):
        metin = k.ozet(self.temel)
        self.assertIn("kaldıraç 2 kat", metin)
        self.assertIn("fiyat %8 aleyhe gidince ilk tutarın 2 katı ek giriş", metin)
        self.assertNotIn("kaldıraç", k.ozet(k.kural_yukle("SMK")))

    def test_ekleme_gerekli(self):
        self.assertFalse(k.ekleme_gerekli(self.temel, 100.0, 107.99))
        self.assertTrue(k.ekleme_gerekli(self.temel, 100.0, 108.0))
        alim = dict(self.temel, yon="alim")
        self.assertTrue(k.ekleme_gerekli(alim, 100.0, 92.0))
        self.assertFalse(k.ekleme_gerekli(alim, 100.0, 92.1))


if __name__ == "__main__":
    unittest.main()
