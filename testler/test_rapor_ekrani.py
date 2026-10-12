"""Rapor ekranı: bot seçimli günlük kâr / zarar (12 Ekim 2026, Ahmet'in isteği)."""

import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from karabasan import panel, sayfa, sonuc
from testler.veri import ESKI_BOTLAR, eski_bot_listesi_baslat, sahte_sinav_klasoru

SIMDI = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)


def setUpModule():
    global _geri_al
    _geri_al = eski_bot_listesi_baslat()


def tearDownModule():
    _geri_al()


def islem(cikis, net):
    return {"cikis_zamani": cikis, "net_tutar": net}


class GunlukOzet(unittest.TestCase):
    def test_yerel_gune_gore_toplanir(self):
        # 21:30 UTC Bükreş'te ertesi gündür (kış saati UTC+2, yaz saati UTC+3).
        islemler = [islem(datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc), 1.0),
                    islem(datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc), -0.4),
                    islem(datetime(2026, 11, 1, 22, 30, tzinfo=timezone.utc), 2.0)]
        gunluk = sonuc.gunluk_ozet(islemler)
        self.assertEqual([g["gun"] for g in gunluk], ["2026-11-01", "2026-11-02"])
        self.assertEqual((gunluk[0]["islem"], gunluk[0]["kazanan"]), (2, 1))
        self.assertAlmostEqual(gunluk[0]["net_tutar"], 0.6)
        self.assertAlmostEqual(gunluk[1]["birikimli"], 2.6)

    def test_bos(self):
        self.assertEqual(sonuc.gunluk_ozet([]), [])

    def test_botlar_toplanir(self):
        a = sonuc.gunluk_ozet([islem(datetime(2026, 11, 1, 10, tzinfo=timezone.utc), 1.0)])
        b = sonuc.gunluk_ozet([islem(datetime(2026, 11, 1, 11, tzinfo=timezone.utc), -3.0),
                               islem(datetime(2026, 11, 2, 11, tzinfo=timezone.utc), 0.5)])
        toplam = sonuc.gunluk_topla([a, b])
        self.assertEqual([(g["gun"], g["islem"]) for g in toplam], [("2026-11-01", 2), ("2026-11-02", 1)])
        self.assertAlmostEqual(toplam[0]["net_tutar"], -2.0)
        self.assertAlmostEqual(toplam[-1]["birikimli"], -1.5)


class RaporEkrani(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        klasor = sahte_sinav_klasoru(Path(cls.gecici.name) / "veri", SIMDI)
        cls.ozet = sonuc.genel_ozet(klasor, SIMDI)
        cls.html = sayfa.html_uret(cls.ozet)

    @classmethod
    def tearDownClass(cls):
        cls.gecici.cleanup()

    def bolum(self, html=None):
        html = html or self.html
        return html[html.index('<section id="rapor"'):html.index("</section>", html.index('<section id="rapor"'))]

    def test_ozet_her_bot_icin_gunluk_tasir(self):
        for b in self.ozet["botlar"]:
            self.assertAlmostEqual(sum(g["net_tutar"] for g in b["gunluk"]), b["net_tutar"], places=6)
        self.assertAlmostEqual(sum(g["net_tutar"] for g in self.ozet["gunluk_toplam"]),
                               self.ozet["toplam"]["net_tutar"], places=6)

    def test_ekran_ve_gezinti(self):
        self.assertIn('<a href="#rapor">Rapor</a>', self.html)
        self.assertIn('<section id="rapor" class="ekran">', self.html)

    def test_bot_secimi(self):
        b = self.bolum()
        dugmeler = re.findall(r'<input type="radio" name="rapor-bot" id="rb-(\d+)"', b)
        self.assertEqual(len(dugmeler), len(ESKI_BOTLAR) + 1)            # bütün botlar + her bot
        self.assertEqual(b.count(" checked>"), 1)
        self.assertIn('<label for="rb-0">Bütün botlar</label>', b)
        for k in range(len(dugmeler)):
            self.assertIn(f'class="rapor-panel rp-{k}"', b)
            self.assertIn(f"#rb-{k}:checked~.rapor-paneller .rp-{k}", sayfa.STIL)

    def test_gunluk_tablo_ve_grafik(self):
        b = self.bolum()
        self.assertIn('<table class="cizelge gunluk">', b)
        self.assertIn('class="g-grafik"', b)
        self.assertIn("Artıda biten gün", b)
        # İşlemsiz bot boş panel gösterir.
        bos = [b_ for b_ in self.ozet["botlar"] if not b_["gunluk"]]
        if bos:
            self.assertIn("Henüz kapanmış işlem yok.", b)

    def test_telegram_dosyasinda_da_calisir(self):
        dosya = sayfa.html_uret(self.ozet, yenile_saniye=0)
        self.assertNotIn("<script", dosya)
        self.assertIn('name="rapor-bot"', self.bolum(dosya))

    def test_tazelemede_secim_korunur_ve_izin_basligi_uyar(self):
        metin = sayfa.betik(60)
        self.assertIn(".rapor-radyo:checked", metin)
        # Betik değişti; izin başlığı yeni metnin özetini taşımalı (yoksa tarayıcı betiği çalıştırmaz).
        import base64
        import hashlib

        ozet = base64.b64encode(hashlib.sha256(metin.encode("utf-8")).digest()).decode("ascii")
        self.assertIn(f"'sha256-{ozet}'", panel.guvenlik_basligi(60))
        self.assertIn(f"<script>{metin}</script>", sayfa.html_uret(self.ozet, yenile_saniye=60))


if __name__ == "__main__":
    unittest.main()
