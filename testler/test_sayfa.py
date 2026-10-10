"""Sonuç sayfası ve sunucusu."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import panel, sayfa, sonuc
from testler.veri import sahte_sinav_klasoru

SIMDI = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)


class BicimTesti(unittest.TestCase):
    def test_turkce_sayi_bicimi(self):
        self.assertEqual(sayfa.sayi(1234.5), "1.234,50")
        self.assertEqual(sayfa.sayi(-0.75), "−0,75")
        self.assertEqual(sayfa.sayi(None), "–")
        self.assertEqual(sayfa.sayi(float("inf")), "sonsuz")

    def test_isaretli_sayi(self):
        self.assertEqual(sayfa.isaretli(19.31), "+19,31")
        self.assertEqual(sayfa.isaretli(-9.256), "−9,26")
        self.assertEqual(sayfa.isaretli(0.001), "0,00")   # eksi sıfır ya da artı sıfır yazılmaz
        self.assertEqual(sayfa.isaretli(-0.001), "0,00")

    def test_yuzde_isareti_basta(self):
        self.assertEqual(sayfa.yuzde(64.62), "%64,6")

    def test_yerel_saat_bukres(self):
        yerel, ad = sayfa.yerel_zaman(SIMDI)
        self.assertEqual(yerel.hour, 11)  # kasımda UTC+2
        self.assertEqual(ad, "Bükreş saati")


class SayfaTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        cls.klasor = sahte_sinav_klasoru(Path(cls.gecici.name) / "veri", SIMDI)

    @classmethod
    def tearDownClass(cls):
        cls.gecici.cleanup()

    def test_sinav_sayfasi(self):
        html = sayfa.html_uret(sonuc.genel_ozet(self.klasor, SIMDI))
        self.assertIn("Sınavın 12. günü.", html)
        self.assertIn("18 gün kaldı", html)
        for bot in ("s1-spot", "s5k-vadeli", "s6-vadeli"):
            self.assertIn(bot, html)
        # Botlar düz adlarıyla görünür.
        self.assertIn("Yükselişte düşüşü al", html)
        self.assertIn("Likidite avı sonrası alım (akıllı para + RSI)", html)
        self.assertEqual(html.count('class="gun gecti'), 11)
        self.assertEqual(html.count('class="gun bugun'), 1)

    def test_dis_kaynak_yok(self):
        html = sayfa.html_uret(sonuc.genel_ozet(self.klasor, SIMDI))
        for yasak in ("http://", "https://", "<script", "@import", "url("):
            self.assertNotIn(yasak, html)

    def test_bos_sunucu_sayfasi(self):
        with tempfile.TemporaryDirectory() as bos:
            html = sayfa.html_uret(sonuc.genel_ozet(Path(bos), SIMDI))
        self.assertIn("Botlar henüz kurulmadı.", html)
        self.assertIn("Henüz kapanmış işlem yok", html)

    def test_isinma_sayfasi_sinav_saati_baslamadi_der(self):
        with tempfile.TemporaryDirectory() as gecici:
            klasor = Path(gecici)
            (klasor / "isinma_baslangici.txt").write_text((SIMDI - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            html = sayfa.html_uret(sonuc.genel_ozet(klasor, SIMDI))
        self.assertIn("Isınma dönemi, 3. gün.", html)
        self.assertIn("sınava sayılmıyor", html)
        self.assertEqual(html.count('class="gun gecti'), 0)

    def test_bitis_sayfasi_gercek_paraya_gecilmedigini_soyler(self):
        html = sayfa.html_uret(sonuc.genel_ozet(self.klasor, SIMDI + timedelta(days=25)))
        self.assertIn("Sınav bitti.", html)
        self.assertIn("Gerçek paraya geçilmiyor", html)

    def test_parite_adi_html_olarak_calismaz(self):
        ozet = sonuc.genel_ozet(self.klasor, SIMDI)
        ozet["son_islemler"][0]["parite"] = "<img src=x onerror=alert(1)>"
        html = sayfa.html_uret(ozet)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)

    def test_yenileme_kapatilabilir(self):
        ozet = sonuc.genel_ozet(self.klasor, SIMDI)
        self.assertIn('http-equiv="refresh"', sayfa.html_uret(ozet))
        self.assertNotIn('http-equiv="refresh"', sayfa.html_uret(ozet, yenile_saniye=0))


class SunucuTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        klasor = sahte_sinav_klasoru(Path(cls.gecici.name) / "veri", datetime.now(timezone.utc))
        cls.sunucu = panel.sunucu_kur(klasor, adres="127.0.0.1", port=0)
        cls.adres = f"http://127.0.0.1:{cls.sunucu.server_address[1]}"
        threading.Thread(target=cls.sunucu.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()
        cls.sunucu.server_close()
        cls.gecici.cleanup()

    def _al(self, yol):
        with urllib.request.urlopen(self.adres + yol, timeout=5) as yanit:
            return yanit.status, yanit.headers, yanit.read().decode("utf-8")

    def test_ana_sayfa(self):
        kod, baslik, govde = self._al("/")
        self.assertEqual(kod, 200)
        self.assertIn("text/html", baslik["Content-Type"])
        self.assertIn("Sınavın 12. günü.", govde)
        self.assertEqual(baslik["Cache-Control"], "no-store")

    def test_veri_json(self):
        _kod, _baslik, govde = self._al("/veri.json")
        veri = json.loads(govde)
        self.assertEqual(veri["donem"], "sinav")
        self.assertEqual(len(veri["botlar"]), 10)

    def test_saglik(self):
        self.assertEqual(self._al("/saglik")[2], "tamam\n")

    def test_bilinmeyen_adres_404(self):
        with self.assertRaises(urllib.error.HTTPError) as hata:
            self._al("/../.env")
        self.assertEqual(hata.exception.code, 404)

    def test_yazma_istegi_kabul_edilmez(self):
        istek = urllib.request.Request(self.adres + "/", data=b"x=1", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as hata:
            urllib.request.urlopen(istek, timeout=5)
        self.assertEqual(hata.exception.code, 501)


if __name__ == "__main__":
    unittest.main()
