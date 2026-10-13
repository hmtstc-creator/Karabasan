"""Stop sonrası izleme: stop daha geniş olsaydı ne olurdu?"""

import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

from karabasan import kayitci, sonuc
from karabasan import stop_sonrasi as ss
from testler.veri import eski_bot_listesi_baslat, sahte_islem_db

T0 = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)

def setUpModule():
    # Bu testler on iki botluk eski listeyle kurulur (bkz. testler.veri.ESKI_BOTLAR).
    global _geri_al
    _geri_al = eski_bot_listesi_baslat()


def tearDownModule():
    _geri_al()



def mumlar(fiyatlar, baslangic=T0, dakika=1):
    """(düşük, yüksek) çiftlerinden mum üretir; kapanış = yüksek ile düşüğün ortası."""
    sonuc_ = []
    for k, (dusuk, yuksek) in enumerate(fiyatlar):
        sonuc_.append((baslangic + timedelta(minutes=k * dakika), (dusuk + yuksek) / 2, yuksek, dusuk, (dusuk + yuksek) / 2))
    return sonuc_


def izle(fiyatlar, yon="alim", sure=10, **ek):
    """Giriş 100, hedef %1, stop %1, komisyon taraf başına %0,1; stop ilk mumda oldu."""
    return ss.izle(yon, 100.0, T0, T0 + timedelta(seconds=20), mumlar(fiyatlar),
                   hedef_yuzde=1.0, stop_yuzde=1.0, sure_dakika=sure, komisyon_yuzde=0.1, **ek)


class TekIslemTesti(unittest.TestCase):
    def test_hafif_sarkip_donen_islem_genis_stopla_hedefe_ulasir(self):
        # 98,9'a iner (stop 99), sonra 101'i görür.
        s = izle([(98.9, 99.5)] + [(99.2, 100.0)] * 4 + [(100.0, 101.1)] + [(100.5, 101.0)] * 4)
        self.assertTrue(s["hedefi_gordu"])
        for carpan in ("1.5", "2", "3"):
            self.assertEqual(s["alternatif"][carpan], {"sonuc": "hedef", "net_yuzde": 0.8})
        self.assertAlmostEqual(s["en_kotu_yuzde"], -1.1)

    def test_derine_inen_islemde_dar_secenek_de_stop_olur(self):
        # 98,2'ye iner: 1,5 kat (98,5) stop olur, 2 kat (98,0) dayanır, sonra hedef gelir.
        s = izle([(98.9, 99.5), (98.2, 99.0)] + [(98.6, 99.9)] * 3 + [(100.0, 101.2)] + [(100.0, 101.0)] * 4)
        self.assertEqual(s["alternatif"]["1.5"], {"sonuc": "stop", "net_yuzde": -1.7})
        self.assertEqual(s["alternatif"]["2"]["sonuc"], "hedef")
        self.assertEqual(s["alternatif"]["3"]["sonuc"], "hedef")
        self.assertEqual(ss.islem_cumlesi(s), "stop 2 kat geniş olsaydı hedefe ulaşırdı")

    def test_dusmeye_devam_eden_islemde_genis_stop_zarari_buyutur(self):
        s = izle([(98.9, 99.5), (97.9, 98.8), (96.5, 97.8)] + [(96.0, 96.8)] * 7)
        self.assertFalse(s["hedefi_gordu"])
        self.assertEqual(s["alternatif"]["1.5"]["net_yuzde"], -1.7)
        self.assertEqual(s["alternatif"]["2"]["net_yuzde"], -2.2)
        self.assertEqual(s["alternatif"]["3"]["net_yuzde"], -3.2)
        self.assertEqual(ss.islem_cumlesi(s), "3 kat geniş stop da olurdu")

    def test_sure_dolarsa_son_fiyattan_kapanir(self):
        # Ne geniş stop ne hedef: süre sonunda 99,5'ten kapanır (−%0,5 eksi komisyon).
        s = izle([(98.9, 99.5)] + [(99.3, 99.7)] * 9)
        for carpan in ("1.5", "2", "3"):
            self.assertEqual(s["alternatif"][carpan], {"sonuc": "sure", "net_yuzde": -0.7})
        self.assertEqual(ss.islem_cumlesi(s), "geniş stopla da hedefe ulaşmazdı")

    def test_sure_dolduktan_sonraki_yukselis_sayilmaz(self):
        # Hedef 12. dakikada geliyor ama işlemin süresi 10 dakika.
        s = izle([(98.9, 99.5)] + [(99.3, 99.7)] * 9 + [(100.5, 102.0)] * 5)
        self.assertFalse(s["hedefi_gordu"])
        self.assertEqual(s["alternatif"]["2"]["sonuc"], "sure")

    def test_ayni_mumda_genis_stop_ve_hedef_varsa_stop_sayilir(self):
        s = izle([(98.9, 99.5), (98.4, 101.5)] + [(100.0, 100.5)] * 8)
        self.assertEqual(s["alternatif"]["1.5"]["sonuc"], "stop")   # 98,5 görüldü: kötümser
        self.assertEqual(s["alternatif"]["2"]["sonuc"], "hedef")    # 98,0 görülmedi

    def test_stoptan_onceki_mumlar_hesaba_girmez(self):
        # Stop 5. dakikada oldu; ondan önceki 97'lik iğne (olamaz ama) sayılmamalı.
        liste = mumlar([(97.0, 100.2)] * 5 + [(98.9, 99.5)] + [(99.5, 101.2)] * 4)
        s = ss.izle("alim", 100.0, T0, T0 + timedelta(minutes=5, seconds=10), liste, 1.0, 1.0, 10, 0.1)
        self.assertEqual(s["alternatif"]["1.5"]["sonuc"], "hedef")
        self.assertAlmostEqual(s["en_kotu_yuzde"], -1.1)

    def test_aciga_satis_ters_yonde_hesaplanir(self):
        # Açığa satış: stop 101, hedef 99. 101,2'ye çıkıp 98,9'a iniyor.
        s = izle([(100.4, 101.2)] + [(100.0, 100.9)] * 3 + [(98.9, 100.0)] + [(99.0, 99.5)] * 5, yon="aciga_satis")
        self.assertEqual(s["alternatif"]["1.5"], {"sonuc": "hedef", "net_yuzde": 0.8})
        self.assertAlmostEqual(s["en_kotu_yuzde"], -1.2)
        # Yükselmeye devam ederse geniş stop da olur.
        s = izle([(100.4, 101.2), (101.0, 102.1)] + [(101.5, 101.9)] * 8, yon="aciga_satis")
        self.assertEqual(s["alternatif"]["2"], {"sonuc": "stop", "net_yuzde": -2.2})

    def test_veri_pencerenin_sonuna_yetmiyorsa_sonuc_verilmez(self):
        self.assertIsNone(izle([(98.9, 99.5)] + [(99.3, 99.7)] * 4))     # 10 dakikanın 5'i var
        self.assertIsNone(izle([]))
        self.assertIsNone(ss.izle("alim", 0.0, T0, T0, mumlar([(99, 100)] * 10), 1.0, 1.0, 10, 0.1))


