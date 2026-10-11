"""Çıkış varyasyonu taraması: aynı girişler, 20 çıkış ayarı, seçim ve doğrulama dönemi."""

import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from karabasan import kural as k
from karabasan import tarama as t
from testler.test_yillik import AYAR, yukleyici

KOK = Path(__file__).resolve().parent.parent


class Varyasyonlar(unittest.TestCase):
    def test_yirmi_gecerli_ve_farkli_ayar(self):
        self.assertEqual(len(t.VARYASYONLAR), 20)
        self.assertEqual(len({v for v, _ in t.VARYASYONLAR}), 20)
        cikislar = [repr(sorted(c.items())) for _v, c in t.VARYASYONLAR]
        self.assertEqual(len(set(cikislar)), 20)
        sablon = k.kural_yukle("SM")
        for v, cikis in t.VARYASYONLAR:
            with self.subTest(v=v):
                k.kural_dogrula({**sablon, "cikis": cikis})

    def test_ilk_varyasyon_canli_ayar(self):
        self.assertEqual(dict(t.VARYASYONLAR)["V01"], k.kural_yukle("SM")["cikis"])


class TaramaRaporu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Hız için iki bot ve 120 günlük yapay veride 100 günlük dönem.
        botlar = [("sm-vadeli", "SMVadeli", "SM", "vadeli"), ("sniper5-vadeli", "SniperVadeli", "SNIPER", "vadeli")]
        bas = time.time()
        with mock.patch.object(t, "BOTLAR", botlar):
            cls.metin, cls.satirlar, cls.eksik = t.tara(yukleyici(), gun=100, ayar=AYAR)
        cls.sure = time.time() - bas

    def test_her_bot_icin_yirmi_satir(self):
        self.assertEqual(self.eksik, 0)
        self.assertEqual(len(self.satirlar), 40)
        for bot in ("sm-vadeli", "sniper5-vadeli"):
            self.assertIn(bot, self.metin)
        self.assertIn("ÖZET", self.metin)
        self.assertIn("<- şimdiki ayar", self.metin)

    def test_donemler_toplami_yila_esit(self):
        for s in self.satirlar:
            self.assertAlmostEqual(s["secim"] + s["dogrulama"], s["net"], places=6, msg=s["varyasyon"])

    def test_ayni_girisler_farkli_cikislar(self):
        sm = {s["varyasyon"]: s for s in self.satirlar if s["kod"] == "SM"}
        self.assertGreater(sm["V01"]["islem"], 0)
        self.assertNotEqual(sm["V15"]["net"], sm["V01"]["net"])

    def test_ezber_uyarisi_ve_durust_secim(self):
        self.assertIn("ezbere açık", self.metin)
        self.assertIn("Dürüst seçim (ilk 9 aya göre seçilip son 3 ayda sınanan)", self.metin)
        self.assertIn("Bu rapor hiçbir ayarı değiştirmez.", self.metin)

    def test_makul_surede_biter(self):
        self.assertLess(self.sure, 120)


class Betik(unittest.TestCase):
    def test_yazim_ve_kur_sh_baglantisi(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(KOK / "araclar" / "tarama.sh")]).returncode, 0)
        kur = (KOK / "kur.sh").read_text(encoding="utf-8")
        self.assertIn("bash araclar/tarama.sh", kur)
        self.assertIn("TARAMA_SURUMU=", kur)
        # Tarama, veriyi indiren 12 aylık testten sonra çalışır.
        self.assertLess(kur.index("bash araclar/yillik_test.sh"), kur.index("bash araclar/tarama.sh"))


if __name__ == "__main__":
    unittest.main()
