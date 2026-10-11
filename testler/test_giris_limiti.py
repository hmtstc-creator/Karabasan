"""Limitli giriş (12 Ekim 2026, Ahmet'in isteği): sinyalden sonra daha iyi fiyattan gir.

Alımda fiyatın biraz altına, açığa satışta biraz üstüne limit emir konur; uzaklık
oynaklığa (ATR) göre ayarlanır, emir süresinde dolmazsa iptal edilir.
"""

import copy
import unittest
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from karabasan import benzetim as b
from karabasan import gostergeler as g
from karabasan import kural as k
from testler.test_motor_baglantisi import strateji_modulu
from testler.veri import duz_mumlar, yapay_mumlar

CANLI = ("SM", "SMK", "SMD", "SMDK", "SNIPER")


def deneme_kurali(yon="alim", uzaklik=0.5, sure=15, hedef=1.0, stop=1.0):
    """Kapanış 100,5'i yukarı (açığa satışta 99,5'i aşağı) kesince sinyal veren basit kural."""
    alim = yon == "alim"
    return {
        "kod": "T", "ad": "Deneme kuralı", "yon": yon, "zaman_dilimi": "5m",
        "gostergeler": {"k1": {"tur": "sma", "periyot": 1}},
        "giris": {"sol": "kapanis", "islem": "yukari_keser" if alim else "asagi_keser",
                  "sag": 100.5 if alim else 99.5},
        "giris_limiti": {"atr_kat": 0.0, "en_az_yuzde": uzaklik, "en_fazla_yuzde": uzaklik,
                         "sure_dakika": sure},
        "cikis": {"kar_hedefi_yuzde": hedef, "zarar_durdur_yuzde": stop, "sure_asimi_dakika": 60},
    }


class LimitUzakligi(unittest.TestCase):
    def test_atr_ile_olceklenir_ve_kirpilir(self):
        df = yapay_mumlar(3000, tohum=2, oynaklik=0.004)
        kural = k.kural_yukle("SNIPER")
        limit = kural["giris_limiti"]
        uzaklik = k.giris_limit_yuzde(df, kural)
        beklenen = (limit["atr_kat"] * g.atr_yuzde(df, 14)).clip(limit["en_az_yuzde"], limit["en_fazla_yuzde"])
        np.testing.assert_allclose(uzaklik.iloc[50:].to_numpy(), beklenen.iloc[50:].to_numpy())
        self.assertTrue(((uzaklik >= limit["en_az_yuzde"]) & (uzaklik <= limit["en_fazla_yuzde"])).all())
        self.assertFalse(uzaklik.isna().any())

    def test_limitsiz_kuralda_sifir(self):
        df = yapay_mumlar(500, tohum=2)
        self.assertTrue((k.giris_limit_yuzde(df, k.kural_yukle("S1")) == 0).all())

    def test_gelecege_bakmaz(self):
        df = yapay_mumlar(3000, tohum=5, oynaklik=0.004)
        kural = k.kural_yukle("SM")
        tam = k.giris_limit_yuzde(df, kural)
        for kesim in (300, 1500, 2999):
            np.testing.assert_array_equal(tam.to_numpy()[:kesim], k.giris_limit_yuzde(df.iloc[:kesim], kural).to_numpy())

    def test_limit_fiyati(self):
        self.assertAlmostEqual(k.limit_fiyati(100.0, 0.5, True), 99.5)
        self.assertAlmostEqual(k.limit_fiyati(100.0, 0.5, False), 100.5)

    def test_dogrulama(self):
        k.kural_dogrula(deneme_kurali())
        for alan, deger in (("atr_kat", -0.1), ("atr_kat", "0.5"), ("en_az_yuzde", 2.5),
                            ("en_fazla_yuzde", 0), ("sure_dakika", 12), ("sure_dakika", 0),
                            ("sure_dakika", 245), ("sure_dakika", 15.0)):
            kural = deneme_kurali()
            kural["giris_limiti"][alan] = deger
            with self.subTest(alan=alan, deger=deger), self.assertRaises(k.KuralHatasi):
                k.kural_dogrula(kural)
        kural = deneme_kurali()
        kural["giris_limiti"].update(en_az_yuzde=0.7, en_fazla_yuzde=0.6)
        with self.assertRaises(k.KuralHatasi):
            k.kural_dogrula(kural)
        kural["giris_limiti"] = 0.5
        with self.assertRaises(k.KuralHatasi):
            k.kural_dogrula(kural)

    def test_canli_kurallarin_hepsi_limitle_girer(self):
        for kod in CANLI:
            limit = k.kural_yukle(kod)["giris_limiti"]
            self.assertEqual(limit, {"atr_kat": 0.5, "en_az_yuzde": 0.1, "en_fazla_yuzde": 0.6,
                                     "sure_dakika": 15}, kod)


