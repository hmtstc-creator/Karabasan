"""İşlem grafiği ekranı ve /islem sayfası (6 Kasım 2026)."""

import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from karabasan import islem_grafik as ig
from karabasan import panel, sayfa, sonuc
from testler.veri import eski_bot_listesi_baslat, sahte_sinav_klasoru

SIMDI = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)


def setUpModule():
    global _geri_al
    _geri_al = eski_bot_listesi_baslat()


def tearDownModule():
    _geri_al()


def sahte_mumlar(parite, piyasa, aralik, bas, son):
    dk = dict(ig.ARALIKLAR)[aralik]
    m, t = [], bas
    while t <= son:
        m.append((t, 100.0, 101.0, 99.0, 100.5))
        t += timedelta(minutes=dk)
    return m


class Yardimcilar(unittest.TestCase):
    def test_aralik_mum_sayisi_sinirli(self):
        t0 = SIMDI - timedelta(days=3)
        for sure in (timedelta(minutes=5), timedelta(hours=3), timedelta(days=2), timedelta(days=20)):
            ad, dk, bas, son = ig.aralik_sec(t0, t0 + sure)
            self.assertLess(bas, t0)
            self.assertGreater(son, t0 + sure)
            if ad != "1d":
                self.assertLessEqual((son - bas) / timedelta(minutes=dk), ig.EN_FAZLA_MUM + 1)
            self.assertGreaterEqual((son - bas) / timedelta(minutes=dk), ig.EN_AZ_MUM - 1)

    def test_seviyeler_aciga_satis_stop_yukarida(self):
        kural = {"cikis": {"zarar_durdur_yuzde": 9.0, "iz_suren_stop": {"tetik_yuzde": 1.2, "mesafe_yuzde": 0.3}}}
        s = ig.seviyeler({"yon": "aciga_satis", "giris_fiyati": 100.0}, kural)
        self.assertAlmostEqual(s["stop"], 109.0)
        self.assertAlmostEqual(s["tetik"], 98.8)

    def test_seviyeler_alim(self):
        s = ig.seviyeler({"yon": "alim", "giris_fiyati": 100.0},
                         {"cikis": {"zarar_durdur_yuzde": 3.0, "kar_hedefi_yuzde": 2.0}})
        self.assertAlmostEqual(s["stop"], 97.0)
        self.assertAlmostEqual(s["hedef"], 102.0)

    def test_bilinmeyen_bot(self):
        self.assertIsNone(ig.bot_bul("../../etc"))


class Sayfalar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        cls.klasor = sahte_sinav_klasoru(Path(cls.gecici.name) / "veri", SIMDI)
        cls.ozet = sonuc.genel_ozet(cls.klasor, SIMDI)

    @classmethod
    def tearDownClass(cls):
        cls.gecici.cleanup()

    def test_liste_ekrani_baglantilar(self):
        html = sayfa._islem_grafigi_ekrani(self.ozet, "Europe/Bucharest")
        b = self.ozet["islem_listesi"][0]
        i = b["kapali"][0]
        self.assertIn(f'/islem?bot={b["bot"]}&amp;id={i["kimlik"]}', html)
        self.assertIn('id="ig-0"', html)

    def test_islem_sayfasi_grafik_ve_isaretler(self):
        b = self.ozet["islem_listesi"][0]
        i = b["kapali"][0]
        html = ig.islem_sayfasi(self.klasor, b["bot"], i["kimlik"], getir=sahte_mumlar, simdi=SIMDI)
        self.assertIn('class="g-svg ig-svg"', html)
        self.assertIn('ig-isaret giris', html)
        self.assertIn('ig-isaret cikis', html)
        self.assertIn("ig-seviye stop", html)
        self.assertNotIn("<script", html)

    def test_ag_hatasi_sayfayi_dusurmez(self):
        b = self.ozet["islem_listesi"][0]
        i = b["kapali"][0]

        def bozuk(*a):
            raise OSError("ağ yok")

        html = ig.islem_sayfasi(self.klasor, b["bot"], i["kimlik"], getir=bozuk, simdi=SIMDI)
        self.assertIn("şu an alınamadı", html)

    def test_olmayan_islem(self):
        b = self.ozet["islem_listesi"][0]
        self.assertIn("bulunamadı", ig.islem_sayfasi(self.klasor, b["bot"], 999999, getir=sahte_mumlar, simdi=SIMDI))

    def test_kapali_islem_mumlari_bir_kez_indirilir(self):
        b = self.ozet["islem_listesi"][0]
        i = b["kapali"][0]
        sayac = mock.Mock(side_effect=sahte_mumlar)
        ob = ig.MumOnbellegi()
        for _ in range(3):
            ig.islem_sayfasi(self.klasor, b["bot"], i["kimlik"], ob, getir=sayac, simdi=SIMDI)
        self.assertEqual(sayac.call_count, 1)


class Sunucu(unittest.TestCase):
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

    def test_gecersiz_istekler_404(self):
        for yol in ("/islem", "/islem?bot=yok&id=1", "/islem?bot=s1-vadeli&id=abc", "/islem?bot=s1-vadeli&id=-1"):
            with self.assertRaises(urllib.error.HTTPError) as h:
                urllib.request.urlopen(self.adres + yol, timeout=5)
            self.assertEqual(h.exception.code, 404, yol)

    def test_gecerli_istek_sayfa_doner(self):
        with mock.patch.object(ig, "mum_getir", side_effect=sahte_mumlar):
            with urllib.request.urlopen(self.adres + "/islem?bot=s1-vadeli&id=1", timeout=10) as y:
                metin = y.read().decode("utf-8")
        self.assertEqual(y.status, 200)
        self.assertIn("KARABASAN", metin)


if __name__ == "__main__":
    unittest.main()
