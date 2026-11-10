"""Güven ekranı: istatistik işlevleri, veri, çizim (betiksiz), pandas'sız içe aktarma."""

import math
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import sayfa, sonuc
from karabasan import sonuc_guven as sg
from karabasan import karne
from testler.veri import sahte_sinav_klasoru

SIMDI = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)
KOK = Path(__file__).resolve().parent.parent


class Istatistik(unittest.TestCase):
    def test_wilson_elle_hesaplanan(self):
        # 60 / 100: merkez (0,6 + 1,9208/100) / 1,038415 = 0,59633; yarı genişlik 1,96 × 0,04996 / 1,038415 = 0,09430
        alt, ust = sg.wilson(60, 100)
        self.assertAlmostEqual(alt, 50.20, places=2)
        self.assertAlmostEqual(ust, 69.06, places=2)
        # 0 / 10: üst sınır z² / (n + z²) = 3,8415 / 13,8415 = 0,27753
        alt, ust = sg.wilson(0, 10)
        self.assertEqual(alt, 0.0)
        self.assertAlmostEqual(ust, 27.75, places=2)
        self.assertIsNone(sg.wilson(0, 0))

    def test_p_degeri_tablo(self):
        # t tablosu: iki yönlü %5 kritik değerleri
        self.assertAlmostEqual(sg.p_degeri(2.228, 10), 0.05, places=3)
        self.assertAlmostEqual(sg.p_degeri(2.045, 29), 0.05, places=3)
        self.assertAlmostEqual(sg.p_degeri(3.169, 10), 0.01, places=3)
        self.assertAlmostEqual(sg.p_degeri(-2.228, 10), 0.05, places=3)
        # normal yaklaşım
        self.assertAlmostEqual(sg.p_degeri(1.96, None), 0.05, places=3)
        self.assertAlmostEqual(sg.p_degeri(0.0, 5), 1.0, places=6)
        self.assertIsNone(sg.p_degeri(None, 5))

    def test_aralik_konumu(self):
        self.assertEqual(sg.aralik_konumu((55.0, 70.0), 50.0), "ustunde")
        self.assertEqual(sg.aralik_konumu((40.0, 60.0), 50.0), "icinde")
        self.assertEqual(sg.aralik_konumu((30.0, 45.0), 50.0), "altinda")
        self.assertEqual(sg.aralik_konumu(None, 50.0), "veri_yok")

    def test_coklu_bakis(self):
        self.assertAlmostEqual(sg.coklu_bakis(1), 0.05)
        self.assertAlmostEqual(sg.coklu_bakis(17), 1 - 0.95 ** 17)

    def test_coin_bagimliligi(self):
        p = [{"parite": "SOL", "islem": 5, "net_tutar": 10.0}, {"parite": "XRP", "islem": 3, "net_tutar": -4.0},
             {"parite": "ADA", "islem": 2, "net_tutar": -2.0}]
        c = sg.coin_bagimliligi(p)
        self.assertAlmostEqual(c["en_iyisiz"], -6.0)
        self.assertAlmostEqual(c["en_kotusuz"], 8.0)
        self.assertTrue(c["tek_coine_bagli"])
        self.assertIsNone(sg.coin_bagimliligi(p[:1])["tek_coine_bagli"])

    def test_en_iyi_gunsuz(self):
        g = [{"gun": "2026-11-01", "net_tutar": 5.0}, {"gun": "2026-11-02", "net_tutar": -1.0}]
        r = sg.en_iyi_gunsuz(g)
        self.assertEqual(r["en_iyi_gun"], "2026-11-01")
        self.assertAlmostEqual(r["kalan"], -1.0)
        self.assertTrue(r["tek_gune_bagli"])
        self.assertIsNone(sg.en_iyi_gunsuz([])["kalan"])

    def test_islem_hizi(self):
        h = sg.islem_hizi(20, 10.0, 20.0, 100)
        self.assertAlmostEqual(h["gunluk_hiz"], 2.0)
        self.assertAlmostEqual(h["gereken_gun"], 40.0)
        self.assertFalse(h["yetisir"])
        self.assertTrue(sg.islem_hizi(60, 10.0, 20.0, 100)["yetisir"])
        self.assertEqual(sg.islem_hizi(120, 10.0, 5.0, 100)["eksik"], 0)
        self.assertIsNone(sg.islem_hizi(0, 0.0, 30.0, 100)["gereken_gun"])

    def test_hukum_yesil_cita(self):
        self.assertEqual(sg.hukum(None, None, 0, 100, "veri_yok", None, None, 2.5)["kod"], "islem_yok")
        self.assertEqual(sg.hukum(None, None, 5, 100, "icinde", None, None, 2.5)["kod"], "veri_az")
        self.assertEqual(sg.hukum(-3.0, 0.01, 50, 100, "altinda", False, False, 2.5)["kod"], "eksi")
        self.assertEqual(sg.hukum(3.5, 0.002, 150, 100, "ustunde", False, False, 2.5)["kod"], "arti")
        # Bir şart eksikse yeşil verilmez
        self.assertEqual(sg.hukum(3.5, 0.002, 90, 100, "ustunde", False, False, 2.5)["kod"], "zayif_arti")
        self.assertEqual(sg.hukum(3.5, 0.002, 150, 100, "ustunde", True, False, 2.5)["kod"], "zayif_arti")
        self.assertEqual(sg.hukum(1.0, 0.3, 150, 100, "icinde", False, False, 2.5)["kod"], "kanit_yok")