def kayit(k, fark15, fark2=None, fark3=None, hedef=True):
    """Gerçek sonucu −1,2 olan bir stop; seçenekler gerçekten 'fark' kadar iyi ya da kötü."""
    gercek = -1.2

    def secenek(fark):
        return {"sonuc": "hedef" if fark > 0 else "stop", "net_yuzde": gercek + fark}

    return {
        "bot": "s1-vadeli",
        "cikis_zamani": (T0 + timedelta(hours=k)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "giris_zamani": (T0 + timedelta(hours=k, minutes=-30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gercek_net_yuzde": gercek,
        "hedefi_gordu": hedef,
        "en_kotu_yuzde": -1.4 - k * 0.01,
        "alternatif": {
            "1.5": secenek(fark15),
            "2": secenek(fark15 if fark2 is None else fark2),
            "3": secenek(fark15 if fark3 is None else fark3),
        },
    }


class OzetVeKararTesti(unittest.TestCase):
    def test_az_stopla_karar_verilmez(self):
        o = ss.ozetle([kayit(k, 2.0) for k in range(ss.EN_AZ_STOP - 1)], 1.0, 50.0)
        self.assertEqual(o["karar"]["kod"], "yetersiz")
        self.assertIn(f"şimdilik {ss.EN_AZ_STOP - 1} var", o["karar"]["metin"])

    def test_toplamlar(self):
        o = ss.ozetle([kayit(0, 2.0), kayit(1, -0.5), kayit(2, 2.0), kayit(3, -0.5)], 1.0, 50.0)
        self.assertEqual(o["stop_sayisi"], 4)
        satir = o["carpanlar"][0]
        self.assertEqual((satir["carpan"], satir["stop_yuzde"]), (1.5, 1.5))
        self.assertEqual((satir["hedef"], satir["stop"], satir["sure"]), (2, 2, 0))
        self.assertAlmostEqual(satir["fark_yuzde"], 3.0)
        self.assertAlmostEqual(satir["fark_tutar"], 1.5)          # 50 USDT'nin %3'ü
        self.assertAlmostEqual(satir["fark_tutar_ilk_yari"], 0.75)
        self.assertAlmostEqual(satir["fark_tutar_son_yari"], 0.75)
        self.assertAlmostEqual(o["en_kotu_yuzde"], -1.43)

    def test_iki_yarida_da_iyilesme_varsa_stop_dar(self):
        # Üçte biri kurtuluyor (+2,0), üçte ikisi yarım stop daha kaybediyor (−0,5).
        kayitlar = [kayit(k, 2.0 if k % 3 == 0 else -0.5, fark2=-1.0, fark3=-2.0) for k in range(90)]
        o = ss.ozetle(kayitlar, 1.0, 50.0)
        self.assertGreaterEqual(o["carpanlar"][0]["fark_t"], ss.EN_AZ_T)
        self.assertEqual(o["karar"]["kod"], "dar")
        self.assertEqual(o["karar"]["carpan"], 1.5)
        self.assertIn("1,5 kat geniş olsaydı", o["karar"]["metin"])
        self.assertIn("mevcut ayar değişmez", o["karar"]["metin"])

    def test_genis_stop_kotulestiriyorsa_stop_yerinde(self):
        o = ss.ozetle([kayit(k, -0.5, fark2=-1.0, fark3=-2.0, hedef=False) for k in range(40)], 1.0, 50.0)
        self.assertEqual(o["karar"]["kod"], "yerinde")
        self.assertIsNone(o["karar"]["carpan"])

    def test_iyilesme_yalniz_bir_yaridaysa_kararsiz(self):
        # Bütün kurtulanlar dönemin ilk yarısında: şans olabilir.
        kayitlar = [kayit(k, 2.0 if k < 15 else -0.5) for k in range(40)]
        o = ss.ozetle(kayitlar, 1.0, 50.0)
        self.assertGreater(o["carpanlar"][0]["fark_tutar"], 0)
        self.assertLess(o["carpanlar"][0]["fark_tutar_son_yari"], 0)
        self.assertEqual(o["karar"]["kod"], "kararsiz")

    def test_kucuk_fark_dar_sayilmaz(self):
        # Stop başına ortalama iyileşme eşiğin altında.
        kayitlar = [kayit(k, 0.05) for k in range(40)]
        self.assertEqual(ss.ozetle(kayitlar, 1.0, 50.0)["karar"]["kod"], "kararsiz")

    def test_ayni_oran_az_stopla_sansa_baglanir(self):
        # Yukarıdaki "dar" örneğiyle aynı oranlar, ama 36 stop: fark henüz şanstan ayırt edilemez.
        kayitlar = [kayit(k, 2.0 if k % 3 == 0 else -0.5, fark2=-1.0, fark3=-2.0) for k in range(36)]
        o = ss.ozetle(kayitlar, 1.0, 50.0)
        self.assertLess(o["carpanlar"][0]["fark_t"], ss.EN_AZ_T)
        self.assertEqual(o["karar"]["kod"], "kararsiz")
        self.assertIn("şansla da çıkabilir", o["karar"]["metin"])

    def test_iyilesme_tek_yariya_yigilmissa_dar_sayilmaz(self):
        # İki yarı da artıda, ama kazancın onda dokuzu ilk yarıdan geliyor.
        kayitlar = [kayit(k, 2.0 if k < 45 else 0.2) for k in range(90)]
        o = ss.ozetle(kayitlar, 1.0, 50.0)
        self.assertGreater(o["carpanlar"][0]["fark_tutar_son_yari"], 0)
        self.assertEqual(o["karar"]["kod"], "kararsiz")

    def test_rastgele_farklarda_dar_cikmaz(self):
        # Ortalaması sıfır olan rastgele farklar: yüz denemenin en fazla birkaçında "dar" çıkmalı.
        import random

        rastgele = random.Random(11)
        dar = 0
        for _ in range(100):
            kayitlar = [kayit(k, rastgele.choice([2.0, -0.5, -0.5, -0.5, -0.5])) for k in range(60)]
            dar += ss.ozetle(kayitlar, 1.0, 50.0)["karar"]["kod"] == "dar"
        self.assertLessEqual(dar, 5)

    def test_t_degeri(self):
        self.assertIsNone(ss.t_degeri([1.0]))
        self.assertEqual(ss.t_degeri([2.0, 2.0, 2.0]), 99.0)
        self.assertEqual(ss.t_degeri([0.0, 0.0]), 0.0)
        self.assertAlmostEqual(ss.t_degeri([1.0, -1.0, 1.0, -1.0]), 0.0)
        self.assertAlmostEqual(ss.t_degeri([1.0, 2.0, 3.0]), 2.0 / (1.0 / 3 ** 0.5))

    def test_ders_yalniz_karar_degisince_yazilir(self):
        dar = {"kod": "dar", "carpan": 1.5, "metin": "x"}
        yerinde = {"kod": "yerinde", "carpan": None, "metin": "y"}
        self.assertFalse(ss.ders_gerekli_mi([], "s1-vadeli", {"kod": "yetersiz", "carpan": None, "metin": ""}, T0))
        self.assertTrue(ss.ders_gerekli_mi([], "s1-vadeli", dar, T0))
        # "Kararsız" tek başına ders değildir; yalnız önceki bir sonucu geri alıyorsa yazılır.
        kararsiz = {"kod": "kararsiz", "carpan": None, "metin": "z"}
        self.assertFalse(ss.ders_gerekli_mi([], "s1-vadeli", kararsiz, T0))
        dersler = [{"zaman": T0.strftime("%Y-%m-%dT%H:%M:%SZ"), "bot": "s1-vadeli", "karar": "dar", "carpan": 1.5}]
        self.assertFalse(ss.ders_gerekli_mi(dersler, "s1-vadeli", dar, T0 + timedelta(days=3)))
        self.assertTrue(ss.ders_gerekli_mi(dersler, "s2-vadeli", dar, T0))            # başka bot
        # Karar değişti ama son dersin üstünden bir gün geçmedi: sınırda gidip gelmesin.
        self.assertFalse(ss.ders_gerekli_mi(dersler, "s1-vadeli", yerinde, T0 + timedelta(hours=5)))
        self.assertTrue(ss.ders_gerekli_mi(dersler, "s1-vadeli", yerinde, T0 + timedelta(hours=25)))
        self.assertTrue(ss.ders_gerekli_mi(dersler, "s1-vadeli", kararsiz, T0 + timedelta(hours=25)))


IZ = {"tetik_yuzde": 1.2, "mesafe_yuzde": 0.3}


def iz_izle(fiyatlar, yon="alim", carpanlar=(1.5, 2.0, 3.0), acilislar=None):
    """Canlı botların çıkışı: stop %3, iz süren stop 1,2 / 0,3, hedef ve süre yok.

    Giriş 100, komisyon taraf başına %0,05 (gidiş-dönüş %0,1); stop ilk mumda oldu.
    İzleme mum sayısı kadar sürer. acilislar verilirse mumların açılış fiyatı onlardır.
    """
    liste = mumlar(fiyatlar)
    if acilislar:
        liste = [(m[0], a if a is not None else m[1], m[2], m[3], m[4]) for m, a in zip(liste, acilislar)]
    return ss.izle(yon, 100.0, T0, T0 + timedelta(seconds=20), liste, None, 3.0, None, 0.05,
                   carpanlar=carpanlar, iz=IZ, bitis=T0 + timedelta(minutes=len(fiyatlar)))


class IzSurenStopTesti(unittest.TestCase):
    """Hedefi ve süresi olmayan, iz süren stoplu botlar (12 Ekim 2026'dan beri hepsi)."""

    def test_toparlanan_islem_iz_suren_stopla_karla_kapanir(self):
        # Stop %3'te oldu (97); fiyat 96,5'e iner (1,5 kat stop 95,5 olmaz), 102'ye çıkar, sonra düşer.
        s = iz_izle([(96.9, 97.5), (96.5, 98.0), (98.0, 101.0), (101.0, 102.0), (101.8, 101.95), (100.0, 101.0)],
                    acilislar=[None] * 5 + [101.8])
        self.assertEqual(s["esik"], "iz")
        self.assertTrue(s["hedefi_gordu"])
        a = s["alternatif"]["1.5"]
        self.assertEqual(a["sonuc"], "iz")
        # En iyi fiyat 102; seviye 102 × 0,997 = 101,694. Önceki mumun tepesiyle taşınır:
        # 101,8 / 101,95 mumu seviyenin üstünde kalır, sonraki mum keser.
        self.assertAlmostEqual(a["net_yuzde"], 1.694 - 0.1, places=4)
        self.assertEqual(ss.islem_cumlesi(s), "stop 1,5 kat geniş olsaydı iz süren stopla kârla kapanırdı")

    def test_derine_inen_islemde_dar_secenek_stop_olur(self):
        s = iz_izle([(96.9, 97.5), (95.0, 97.0), (95.0, 102.0), (100.0, 101.0)])
        self.assertEqual(s["alternatif"]["1.5"]["sonuc"], "stop")
        self.assertAlmostEqual(s["alternatif"]["1.5"]["net_yuzde"], -4.5 - 0.1)
        self.assertEqual(s["alternatif"]["2"]["sonuc"], "iz")

    def test_tetige_ulasmazsa_izleme_bitince_acik_sayilir(self):
        s = iz_izle([(96.9, 97.5)] + [(98.0, 99.0)] * 5)
        self.assertFalse(s["hedefi_gordu"])
        for c in ("1.5", "2", "3"):
            self.assertEqual(s["alternatif"][c]["sonuc"], "acik")
            self.assertAlmostEqual(s["alternatif"][c]["net_yuzde"], -1.5 - 0.1)
        self.assertEqual(ss.islem_cumlesi(s), "geniş stopla da kârla kapanmazdı")

    def test_tetik_komisyon_dusulmus_karla_olculur(self):
        # 101,25: kâr %1,25, komisyon sonrası %1,15 < 1,2: iz süren stop devreye girmez.
        s = iz_izle([(96.9, 97.5), (100.0, 101.25), (99.0, 100.0)])
        self.assertEqual(s["alternatif"]["1.5"]["sonuc"], "acik")
        self.assertFalse(s["hedefi_gordu"])

    def test_ayni_mumun_tepesi_stopu_o_mumda_tasimaz_ve_bosluktan_acilista_kapanir(self):
        # 102'yi gören mumun dibi 100: o mumda iz süren stop yok (kötümser). Sonraki mum 100,5'ten
        # açılıp düşer: seviye 101,694'ün altında açıldığı için açılıştan kapanır.
        s = iz_izle([(96.9, 97.5), (100.0, 102.0), (99.0, 100.6)], acilislar=[None, None, 100.5])
        self.assertEqual(s["alternatif"]["1.5"]["sonuc"], "iz")
        self.assertAlmostEqual(s["alternatif"]["1.5"]["net_yuzde"], 0.5 - 0.1, places=4)

    def test_aciga_satis_ters_yonde(self):
        s = iz_izle([(102.5, 103.1), (101.0, 103.5), (98.0, 99.0), (98.5, 99.2)], yon="aciga_satis",
                    acilislar=[None, None, None, 98.2])
        a = s["alternatif"]["1.5"]
        self.assertEqual(a["sonuc"], "iz")
        # En iyi 98; seviye 98 × 1,003 = 98,294; çıkış kârı %1,706.
        self.assertAlmostEqual(a["net_yuzde"], 1.706 - 0.1, places=4)

    def test_bitis_verilmeden_suresiz_izleme_olmaz(self):
        with self.assertRaises(ValueError):
            ss.izle("alim", 100.0, T0, T0, mumlar([(99, 100)] * 3), None, 3.0, None, 0.05, iz=IZ)

    def test_ozet_ve_metinler(self):
        kayitlar = [dict(iz_izle([(96.9, 97.5), (96.5, 98.0), (98.0, 102.0), (100.0, 101.0)]),
                         gercek_net_yuzde=-3.1, cikis_zamani=f"2026-10-12T1{k}:00:00Z") for k in range(3)]
        ozet = ss.ozetle(kayitlar, 3.0, 50.0)
        self.assertEqual(ozet["esik"], "iz")
        satir = ozet["carpanlar"][0]
        self.assertEqual((satir["iz"], satir["stop"], satir["acik"]), (3, 0, 0))
        self.assertEqual(ss.secenek_metni(satir), "3 tanesi iz süren stopla kârla kapanır")
        self.assertEqual(ss.esik_metni("iz"), "iz süren stopun devreye girdiği kâra ulaştı")


class CanliBotTurTesti(unittest.TestCase):
    """bir_tur bugünkü canlı botların (iz süren stop, süre sınırı yok) stoplarını da izler."""

    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.klasor = Path(self.gecici.name)
        (self.klasor / "isinma_baslangici.txt").write_text((T0 - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        sahte_islem_db(self.klasor / "db" / "sm-vadeli.sqlite", [
            ("SOL/USDT", T0, T0 + timedelta(hours=5), -3.1, "stop_loss", False),
            ("XRP/USDT", T0, T0 + timedelta(hours=2), 0.9, "trailing_stop_loss", False),   # stop değil
        ])
        self.istekler = []
        self.yama = mock.patch("karabasan.botlar.BOTLAR", [("sm-vadeli", "SMVadeli", "SM", "vadeli")])
        self.yama.start()

    def tearDown(self):
        self.yama.stop()
        self.gecici.cleanup()

    def getir(self, parite, piyasa, baslangic, bitis):
        self.istekler.append((parite, baslangic, bitis))
        adet = int((bitis - baslangic) / timedelta(minutes=5))
        # Stoptan sonra 96,5'e iner, 102'ye çıkar, sonra 100 civarına döner (5 dakikalık mumlar).
        fiyatlar = [(96.9, 97.5), (96.5, 98.0), (98.0, 102.0)] + [(100.0, 101.0)] * (adet - 3)
        return mumlar(fiyatlar, baslangic, dakika=5), 5

    def test_stoptan_uc_gun_sonra_izlenir(self):
        sayim = ss.bir_tur(self.klasor, T0 + timedelta(hours=60), getir=self.getir, ara=0)
        self.assertEqual((sayim["izlenen"], sayim["bekleyen"]), (0, 1))     # henüz 72 saat dolmadı
        sayim = ss.bir_tur(self.klasor, T0 + timedelta(hours=72, minutes=10), getir=self.getir, ara=0)
        self.assertEqual(sayim["izlenen"], 1)
        parite, bas, bitis = self.istekler[0]
        self.assertEqual((parite, bitis), ("SOL/USDT", T0 + timedelta(hours=72)))
        self.assertLessEqual(bas, T0 + timedelta(hours=5))
        k = ss.dosya_oku(ss.dosya_yolu(self.klasor))["islemler"]["sm-vadeli#1"]
        self.assertEqual(k["esik"], "iz")
        self.assertEqual(k["alternatif"]["1.5"]["sonuc"], "iz")
        # 102'den sonraki mum 100,5'ten açılır (seviye 101,694'ün altı): açılıştan kapanır.
        self.assertAlmostEqual(k["alternatif"]["1.5"]["net_yuzde"], 0.5 - 0.1, places=4)

    def test_gec_kapanan_stop_ardindan_bir_gun_izlenir(self):
        (self.klasor / "db" / "sm-vadeli.sqlite").unlink()
        sahte_islem_db(self.klasor / "db" / "sm-vadeli.sqlite", [
            ("ADA/USDT", T0, T0 + timedelta(hours=60), -3.1, "stop_loss", False),
        ])
        ss.bir_tur(self.klasor, T0 + timedelta(hours=84, minutes=10), getir=self.getir, ara=0)
        self.assertEqual(self.istekler[-1][2], T0 + timedelta(hours=84))


class TurTesti(unittest.TestCase):
    """bir_tur: botların kayıtlarından stopları bulur, mumları ister, sonucu dosyaya yazar."""

    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.klasor = Path(self.gecici.name)
        (self.klasor / "isinma_baslangici.txt").write_text((T0 - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        # S1: hedef %0,8, stop %3, süre 240 dakika, vadeli (komisyon %0,05). Giriş fiyatı 100.
        self.islemler = [
            ("SOL/USDT", T0, T0 + timedelta(minutes=30), -1.15, "stop_loss", False),          # süresi doldu
            ("XRP/USDT", T0, T0 + timedelta(minutes=50), 1.05, "roi", False),                 # stop değil
            ("ADA/USDT", T0 + timedelta(hours=3), T0 + timedelta(hours=3, minutes=20), -1.15, "stop_loss", False),
        ]
        sahte_islem_db(self.klasor / "db" / "s1-vadeli.sqlite", self.islemler)
        self.istekler = []

    def tearDown(self):
        self.gecici.cleanup()

    def getir(self, parite, piyasa, baslangic, bitis):
        self.istekler.append((parite, piyasa, baslangic, bitis))
        adet = int((bitis - baslangic) / timedelta(minutes=1))
        # Stoptan sonra 99,2 ile 100 arasında gezer, son yarım saatte 101,3'ü görür.
        fiyatlar = [(98.9, 99.6)] * 6 + [(99.2, 100.0)] * (adet - 36) + [(100.2, 101.3)] * 30
        return mumlar(fiyatlar, baslangic), 1

    def test_yalniz_suresi_dolmus_stoplar_izlenir(self):
        simdi = T0 + timedelta(hours=4, minutes=10)
        sayim = ss.bir_tur(self.klasor, simdi, getir=self.getir, ara=0)
        self.assertEqual(sayim, {"izlenen": 1, "bekleyen": 1, "basarisiz": 0, "yeni_ders": 0})
        self.assertEqual([i[0] for i in self.istekler], ["SOL/USDT"])
        parite, piyasa, bas, bitis = self.istekler[0]
        self.assertEqual(piyasa, "vadeli")
        self.assertEqual(bitis, T0 + timedelta(minutes=240))             # giriş + stratejinin süresi
        self.assertLessEqual(bas, T0 + timedelta(minutes=30))            # stop anını kapsar
        veri = json.loads(ss.dosya_yolu(self.klasor).read_text(encoding="utf-8"))
        k = veri["islemler"]["s1-vadeli#1"]
        self.assertEqual((k["bot"], k["kod"], k["parite"]), ("s1-vadeli", "S1", "SOL/USDT"))
        self.assertAlmostEqual(k["gercek_net_yuzde"], -1.15)
        self.assertEqual(k["alternatif"]["1.5"]["sonuc"], "hedef")
        self.assertAlmostEqual(k["alternatif"]["1.5"]["net_yuzde"], 0.8 - 0.1)

    def test_izlenen_islem_yeniden_istenmez(self):
        simdi = T0 + timedelta(hours=4, minutes=10)
        ss.bir_tur(self.klasor, simdi, getir=self.getir, ara=0)
        ss.bir_tur(self.klasor, simdi + timedelta(minutes=10), getir=self.getir, ara=0)
        self.assertEqual(len(self.istekler), 1)
        # İkinci stopun süresi dolunca o da izlenir.
        sayim = ss.bir_tur(self.klasor, T0 + timedelta(hours=8), getir=self.getir, ara=0)
        self.assertEqual(sayim["izlenen"], 1)
        self.assertEqual([i[0] for i in self.istekler], ["SOL/USDT", "ADA/USDT"])

    def test_mum_alinamazsa_uc_kez_denenir_sonra_birakilir(self):
        cagri = []

        def bozuk(*a):
            cagri.append(a)
            raise TimeoutError("ulaşılamadı")

        simdi = T0 + timedelta(hours=8)
        with self.assertLogs("karabasan.stop_sonrasi", level="WARNING"):
            for _ in range(5):
                ss.bir_tur(self.klasor, simdi, getir=bozuk, ara=0)
        self.assertEqual(len(cagri), 2 * ss.DENEME_SINIRI)      # iki stop, üçer deneme
        veri = ss.dosya_oku(ss.dosya_yolu(self.klasor))
        self.assertEqual(veri["islemler"], {})
        self.assertEqual(veri["basarisiz"], {"s1-vadeli#1": 3, "s1-vadeli#3": 3})

    def test_botlarin_kayit_dosyasi_degismez(self):
        yol = self.klasor / "db" / "s1-vadeli.sqlite"
        once = yol.read_bytes()
        ss.bir_tur(self.klasor, T0 + timedelta(hours=8), getir=self.getir, ara=0)
        self.assertEqual(yol.read_bytes(), once)

    def test_yeterli_stop_birikince_ders_yazilir_ve_yinelenmez(self):
        # 36 stop; hepsi geniş stopla hedefe ulaşıyor (getir'in çizdiği yol).
        islemler = [
            ("SOL/USDT", T0 + timedelta(minutes=10 * k), T0 + timedelta(minutes=10 * k + 5), -1.15, "stop_loss", False)
            for k in range(36)
        ]
        (self.klasor / "db" / "s1-vadeli.sqlite").unlink()
        sahte_islem_db(self.klasor / "db" / "s1-vadeli.sqlite", islemler)
        simdi = T0 + timedelta(hours=12)
        ilk = ss.bir_tur(self.klasor, simdi, getir=self.getir, ara=0)
        self.assertEqual((ilk["izlenen"], ilk["bekleyen"], ilk["yeni_ders"]), (ss.TUR_SINIRI, 36 - ss.TUR_SINIRI, 0))
        ikinci = ss.bir_tur(self.klasor, simdi + timedelta(minutes=10), getir=self.getir, ara=0)
        self.assertEqual((ikinci["izlenen"], ikinci["yeni_ders"]), (36 - ss.TUR_SINIRI, 1))
        ucuncu = ss.bir_tur(self.klasor, simdi + timedelta(minutes=20), getir=self.getir, ara=0)
        self.assertEqual(ucuncu["yeni_ders"], 0)
        veri = ss.dosya_oku(ss.dosya_yolu(self.klasor))
        self.assertEqual(len(veri["dersler"]), 1)
        ders = veri["dersler"][0]
        self.assertEqual((ders["bot"], ders["kod"], ders["karar"], ders["stop_sayisi"]), ("s1-vadeli", "S1", "dar", 36))
        self.assertEqual(ders["ad"], "Yükselişte düşüşü al")

    def test_ozet_sayfaya_gider(self):
        simdi = T0 + timedelta(hours=8)
        ss.bir_tur(self.klasor, simdi, getir=self.getir, ara=0)
        ozet = sonuc.genel_ozet(self.klasor, simdi)
        s1 = next(b for b in ozet["botlar"] if b["bot"] == "s1-vadeli")
        self.assertEqual(s1["stop_sonrasi"]["stop_sayisi"], 2)
        self.assertEqual(s1["stop_sonrasi"]["hedefi_goren"], 2)
        self.assertEqual(s1["stop_sonrasi"]["izlenmeyi_bekleyen"], 0)
        self.assertEqual(s1["stop_sonrasi"]["karar"]["kod"], "yetersiz")
        stoplar = [i for i in ozet["son_islemler"] if i["neden"] == "stop"]
        self.assertEqual({i["stop_sonrasi"] for i in stoplar}, {"stop 1,5 kat geniş olsaydı hedefe ulaşırdı"})
        self.assertIsNone(next(i for i in ozet["son_islemler"] if i["neden"] != "stop")["stop_sonrasi"])
        self.assertEqual(ozet["dersler"], [])
        json.dumps(sonuc.json_icin(ozet))   # JSON'a çevrilebilir kalmalı

    def test_izleme_dosyasi_yokken_ozet_bos_gelir(self):
        ozet = sonuc.genel_ozet(self.klasor, T0 + timedelta(hours=8))
        s1 = next(b for b in ozet["botlar"] if b["bot"] == "s1-vadeli")
        self.assertEqual(s1["stop_sonrasi"]["stop_sayisi"], 0)
        self.assertEqual(s1["stop_sonrasi"]["izlenmeyi_bekleyen"], 2)

    def test_bozuk_izleme_dosyasi_sayfayi_dusurmez(self):
        ss.dosya_yolu(self.klasor).parent.mkdir(parents=True)
        ss.dosya_yolu(self.klasor).write_text("{yarım", encoding="utf-8")
        self.assertEqual(sonuc.genel_ozet(self.klasor, T0)["dersler"], [])

    def test_kayitci_izleme_hatasini_yutar(self):
        with mock.patch.object(ss, "bir_tur", side_effect=RuntimeError("patladı")):
            with self.assertLogs("karabasan.kayitci", level="ERROR"):
                kayitci.stop_sonrasi_turu(self.klasor)


class MumGetirTesti(unittest.TestCase):
    """Binance'in mum yanıtı biçimi, sahte bir sunucuyla."""

    def test_sembol(self):
        self.assertEqual(ss.sembol("SOL/USDT"), "SOLUSDT")
        self.assertEqual(ss.sembol("1000PEPE/USDT:USDT"), "1000PEPEUSDT")

    def test_istek_ve_yanit(self):
        gelen = []

        class Isleyici(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                gelen.append(self.path)
                ms = int(T0.timestamp() * 1000)
                govde = json.dumps([
                    [ms, "100.0", "100.5", "99.5", "100.2", "12.3", ms + 59999, "0", 1, "0", "0", "0"],
                    [ms + 60000, "100.2", "100.9", "100.1", "100.8", "9.1", ms + 119999, "0", 1, "0", "0", "0"],
                ]).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(govde)))
                self.end_headers()
                self.wfile.write(govde)

            def log_message(self, *a):
                pass

        sunucu = HTTPServer(("127.0.0.1", 0), Isleyici)
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        adres = f"http://127.0.0.1:{sunucu.server_address[1]}"
        try:
            with mock.patch.dict("os.environ", {"KARABASAN_BINANCE_SPOT": adres + "/spot",
                                                "KARABASAN_BINANCE_VADELI": adres + "/vadeli"}):
                liste, uzunluk = ss.mum_getir("SOL/USDT:USDT", "vadeli", T0, T0 + timedelta(hours=4))
                ss.mum_getir("SOL/USDT", "spot", T0, T0 + timedelta(hours=20))
        finally:
            sunucu.shutdown()
            sunucu.server_close()
        self.assertEqual(uzunluk, 1)
        self.assertEqual(liste[0], (T0, 100.0, 100.5, 99.5, 100.2))
        self.assertEqual(liste[1][0], T0 + timedelta(minutes=1))
        self.assertTrue(gelen[0].startswith("/vadeli?symbol=SOLUSDT&interval=1m&startTime="))
        self.assertIn("interval=5m", gelen[1])      # 990 dakikadan uzun pencere: 5 dakikalık mum


if __name__ == "__main__":
    unittest.main()