def mumlar(fiyatlar):
    """(açılış, yüksek, düşük, kapanış) listesinin başına 20 sakin mum ekler."""
    return duz_mumlar([(100, 100.2, 99.8, 100)] * 20 + fiyatlar)


class LimitBenzetimi(unittest.TestCase):
    def test_ucuncu_mumda_dolar(self):
        # 20: sinyal (kapanış 100,6). 21: açılış 100,6 -> limit 100,097. 21-22 inmez, 23 iner.
        df = mumlar([(100, 100.7, 99.9, 100.6), (100.6, 100.8, 100.3, 100.5),
                     (100.5, 100.7, 100.2, 100.4), (100.4, 100.5, 100.0, 100.3),
                     (100.3, 101.5, 100.2, 101.4), (101.4, 101.5, 101.0, 101.2)])
        islemler = b.benzet(df, deneme_kurali(), komisyon_yuzde=0.05)
        self.assertEqual(len(islemler), 1)
        i = islemler[0]
        self.assertAlmostEqual(i["giris_fiyati"], 100.6 * 0.995)
        # Açılış anı emrin konduğu mum (hazır motor da öyle kaydeder), dolduğu mum değil.
        self.assertEqual(i["giris_zamani"], df["date"].iloc[21])
        self.assertEqual(i["neden"], "kar_hedefi")               # 24. mumda %1 hedef
        self.assertEqual(i["cikis_zamani"], df["date"].iloc[25])

    def test_sure_asimi_emrin_kondugu_andan_sayilir(self):
        # Emir 21. mumda konur, 23. mumda dolar; 60 dk süre 21. mumdan sayılır (motor gibi).
        df = mumlar([(100, 100.7, 99.9, 100.6), (100.6, 100.8, 100.3, 100.5),
                     (100.5, 100.7, 100.2, 100.4), (100.4, 100.5, 100.0, 100.3)]
                    + [(100.3, 100.5, 100.2, 100.3)] * 15)
        i = b.benzet(df, deneme_kurali())[0]
        self.assertEqual(i["neden"], "sure_asimi")
        self.assertEqual(i["giris_zamani"], df["date"].iloc[21])
        self.assertEqual(i["cikis_zamani"] - i["giris_zamani"], pd.Timedelta(minutes=60))

    def test_suresinde_dolmazsa_islem_yok(self):
        df = mumlar([(100, 100.7, 99.9, 100.6)] + [(100.6, 101.5, 100.3, 101.2)] * 10)
        self.assertEqual(b.benzet(df, deneme_kurali()), [])

    def test_iptalden_sonra_yeni_sinyal_yeni_emir(self):
        # İlk emir dolmaz (3 mum); sonra fiyat 100,5'in altına inip yeniden keser -> ikinci emir dolar.
        df = mumlar([(100, 100.7, 99.9, 100.6)] + [(100.6, 101.0, 100.4, 100.8)] * 3
                    + [(100.8, 100.8, 100.2, 100.3), (100.3, 100.7, 100.2, 100.6),
                       (100.6, 100.6, 99.9, 100.1), (100.1, 100.3, 99.0, 99.2)])
        islemler = b.benzet(df, deneme_kurali())
        self.assertEqual(len(islemler), 1)
        self.assertEqual(islemler[0]["giris_zamani"], df["date"].iloc[26])   # emir de dolum da 26. mumda
        self.assertEqual(islemler[0]["neden"], "zarar_durdur")

    def test_doldugu_mumda_hedef_sayilmaz_stop_sayilir(self):
        # Dolduğu mumun tepesi hedefin üstünde ama sıra belli değil: hedef sayılmaz.
        df = mumlar([(100, 100.7, 99.9, 100.6), (100.6, 102.0, 100.0, 100.5),
                     (100.5, 100.6, 100.4, 100.5)] + [(100.5, 100.6, 100.4, 100.5)] * 12)
        islemler = b.benzet(df, deneme_kurali())
        self.assertEqual(islemler[0]["neden"], "sure_asimi")
        # Aynı mumda stop seviyesine de inerse stop sayılır (kötümser).
        df = mumlar([(100, 100.7, 99.9, 100.6), (100.6, 102.0, 98.9, 100.5)] + [(100.5, 100.6, 100.4, 100.5)] * 3)
        self.assertEqual(b.benzet(df, deneme_kurali())[0]["neden"], "zarar_durdur")

    def test_aciga_satista_ustten_satar(self):
        df = mumlar([(100, 100.1, 99.3, 99.4), (99.4, 99.7, 99.2, 99.5),
                     (99.5, 99.95, 99.4, 99.9), (99.9, 99.9, 98.5, 98.6), (98.6, 98.7, 98.4, 98.5)])
        islemler = b.benzet(df, deneme_kurali(yon="aciga_satis"), komisyon_yuzde=0.05)
        self.assertEqual(len(islemler), 1)
        self.assertAlmostEqual(islemler[0]["giris_fiyati"], 99.4 * 1.005)
        self.assertEqual(islemler[0]["giris_zamani"], df["date"].iloc[21])
        self.assertEqual(islemler[0]["neden"], "kar_hedefi")

    def test_limitsiz_kural_eskisi_gibi(self):
        kural = deneme_kurali()
        del kural["giris_limiti"]
        df = mumlar([(100, 100.7, 99.9, 100.6), (100.6, 100.8, 100.3, 100.5)] + [(100.5, 100.6, 100.4, 100.5)] * 12)
        i = b.benzet(df, kural)[0]
        self.assertEqual(i["giris_fiyati"], 100.6)
        self.assertEqual(i["giris_zamani"], df["date"].iloc[21])