class Veri(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        cls.klasor = sahte_sinav_klasoru(Path(cls.gecici.name) / "veri", SIMDI)
        cls.ozet = sonuc.genel_ozet(cls.klasor, SIMDI)

    @classmethod
    def tearDownClass(cls):
        cls.gecici.cleanup()

    def test_hesap_yeniden_kullanir(self):
        v = self.ozet["ek"]["guven"]
        self.assertNotIn("hata", v)
        self.assertEqual(v["hedef_islem"], karne.SINAV_ESIKLERI["en_az_islem"])
        for b, o in zip(v["botlar"], self.ozet["botlar"]):
            self.assertEqual(b["t"], o["guven"]["t"])
            self.assertEqual(b["islem"], o["islem_sayisi"])
            self.assertEqual(b["basabas"], o["basabas_orani"])
        toplam = sonuc.guven_etiketi(sonuc.gunluk_topla([o["gunluk"] for o in self.ozet["botlar"]]))
        self.assertEqual(v["toplam"]["t"], toplam["t"])
        self.assertTrue(v["sinavda"])
        self.assertIsNone(v["botlar"][0]["gecmis_beklenti"])

    def test_json_icin(self):
        import json

        json.dumps(sonuc.json_icin(self.ozet["ek"]["guven"]))

    def test_gelecege_bakmaz(self):
        """simdi'den sonra kapanan işlemler bugünkü sayıları değiştirmez."""
        oz = self.ozet
        baglam = {"veri_klasoru": self.klasor, "simdi": SIMDI - timedelta(days=3),
                  "donem": {"donem": "sinav", "gun": 9, "baslangic": oz["baslangic"], "bitis": oz["bitis"]},
                  "ayar": {}, "botlar": oz["botlar"], "gecmis_test": {}}
        from karabasan.botlar import BOTLAR

        tum_islemler = {}
        for bot, _s, kod, _p in BOTLAR:
            kayit = sonuc.islemleri_oku(self.klasor / "db" / f"{bot}.sqlite")
            tum_islemler[kod] = [i for i in kayit["kapali"] if i["giris_zamani"] >= oz["baslangic"]]
        kesik = {k: [i for i in v if i["cikis_zamani"] <= baglam["simdi"]] for k, v in tum_islemler.items()}
        a = sg.hesapla({**baglam, "bot_islemleri": tum_islemler})
        b = sg.hesapla({**baglam, "bot_islemleri": kesik})
        alanlar = ("islem", "kazanan", "wilson", "coin", "en_iyi_gun", "hiz", "net_tutar")
        for x, y in zip(a["botlar"], b["botlar"]):
            for alan in alanlar:
                self.assertEqual(x[alan], y[alan], alan)
        self.assertEqual(a["toplam"]["t"], b["toplam"]["t"])

    def test_bos_veri(self):
        with tempfile.TemporaryDirectory() as gecici:
            klasor = Path(gecici) / "bos"
            klasor.mkdir()
            ozet = sonuc.genel_ozet(klasor, SIMDI)
            self.assertNotIn("hata", ozet["ek"]["guven"])
            html = sayfa.html_uret(ozet, yenile_saniye=0)
            self.assertEqual(html.count('<section id="guven"'), 1)
            bolum = html.split('<section id="guven"', 1)[1].split("</section>", 1)[0]
            self.assertIn("Henüz işlem yok", bolum)
            self.assertNotIn("hazırlanamadı", bolum)


class Cizim(unittest.TestCase):
    def test_betiksiz_render(self):
        with tempfile.TemporaryDirectory() as gecici:
            klasor = sahte_sinav_klasoru(Path(gecici) / "veri", SIMDI)
            (klasor / "gecmis_test.json").write_text('{"smk-vadeli": -0.12}', encoding="utf-8")
            html = sayfa.html_uret(sonuc.genel_ozet(klasor, SIMDI), yenile_saniye=0)
        self.assertEqual(html.count('<section id="guven"'), 1)
        self.assertNotIn("<script", html)
        bolum = html.split('<section id="guven"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn("hazırlanamadı", bolum)
        self.assertIn("Bugün için:", bolum)
        self.assertIn("tek dönem", bolum.lower())
        self.assertIn("Çoklu bakış", bolum)
        self.assertIn("Student t", bolum)
        self.assertIn("12 aylık test sonucu sunucuda bu sayfaya ulaşmadı", bolum)
        self.assertIn("−%0,120", bolum)
        self.assertIn('role="img"', bolum)


class PandasOlmadan(unittest.TestCase):
    def test_pandas_olmadan(self):
        kod = (
            "import sys\n"
            "sys.modules['pandas'] = None\nsys.modules['numpy'] = None\n"
            "from karabasan import sonuc_guven, sayfa_guven\n"
            "from datetime import datetime, timezone\n"
            "try:\n"
            "    from karabasan import sonuc\n"
            "except ImportError:\n"
            "    print('SONUC_PANDAS_ISTIYOR'); raise SystemExit(0)\n"
            "v = sonuc_guven.hesapla({'simdi': datetime(2026, 11, 2, tzinfo=timezone.utc),\n"
            "    'donem': {'donem': 'kurulmadi', 'gun': 0, 'baslangic': None, 'bitis': None},\n"
            "    'botlar': [], 'bot_islemleri': {}, 'gecmis_test': {}})\n"
            "assert v['toplam']['hukum']['kod'] == 'islem_yok'\n"
        )
        r = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True, cwd=KOK, env=dict(os.environ))
        self.assertEqual(r.returncode, 0, r.stderr)
        if "SONUC_PANDAS_ISTIYOR" in r.stdout:
            # Bizim iki modülümüz pandas'sız içe aktarıldı; hesapla için sonuc.py gerekir ve o, karne.py'nin
            # dosya başındaki 'import pandas' yüzünden şu an pandas ister (başkoordinatöre bildirildi).
            self.skipTest("sonuc.py şu an karne.py üzerinden pandas istiyor; hesapla bu yüzden atlandı")


if __name__ == "__main__":
    unittest.main()
