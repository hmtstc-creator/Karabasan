import copy
import unittest

import numpy as np
import pandas as pd

from karabasan import gostergeler as g
from karabasan import kural as k
from testler.veri import yapay_mumlar


def basit_kural(**ek):
    kural = {
        "kod": "T1", "ad": "Test", "yon": "alim", "zaman_dilimi": "5m",
        "gostergeler": {"ema3": {"tur": "ema", "kaynak": "kapanis", "periyot": 3}},
        "giris": {"sol": "kapanis", "islem": ">", "sag": "ema3"},
        "cikis": {"kar_hedefi_yuzde": 1.0, "zarar_durdur_yuzde": 1.0, "sure_asimi_dakika": 60},
    }
    kural.update(ek)
    return kural


class KuralDosyalari(unittest.TestCase):
    def test_on_strateji_yuklenir(self):
        kurallar = k.tum_kurallar()
        self.assertEqual(sorted(kurallar),
                         ["S1", "S1K", "S2", "S2K", "S3", "S4", "S5", "S5K", "S6", "S6K"])
        for kod, kural in kurallar.items():
            with self.subTest(kod=kod):
                self.assertEqual(kural["kod"], kod)
                self.assertLessEqual(k.gereken_mum(kural), k.EN_FAZLA_BASLANGIC_MUMU)

    def test_ters_yonluler_aciga_satis(self):
        kurallar = k.tum_kurallar()
        for kod, kural in kurallar.items():
            self.assertEqual(kural["yon"], "aciga_satis" if kod.endswith("K") else "alim", kod)

    def test_her_stratejinin_duz_adi_ve_aciklamasi_var(self):
        """Adlar ne yaptığını söylemeli; kod (S1, S5K) tek başına ad olamaz."""
        adlar = set()
        for kod, kural in k.tum_kurallar().items():
            self.assertGreater(len(kural["ad"]), 10, kod)
            self.assertNotIn(kod, kural["ad"])
            self.assertGreater(len(kural.get("aciklama", "")), 40, kod)
            adlar.add(kural["ad"])
        self.assertEqual(len(adlar), 10)   # adlar birbirinden farklı

    def test_ters_yonlu_ciftler_ayni_cikisi_kullanir(self):
        kurallar = k.tum_kurallar()
        for kod in ("S5", "S6"):
            self.assertEqual(kurallar[kod]["cikis"], kurallar[kod + "K"]["cikis"], kod)
            self.assertEqual(kurallar[kod]["gostergeler"], kurallar[kod + "K"]["gostergeler"], kod)

    def test_basabas_oranlari_raporla_ayni(self):
        kurallar = k.tum_kurallar()
        beklenen = {"S1": 54.55, "S2": 48.0, "S3": 60.0, "S4": 55.56}
        for kod, oran in beklenen.items():
            self.assertAlmostEqual(k.basabas_orani(kurallar[kod], 0.20), oran, places=2)

    def test_tum_stratejiler_yapay_veride_calisir(self):
        df5 = yapay_mumlar(6000, dilim_dk=5, tohum=3)
        df15 = yapay_mumlar(3000, dilim_dk=15, tohum=3)
        for kod, kural in k.tum_kurallar().items():
            with self.subTest(kod=kod):
                df = df15 if kural["zaman_dilimi"] == "15m" else df5
                tablo = k.sinyal_uret(df, kural)
                self.assertEqual(len(tablo), len(df))
                self.assertEqual(tablo["sinyal"].dtype, bool)
                # Başlangıç mumları dolmadan sinyal üretilmemeli
                self.assertFalse(tablo["sinyal"].iloc[:50].any())


