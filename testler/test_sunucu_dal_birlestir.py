import unittest

from araclar import sunucu_dal_birlestir as b


class KorunanYollar(unittest.TestCase):
    def test_denetim_ve_is_akisi_korunur(self):
        for yol in (".github/workflows/test.yml", "CLAUDE.md", "araclar/korunan_dosya_denetimi.py",
                    "testler/test_guvenlik_kapisi.py", "araclar/sunucu_dal_birlestir.py"):
            self.assertEqual(b.korunana_dokunan([yol]), [yol])

    def test_normal_dosya_korunmaz(self):
        self.assertEqual(b.korunana_dokunan(["karabasan/sonuc.py", "docs/wiki/gunluk.md", "testler/test_sonuc.py"]), [])


if __name__ == "__main__":
    unittest.main()
