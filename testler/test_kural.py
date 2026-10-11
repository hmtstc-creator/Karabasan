import copy
import unittest

import numpy as np
import pandas as pd

from karabasan import gostergeler as g
from karabasan import kural as k
from testler.veri import butun_kurallar, yapay_mumlar


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
    def test_tum_stratejiler_yuklenir(self):
        kurallar = k.tum_kurallar()
        self.assertEqual(sorted(kurallar),
                         ["SM", "SMD", "SMDK", "SMK", "SNIPER"])
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
        self.assertEqual(len(adlar), len(k.tum_kurallar()))   # adlar birbirinden farklı

    def test_smartmoney_adi_gorunur(self):
        """Ahmet bu stratejiye "smartmoney" adını verdi; sayfada ve Telegram'da ad böyle başlar."""
        kurallar = k.tum_kurallar()
        for kod in ("SM", "SMK"):
            self.assertTrue(kurallar[kod]["ad"].startswith("Smartmoney: "), kod)
            self.assertEqual(kurallar[kod]["borsa_dilimleri"], ["1d"])

    def test_her_bot_bir_kurala_baglidir(self):
        from karabasan.botlar import BOTLAR

        kurallar = k.tum_kurallar()
        self.assertEqual(sorted(b[2] for b in BOTLAR), sorted(kurallar))

    def test_emekli_stratejiler_yuklenmez_ama_okunabilir(self):
        kurallar = k.tum_kurallar()
        for kod in ("S1", "S1K", "S2", "S2K", "S3", "S4", "S5", "S5K", "S6", "S6K", "S7", "S7K"):
            self.assertNotIn(kod, kurallar)
            self.assertEqual(k.kural_yukle(k.STRATEJI_KLASORU / "emekli" / f"{kod}.json")["kod"], kod)

    def test_butun_stratejilerde_hedef_ve_stop_ayni(self):
        """Ahmet'in isteği (12 Ekim 2026): 1 kat vadelide %0,8 hedef, %3 stop.

        Sniper bilerek ayrıdır: 5 dakikalık kısa vuruş, %1,2 hedef, %1,5 stop (Ahmet'in isteği).
        """
        for kod, kural in k.tum_kurallar().items():
            if kod == "SNIPER":
                continue
            self.assertEqual(kural["cikis"]["kar_hedefi_yuzde"], 0.8, kod)
            self.assertEqual(kural["cikis"]["zarar_durdur_yuzde"], 3.0, kod)

    def test_ters_yonlu_ciftler_ayni_cikisi_kullanir(self):
        kurallar = k.tum_kurallar()
        for kod in ("SM", "SMD"):
            self.assertEqual(kurallar[kod]["cikis"], kurallar[kod + "K"]["cikis"], kod)
            self.assertEqual(kurallar[kod]["gostergeler"], kurallar[kod + "K"]["gostergeler"], kod)

    def test_basabas_oranlari_raporla_ayni(self):
        kurallar = k.tum_kurallar()
        # 12 Ekim 2026'dan beri bütün stratejilerde hedef %0,8, stop %3:
        # (3 + 0,2) / (0,8 + 3) = %84,21.
        beklenen = {"SM": 84.21, "SMK": 84.21, "SMD": 84.21, "SMDK": 84.21,
                    # Sniper: (1,5 + 0,2) / (1,2 + 1,5) = %62,96
                    "SNIPER": 62.96}
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
        cls.df15 = yapay_mumlar(6000, dilim_dk=15, tohum=17, oynaklik=0.004)
        # Bu stratejiler 12 Ekim 2026'dan beri emekli; kural dosyaları geçerli kalsın diye sınanır.
        cls.kurallar = butun_kurallar()

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
        a = k.sinyal_uret(self.df15, self.kurallar["S7"])["sinyal"]
        b = k.sinyal_uret(self.df15, self.kurallar["S7K"])["sinyal"]
        self.assertFalse((a & b).any(), "S7")

    def _sinyaller15(self, kod):
        tablo = k.sinyal_uret(self.df15, self.kurallar[kod])
        mumlar = [i for i in range(len(tablo)) if tablo["sinyal"].iloc[i]]
        self.assertGreater(len(mumlar), 5, f"{kod} yapay veride neredeyse hiç sinyal vermedi")
        return tablo, mumlar

    def test_s7_yukselis_trendinde_rsi2_dibi(self):
        tablo, mumlar = self._sinyaller15("S7")
        kapanis = self.df15["close"]
        sma200 = kapanis.rolling(200).mean()
        rsi2 = g.rsi(kapanis, 2)
        for i in mumlar:
            self.assertLess(rsi2.iloc[i], 10, i)
            self.assertGreater(kapanis.iloc[i], sma200.iloc[i], i)
            self.assertGreater(tablo["ema50_1s_egim"].iloc[i], 0, i)
            self.assertGreater(tablo["kapanis_1s"].iloc[i], tablo["ema50_1s"].iloc[i], i)

    def test_s7k_dusus_trendinde_rsi2_tepesi(self):
        tablo, mumlar = self._sinyaller15("S7K")
        kapanis = self.df15["close"]
        sma200 = kapanis.rolling(200).mean()
        rsi2 = g.rsi(kapanis, 2)
        for i in mumlar:
            self.assertGreater(rsi2.iloc[i], 90, i)
            self.assertLess(kapanis.iloc[i], sma200.iloc[i], i)
            self.assertLess(tablo["ema50_1s_egim"].iloc[i], 0, i)