class YeniStratejilerinMantigi(unittest.TestCase):
    """S5 ve S6'nın kural dosyaları, anlatılan fikri gerçekten kodluyor mu?

    Sinyal veren her mumda koşullar ham fiyat verisinden yeniden hesaplanır.
    """

    @classmethod
    def setUpClass(cls):
        cls.df = yapay_mumlar(12000, tohum=17, oynaklik=0.003)
        cls.kurallar = k.tum_kurallar()

    def _sinyaller(self, kod):
        tablo = k.sinyal_uret(self.df, self.kurallar[kod])
        mumlar = [i for i in range(len(tablo)) if tablo["sinyal"].iloc[i]]
        self.assertGreater(len(mumlar), 5, f"{kod} yapay veride neredeyse hiç sinyal vermedi")
        return tablo, mumlar

    def test_s6_dip_supurulup_geri_alinmis(self):
        tablo, mumlar = self._sinyaller("S6")
        dusuk, kapanis, acilis = self.df["low"], self.df["close"], self.df["open"]
        for i in mumlar:
            seviye = dusuk.iloc[i - 26:i - 2].min()        # süpürmeden önceki 24 mumun dibi
            self.assertLess(dusuk.iloc[i - 2:i + 1].min(), seviye, i)   # son 3 mumda altına sarktı
            self.assertGreater(kapanis.iloc[i], seviye, i)              # yeniden üstünde kapandı
            self.assertGreater(kapanis.iloc[i], acilis.iloc[i], i)      # yükseliş mumu
            self.assertGreater(tablo["rsi14"].iloc[i], tablo["rsi14"].iloc[i - 1], i)
            self.assertGreater(tablo["ema50_1s_egim"].iloc[i], 0, i)    # üst dilim trendi yukarı

    def test_s6k_tepe_supurulup_geri_verilmis(self):
        tablo, mumlar = self._sinyaller("S6K")
        yuksek, kapanis, acilis = self.df["high"], self.df["close"], self.df["open"]
        for i in mumlar:
            seviye = yuksek.iloc[i - 26:i - 2].max()
            self.assertGreater(yuksek.iloc[i - 2:i + 1].max(), seviye, i)
            self.assertLess(kapanis.iloc[i], seviye, i)
            self.assertLess(kapanis.iloc[i], acilis.iloc[i], i)
            self.assertLess(tablo["ema50_1s_egim"].iloc[i], 0, i)

    def test_s5_macd_yukari_kesmis_rsi_ivmeli(self):
        tablo, mumlar = self._sinyaller("S5")
        for i in mumlar:
            self.assertGreater(tablo["macd_cizgi"].iloc[i], tablo["macd_sinyal"].iloc[i], i)
            # Kesişme bu mumda ya da bir önceki mumda oldu.
            onceki = [tablo["macd_cizgi"].iloc[j] <= tablo["macd_sinyal"].iloc[j] for j in (i - 1, i - 2)]
            self.assertTrue(any(onceki), i)
            self.assertTrue(50 < tablo["rsi14"].iloc[i] < 70, i)
            self.assertGreater(tablo["rsi14"].iloc[i], tablo["rsi14"].iloc[i - 3], i)
            self.assertGreater(self.df["volume"].iloc[i], 1.2 * tablo["hacim20"].iloc[i], i)

    def test_s5k_macd_asagi_kesmis(self):
        tablo, mumlar = self._sinyaller("S5K")
        for i in mumlar:
            self.assertLess(tablo["macd_cizgi"].iloc[i], tablo["macd_sinyal"].iloc[i], i)
            self.assertTrue(30 < tablo["rsi14"].iloc[i] < 50, i)

    def test_ayni_mumda_hem_alim_hem_satis_sinyali_olmaz(self):
        for uzun, kisa in (("S5", "S5K"), ("S6", "S6K")):
            a = k.sinyal_uret(self.df, self.kurallar[uzun])["sinyal"]
            b = k.sinyal_uret(self.df, self.kurallar[kisa])["sinyal"]
            self.assertFalse((a & b).any(), uzun)


