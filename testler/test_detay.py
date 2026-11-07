"""Bot detayı (/detay): simülasyon, oranlar, günlük bütçe kullanımı (8 Kasım 2026)."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import detay
from karabasan.kural import kural_yukle
from testler.veri import sahte_islem_db

T0 = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def mum(i, o, h, l, c):
    return (T0 + timedelta(minutes=5 * i), o, h, l, c)


class Simule(unittest.TestCase):
    def test_alimda_iz_suren_stop_tetikten_sonra_gerileyince(self):
        # giriş 100; 1. mum 1,5'e çıkar (tetik 1,2 aşılır); 2. mum 0,9'a düşer: seviye 1,5-0,3 = 1,2 → iz
        m = [mum(0, 100, 101.5, 100, 101.4), mum(1, 101.4, 101.2, 100.9, 101.0)]
        r = detay.simule(m, 100.0, "alim", 3.0, 1.2, 0.3, komisyon=0.0)
        self.assertEqual(r["neden"], "iz")
        self.assertAlmostEqual(r["cikis_fiyati"], 101.2)
        self.assertAlmostEqual(r["kz_yuzde"], 1.2)

    def test_mesafe_buyudukce_ayni_girisler_farkli_sonuc(self):
        m = [mum(0, 100, 101.5, 100, 101.4), mum(1, 101.4, 101.2, 100.9, 101.0), mum(2, 101.0, 102.0, 101.0, 101.8)]
        dar = detay.simule(m, 100.0, "alim", 3.0, 1.2, 0.3, komisyon=0.0)
        genis = detay.simule(m, 100.0, "alim", 3.0, 1.2, 0.6, komisyon=0.0)
        self.assertEqual(dar["neden"], "iz")
        self.assertIn(genis["neden"], ("iz", "veri_bitti"))
        self.assertNotAlmostEqual(dar["kz_yuzde"], genis["kz_yuzde"])

    def test_stop_once_gelir_ve_mae_yazilir(self):
        m = [mum(0, 100, 100.4, 98.5, 98.8)]
        r = detay.simule(m, 100.0, "alim", 1.5, 1.2, 0.3, komisyon=0.0)
        self.assertEqual(r["neden"], "stop")
        self.assertAlmostEqual(r["kz_yuzde"], -1.5)
        self.assertAlmostEqual(r["mae"], 1.5)

    def test_acigа_satista_ters_yon_yukari(self):
        # açığa satış, giriş 100: fiyat 99,1'e düşer (lehe 0,9), sonra 1,0'e kadar yükselir (ters)
        m = [mum(0, 100, 100.0, 99.1, 99.2), mum(1, 99.2, 100.3, 99.0, 100.2)]
        r = detay.simule(m, 100.0, "aciga_satis", 3.0, None, None, komisyon=0.0)
        self.assertEqual(r["neden"], "veri_bitti")
        self.assertAlmostEqual(r["mae"], 0.3)
        self.assertAlmostEqual(r["mfe"], 1.0)   # en düşük 99,0 → lehe %1

    def test_veri_bitince_son_kapanis_kullanilir(self):
        m = [mum(0, 100, 100.5, 99.8, 100.2)]
        r = detay.simule(m, 100.0, "alim", 3.0, None, None, komisyon=0.05)
        self.assertEqual(r["neden"], "veri_bitti")
        self.assertAlmostEqual(r["kz_yuzde"], 0.2 - 0.1)

    def test_kural_kopyasi_aynidir_botun_stopu_tetigi(self):
        kural = kural_yukle("SMK")
        k = detay.senaryo_kurallari(kural)
        self.assertEqual(k["stop"], kural["cikis"]["zarar_durdur_yuzde"])
        self.assertEqual(k["tetik"], kural["cikis"]["iz_suren_stop"]["tetik_yuzde"])


class StopEsleme(unittest.TestCase):
    def test_veritabani_stop_nedeni_stop_sayilir(self):
        # sonuc.CIKIS_NEDENI: stop_loss -> "stop"; satır stop olarak işaretlenmeli
        kural = kural_yukle("SMK")
        islem = {"kimlik": 1, "parite": "ETH/USDT:USDT", "piyasa": "vadeli", "bot": "smk-vadeli", "yon": "aciga_satis",
                 "giris_zamani": T0, "cikis_zamani": T0 + timedelta(minutes=30), "giris_fiyati": 100.0,
                 "ilk_giris_fiyati": 100.0, "net_yuzde": -9.2, "net_tutar": -4.6, "neden": "stop", "tutar": 50.0}
        def getir(*_):
            return [(T0 + timedelta(minutes=5 * k), 100, 100.5, 99.5, 100) for k in range(8)]
        satir = detay.islem_satiri(islem, kural, getir)
        self.assertTrue(satir["stop_oldu"])
        islem["neden"] = "iz süren stop"
        self.assertFalse(detay.islem_satiri(islem, kural, getir)["stop_oldu"])


class Oranlar(unittest.TestCase):
    def test_yuzdeler_ve_stopsuz_ortalama(self):
        satirlar = [
            {"gercek_yuzde": 1.0, "stop_oldu": False, "mae": 0.5, "m06": 1.2, "t2m05": 0.8, "bot_kurali": 1.0},
            {"gercek_yuzde": -9.0, "stop_oldu": True, "mae": 9.0, "m06": -9.0, "t2m05": -9.0, "bot_kurali": -9.0},
            {"gercek_yuzde": -0.5, "stop_oldu": False, "mae": 1.5, "m06": -0.2, "t2m05": 0.1, "bot_kurali": -0.5},
            {"gercek_yuzde": 2.0, "stop_oldu": False, "mae": 0.0, "m06": 2.0, "t2m05": 2.0, "bot_kurali": 2.0},
        ]
        o = detay.oranlar(satirlar)
        self.assertEqual(o["n"], 4)
        self.assertEqual(o["kazanan"], 2)
        self.assertAlmostEqual(o["per100_kazanan"], 50.0)
        self.assertAlmostEqual(o["per100_stop"], 25.0)
        self.assertAlmostEqual(o["stopsuz_ort_mae"], (0.5 + 1.5 + 0.0) / 3)
        self.assertAlmostEqual(o["t2m05_toplam_yuzde"], 0.8 - 9.0 + 0.1 + 2.0)

    def test_bos_liste(self):
        self.assertEqual(detay.oranlar([]), {"n": 0})


class GunlukKullanim(unittest.TestCase):
    def test_ayni_gun_ust_uste_binen_teminatlar(self):
        g = T0.replace(hour=0, minute=0)
        kapali = [
            {"giris_zamani": g + timedelta(hours=1), "cikis_zamani": g + timedelta(hours=5), "tutar": 50.0},
            {"giris_zamani": g + timedelta(hours=2), "cikis_zamani": g + timedelta(hours=3), "tutar": 150.0},
            {"giris_zamani": g + timedelta(hours=6), "cikis_zamani": g + timedelta(hours=7), "tutar": 50.0},
        ]
        gun = detay.gunluk_kullanim(kapali, butce=1000.0)
        self.assertEqual(len(gun), 1)
        self.assertAlmostEqual(gun[0]["en_cok"], 200.0)           # 50 + 150 aynı anda
        self.assertAlmostEqual(gun[0]["dokunulmadi"], 800.0)

    def test_gece_yarisindan_acik_kalan_islem_o_gunde_de_sayilir(self):
        g = T0.replace(hour=0, minute=0)
        kapali = [{"giris_zamani": g - timedelta(hours=3), "cikis_zamani": g + timedelta(hours=2), "tutar": 300.0}]
        gun = {r["gun"]: r for r in detay.gunluk_kullanim(kapali, butce=1000.0)}
        self.assertIn(g.date(), gun)                                   # işlemin çıkış günü
        self.assertAlmostEqual(gun[g.date()]["en_cok"], 300.0)         # gece yarısından önce açık teminat
        self.assertAlmostEqual(gun[g.date()]["dokunulmadi"], 700.0)

    def test_butce_asilirsa_dokunulmayan_sifir(self):
        g = T0.replace(hour=0, minute=0)
        kapali = [{"giris_zamani": g, "cikis_zamani": g + timedelta(hours=1), "tutar": 1200.0}]
        self.assertEqual(detay.gunluk_kullanim(kapali, butce=1000.0)[0]["dokunulmadi"], 0.0)


class Sayfa(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.klasor = Path(self.gecici.name)
        self.yol = self.klasor / "db" / "smk-vadeli.sqlite"
        sahte_islem_db(self.yol, [
            ("ETH/USDT:USDT", T0, T0 + timedelta(hours=2), -2.0, "stop_loss", True),
            ("SOL/USDT:USDT", T0 + timedelta(hours=3), T0 + timedelta(hours=4), 1.0, "exit_signal", True),
        ])

    def tearDown(self):
        self.gecici.cleanup()

    def test_sayfa_bolumleri_ve_hesap(self):
        def getir(parite, piyasa, aralik, bas, bit):
            m, t = [], bas
            while t <= bit:
                m.append((t, 100.0, 100.4, 99.6, 100.1))
                t += timedelta(minutes=5)
            return m

        html = detay.sayfa_uret("smk-vadeli", self.klasor, getir=getir, simdi=T0 + timedelta(days=1))
        self.assertIn("Oranlar", html)
        self.assertIn("Trailing 0,6 olsaydı", html)
        self.assertIn("Tetik %2 + trailing 0,5", html)
        self.assertIn("Günlük bütçe kullanımı", html)
        self.assertIn("ETH", html)
        self.assertNotIn("<script", html)

    def test_mum_alinamazsa_satir_yine_gelir(self):
        def bozuk(*_):
            raise OSError("ağ yok")

        html = detay.sayfa_uret("smk-vadeli", self.klasor, getir=bozuk, simdi=T0 + timedelta(days=1))
        self.assertIn("ETH", html)
        self.assertIn("–", html)

    def test_bilinmeyen_bot(self):
        self.assertIn("Böyle bir bot yok", detay.sayfa_uret("yok", self.klasor, simdi=T0))


if __name__ == "__main__":
    unittest.main()
