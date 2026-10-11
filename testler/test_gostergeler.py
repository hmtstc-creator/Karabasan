import unittest

import numpy as np
import pandas as pd

from karabasan import gostergeler as g
from testler.veri import duz_mumlar, yapay_mumlar


class GostergeTestleri(unittest.TestCase):
    def test_dilim_dakika(self):
        self.assertEqual(g.dilim_dakika("5m"), 5)
        self.assertEqual(g.dilim_dakika("1h"), 60)
        self.assertEqual(g.dilim_dakika("4h"), 240)
        self.assertEqual(g.dilim_dakika("1d"), 1440)
        with self.assertRaises(ValueError):
            g.dilim_dakika("5x")

    def test_ema_elle_hesapla_ayni(self):
        seri = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        sonuc = g.ema(seri, 3)
        alfa = 2 / (3 + 1)
        beklenen = [1.0]
        for x in seri[1:]:
            beklenen.append(alfa * x + (1 - alfa) * beklenen[-1])
        self.assertTrue(np.isnan(sonuc.iloc[1]))  # periyot dolmadan değer yok
        np.testing.assert_allclose(sonuc.iloc[2:].to_numpy(), beklenen[2:], rtol=1e-12)

    def test_rsi_sinirlar(self):
        surekli_artan = pd.Series(np.arange(1.0, 60.0))
        self.assertAlmostEqual(g.rsi(surekli_artan, 14).iloc[-1], 100.0)
        surekli_azalan = pd.Series(np.arange(60.0, 1.0, -1.0))
        self.assertAlmostEqual(g.rsi(surekli_azalan, 14).iloc[-1], 0.0)
        karisik = g.rsi(yapay_mumlar(500)["close"], 14).dropna()
        self.assertTrue(((karisik >= 0) & (karisik <= 100)).all())

    def test_bollinger(self):
        kapanis = yapay_mumlar(200)["close"]
        ust, orta, alt = g.bollinger(kapanis, 20, 2.0)
        np.testing.assert_allclose(orta.dropna(), g.sma(kapanis, 20).dropna())
        gecerli = orta.notna()
        self.assertTrue((ust[gecerli] >= orta[gecerli]).all())
        self.assertTrue((alt[gecerli] <= orta[gecerli]).all())
        sabit = pd.Series([5.0] * 30)
        ust, orta, alt = g.bollinger(sabit, 20, 2.0)
        self.assertAlmostEqual(ust.iloc[-1], 5.0)
        self.assertAlmostEqual(alt.iloc[-1], 5.0)

    def test_atr_yuzde_pozitif(self):
        sonuc = g.atr_yuzde(yapay_mumlar(300), 14).dropna()
        self.assertTrue((sonuc > 0).all())

    def test_vwap_gunluk_sifirlanir(self):
        df = yapay_mumlar(600)  # 5 dk mum, iki günden fazla
        vwap = g.vwap_gunluk(df)
        gun_basi = df.index[df["date"].dt.hour.eq(0) & df["date"].dt.minute.eq(0)]
        for i in gun_basi:
            tipik = (df.loc[i, "high"] + df.loc[i, "low"] + df.loc[i, "close"]) / 3
            self.assertAlmostEqual(vwap.loc[i], tipik)

    def test_gelecege_bakmaz(self):
        df = yapay_mumlar(800, tohum=7)
        kisa = df.iloc[:500]
        for ad, fonk in {
            "ema": lambda d: g.ema(d["close"], 20),
            "rsi": lambda d: g.rsi(d["close"], 14),
            "atr": lambda d: g.atr_yuzde(d, 14),
            "vwap": g.vwap_gunluk,
            "tepe": lambda d: g.en_yuksek(d["high"], 48),
        }.items():
            with self.subTest(gosterge=ad):
                np.testing.assert_allclose(
                    fonk(kisa).to_numpy(), fonk(df).iloc[:500].to_numpy(), equal_nan=True
                )

    def test_ust_dilime_cevir(self):
        df = yapay_mumlar(48, dilim_dk=5)  # 4 saat
        ust = g.ust_dilime_cevir(df, "5m", "1h")
        self.assertEqual(len(ust), 4)
        ilk_saat = df.iloc[:12]
        self.assertAlmostEqual(ust.loc[0, "open"], ilk_saat["open"].iloc[0])
        self.assertAlmostEqual(ust.loc[0, "close"], ilk_saat["close"].iloc[-1])
        self.assertAlmostEqual(ust.loc[0, "high"], ilk_saat["high"].max())
        self.assertAlmostEqual(ust.loc[0, "low"], ilk_saat["low"].min())
        self.assertAlmostEqual(ust.loc[0, "volume"], ilk_saat["volume"].sum())
        with self.assertRaises(ValueError):
            g.ust_dilime_cevir(df, "5m", "7m")

    def test_ust_dilim_hizalama_gelecege_bakmaz(self):
        # 3 saatlik 5 dk veri: 00:00 - 02:55
        df = yapay_mumlar(36, dilim_dk=5)
        ust = g.ust_dilime_cevir(df, "5m", "1h")
        hizali = g.ust_dilimden_hizala(ust["close"], ust["date"], df["date"], "5m", "1h")
        # 00:50 mumunda henüz kapanmış bir saatlik mum yok
        self.assertTrue(np.isnan(hizali.iloc[10]))
        # 00:55 mumu kapandığında 00:00 saatlik mumu da kapanmıştır
        self.assertAlmostEqual(hizali.iloc[11], ust.loc[0, "close"])
        # 01:50 mumunda hâlâ 00:00 saatlik mumunun değeri geçerlidir
        self.assertAlmostEqual(hizali.iloc[22], ust.loc[0, "close"])
        # 01:55 mumunda 01:00 saatlik mumunun değeri gelir
        self.assertAlmostEqual(hizali.iloc[23], ust.loc[1, "close"])