class MacdGostergesi(unittest.TestCase):
    def _kural(self, **macd):
        kural = basit_kural()
        kural["gostergeler"]["macd"] = {"tur": "macd", **macd}
        kural["giris"] = {"sol": "macd_cizgi", "islem": "yukari_keser", "sag": "macd_sinyal"}
        return kural

    def test_uc_sutun_uretir_ve_varsayilan_ayar_12_26_9(self):
        from karabasan import gostergeler as g

        df = yapay_mumlar(400, tohum=5)
        tablo = k.gosterge_ekle(df, self._kural())
        cizgi, sinyal, fark = g.macd(df["close"])
        for sutun, beklenen in (("macd_cizgi", cizgi), ("macd_sinyal", sinyal), ("macd_fark", fark)):
            self.assertTrue((tablo[sutun].dropna() == beklenen.dropna()).all(), sutun)
        self.assertTrue(((tablo["macd_cizgi"] - tablo["macd_sinyal"] - tablo["macd_fark"]).dropna().abs() < 1e-12).all())
        # Yavaş ortalama ve sinyal oturmadan değer üretilmez.
        self.assertTrue(tablo["macd_sinyal"].iloc[:33].isna().all())
        self.assertTrue(tablo["macd_sinyal"].iloc[34:].notna().all())

    def test_yukselen_fiyatta_cizgi_arti(self):
        from karabasan import gostergeler as g
        import pandas as pd

        cizgi, _, _ = g.macd(pd.Series([100.0 + i for i in range(100)]))
        self.assertGreater(cizgi.iloc[-1], 0)
        cizgi, _, _ = g.macd(pd.Series([200.0 - i for i in range(100)]))
        self.assertLess(cizgi.iloc[-1], 0)

    def test_hizli_yavastan_kucuk_olmali(self):
        with self.assertRaises(k.KuralHatasi) as baglam:
            k.kural_dogrula(self._kural(hizli=26, yavas=12))
        self.assertIn("'hizli' periyot 'yavas' periyottan küçük olmalı", str(baglam.exception))

    def test_gecersiz_ayar_reddedilir(self):
        for ayar in ({"sinyal": 0}, {"yavas": 500}, {"hizli": 1.5}, {"hizli": True}):
            with self.assertRaises(k.KuralHatasi):
                k.kural_dogrula(self._kural(**ayar))

    def test_baslangic_mumu_ihtiyaci(self):
        self.assertGreaterEqual(k.gereken_mum(self._kural()), (26 + 9) * 3)

    def test_macd_gelecege_bakmaz(self):
        df = yapay_mumlar(600, tohum=9)
        tam = k.sinyal_uret(df, self._kural())
        kisa = k.sinyal_uret(df.iloc[:450], self._kural())
        self.assertEqual(list(tam["sinyal"].iloc[:450]), list(kisa["sinyal"]))


class Dogrulama(unittest.TestCase):
    def test_gecerli_kural(self):
        k.kural_dogrula(basit_kural())

    def hata_bekle(self, kural, parca):
        with self.assertRaises(k.KuralHatasi) as baglam:
            k.kural_dogrula(kural)
        self.assertIn(parca, str(baglam.exception))

    def test_eksik_alan(self):
        kural = basit_kural()
        del kural["cikis"]
        self.hata_bekle(kural, "cikis")

    def test_yanlis_yon(self):
        self.hata_bekle(basit_kural(yon="yukari"), "yon")

    def test_stop_siniri(self):
        kural = basit_kural()
        kural["cikis"]["zarar_durdur_yuzde"] = 100  # yazım hatası: %1 yerine %100
        self.hata_bekle(kural, "zarar_durdur_yuzde")

    def test_hedef_siniri(self):
        kural = basit_kural()
        kural["cikis"]["kar_hedefi_yuzde"] = 0
        self.hata_bekle(kural, "kar_hedefi_yuzde")

    def test_tanimsiz_gosterge(self):
        self.hata_bekle(basit_kural(giris={"sol": "kapanis", "islem": ">", "sag": "yok"}), "yok")

    def test_tanimsiz_islem(self):
        self.hata_bekle(basit_kural(giris={"sol": "kapanis", "islem": "==", "sag": 1}), "işlem")

    def test_negatif_kaydirma_gelecege_bakar(self):
        giris = {"sol": "kapanis", "islem": ">", "sag": {"ad": "ema3", "kaydir": -1}}
        self.hata_bekle(basit_kural(giris=giris), "kaydir")

    def test_ust_dilim_tanimsiz(self):
        kural = basit_kural()
        kural["gostergeler"]["e"] = {"tur": "ema", "periyot": 5, "dilim": "ust"}
        self.hata_bekle(kural, "ust_zaman_dilimi")

    def test_ust_dilim_kat_degil(self):
        self.hata_bekle(basit_kural(ust_zaman_dilimi="7m"), "ust_zaman_dilimi")

    def test_cok_fazla_baslangic_mumu(self):
        kural = basit_kural(ust_zaman_dilimi="1d")
        kural["gostergeler"]["e"] = {"tur": "ema", "periyot": 200, "dilim": "ust"}
        self.hata_bekle(kural, "başlangıç mumu")

    def test_cakisan_gosterge_adi(self):
        kural = basit_kural()
        kural["gostergeler"]["close"] = {"tur": "ema", "periyot": 5}
        self.hata_bekle(kural, "close")

    def test_bos_baglac(self):
        self.hata_bekle(basit_kural(giris={"hepsi": []}), "hepsi")


