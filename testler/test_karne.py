import math
import unittest

import pandas as pd

from karabasan import karne as kr

BASLANGIC = pd.Timestamp("2026-01-01", tz="UTC")


def islem(net, gun=0.5, sure=60):
    cikis = BASLANGIC + pd.Timedelta(days=gun)
    return {"giris_zamani": cikis - pd.Timedelta(minutes=sure), "cikis_zamani": cikis,
            "net_yuzde": net, "sure_dakika": sure}


def dizi(netler, gunler=None):
    gunler = gunler or [0.1 + 0.01 * i for i in range(len(netler))]
    return [islem(n, g) for n, g in zip(netler, gunler)]


class KarneTestleri(unittest.TestCase):
    def test_bos_liste(self):
        k = kr.karne([])
        self.assertEqual(k["islem_sayisi"], 0)
        self.assertIsNone(k["kazanma_orani"])

    def test_temel_olcumler(self):
        k = kr.karne(dizi([1, 1, 1, -1, -1]), islem_tutari=50, bakiye=1000)
        self.assertEqual(k["islem_sayisi"], 5)
        self.assertAlmostEqual(k["kazanma_orani"], 60.0)
        self.assertAlmostEqual(k["net_beklenti"], 0.2)
        self.assertAlmostEqual(k["kar_faktoru"], 1.5)
        self.assertAlmostEqual(k["basabas_orani"], 50.0)
        self.assertAlmostEqual(k["net_tutar"], 0.5)          # %1 x 50 USDT = 0,5 USDT
        self.assertAlmostEqual(k["net_bakiye_yuzde"], 0.05)

    def test_en_buyuk_dusus(self):
        # +1, -1, -1, -1, +1: tepe 1000,5; dip 999,0 -> düşüş 1,5 USDT = bakiyenin %0,15'i
        k = kr.karne(dizi([1, -1, -1, -1, 1]), islem_tutari=50, bakiye=1000)
        self.assertAlmostEqual(k["en_buyuk_dusus_yuzde"], 0.15)

    def test_hic_kayip_yoksa_kar_faktoru_sonsuz(self):
        self.assertEqual(kr.karne(dizi([1, 2]))["kar_faktoru"], math.inf)

    def test_ek_kayma(self):
        kaymali = kr.ek_kayma_uygula(dizi([1.0, -1.0]), 0.05)
        self.assertAlmostEqual(kaymali[0]["net_yuzde"], 0.95)
        self.assertAlmostEqual(kaymali[1]["net_yuzde"], -1.05)

    def test_haftalik_net(self):
        islemler = dizi([1, 1, -1, 2, 3], gunler=[1, 6.9, 8, 20, 29.5])
        self.assertEqual(kr.haftalik_net(islemler, BASLANGIC), [2.0, -1.0, 2.0, 3.0])

    def test_duruma_gore(self):
        islemler = dizi([1, -1, 1])
        for i, durum in zip(islemler, ["YESIL", "KIRMIZI", "YESIL"]):
            i["karabasan_durumu"] = durum
        gruplar = kr.duruma_gore(islemler)
        self.assertEqual(gruplar["YESIL"]["islem_sayisi"], 2)
        self.assertEqual(gruplar["KIRMIZI"]["islem_sayisi"], 1)


class SinavKarari(unittest.TestCase):
    def iyi_bot(self, adet=120):
        # 3 kazanç, 1 kayıp düzeni; dört haftaya eşit yayılmış
        netler = [1.05 if i % 4 else -1.15 for i in range(adet)]
        gunler = [0.2 + i * (27.0 / adet) for i in range(adet)]
        return dizi(netler, gunler)

    def test_iyi_bot_gecer(self):
        sonuc = kr.sinav_karari(self.iyi_bot(), BASLANGIC, gecmis_test_net_beklenti=0.2)
        self.assertTrue(sonuc["gecti"], sonuc["olcutler"])
        self.assertEqual(len(sonuc["olcutler"]), 7)

    def test_az_islem_gecemez(self):
        sonuc = kr.sinav_karari(self.iyi_bot(60), BASLANGIC, gecmis_test_net_beklenti=0.2)
        self.assertFalse(sonuc["gecti"])
        self.assertFalse(sonuc["olcutler"][0]["gecti"])

    def test_gecmis_testi_yoksa_gecemez(self):
        sonuc = kr.sinav_karari(self.iyi_bot(), BASLANGIC, gecmis_test_net_beklenti=None)
        self.assertFalse(sonuc["gecti"])
        self.assertFalse(sonuc["olcutler"][6]["gecti"])
        self.assertTrue(all(o["gecti"] for o in sonuc["olcutler"][:6]))

    def test_gecmis_testi_negatifse_gecemez(self):
        sonuc = kr.sinav_karari(self.iyi_bot(), BASLANGIC, gecmis_test_net_beklenti=-0.1)
        self.assertFalse(sonuc["gecti"])

    def test_zarar_eden_bot_gecemez(self):
        netler = [0.85 if i % 2 else -1.15 for i in range(120)]
        gunler = [0.2 + i * 0.22 for i in range(120)]
        sonuc = kr.sinav_karari(dizi(netler, gunler), BASLANGIC, gecmis_test_net_beklenti=0.2)
        self.assertFalse(sonuc["gecti"])
        self.assertFalse(sonuc["olcutler"][1]["gecti"])

    def test_ek_kayma_karari_degistirebilir(self):
        # Komisyon sonrası çok az kârlı bot: ek kayma eklenince zarara döner
        netler = [1.0 if i % 2 else -0.96 for i in range(120)]
        gunler = [0.2 + i * 0.22 for i in range(120)]
        islemler = dizi(netler, gunler)
        self.assertGreater(kr.karne(islemler)["net_tutar"], 0)
        sonuc = kr.sinav_karari(islemler, BASLANGIC, gecmis_test_net_beklenti=0.2)
        self.assertLess(sonuc["karne_ek_kaymali"]["net_tutar"], 0)
        self.assertFalse(sonuc["gecti"])

    def test_tek_haftada_kazanan_bot_gecemez(self):
        # Tüm kazanç ilk haftada; sonraki üç hafta hafif ekside
        netler = [1.05] * 60 + [1.05 if i % 2 else -1.15 for i in range(60)]
        gunler = [0.1 + i * 0.1 for i in range(60)] + [7.5 + i * 0.33 for i in range(60)]
        sonuc = kr.sinav_karari(dizi(netler, gunler), BASLANGIC, gecmis_test_net_beklenti=0.2)
        self.assertFalse(sonuc["olcutler"][4]["gecti"])
        self.assertFalse(sonuc["gecti"])


if __name__ == "__main__":
    unittest.main()
