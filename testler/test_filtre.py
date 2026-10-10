import unittest

from karabasan import filtre as f


def coin(sembol="AAA/USDT", **ek):
    temel = {
        "sembol": sembol, "isleme_acik": True, "izinli": True, "etiketler": [],
        "listelenme_gun": 400, "hacim_24s": 50_000_000.0, "alis": 9.999, "satis": 10.001,
        "derinlik": 200_000.0, "atr_yuzde_gunluk": 6.0, "degisim_24s_yuzde": 2.0,
        "ema50_4s_ustunde": True, "goreli_guc": 1.5, "son20_net": None,
    }
    temel.update(ek)
    return temel


def tek(c, **kw):
    return f.filtrele([c], pozisyon_tutari=50.0, **kw)[0]


class FiltreTestleri(unittest.TestCase):
    def test_iyi_coin_gecer(self):
        s = tek(coin())
        self.assertTrue(s["gecti"])
        self.assertEqual(s["neden"], "")
        self.assertTrue(all(s["katmanlar"].values()))

    def test_katman1(self):
        self.assertIn("işleme kapalı", tek(coin(isleme_acik=False))["neden"])
        self.assertIn("izinli değil", tek(coin(izinli=False))["neden"])
        self.assertIn("Sabit coin", tek(coin(etiketler=["sabit"]))["neden"])
        self.assertIn("izleme etiketi", tek(coin(etiketler=["izleme"]))["neden"])
        self.assertIn("Listelenme yaşı 12 gün", tek(coin(listelenme_gun=12))["neden"])
        s = tek(coin("KOTU/USDT"), ayar={"kara_liste": ["KOTU/USDT"]})
        self.assertEqual(s["elendigi_katman"], 1)

    def test_katman2(self):
        s = tek(coin(hacim_24s=1_200_000.0))
        self.assertEqual(s["elendigi_katman"], 2)
        self.assertEqual(s["neden"], "Likidite: 24 saatlik hacim 1,2 milyon, sınır 5,0 milyon")
        s = tek(coin(alis=9.99, satis=10.008))
        self.assertEqual(s["neden"], "Likidite: Alıcı-satıcı farkı %0,18, sınır %0,10")
        s = tek(coin(derinlik=500.0))
        self.assertIn("Emir derinliği 500, gereken 1.000", s["neden"])

    def test_katman3(self):
        self.assertIn("alt sınır", tek(coin(atr_yuzde_gunluk=1.5))["neden"])
        self.assertIn("üst sınır", tek(coin(atr_yuzde_gunluk=20.0))["neden"])
        self.assertIn("yükselmiş", tek(coin(degisim_24s_yuzde=40.0))["neden"])
        self.assertIn("düşmüş", tek(coin(degisim_24s_yuzde=-22.0))["neden"])
        self.assertEqual(tek(coin(atr_yuzde_gunluk=1.5))["elendigi_katman"], 3)

    def test_katman4(self):
        self.assertIn("EMA50", tek(coin(ema50_4s_ustunde=False))["neden"])
        self.assertIn("BTC'ye göre zayıf", tek(coin(goreli_guc=-0.4))["neden"])
        self.assertIn("dinleniyor", tek(coin(son20_net=-3.2))["neden"])
        self.assertEqual(tek(coin(son20_net=-3.2))["elendigi_katman"], 4)

    def test_ilk_takildigi_katman_yazilir(self):
        s = tek(coin(hacim_24s=100.0, atr_yuzde_gunluk=50.0, ema50_4s_ustunde=False))
        self.assertEqual(s["elendigi_katman"], 2)
        self.assertEqual(sorted(s["nedenler"]), [2, 3, 4])

    def test_sinav_modu_yalniz_ilk_iki_katman_eler(self):
        c = coin(atr_yuzde_gunluk=1.5, ema50_4s_ustunde=False)
        siki = tek(c)
        sinav = tek(c, eleyen_katmanlar=(1, 2))
        self.assertFalse(siki["gecti"])
        self.assertTrue(sinav["gecti"])
        # Etiket olarak kaydedilecek bilgi korunur
        self.assertFalse(sinav["siki_filtreden_gecer"])
        self.assertFalse(sinav["katmanlar"][3])
        self.assertFalse(sinav["katmanlar"][4])
        # Likidite sınavda da eler
        self.assertFalse(tek(coin(hacim_24s=100.0), eleyen_katmanlar=(1, 2))["gecti"])

    def test_huni(self):
        coinler = [
            coin("A/USDT"), coin("B/USDT"),
            coin("C/USDT", etiketler=["sabit"]),
            coin("D/USDT", hacim_24s=10.0),
            coin("E/USDT", atr_yuzde_gunluk=1.0),
            coin("F/USDT", goreli_guc=-1.0),
        ]
        sonuc = f.filtrele(coinler, pozisyon_tutari=50.0)
        self.assertEqual([s["kalan"] for s in f.huni(sonuc)], [6, 5, 4, 3, 2])
        self.assertEqual(sorted(f.izleme_listesi(sonuc)), ["A/USDT", "B/USDT"])
        sinav = f.filtrele(coinler, pozisyon_tutari=50.0, eleyen_katmanlar=(1, 2))
        self.assertEqual([s["kalan"] for s in f.huni(sinav, (1, 2))], [6, 5, 4])

    def test_siralama_gecenler_once_puana_gore(self):
        coinler = [
            coin("ZAYIF/USDT", hacim_24s=6_000_000.0, goreli_guc=0.1),
            coin("ELENEN/USDT", izinli=False),
            coin("GUCLU/USDT", hacim_24s=200_000_000.0, goreli_guc=6.0),
        ]
        sirali = [s["sembol"] for s in f.filtrele(coinler, pozisyon_tutari=50.0)]
        self.assertEqual(sirali, ["GUCLU/USDT", "ZAYIF/USDT", "ELENEN/USDT"])

    def test_puan_sinirlar_icinde(self):
        for c in (coin(), coin(hacim_24s=1e12, goreli_guc=99.0), coin(hacim_24s=0.0, goreli_guc=-9)):
            self.assertTrue(0.0 <= f.siralama_puani(c, f.VARSAYILAN_AYAR) <= 100.0)

    def test_fark_yuzde(self):
        self.assertAlmostEqual(f.fark_yuzde(99.95, 100.05), 0.1)


if __name__ == "__main__":
    unittest.main()
