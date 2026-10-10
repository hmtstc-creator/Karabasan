"""Sonuç özeti: sahte kayıt dosyalarından doğru sayıları çıkarıyor mu?"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import sonuc
from testler.veri import sahte_islem_db, sahte_sinav_klasoru

SIMDI = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)


class ZamanTesti(unittest.TestCase):
    def test_motorun_yazdigi_bicim_utc_sayilir(self):
        z = sonuc.zaman_coz("2026-10-10 12:00:00.123456")
        self.assertEqual(z, datetime(2026, 10, 10, 12, 0, 0, 123456, tzinfo=timezone.utc))

    def test_z_ile_biten_bicim(self):
        self.assertEqual(sonuc.zaman_coz("2026-10-10T12:00:00Z"),
                         datetime(2026, 10, 10, 12, tzinfo=timezone.utc))

    def test_bozuk_ve_bos_deger(self):
        self.assertIsNone(sonuc.zaman_coz(None))
        self.assertIsNone(sonuc.zaman_coz("  "))
        self.assertIsNone(sonuc.zaman_coz("dün"))


class DonemTesti(unittest.TestCase):
    def test_kurulmadi(self):
        self.assertEqual(sonuc.donem_bilgisi(SIMDI, None, None)["donem"], "kurulmadi")

    def test_isinma_gunu(self):
        d = sonuc.donem_bilgisi(SIMDI, SIMDI - timedelta(days=2, hours=1), None)
        self.assertEqual((d["donem"], d["gun"]), ("isinma", 3))

    def test_sinavin_ilk_ve_son_gunu(self):
        ilk = sonuc.donem_bilgisi(SIMDI, None, SIMDI - timedelta(minutes=5))
        self.assertEqual((ilk["donem"], ilk["gun"]), ("sinav", 1))
        son = sonuc.donem_bilgisi(SIMDI, None, SIMDI - timedelta(days=29, hours=23))
        self.assertEqual((son["donem"], son["gun"]), ("sinav", 30))

    def test_otuz_gun_dolunca_biter(self):
        d = sonuc.donem_bilgisi(SIMDI, None, SIMDI - timedelta(days=30))
        self.assertEqual(d["donem"], "bitti")
        self.assertEqual(d["bitis"], SIMDI)

    def test_gelecekteki_sinav_tarihi_isinma_sayilir(self):
        d = sonuc.donem_bilgisi(SIMDI, SIMDI - timedelta(days=1), SIMDI + timedelta(days=1))
        self.assertEqual(d["donem"], "isinma")


class KayitOkumaTesti(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.klasor = Path(self.gecici.name)

    def tearDown(self):
        self.gecici.cleanup()

    def test_dosya_yoksa_hata_metni(self):
        kayit = sonuc.islemleri_oku(self.klasor / "yok.sqlite")
        self.assertEqual(kayit["kapali"], [])
        self.assertIn("henüz yok", kayit["hata"])

    def test_bozuk_dosya_cokertmez(self):
        yol = self.klasor / "bozuk.sqlite"
        yol.write_bytes(b"bu bir veritabani degil" * 50)
        kayit = sonuc.islemleri_oku(yol)
        self.assertIsNotNone(kayit["hata"])

    def test_tablo_yoksa_hata_metni(self):
        import sqlite3

        yol = self.klasor / "bos.sqlite"
        sqlite3.connect(yol).close()
        self.assertIn("işlem tablosu yok", sonuc.islemleri_oku(yol)["hata"])

    def test_kapali_ve_acik_islemler_ayrilir(self):
        a = SIMDI - timedelta(hours=5)
        yol = sahte_islem_db(self.klasor / "b.sqlite", [
            ("SOL/USDT", a, a + timedelta(minutes=30), 1.05, "roi", False),
            ("XRP/USDT", a, a + timedelta(minutes=90), -1.15, "stop_loss", False),
            ("ADA/USDT:USDT", a, a + timedelta(minutes=240), 0.2, "sure_asimi", True),
            ("DOGE/USDT", SIMDI - timedelta(minutes=10), None, 0.0, None, False),
        ])
        kayit = sonuc.islemleri_oku(yol)
        self.assertIsNone(kayit["hata"])
        self.assertEqual(len(kayit["kapali"]), 3)
        self.assertEqual(len(kayit["acik"]), 1)
        ilk, ikinci, ucuncu = kayit["kapali"]
        self.assertAlmostEqual(ilk["net_yuzde"], 1.05)
        self.assertAlmostEqual(ilk["net_tutar"], 0.525)
        self.assertEqual(ilk["neden"], "kâr hedefi")
        self.assertEqual(ikinci["neden"], "stop")
        self.assertEqual(ucuncu["neden"], "süre aşımı")
        self.assertEqual(ucuncu["yon"], "aciga_satis")
        self.assertAlmostEqual(ilk["sure_dakika"], 30.0)

    def test_kayit_dosyasi_salt_okunur_acilir(self):
        a = SIMDI - timedelta(hours=5)
        yol = sahte_islem_db(self.klasor / "b.sqlite", [("SOL/USDT", a, a + timedelta(minutes=30), 1.0, "roi", False)])
        once = yol.read_bytes()
        sonuc.islemleri_oku(yol)
        self.assertEqual(yol.read_bytes(), once)


class GenelOzetTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        cls.klasor = sahte_sinav_klasoru(Path(cls.gecici.name) / "veri", SIMDI)
        cls.ozet = sonuc.genel_ozet(cls.klasor, SIMDI)
        cls.botlar = {b["bot"]: b for b in cls.ozet["botlar"]}

    @classmethod
    def tearDownClass(cls):
        cls.gecici.cleanup()

    def test_donem_ve_gun(self):
        self.assertEqual((self.ozet["donem"], self.ozet["gun"]), ("sinav", 12))

    def test_on_bot_listelenir(self):
        self.assertEqual(len(self.ozet["botlar"]), 10)

    def test_isinma_islemleri_sinava_sayilmaz(self):
        # Sahte veride her bota ısınma döneminden iki kârlı işlem konur.
        self.assertEqual(self.botlar["s1-spot"]["islem_sayisi"], 130)
        self.assertEqual(self.botlar["s5-vadeli"]["islem_sayisi"], 0)

    def test_kaydi_olmayan_bot_hata_tasir_ama_ozet_cikar(self):
        self.assertIsNotNone(self.botlar["s5k-vadeli"]["hata"])
        self.assertEqual(self.botlar["s5k-vadeli"]["islem_sayisi"], 0)

    def test_toplam_botlarin_toplamidir(self):
        t = self.ozet["toplam"]
        self.assertEqual(t["islem_sayisi"], sum(b["islem_sayisi"] for b in self.ozet["botlar"]))
        self.assertAlmostEqual(t["net_tutar"], sum(b["net_tutar"] for b in self.ozet["botlar"]))

    def test_sinavda_yedi_olcut_gelir_karar_gelmez(self):
        b = self.botlar["s1-spot"]
        self.assertEqual([o["no"] for o in b["olcutler"]], [1, 2, 3, 4, 5, 6, 7])
        self.assertIsNone(b["karar"])
        self.assertEqual(b["olcutler"][0]["durum"], "saglandi")       # 130 işlem
        self.assertEqual(b["olcutler"][6]["durum"], "veri_yok")       # geçmiş testi yok

    def test_son_islemler_yeniden_eskiye_ve_en_fazla_on_bes(self):
        zamanlar = [i["cikis_zamani"] for i in self.ozet["son_islemler"]]
        self.assertEqual(len(zamanlar), 15)
        self.assertEqual(zamanlar, sorted(zamanlar, reverse=True))

    def test_gunluk_dosyasi_olmayan_bot_calisiyor_sayilmaz(self):
        self.assertEqual(self.ozet["toplam"]["calisan_bot"], 0)
        self.assertFalse(self.botlar["s1-spot"]["calisiyor"])

    def test_gunluk_tazeyse_calisiyor_bayatsa_degil(self):
        gunlukler = self.klasor / "logs"
        gunlukler.mkdir(exist_ok=True)
        taze, bayat = gunlukler / "s1-spot.log", gunlukler / "s2-spot.log"
        for dosya, dakika in ((taze, 2), (bayat, 40)):
            dosya.write_text("satir\n")
            zaman = (SIMDI - timedelta(minutes=dakika)).timestamp()
            os.utime(dosya, (zaman, zaman))
        try:
            botlar = {b["bot"]: b for b in sonuc.genel_ozet(self.klasor, SIMDI)["botlar"]}
            self.assertTrue(botlar["s1-spot"]["calisiyor"])
            self.assertFalse(botlar["s2-spot"]["calisiyor"])
            self.assertAlmostEqual(botlar["s2-spot"]["gunluk_yasi_dakika"], 40.0, places=1)
        finally:
            taze.unlink()
            bayat.unlink()

    def test_json_a_cevrilebilir(self):
        import json

        metin = json.dumps(sonuc.json_icin(self.ozet))
        self.assertIn('"donem": "sinav"', metin)

    def test_sinav_bitince_karar_verilir(self):
        ozet = sonuc.genel_ozet(self.klasor, SIMDI + timedelta(days=25))
        self.assertEqual(ozet["donem"], "bitti")
        kararlar = {b["karar"] for b in ozet["botlar"]}
        self.assertEqual(kararlar, {"kaldi"})  # geçmiş testi olmadan kimse geçemez

    def test_gecmis_testi_olan_ve_olcutleri_saglayan_bot_gecer(self):
        import json

        with tempfile.TemporaryDirectory() as gecici:
            klasor = Path(gecici)
            sinav = SIMDI - timedelta(days=30, hours=1)
            (klasor / "sinav_baslangici.txt").write_text(sinav.strftime("%Y-%m-%dT%H:%M:%SZ"))
            (klasor / "gecmis_test.json").write_text(json.dumps({"s1-spot": 0.2}))
            islemler = []
            for k in range(140):
                a = sinav + timedelta(hours=5 * k + 1)
                kazandi = k % 10 < 7
                islemler.append(("SOL/USDT", a, a + timedelta(minutes=30),
                                 1.05 if kazandi else -1.15, "roi" if kazandi else "stop_loss", False))
            sahte_islem_db(klasor / "db" / "s1-spot.sqlite", islemler)
            ozet = sonuc.genel_ozet(klasor, SIMDI)
            botlar = {b["bot"]: b for b in ozet["botlar"]}
            self.assertEqual(botlar["s1-spot"]["karar"], "gecti")
            self.assertEqual(botlar["s2-spot"]["karar"], "kaldi")


if __name__ == "__main__":
    unittest.main()
