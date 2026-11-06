"""Risk ve güven ölçümleri (6 Kasım 2026, uzman toplantısı)."""

import unittest
from datetime import datetime, timedelta, timezone

from karabasan import sonuc
from karabasan.kural import kural_yukle

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


def islem(net, gun=0, parite="SOL/USDT:USDT"):
    return {"net_tutar": net, "cikis_zamani": T0 + timedelta(hours=gun), "parite": parite}


class Risk(unittest.TestCase):
    def test_seri_ve_ortalamalar(self):
        r = sonuc.risk_olcumleri([islem(1, 0), islem(-1, 1), islem(-2, 2), islem(3, 3), islem(-4, 4)])
        self.assertEqual(r["en_uzun_kayip_serisi"], 2)
        self.assertAlmostEqual(r["en_uzun_kayip_toplami"], -3)
        self.assertAlmostEqual(r["ort_kazanc_usdt"], 2)
        self.assertAlmostEqual(r["ort_kayip_usdt"], -7 / 3)
        self.assertAlmostEqual(r["en_buyuk_kayip_usdt"], -4)
        self.assertEqual(r["kayip_sayisi"], 3)

    def test_bos(self):
        r = sonuc.risk_olcumleri([])
        self.assertIsNone(r["ort_kazanc_usdt"])
        self.assertEqual(r["en_uzun_kayip_serisi"], 0)


class Guven(unittest.TestCase):
    def test_az_gun(self):
        self.assertEqual(sonuc.guven_etiketi([{"net_tutar": 1}] * 5)["etiket"], "Veri az")

    def test_gurultu_kanit_yok(self):
        gunluk = [{"net_tutar": x} for x in (1, -1, 2, -2, 1, -1, 0.5, -0.5, 1, -1.2)]
        self.assertIn("Kanıt yok", sonuc.guven_etiketi(gunluk)["etiket"])

    def test_tutarli_arti_belirgin(self):
        gunluk = [{"net_tutar": 1 + (i % 3) * 0.1} for i in range(15)]
        self.assertEqual(sonuc.guven_etiketi(gunluk)["sinif"], "arti")


class Parite(unittest.TestCase):
    def test_gruplar(self):
        p = sonuc.parite_ozeti([islem(1, parite="A"), islem(-3, parite="B"), islem(2, parite="A")])
        self.assertEqual(p[0]["parite"], "A")
        self.assertEqual(p[0]["islem"], 2)
        self.assertAlmostEqual(p[1]["net_tutar"], -3)


class AcikRisk(unittest.TestCase):
    def test_aciga_satis_stop_ustte(self):
        kural = {"cikis": {"zarar_durdur_yuzde": 9.0}, "kaldirac": 1}
        r = sonuc.acik_risk({"yon": "aciga_satis", "giris_fiyati": 100.0, "tutar": 50.0}, kural, 50.0)
        self.assertAlmostEqual(r["stop_fiyati"], 109.0)
        self.assertAlmostEqual(r["stopta_kayip"], -4.5)

    def test_ek_giris_bekleyen_kaldiracli(self):
        kural = kural_yukle("SMK2")
        r = sonuc.acik_risk({"yon": "aciga_satis", "giris_fiyati": 100.0, "tutar": 50.0}, kural, 50.0)
        # 50 x 2 x %9 = 9, + ek giriş 100 x 2 x %1 = 2
        self.assertAlmostEqual(r["stopta_kayip"], -11.0)

    def test_ek_giris_yapilmis(self):
        kural = kural_yukle("SMK2")
        r = sonuc.acik_risk({"yon": "aciga_satis", "giris_fiyati": 100.0, "tutar": 150.0}, kural, 50.0)
        # ilk 50 x 2 x %9 = 9, eklenen 100 x 2 x %1 = 2
        self.assertAlmostEqual(r["stopta_kayip"], -11.0)


if __name__ == "__main__":
    unittest.main()
