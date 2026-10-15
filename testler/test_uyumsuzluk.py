"""SMD / SMDK: uyumsuzluk göstergesi, emir defteri onayı ve bağlantı katmanındaki giriş onayı."""

import unittest
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from karabasan import defter as d
from karabasan import gostergeler as g
from karabasan import kural as k
from testler.test_motor_baglantisi import emekli_sinifi, strateji_modulu
from testler.veri import duz_mumlar, yapay_mumlar


def kapanislardan(kapanislar):
    """Yalnız kapanışı belli mumlar: açılış önceki kapanış, fitil yok, hacim sabit."""
    onceki = [kapanislar[0]] + list(kapanislar[:-1])
    return duz_mumlar([(a, max(a, c), min(a, c), c) for a, c in zip(onceki, kapanislar)])


class UyumsuzlukTesti(unittest.TestCase):
    def test_normal_boga_uyumsuzlugu(self):
        # Sert düşüş ve dip (100), toparlanma, sonra daha yavaş bir düşüşle biraz daha düşük dip
        # (99,5) ve dönüş. İkinci düşüş yavaş olduğu için momentum göstergeleri daha yüksek dip yapar.
        fiyat = [120.0] * 40
        fiyat += list(np.linspace(120, 100, 8))          # hızlı düşüş -> ilk dip
        fiyat += list(np.linspace(100.5, 108, 12))       # toparlanma
        fiyat += list(np.linspace(107.8, 99.5, 30))      # yavaş düşüş -> daha düşük dip
        fiyat += [100.2, 100.9, 101.5, 102.0, 102.4, 102.8]
        df = kapanislardan(fiyat)
        u = g.uyumsuzluk(df, uzunluk=3, tip="normal")
        dip = 40 + 8 + 12 + 29                           # ikinci dibin sırası
        self.assertEqual(int(u["boga"].iloc[:dip].max()), 0)          # ikinci dipten önce yok
        self.assertGreater(int(u["boga"].iloc[dip + 1:dip + 4].max()), 0)
        self.assertEqual(int(u["ayi"].iloc[dip:dip + 4].max()), 0)

    def test_gelecege_bakmaz(self):
        df = yapay_mumlar(1500, tohum=9, oynaklik=0.003)
        tam = g.uyumsuzluk(df.iloc[:1500])
        for kesim in (700, 1000, 1200):
            kismi = g.uyumsuzluk(df.iloc[:kesim])
            np.testing.assert_array_equal(tam["boga"].to_numpy()[:kesim], kismi["boga"].to_numpy())
            np.testing.assert_array_equal(tam["ayi"].to_numpy()[:kesim], kismi["ayi"].to_numpy())

    def test_rastgele_veride_ara_sira_cikar_sinirlar_icinde(self):
        u = g.uyumsuzluk(yapay_mumlar(2000, tohum=3, oynaklik=0.003))
        self.assertTrue(0 < (u["boga"] > 0).mean() < 0.5)
        self.assertTrue(0 < (u["ayi"] > 0).mean() < 0.5)
        self.assertLessEqual(int(u[["boga", "ayi"]].to_numpy().max()), len(g.UYUMSUZLUK_GOSTERGELERI))

    def test_tip_secimi(self):
        df = yapay_mumlar(1500, tohum=4, oynaklik=0.003)
        normal, gizli, ikisi = (g.uyumsuzluk(df, tip=t) for t in ("normal", "gizli", "ikisi"))
        self.assertTrue((ikisi["boga"] >= normal["boga"]).all())
        self.assertTrue((ikisi["boga"] >= gizli["boga"]).all())

    def test_kural_dogrulamasi(self):
        def kural(**tanim):
            return {"kod": "T", "ad": "Deneme kuralı", "yon": "alim", "zaman_dilimi": "5m",
                    "gostergeler": {"u": {"tur": "uyumsuzluk", "periyot": 5, **tanim}},
                    "giris": {"sol": "u_boga", "islem": ">=", "sag": 1},
                    "cikis": {"kar_hedefi_yuzde": 1, "zarar_durdur_yuzde": 1, "sure_asimi_dakika": 60}}

        k.kural_dogrula(kural())
        for hatali in ({"tip": "garip"}, {"periyot": 50}, {"kaynak": "kapanis"}):
            with self.assertRaises(k.KuralHatasi):
                k.kural_dogrula(kural(**hatali))
        onayli = {**kural(), "defter_onayi": {"en_az_dengesizlik": 0.1}}
        k.kural_dogrula(onayli)
        for esik in (1.5, -0.1, "0.1", None):
            with self.assertRaises(k.KuralHatasi):
                k.kural_dogrula({**kural(), "defter_onayi": {"en_az_dengesizlik": esik}})


def kitap(alis_agirlik, satis_agirlik, orta=100.0):
    alislar = [(orta - 0.05 - i * 0.1, alis_agirlik) for i in range(100)]
    satislar = [(orta + 0.05 + i * 0.1, satis_agirlik) for i in range(100)]
    return alislar, satislar