class SahteSaglayici:
    def __init__(self, tablo=None, hata=False):
        self.tablo, self.hata = tablo, hata

    def get_analyzed_dataframe(self, pair, timeframe):
        if self.hata:
            raise RuntimeError("tablo yok")
        return self.tablo, None


class MotorLimitFiyati(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modul = strateji_modulu()

    def tablo(self):
        tarih = pd.date_range("2026-10-12 10:00", periods=4, freq="5min", tz="UTC")
        return pd.DataFrame({"date": tarih, "giris_limit_yuzde": [0.2, 0.3, 0.4, 0.5]})

    def fiyat(self, sinif, saglayici, zaman, side="long"):
        s = getattr(self.modul, sinif)()
        s.dp = saglayici
        return s.custom_entry_price("ETH/USDT:USDT", None, zaman, 100.0, None, side)

    def test_sinyal_mumunun_uzakligi_kullanilir(self):
        # Giriş 10:15 mumunun içinde: sinyal mumu 10:10 (0,4), 10:15 satırı kullanılmaz.
        zaman = datetime(2026, 10, 12, 10, 15, 3, tzinfo=timezone.utc)
        self.assertAlmostEqual(self.fiyat("SMVadeli", SahteSaglayici(self.tablo()), zaman), 99.6)
        self.assertAlmostEqual(self.fiyat("SMKVadeli", SahteSaglayici(self.tablo()), zaman, "short"), 100.4)

    def test_tablo_yoksa_en_kucuk_uzaklik(self):
        zaman = datetime(2026, 10, 12, 10, 15, tzinfo=timezone.utc)
        with self.assertLogs(level="WARNING"):
            self.assertAlmostEqual(self.fiyat("SniperVadeli", SahteSaglayici(hata=True), zaman), 99.9)
        bos = SahteSaglayici(self.tablo())
        self.assertAlmostEqual(self.fiyat("SniperVadeli", bos, datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)), 99.9)

    def test_motor_tablosu_uzakligi_tasir(self):
        df = yapay_mumlar(3000, tohum=4, oynaklik=0.003)
        s = self.modul.SniperVadeli()
        tablo = s.populate_indicators(df.copy(), {"pair": "ETH/USDT:USDT"})
        tablo = s.populate_entry_trend(tablo, {"pair": "ETH/USDT:USDT"})
        np.testing.assert_allclose(tablo["giris_limit_yuzde"].to_numpy(),
                                   k.giris_limit_yuzde(df, k.kural_yukle("SNIPER")).to_numpy())