class SmartmoneyMantigi(unittest.TestCase):
    """SM ve SMK'nın kural dosyaları anlatılan dört katmanı gerçekten kodluyor mu?

    Veri yapaydır (rastgele yürüyüş, 60 gün); stratejinin kazandırıp kazandırmadığını
    değil, sinyalin yalnız anlatılan koşullarda çıktığını sınar.
    """

    @classmethod
    def setUpClass(cls):
        cls.df = yapay_mumlar(60 * 288, tohum=11, oynaklik=0.003)
        cls.gunluk = g.ust_dilime_cevir(cls.df, "5m", "1d")
        cls.kurallar = k.tum_kurallar()
        cls.tablo = {
            kod: k.sinyal_uret(cls.df, cls.kurallar[kod], {"1d": cls.gunluk}) for kod in ("SM", "SMK")
        }
        # Günlük trendin bağımsız hesabı: her günün kapanışı ve 20 günlük üstel ortalaması.
        gun = pd.to_datetime(cls.df["date"], utc=True).dt.floor("D")
        cls.gun_kapanis = cls.df["close"].groupby(gun).last()
        cls.gun_ema = cls.gun_kapanis.ewm(span=20, adjust=False, min_periods=20).mean()

    def _mumlar(self, kod):
        mumlar = [i for i in range(len(self.df)) if self.tablo[kod]["sinyal"].iloc[i]]
        self.assertGreater(len(mumlar), 5, f"{kod} yapay veride neredeyse hiç sinyal vermedi")
        return self.tablo[kod], mumlar

    def _son_kapanan_gun(self, i):
        """i. mum kapandığı anda tamamlanmış son günün (kapanış, ortalama) ikilisi."""
        mum_kapanisi = self.df["date"].iloc[i] + pd.Timedelta(minutes=5)
        gun = (mum_kapanisi - pd.Timedelta(days=1)).floor("D")
        return self.gun_kapanis.loc[gun], self.gun_ema.loc[gun]

    def test_alim_dort_katman(self):
        tablo, mumlar = self._mumlar("SM")
        dusuk, kapanis, hacim = self.df["low"], self.df["close"], self.df["volume"]
        for i in mumlar:
            gun_kapanisi, gun_ortalamasi = self._son_kapanan_gun(i)
            self.assertGreater(gun_kapanisi, gun_ortalamasi, i)                 # günlük trend yukarı
            self.assertEqual(tablo["yapi1s_yon"].iloc[i], 1, i)                 # 1 saatlik yapı yukarı
            self.assertLess(tablo["rsi14_1s"].iloc[i], 70, i)
            pencere = slice(i - 11, i + 1)                                      # son bir saat
            indirimli = (dusuk.iloc[pencere] < tablo["yapi15_denge"].iloc[pencere]).any()
            bloga_dokundu = (dusuk.iloc[pencere] <= tablo["yapi15_blok_ust"].iloc[pencere]).any()
            self.assertTrue(indirimli or bloga_dokundu, i)                      # 15 dakikalık geri çekilme
            self.assertEqual(tablo["yapi5_kirilim"].iloc[i], 1, i)              # 5 dakikalık kırılım
            self.assertGreater(kapanis.iloc[i], tablo["yapi5_tepe"].iloc[i - 1], i)
            self.assertTrue(50 < tablo["rsi14"].iloc[i] < 70, i)
            self.assertGreater(hacim.iloc[i], 1.2 * hacim.iloc[i - 19:i + 1].mean(), i)

    def test_satis_dort_katman(self):
        tablo, mumlar = self._mumlar("SMK")
        yuksek, kapanis, hacim = self.df["high"], self.df["close"], self.df["volume"]
        for i in mumlar:
            gun_kapanisi, gun_ortalamasi = self._son_kapanan_gun(i)
            self.assertLess(gun_kapanisi, gun_ortalamasi, i)
            self.assertEqual(tablo["yapi1s_yon"].iloc[i], -1, i)
            self.assertGreater(tablo["rsi14_1s"].iloc[i], 30, i)
            pencere = slice(i - 11, i + 1)
            pahali = (yuksek.iloc[pencere] > tablo["yapi15_denge"].iloc[pencere]).any()
            bloga_dokundu = (yuksek.iloc[pencere] >= tablo["yapi15_sblok_alt"].iloc[pencere]).any()
            self.assertTrue(pahali or bloga_dokundu, i)
            self.assertEqual(tablo["yapi5_kirilim"].iloc[i], -1, i)
            self.assertLess(kapanis.iloc[i], tablo["yapi5_dip"].iloc[i - 1], i)
            self.assertTrue(30 < tablo["rsi14"].iloc[i] < 50, i)
            self.assertGreater(hacim.iloc[i], 1.2 * hacim.iloc[i - 19:i + 1].mean(), i)

    def test_ayni_mumda_hem_alim_hem_satis_olmaz(self):
        self.assertFalse((self.tablo["SM"]["sinyal"] & self.tablo["SMK"]["sinyal"]).any())

    def test_gunluk_mum_ancak_gun_kapaninca_kullanilir(self):
        tablo = self.tablo["SM"]
        # 3. günün 23:50 mumu: geçerli günlük kapanış hâlâ 2. gününkidir.
        gun3_son = 3 * 288 + 287
        self.assertEqual(tablo["kapanis_1g"].iloc[gun3_son - 1], self.gunluk["close"].iloc[2])
        # 23:55 mumu kapandığında 3. gün de kapanmıştır.
        self.assertEqual(tablo["kapanis_1g"].iloc[gun3_son], self.gunluk["close"].iloc[3])
        self.assertEqual(self.gunluk["close"].iloc[3], self.df["close"].iloc[gun3_son])

    def test_gelecekteki_gunluk_mum_gecmis_sinyali_degistirmez(self):
        """Geçmiş testinde motor günlük tablonun tamamını verir; ileriki günler sızmamalı."""
        kesim = 45 * 288 + 100
        for kod in ("SM", "SMK"):
            kismi = k.sinyal_uret(self.df.iloc[:kesim], self.kurallar[kod], {"1d": self.gunluk})
            np.testing.assert_array_equal(
                self.tablo[kod]["sinyal"].to_numpy()[:kesim], kismi["sinyal"].to_numpy(), kod)
            self.assertGreater(int(kismi["sinyal"].sum()), 0, kod)

    def test_sinyal_veri_baslangicindan_bagimsizdir(self):
        """Motor veriyi 'gereken_mum' kadar geriden başlatır; benzetim dosyanın başından.

        İkisi aynı sinyali vermeli, yoksa uyum denemesindeki karşılaştırma tutmaz.
        """
        for kod in ("SM", "SMK"):
            isinma = k.gereken_mum(self.kurallar[kod])
            for bas in (20 * 288 + 7, 37 * 288 + 131):
                kismi = k.sinyal_uret(
                    self.df.iloc[bas:].reset_index(drop=True), self.kurallar[kod], {"1d": self.gunluk})
                np.testing.assert_array_equal(
                    self.tablo[kod]["sinyal"].to_numpy()[bas + isinma:],
                    kismi["sinyal"].to_numpy()[isinma:], f"{kod} {bas}")

    def test_gunluk_veri_verilmezse_taban_mumlardan_toplanir(self):
        for kod in ("SM", "SMK"):
            toplanan = k.sinyal_uret(self.df, self.kurallar[kod])
            np.testing.assert_array_equal(
                toplanan["sinyal"].to_numpy(), self.tablo[kod]["sinyal"].to_numpy(), kod)

    def test_gunluk_gecmis_yetmezse_sinyal_cikmaz(self):
        # 15 günlük veri: 20 günlük ortalama kurulamaz; kural susar, hata vermez.
        kisa = self.df.iloc[:15 * 288]
        for kod in ("SM", "SMK"):
            self.assertEqual(int(k.sinyal_uret(kisa, self.kurallar[kod])["sinyal"].sum()), 0, kod)

    def test_bos_gunluk_tablo_verilirse_toplanmaz(self):
        """Boş tablo "borsadan veri gelmedi" demektir: 5 dakikalıklardan toplamaya gidilmez."""
        bos = self.gunluk.iloc[:0]
        for kod in ("SM", "SMK"):
            tablo = k.sinyal_uret(self.df, self.kurallar[kod], {"1d": bos})
            self.assertEqual(int(tablo["sinyal"].sum()), 0, kod)
            self.assertTrue(tablo["ema20_1g"].isna().all())
            self.assertTrue(tablo["kapanis_1g"].isna().all())
            # Diğer dilimler bundan etkilenmez.
            self.assertTrue(tablo["yapi1s_yon"].abs().sum() > 0)

    def test_baslangic_mumu_ihtiyaci(self):
        kural = self.kurallar["SM"]
        # 1 saatlik yapı: 30 x 5 = 150 saatlik mum = 1800 beş dakikalık mum (+10 pay).
        self.assertEqual(k.gereken_mum(kural), 1810)
        # Günlük ortalama: 3 x 20 günlük mum (+10 pay); taban mum ihtiyacına katılmaz.
        self.assertEqual(k.gereken_ek_mum(kural), {"1d": 70})