class Degerlendirme(unittest.TestCase):
    def setUp(self):
        self.df = yapay_mumlar(400, tohum=11)

    def test_basit_karsilastirma(self):
        tablo = k.sinyal_uret(self.df, basit_kural())
        ema3 = g.ema(self.df["close"], 3)
        beklenen = (self.df["close"] > ema3) & ema3.notna()
        pd.testing.assert_series_equal(tablo["sinyal"], beklenen.astype(bool), check_names=False)

    def test_yukari_keser(self):
        kural = basit_kural(giris={"sol": "kapanis", "islem": "yukari_keser", "sag": "ema3"})
        sinyal = k.sinyal_uret(self.df, kural)["sinyal"]
        ema3 = g.ema(self.df["close"], 3)
        c = self.df["close"]
        beklenen = (c > ema3) & (c.shift(1) <= ema3.shift(1))
        pd.testing.assert_series_equal(sinyal, beklenen.astype(bool), check_names=False)
        # Kesişim mumlarından hemen önce fiyat ortalamanın üstünde olamaz
        onceki = (c.shift(1) > ema3.shift(1))[sinyal]
        self.assertFalse(onceki.any())

    def test_hepsi_ve_herhangi(self):
        a = {"sol": "kapanis", "islem": ">", "sag": "ema3"}
        b = {"sol": "kapanis", "islem": ">", "sag": "acilis"}
        sa = k.sinyal_uret(self.df, basit_kural(giris=a))["sinyal"]
        sb = k.sinyal_uret(self.df, basit_kural(giris=b))["sinyal"]
        ve = k.sinyal_uret(self.df, basit_kural(giris={"hepsi": [a, b]}))["sinyal"]
        veya = k.sinyal_uret(self.df, basit_kural(giris={"herhangi": [a, b]}))["sinyal"]
        pd.testing.assert_series_equal(ve, sa & sb, check_names=False)
        pd.testing.assert_series_equal(veya, sa | sb, check_names=False)

    def test_kaydir_ve_carpan(self):
        giris = {"sol": "hacim", "islem": ">", "sag": {"ad": "hacim", "kaydir": 1, "carpan": 2.0}}
        sinyal = k.sinyal_uret(self.df, basit_kural(giris=giris))["sinyal"]
        v = self.df["volume"]
        beklenen = (v > v.shift(1) * 2.0).fillna(False)
        pd.testing.assert_series_equal(sinyal, beklenen.astype(bool), check_names=False)

    def test_son_n_mumda(self):
        tek = {"sol": "kapanis", "islem": "yukari_keser", "sag": "ema3"}
        genis = {**tek, "son_n_mumda": 3}
        s1 = k.sinyal_uret(self.df, basit_kural(giris=tek))["sinyal"]
        s3 = k.sinyal_uret(self.df, basit_kural(giris=genis))["sinyal"]
        beklenen = s1 | s1.shift(1, fill_value=False) | s1.shift(2, fill_value=False)
        pd.testing.assert_series_equal(s3, beklenen.astype(bool), check_names=False)

    def test_girdi_tablosu_degismez(self):
        kopya = self.df.copy()
        k.sinyal_uret(self.df, basit_kural())
        pd.testing.assert_frame_equal(self.df, kopya)

    def test_sinyaller_gelecege_bakmaz(self):
        """Sonradan gelen veri, geçmişteki sinyali değiştirmemeli."""
        df5 = yapay_mumlar(5000, dilim_dk=5, tohum=5)
        df15 = yapay_mumlar(2500, dilim_dk=15, tohum=5)
        for kod, kural in k.tum_kurallar().items():
            with self.subTest(kod=kod):
                df = df15 if kural["zaman_dilimi"] == "15m" else df5
                kesim = len(df) - 700
                tam = k.sinyal_uret(df, kural)["sinyal"].iloc[:kesim]
                kismi = k.sinyal_uret(df.iloc[:kesim], kural)["sinyal"]
                np.testing.assert_array_equal(tam.to_numpy(), kismi.to_numpy())

    def test_ust_dilim_gostergesi_gecikmeli_gelir(self):
        kural = basit_kural(ust_zaman_dilimi="1h")
        kural["gostergeler"] = {"k1s": {"tur": "sma", "kaynak": "kapanis", "periyot": 1, "dilim": "ust"}}
        kural["giris"] = {"sol": "kapanis", "islem": ">", "sag": "k1s"}
        tablo = k.gosterge_ekle(self.df, kural)
        # 01:50 mumu (indeks 22): geçerli saatlik kapanış 00:55 mumunun kapanışıdır
        self.assertAlmostEqual(tablo["k1s"].iloc[22], self.df["close"].iloc[11])
        # 01:55 mumu (indeks 23): artık 01:00 saatlik mumu kapanmıştır
        self.assertAlmostEqual(tablo["k1s"].iloc[23], self.df["close"].iloc[23])


if __name__ == "__main__":
    unittest.main()
