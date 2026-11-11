import unittest

from karabasan import site_gezinti


class SiteGezintiTesti(unittest.TestCase):
    def test_serit_panoya_cikar_ve_klasige_gitmez(self):
        h = site_gezinti.serit("ayar")
        for adres in ("/#sonuc", "/#uzay", "/#lab", "/#ajan", "/ayar", "/coinler"):
            self.assertIn(f'href="{adres}"', h)
        self.assertNotIn("/klasik", h)
        self.assertIn('href="/ayar" aria-current=page', h)

    def test_alt_sayfa_kaynaklari_klasige_donmez(self):
        from pathlib import Path
        for ad in ("ayar_sayfa", "detay", "islem_grafik", "coinler"):
            kaynak = Path(f"karabasan/{ad}.py").read_text(encoding="utf-8")
            self.assertNotIn('href="/klasik', kaynak, ad)
            self.assertIn("site_gezinti.serit", kaynak, ad)


if __name__ == "__main__":
    unittest.main()