class CokluDilim(unittest.TestCase):
    """Bir kuralda birden çok üst dilim, borsadan gelen dilimler ve piyasa yapısı göstergesi."""

    def test_acik_dilim_ust_ile_ayni_sonucu_verir(self):
        df = yapay_mumlar(900, tohum=13)
        eski = basit_kural(ust_zaman_dilimi="15m")
        eski["gostergeler"] = {"e": {"tur": "ema", "periyot": 10, "dilim": "ust"}}
        yeni = basit_kural()
        yeni["gostergeler"] = {"e": {"tur": "ema", "periyot": 10, "dilim": "15m"}}
        for kural in (eski, yeni):
            kural["giris"] = {"sol": "kapanis", "islem": ">", "sag": "e"}
        k.kural_dogrula(yeni)
        pd.testing.assert_series_equal(k.gosterge_ekle(df, eski)["e"], k.gosterge_ekle(df, yeni)["e"])
        self.assertEqual(k.gereken_mum(eski), k.gereken_mum(yeni))

    def test_iki_ayri_ust_dilim(self):
        df = yapay_mumlar(1500, tohum=14)
        kural = basit_kural()
        kural["gostergeler"] = {
            "k15": {"tur": "sma", "kaynak": "kapanis", "periyot": 1, "dilim": "15m"},
            "k1s": {"tur": "sma", "kaynak": "kapanis", "periyot": 1, "dilim": "1h"},
        }
        kural["giris"] = {"sol": "k15", "islem": ">", "sag": "k1s"}
        k.kural_dogrula(kural)
        tablo = k.gosterge_ekle(df, kural)
        # 01:55 mumu (indeks 23): hem 01:45'lik 15 dakikalık mum hem 01:00'lık saatlik mum kapanmıştır.
        self.assertEqual(tablo["k15"].iloc[23], df["close"].iloc[23])
        self.assertEqual(tablo["k1s"].iloc[23], df["close"].iloc[23])
        # 01:40 mumu (indeks 20): 15 dakikalıkta 01:30 mumu kapandı, saatlikte hâlâ 00:00 mumu geçerli.
        self.assertEqual(tablo["k15"].iloc[20], df["close"].iloc[20])
        self.assertEqual(tablo["k1s"].iloc[20], df["close"].iloc[11])

    def test_gecersiz_dilim_reddedilir(self):
        for dilim in ("7m", "5m", "1m", "abc", 15, ""):
            kural = basit_kural()
            kural["gostergeler"]["e"] = {"tur": "ema", "periyot": 5, "dilim": dilim}
            with self.assertRaises(k.KuralHatasi, msg=repr(dilim)) as baglam:
                k.kural_dogrula(kural)
            self.assertIn("dilim", str(baglam.exception))

    def test_kaynak_ayni_dilimde_olmali(self):
        kural = basit_kural()
        kural["gostergeler"]["r15"] = {"tur": "rsi", "periyot": 14, "dilim": "15m"}
        kural["gostergeler"]["o1s"] = {"tur": "sma", "kaynak": "r15", "periyot": 3, "dilim": "1h"}
        with self.assertRaises(k.KuralHatasi) as baglam:
            k.kural_dogrula(kural)
        self.assertIn("aynı dilimdeki", str(baglam.exception))
        kural["gostergeler"]["o1s"]["dilim"] = "15m"
        k.kural_dogrula(kural)

    def test_borsa_dilimleri_denetlenir(self):
        for deger in ("1d", ["7m"], ["5m"], ["1d", "1d"], [1440]):
            with self.assertRaises(k.KuralHatasi, msg=repr(deger)) as baglam:
                k.kural_dogrula(basit_kural(borsa_dilimleri=deger))
            self.assertIn("borsa_dilimleri", str(baglam.exception))
        k.kural_dogrula(basit_kural(borsa_dilimleri=["1d"]))

    def test_gunluk_ortalama_borsadan_istenmezse_reddedilir(self):
        kural = basit_kural()
        kural["gostergeler"]["e"] = {"tur": "ema", "periyot": 20, "dilim": "1d"}
        with self.assertRaises(k.KuralHatasi) as baglam:
            k.kural_dogrula(kural)
        self.assertIn("başlangıç mumu", str(baglam.exception))
        kural["borsa_dilimleri"] = ["1d"]
        k.kural_dogrula(kural)
        self.assertLess(k.gereken_mum(kural), 100)
        self.assertEqual(k.gereken_ek_mum(kural), {"1d": 70})
        self.assertEqual(k.borsa_dilimleri(kural), ["1d"])
        self.assertEqual(k.borsa_dilimleri(basit_kural()), [])

    def test_borsadan_gelen_mumlar_kullanilir(self):
        df = yapay_mumlar(3 * 288, tohum=15)
        kural = basit_kural(borsa_dilimleri=["1d"])
        kural["gostergeler"] = {"kg": {"tur": "sma", "kaynak": "kapanis", "periyot": 1, "dilim": "1d"}}
        kural["giris"] = {"sol": "kapanis", "islem": ">", "sag": "kg"}
        # Borsadan gelen tablo: sırası karışık, bir satırı yinelenmiş, ileriki bir gün de var.
        gunler = pd.to_datetime(["2026-01-02", "2025-12-31", "2026-01-01", "2026-01-01", "2026-01-03"], utc=True)
        borsa = pd.DataFrame({"date": gunler, "open": 1.0, "high": 1.0, "low": 1.0,
                              "close": [222.0, 999.0, 0.0, 111.0, 333.0], "volume": 1.0})
        tablo = k.gosterge_ekle(df, kural, {"1d": borsa})
        self.assertEqual(tablo["kg"].iloc[0], 999.0)            # 1 Ocak 00:00: geçerli olan 31 Aralık
        self.assertEqual(tablo["kg"].iloc[286], 999.0)          # 1 Ocak 23:50
        self.assertEqual(tablo["kg"].iloc[287], 111.0)          # 1 Ocak 23:55 (yinelenenin sonuncusu)
        self.assertEqual(tablo["kg"].iloc[288 + 287], 222.0)
        self.assertEqual(tablo["kg"].iloc[-1], 333.0)           # 3 Ocak 23:55
        self.assertNotIn(333.0, tablo["kg"].iloc[:-1].tolist())

    def test_ek_veri_topla(self):
        kural = basit_kural(borsa_dilimleri=["1h", "1d"])
        tablo = yapay_mumlar(10, dilim_dk=1440)
        ek, eksik = k.ek_veri_topla(kural, lambda dilim: tablo if dilim == "1d" else None)
        self.assertEqual((list(ek), eksik), (["1d"], ["1h"]))
        self.assertEqual(k.ek_veri_topla(basit_kural(), lambda dilim: tablo), ({}, []))

    def _yapi_kurali(self, **ek):
        kural = basit_kural()
        kural["gostergeler"] = {"y": {"tur": "yapi", "periyot": 5, **ek}}
        kural["giris"] = {"sol": "y_kirilim", "islem": ">", "sag": 0}
        return kural

    def test_yapi_gostergesi_sutunlari(self):
        df = yapay_mumlar(800, tohum=16, oynaklik=0.004)
        kural = self._yapi_kurali()
        k.kural_dogrula(kural)
        tablo = k.sinyal_uret(df, kural)
        beklenen = g.piyasa_yapisi(df, 5)
        for sutun in g.YAPI_SUTUNLARI:
            pd.testing.assert_series_equal(tablo[f"y_{sutun}"], beklenen[sutun], check_names=False)
        self.assertEqual(tablo["sinyal"].tolist(), (beklenen["kirilim"] > 0).tolist())
        self.assertGreater(int(tablo["sinyal"].sum()), 5)
        # 30 x uzunluk mum: salınımlar ve yön yeniden kurulsun, en eski blok da düşmüş olsun.
        self.assertEqual(k.gereken_mum(kural), 160)

    def test_yapi_ust_dilimde(self):
        df = yapay_mumlar(3000, tohum=18, oynaklik=0.004)
        kural = self._yapi_kurali(dilim="15m")
        k.kural_dogrula(kural)
        tablo = k.gosterge_ekle(df, kural)
        ust = g.ust_dilime_cevir(df, "5m", "15m")
        beklenen = g.ust_dilimden_hizala(g.piyasa_yapisi(ust, 5)["yon"], ust["date"], df["date"], "5m", "15m")
        pd.testing.assert_series_equal(tablo["y_yon"], beklenen, check_names=False)
        self.assertEqual(k.gereken_mum(kural), 460)

    def test_yapi_ayarlari_denetlenir(self):
        for ek, parca in (({"periyot": 1}, "salınım uzunluğu"), ({"periyot": 51}, "salınım uzunluğu"),
                          ({"blok_omru": 0}, "blok_omru"), ({"blok_omru": 2.5}, "blok_omru"),
                          ({"kaynak": "kapanis"}, "kaynak")):
            with self.assertRaises(k.KuralHatasi, msg=repr(ek)) as baglam:
                k.kural_dogrula(self._yapi_kurali(**ek))
            self.assertIn(parca, str(baglam.exception))
        k.kural_dogrula(self._yapi_kurali(blok_omru=60))
        self.assertEqual(k.gereken_mum(self._yapi_kurali(blok_omru=300)), 360)

    def test_yapi_sutunuyla_cakisan_ad_reddedilir(self):
        kural = self._yapi_kurali()
        kural["gostergeler"] = {"y_yon": {"tur": "ema", "periyot": 5}, **kural["gostergeler"]}
        with self.assertRaises(k.KuralHatasi) as baglam:
            k.kural_dogrula(kural)
        self.assertIn("y_yon", str(baglam.exception))


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