class PiyasaYapisi(unittest.TestCase):
    """Salınım, yapı kırılımı (BOS / CHoCH), denge ve emir blokları."""

    # (açılış, yüksek, düşük, kapanış). Uzunluk 2 ile:
    # 3. mum tepe (110), 5. mum dip (104), 8. mum tepeyi kırar, 12. mum dibi kırar.
    MUMLAR = [
        (100, 101, 99, 100),
        (100, 103, 100, 102),
        (102, 106, 102, 105),
        (105, 110, 105, 109),
        (109, 109, 106, 107),
        (107, 108, 104, 105),
        (105, 107, 104.5, 106),
        (106, 109, 105.5, 108.5),
        (108.5, 112, 108, 111.5),
        (111.5, 113, 110, 110.5),
        (110.5, 111, 107, 107.5),
        (107.5, 108, 105, 105.5),
        (105.5, 106, 103, 103.5),
    ]

    @classmethod
    def setUpClass(cls):
        cls.df = duz_mumlar(cls.MUMLAR)
        cls.y = g.piyasa_yapisi(cls.df, 2)

    def test_sutunlar(self):
        self.assertEqual(tuple(self.y.columns), g.YAPI_SUTUNLARI)
        self.assertEqual(len(self.y), len(self.df))

    def test_salinim_ancak_onaylaninca_bilinir(self):
        # Tepe 3. mumda oluştu ama iki mum sonra (5. mumda) onaylandı.
        self.assertTrue(np.isnan(self.y["tepe"].iloc[4]))
        self.assertEqual(self.y["tepe"].iloc[5], 110.0)
        # 5. mumdaki dip 7. mumda onaylandı; ondan önce bilinen dip 0. mumunkiydi.
        self.assertEqual(self.y["dip"].iloc[6], 99.0)
        self.assertEqual(self.y["dip"].iloc[7], 104.0)

    def test_yukari_kirilim_ve_alim_blogu(self):
        y = self.y
        self.assertEqual(y["kirilim"].tolist()[:9], [0, 0, 0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(y["yon"].iloc[7], 0)       # henüz kırılım yok
        self.assertEqual(y["yon"].iloc[8], 1)
        self.assertEqual(y["donus"].iloc[8], 0)     # öncesinde ters yön yoktu: dönüş sayılmaz
        # Blok: kırılan tepe ile kırılım arasındaki en düşük mum (5. mum: 104-108).
        self.assertTrue(np.isnan(y["blok_ust"].iloc[7]))
        self.assertEqual((y["blok_ust"].iloc[8], y["blok_alt"].iloc[8]), (108.0, 104.0))
        # 10. mum bloğa dokundu (düşük 107) ama delmedi: blok geçerli kalır.
        self.assertLessEqual(self.df["low"].iloc[10], y["blok_ust"].iloc[10])
        self.assertEqual(y["blok_alt"].iloc[11], 104.0)

    def test_asagi_kirilim_donustur_ve_blok_delinir(self):
        y = self.y
        self.assertEqual(y["kirilim"].iloc[12], -1)
        self.assertEqual(y["donus"].iloc[12], -1)   # yön yukarıyken aşağı kırıldı: CHoCH
        self.assertEqual(y["yon"].iloc[12], -1)
        # Fiyat alım bloğunun altına sarktı (103 < 104): blok düşer.
        self.assertTrue(np.isnan(y["blok_ust"].iloc[12]))
        # Satış bloğu: kırılan dip ile kırılım arasındaki en yüksek mum (9. mum: 110-113).
        self.assertEqual((y["sblok_ust"].iloc[12], y["sblok_alt"].iloc[12]), (113.0, 110.0))

    def test_denge_araligin_ortasidir(self):
        # Son tepeden beri en yüksek 113, son dipten beri en düşük 103.
        self.assertEqual(self.y["denge"].iloc[12], 108.0)
        # 8. mumda: en yüksek 112 (bu mum), son dip 104.
        self.assertEqual(self.y["denge"].iloc[8], 108.0)
        self.assertEqual(self.y["denge"].iloc[7], (110 + 104) / 2)

    def test_her_tepe_bir_kez_kirilir(self):
        ek = [(103.5, 114, 103, 113.5), (113.5, 116, 113, 115.5), (115.5, 118, 115, 117.5)]
        y = g.piyasa_yapisi(duz_mumlar(self.MUMLAR + ek), 2)
        # 13. mum 113'lük tepeyi kırar (aşağı yönden: dönüş); sonraki mumlar yeniden kırılım saymaz.
        self.assertEqual(y["kirilim"].tolist()[13:], [1, 0, 0])
        self.assertEqual(y["donus"].iloc[13], 1)

    def test_blok_omru_dolunca_duser(self):
        duz = [(111.5, 112, 110, 111.5)] * 6
        mumlar = self.MUMLAR[:9] + duz
        uzun = g.piyasa_yapisi(duz_mumlar(mumlar), 2, blok_omru=40)
        kisa = g.piyasa_yapisi(duz_mumlar(mumlar), 2, blok_omru=3)
        self.assertEqual(uzun["blok_ust"].iloc[-1], 108.0)
        self.assertEqual(kisa["blok_ust"].iloc[11], 108.0)   # oluştuğu mumdan 3 mum sonra hâlâ geçerli
        self.assertTrue(np.isnan(kisa["blok_ust"].iloc[12]))

    def test_asiri_genis_mum_blok_secilmez(self):
        mumlar = [list(m) for m in self.MUMLAR]
        onceki = g.piyasa_yapisi(duz_mumlar(mumlar), 2, blok_omru=4)
        self.assertEqual(onceki["blok_alt"].iloc[8], 104.0)
        # 5. mumun aralığı çok geniş olsun (90-108): son 4 mumun ortalamasının 2 katından fazla.
        mumlar[5] = [107, 108, 90, 105]
        y = g.piyasa_yapisi(duz_mumlar(mumlar), 2, blok_omru=4)
        self.assertEqual(y["kirilim"].iloc[8], 1)
        # En düşük mum 5. mumdu ama geniş olduğu için seçilmez; sıradaki en düşük 6. mum (104,5-107).
        self.assertEqual((y["blok_ust"].iloc[8], y["blok_alt"].iloc[8]), (107.0, 104.5))

    def test_gelecege_bakmaz(self):
        df = yapay_mumlar(1500, tohum=41, oynaklik=0.004)
        tam = g.piyasa_yapisi(df, 5)
        for kesim in (300, 777, 1234):
            kismi = g.piyasa_yapisi(df.iloc[:kesim], 5)
            pd.testing.assert_frame_equal(tam.iloc[:kesim], kismi)

    def test_rastgele_veride_tutarlilik(self):
        df = yapay_mumlar(4000, tohum=42, oynaklik=0.004)
        y = g.piyasa_yapisi(df, 5)
        self.assertTrue(set(y["yon"].unique()) <= {-1.0, 0.0, 1.0})
        yukari, asagi = y["kirilim"] > 0, y["kirilim"] < 0
        self.assertGreater(int(yukari.sum()), 20)
        self.assertGreater(int(asagi.sum()), 20)
        # Kırılım mumu, bir önceki mumda bilinen seviyenin ötesinde kapanmıştır.
        self.assertTrue((df["close"][yukari] > y["tepe"].shift(1)[yukari]).all())
        self.assertTrue((df["close"][asagi] < y["dip"].shift(1)[asagi]).all())
        # Kırılımdan sonra yön o taraftadır; dönüş yalnız kırılım mumunda ve aynı işaretle olur.
        self.assertTrue((y["yon"][yukari] == 1).all())
        self.assertTrue((y["yon"][asagi] == -1).all())
        self.assertTrue((y["donus"][y["donus"] != 0] == y["kirilim"][y["donus"] != 0]).all())
        self.assertTrue((y["yon"].shift(1)[y["donus"] > 0] == -1).all())
        # Yön yalnız kırılım mumunda değişir.
        degisti = y["yon"] != y["yon"].shift(1).fillna(0.0)
        self.assertTrue((y["kirilim"][degisti] != 0).all())
        # Geçerli bloklar: üst sınır alttan büyük; fiyat alım bloğunu delmemiş, satış bloğunu aşmamış.
        alim, satis = y["blok_ust"].notna(), y["sblok_ust"].notna()
        self.assertGreater(int(alim.sum()), 100)
        self.assertGreater(int(satis.sum()), 100)
        self.assertTrue((y["blok_ust"][alim] >= y["blok_alt"][alim]).all())
        self.assertTrue((df["low"][alim] >= y["blok_alt"][alim]).all())
        self.assertTrue((df["high"][satis] <= y["sblok_ust"][satis]).all())
        # Denge, son tepe ile son dibin oluşturduğu aralığın içindedir.
        denge = y["denge"].dropna()
        self.assertTrue((denge > 0).all())

    def test_veri_baslangicindan_bagimsiz_oturur(self):
        """Aynı mumlar, veri daha geç başlasa da bir süre sonra aynı yapıyı vermeli."""
        df = yapay_mumlar(3000, tohum=43, oynaklik=0.004)
        tam = g.piyasa_yapisi(df, 5)
        isinma = 150   # kural motorunun bu gösterge için istediği başlangıç mumu (30 x uzunluk)
        for bas in (500, 1203, 2011):
            kismi = g.piyasa_yapisi(df.iloc[bas:], 5)
            pd.testing.assert_frame_equal(tam.iloc[bas + isinma:], kismi.iloc[isinma:])


if __name__ == "__main__":
    unittest.main()