class KuralRsiSinirlari(unittest.TestCase):
    """12 Ekim 2026: RSI sınırları 70 / 30'dan 80 / 20'ye; 15 dakikalık RSI'a sınır."""

    def test_sinirlar(self):
        def esikler(kod):
            kural = k.kural_yukle(kod)
            return {(c["sol"], c["islem"]): c["sag"] for c in kural["giris"]["hepsi"]
                    if isinstance(c.get("sag"), (int, float)) and str(c.get("sol", "")).startswith("rsi")}

        for kod in ("SM", "SMD"):
            self.assertEqual(esikler(kod), {("rsi14_1s", "<"): 80, ("rsi14", ">"): 50, ("rsi14", "<"): 80,
                                            ("rsi14_15", "<"): 65}, kod)
        for kod in ("SMK", "SMDK"):
            self.assertEqual(esikler(kod), {("rsi14_1s", ">"): 20, ("rsi14", "<"): 50, ("rsi14", ">"): 20,
                                            ("rsi14_15", ">"): 35}, kod)
        sniper = k.kural_yukle("SNIPER")["giris"]["hepsi"]
        self.assertIn({"sol": "rsi14_15", "islem": "<", "sag": 50}, sniper)
        self.assertIn({"sol": "rsi14", "islem": "<", "sag": 80}, sniper)
        for kod in CANLI:
            yon = ">" if k.kural_yukle(kod)["yon"] == "alim" else "<"
            self.assertIn({"sol": "rsi14", "islem": yon, "sag": {"ad": "rsi14", "kaydir": 3}},
                          k.kural_yukle(kod)["giris"]["hepsi"], kod)

    def test_sinyaller_gelecege_bakmaz(self):
        df = yapay_mumlar(60 * 288, tohum=11, oynaklik=0.003)
        gunluk = g.ust_dilime_cevir(df, "5m", "1d")
        for kod in CANLI:
            kural = k.kural_yukle(kod)
            ek = {"1d": gunluk} if k.borsa_dilimleri(kural) else None
            tam = k.sinyal_uret(df, kural, ek)["sinyal"].to_numpy()
            kesim = 50 * 288
            kismi = k.sinyal_uret(df.iloc[:kesim], kural,
                                  {"1d": gunluk[gunluk["date"] < df["date"].iloc[kesim]]} if ek else None)
            np.testing.assert_array_equal(tam[:kesim], kismi["sinyal"].to_numpy(), err_msg=kod)


if __name__ == "__main__":
    unittest.main()