class DefterOnayiTesti(unittest.TestCase):
    def test_alim_alicilar_kalabaliksa_onaylanir(self):
        self.assertTrue(d.defter_onayi("alim", *kitap(2.0, 1.0))[0])
        self.assertFalse(d.defter_onayi("alim", *kitap(1.0, 1.0))[0])
        self.assertFalse(d.defter_onayi("alim", *kitap(1.0, 2.0))[0])

    def test_satis_saticilar_kalabaliksa_onaylanir(self):
        self.assertTrue(d.defter_onayi("satis", *kitap(1.0, 2.0))[0])
        self.assertFalse(d.defter_onayi("satis", *kitap(2.0, 1.0))[0])

    def test_aciklama(self):
        onay, aciklama = d.defter_onayi("alim", *kitap(2.0, 1.0))
        self.assertIn("onayladı", aciklama)
        self.assertIn("dengesizlik ilk 20 kademe +0.33", aciklama)


class SahteKip:
    def __init__(self, deger):
        self.value = deger


class SahteSaglayici:
    def __init__(self, kip, kitap_=None, hata=False):
        self.runmode = SahteKip(kip)
        self.kitap, self.hata = kitap_, hata
        self.istek = 0

    def orderbook(self, pair, maximum):
        self.istek += 1
        if self.hata:
            raise RuntimeError("defter yok")
        alislar, satislar = self.kitap
        return {"bids": [[f, m] for f, m in alislar], "asks": [[f, m] for f, m in satislar]}


class GirisOnayiTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modul = strateji_modulu()

    def _onay(self, sinif, saglayici, side):
        # Canlı botun sınıf adı (SMDKVadeli) ya da emekli kuralın kodu (SM, SMD; 15 Ekim 2026'dan beri).
        s = (getattr(self.modul, sinif) if sinif.endswith("Vadeli") else emekli_sinifi(self.modul, sinif))()
        s.dp = saglayici
        zaman = datetime(2026, 10, 12, tzinfo=timezone.utc)
        return s.confirm_trade_entry("ETH/USDT:USDT", "market", 1.0, 100.0, "GTC", zaman, None, side)

    def test_sanal_modda_defter_sorulur(self):
        self.assertTrue(self._onay("SMD", SahteSaglayici("dry_run", kitap(2.0, 1.0)), "long"))
        self.assertFalse(self._onay("SMD", SahteSaglayici("dry_run", kitap(1.0, 2.0)), "long"))
        self.assertTrue(self._onay("SMDKVadeli", SahteSaglayici("dry_run", kitap(1.0, 2.0)), "short"))
        self.assertFalse(self._onay("SMDKVadeli", SahteSaglayici("live", kitap(2.0, 1.0)), "short"))

    def test_gecmis_testinde_defter_sorulmaz(self):
        saglayici = SahteSaglayici("backtest", kitap(1.0, 2.0))
        self.assertTrue(self._onay("SMD", saglayici, "long"))
        self.assertEqual(saglayici.istek, 0)

    def test_defter_okunamazsa_girmez(self):
        self.assertFalse(self._onay("SMD", SahteSaglayici("dry_run", hata=True), "long"))

    def test_eski_smartmoney_defter_sormaz(self):
        saglayici = SahteSaglayici("dry_run", kitap(1.0, 2.0))
        self.assertTrue(self._onay("SM", saglayici, "long"))
        self.assertEqual(saglayici.istek, 0)


class SmdMantigi(unittest.TestCase):
    """SMD, Smartmoney'nin bütün koşullarını korur ve üstüne uyumsuzluk ister."""

    @classmethod
    def setUpClass(cls):
        cls.df = yapay_mumlar(60 * 288, tohum=11, oynaklik=0.003)
        gunluk = g.ust_dilime_cevir(cls.df, "5m", "1d")
        cls.tablo = {kod: k.sinyal_uret(cls.df, k.kural_yukle(kod), {"1d": gunluk})
                     for kod in ("SM", "SMK", "SMD", "SMDK")}

    def test_smd_sinyali_sm_sinyalinin_alt_kumesidir(self):
        for yeni, eski, sutun in (("SMD", "SM", "uyum5_boga"), ("SMDK", "SMK", "uyum5_ayi")):
            yeni_s, eski_s = self.tablo[yeni]["sinyal"], self.tablo[eski]["sinyal"]
            self.assertTrue((~yeni_s | eski_s).all(), yeni)          # SMD varsa SM de var
            self.assertGreater(int(yeni_s.sum()), 0, f"{yeni} yapay veride hiç sinyal vermedi")
            self.assertLess(int(yeni_s.sum()), int(eski_s.sum()), yeni)
            son12 = self.tablo[yeni][sutun].rolling(12, min_periods=1).max()
            self.assertTrue((son12[yeni_s] >= 1).all(), yeni)

    def test_ayni_mumda_alim_ve_satis_olmaz(self):
        self.assertFalse((self.tablo["SMD"]["sinyal"] & self.tablo["SMDK"]["sinyal"]).any())


if __name__ == "__main__":
    unittest.main()
