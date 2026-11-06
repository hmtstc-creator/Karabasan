"""Grafikler ve Zaman ekranları, başlık ve açılır menü (6 Kasım 2026)."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import sayfa, sonuc
from testler.veri import eski_bot_listesi_baslat, sahte_sinav_klasoru

SIMDI = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)
T0 = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)  # Bükreş 08:00, Pazartesi


def setUpModule():
    global _geri_al
    _geri_al = eski_bot_listesi_baslat()


def tearDownModule():
    _geri_al()


def islem(net, saat=0, sure=30):
    giris = T0 + timedelta(hours=saat)
    return {"net_tutar": net, "giris_zamani": giris, "cikis_zamani": giris + timedelta(minutes=sure),
            "sure_dakika": sure}


class Veri(unittest.TestCase):
    def test_egri_ve_dusus(self):
        egri = sonuc.zamanli_egri([islem(1, 0), islem(-3, 1), islem(4, 2)])
        self.assertEqual([v for _, v in egri], [0.0, 1.0, -2.0, 2.0])
        self.assertEqual([v for _, v in sonuc.dusus_egrisi(egri)], [0.0, 0.0, -3.0, 0.0])

    def test_zaman_dagilimi_yerel_saat(self):
        z = sonuc.zaman_dagilimi([islem(1, 0), islem(-2, 0)])
        self.assertEqual(z["saat"][8]["islem"], 2)       # 06:00 UTC = 08:00 Bükreş (kış)
        self.assertAlmostEqual(z["saat"][8]["net"], -1)
        self.assertEqual(z["gun"][0]["islem"], 2)        # Pazartesi

    def test_dagilim_toplami_ve_sifir_siniri(self):
        kutular = sonuc.sonuc_dagilimi([islem(x) for x in (-1.0, -0.2, 0.3, 0.5, 2.0)])
        self.assertEqual(sum(k["adet"] for k in kutular), 5)
        sinirlar = {round(k["alt"], 9) for k in kutular}
        self.assertIn(0.0, sinirlar)

    def test_bos(self):
        self.assertEqual(sonuc.zamanli_egri([]), [])
        self.assertEqual(sonuc.sonuc_dagilimi([]), [])

    def test_eksen_ust_siniri_kapsar(self):
        adim = sayfa._guzel_adimlar(0, 3.2)
        self.assertGreaterEqual(adim[-1], 3.2)


class Ekranlar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        cls.ozet = sonuc.genel_ozet(sahte_sinav_klasoru(Path(cls.gecici.name) / "veri", SIMDI), SIMDI)
        cls.html = sayfa.html_uret(cls.ozet)

    @classmethod
    def tearDownClass(cls):
        cls.gecici.cleanup()

    def test_yeni_ekranlar_ve_grafikler(self):
        for kimlik in ("grafikler", "zaman"):
            self.assertIn(f'<section id="{kimlik}"', self.html)
        bolum = sayfa._grafikler_ekrani(self.ozet)
        self.assertEqual(bolum.count('<svg class="g-svg"'), 4)
        self.assertIn("Tepeden düşüş", bolum)
        self.assertEqual(sayfa._zaman_ekrani(self.ozet, "Europe/Bucharest").count('<svg class="g-svg"'), 2)

    def test_en_fazla_sekiz_seri(self):
        self.assertLessEqual(sayfa._grafikler_ekrani(self.ozet).count('class="g-cizgi"'), sayfa.SERI_EN_FAZLA)

    def test_menu_butun_ekranlari_tasir(self):
        menu = self.html[self.html.index('<nav class="menu-liste"'):]
        menu = menu[:menu.index("</nav>")]
        for kimlik, _ad in sayfa.EKRANLAR:
            self.assertIn(f'href="#{kimlik}"', menu)

    def test_alt_cubuk_bes_sekme(self):
        cubuk = self.html[self.html.index('<nav class="gezinti"'):]
        cubuk = cubuk[:cubuk.index("</nav>")]
        self.assertEqual(cubuk.count("<a "), len(sayfa.ALT_CUBUK))

    def test_grafiksiz_ozet_cokmez(self):
        bos = {**self.ozet, "grafik": {}}
        self.assertIn("henüz yeterli", sayfa._grafikler_ekrani(bos))
        self.assertIn("henüz yeterli", sayfa._zaman_ekrani(bos, "Europe/Bucharest").lower())


if __name__ == "__main__":
    unittest.main()
