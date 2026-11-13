"""Gerçek para ve gizli bilgi kapısı (CLAUDE.md 1. ve 2. kural).

Bu testler CI'da her dalda çalışır; sunucudaki oturum yanlışlıkla gizli bilgi
ya da gerçek emir ayarı yazarsa dal ana dala alınmadan önce burada durur.
"""
import os
import re
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATLA = {".git", "__pycache__", "sahte"}
# Desenler parçalı yazıldı ki bu dosya kendini yakalamasın.
GIZLI = [
    re.compile("-----BEGIN [A-Z ]*PRIV" + "ATE KEY-----"),
    re.compile("gh" + r"p_[A-Za-z0-9]{30,}"),
    re.compile("github" + r"_pat_[A-Za-z0-9_]{30,}"),
    re.compile("AI" + r"za[0-9A-Za-z_-]{30,}"),
    re.compile("sk-" + r"ant-[A-Za-z0-9_-]{20,}"),
]
YASAK_DOSYA = {".env", "telegram.env", "karabasan.env", ".credentials.json"}


def dosyalar():
    for yol, klasorler, adlar in os.walk(KOK):
        klasorler[:] = [k for k in klasorler if k not in ATLA]
        for ad in adlar:
            yield os.path.join(yol, ad)


class GuvenlikKapisi(unittest.TestCase):
    def test_gizli_dosya_yok(self):
        bulunan = [d for d in dosyalar() if os.path.basename(d) in YASAK_DOSYA]
        self.assertEqual(bulunan, [])

    def test_gizli_anahtar_deseni_yok(self):
        kendisi = os.path.abspath(__file__)
        for d in dosyalar():
            if os.path.abspath(d) == kendisi or not d.endswith((".py", ".sh", ".md", ".json", ".yml", ".txt", ".env")):
                continue
            with open(d, encoding="utf-8", errors="ignore") as f:
                metin = f.read()
            for desen in GIZLI:
                self.assertIsNone(desen.search(metin), f"gizli bilgi benzeri: {d}")

    def test_gercek_emir_ayari_yok(self):
        for d in dosyalar():
            if not d.endswith(".py") or "testler" in d.split(os.sep):
                continue
            with open(d, encoding="utf-8") as f:
                metin = f.read()
            self.assertIsNone(re.search(r"""["']dry_run["']\s*:\s*False""", metin), d)
            self.assertIsNone(re.search(r"dry_run\s*=\s*False", metin), d)

    def test_yapilandirma_dry_run_true(self):
        with open(os.path.join(KOK, "araclar", "yapilandirma_uret.py"), encoding="utf-8") as f:
            self.assertIn('"dry_run": True', f.read())


if __name__ == "__main__":
    unittest.main()
