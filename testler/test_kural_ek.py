"""Panel sınaması için kural motoruna eklenenler (12 Ekim 2026): başka paritenin göstergesi,
göstergede kaydırma, ortanca hacim, fonlama göstergesi, ATR'ye bağlı stop, portföy ve bilgi alanları."""

import copy
import unittest

import numpy as np
import pandas as pd

from karabasan import benzetim as b
from karabasan import gostergeler as g
from karabasan import kural as k
from testler.veri import duz_mumlar, yapay_mumlar


def temel(**ek):
    kural = {
        "kod": "T", "ad": "Deneme", "yon": "alim", "zaman_dilimi": "15m",
        "gostergeler": {"btc": {"tur": "degisim_yuzde", "kaynak": "kapanis", "periyot": 4, "parite": "BTC"}},
        "giris": {"sol": "btc", "islem": "<=", "sag": -2.0},
        "cikis": {"kar_hedefi_yuzde": 2.0, "zarar_durdur_yuzde": 2.0},
    }
    kural.update(ek)
    return kural


def fonlama_tablosu(zamanlar, oranlar):
    return pd.DataFrame({"date": pd.to_datetime(zamanlar, utc=True), "oran_yuzde": oranlar})


class ReferansParite(unittest.TestCase):
    def test_btc_gostergesi_btc_mumlarindan_hesaplanir(self):
        coin = yapay_mumlar(300, dilim_dk=15, tohum=1)
        btc = yapay_mumlar(300, dilim_dk=15, tohum=2, fiyat=60000)
        tablo = k.gosterge_ekle(coin, temel(), {"BTC@15m": btc})
        beklenen = g.degisim_yuzde(btc["close"], 4)
        np.testing.assert_allclose(tablo["btc"].to_numpy()[10:], beklenen.to_numpy()[10:])

    def test_referans_yoksa_gosterge_bos_sinyal_yok(self):
        coin = yapay_mumlar(300, dilim_dk=15, tohum=1)
        tablo = k.sinyal_uret(coin, temel())
        self.assertTrue(tablo["btc"].isna().all())
        self.assertFalse(tablo["sinyal"].any())

    def test_referans_istekleri_ve_ek_veri(self):
        kural = temel()
        kural["gostergeler"]["btc1s"] = {"tur": "rsi", "periyot": 14, "parite": "BTC", "dilim": "1h"}
        self.assertEqual(k.referans_istekleri(kural), [("BTC", "15m"), ("BTC", "1h")])
        ek, eksik = k.ek_veri_topla(kural, lambda d: None, lambda p, d: yapay_mumlar(10) if d == "15m" else None)
        self.assertEqual(set(ek), {"BTC@15m"})
        self.assertEqual(eksik, ["BTC@1h"])
        self.assertIn("BTC@1h", k.gereken_ek_mum(kural))

    def test_ust_dilim_referans_gelecege_bakmaz(self):
        kural = temel()
        kural["gostergeler"]["btc1s"] = {"tur": "sma", "kaynak": "kapanis", "periyot": 3, "parite": "BTC", "dilim": "1h"}
        coin = yapay_mumlar(400, dilim_dk=15, tohum=1)
        btc = yapay_mumlar(400, dilim_dk=15, tohum=2)
        btc1s = g.ust_dilime_cevir(btc, "15m", "1h")
        tam = k.gosterge_ekle(coin, kural, {"BTC@15m": btc, "BTC@1h": btc1s})
        kesik = k.gosterge_ekle(coin.iloc[:200], kural, {"BTC@15m": btc.iloc[:200],
                                                          "BTC@1h": g.ust_dilime_cevir(btc.iloc[:200], "15m", "1h")})
        pd.testing.assert_series_equal(tam["btc1s"].iloc[:200], kesik["btc1s"], check_names=False)

    def test_gecersiz_parite(self):
        kural = temel()
        kural["gostergeler"]["btc"]["parite"] = "btc/usdt"
        with self.assertRaises(k.KuralHatasi):
            k.kural_dogrula(kural)


class KaydirVeOrtanca(unittest.TestCase):
    def test_gosterge_kendi_diliminde_kaydirilir(self):
        kural = temel(gostergeler={
            "tepe": {"tur": "en_yuksek", "kaynak": "kapanis", "periyot": 2, "dilim": "1d", "kaydir": 1},
            "tepe0": {"tur": "en_yuksek", "kaynak": "kapanis", "periyot": 2, "dilim": "1d"},
        }, giris={"sol": "kapanis", "islem": ">", "sag": "tepe"}, zaman_dilimi="1h")
        df = yapay_mumlar(24 * 10, dilim_dk=60, tohum=3)
        tablo = k.gosterge_ekle(df, kural)
        gunluk = g.ust_dilime_cevir(df, "1h", "1d")
        beklenen = g.ust_dilimden_hizala(g.en_yuksek(gunluk["close"], 2).shift(1), gunluk["date"], df["date"], "1h", "1d")
        pd.testing.assert_series_equal(tablo["tepe"], beklenen, check_names=False)
        self.assertGreater(k.gereken_mum(kural), 0)

    def test_negatif_kaydirma_yok(self):
        kural = temel()
        kural["gostergeler"]["btc"]["kaydir"] = -1
        with self.assertRaises(k.KuralHatasi):
            k.kural_dogrula(kural)

    def test_ortanca_hacim(self):
        kural = temel(gostergeler={"orta": {"tur": "hacim_ortanca", "periyot": 5}},
                      giris={"sol": "hacim", "islem": ">", "sag": "orta"})
        df = yapay_mumlar(50, dilim_dk=15)
        tablo = k.gosterge_ekle(df, kural)
        self.assertAlmostEqual(tablo["orta"].iloc[10], float(np.median(df["volume"].iloc[6:11])))


class Fonlama(unittest.TestCase):
    def kural(self, periyot=2):
        return temel(gostergeler={"fon": {"tur": "fonlama", "periyot": periyot}},
                     giris={"sol": "fon", "islem": ">=", "sag": 0})

    def test_odeme_ancak_gerceklestikten_sonra_gorulur(self):
        df = yapay_mumlar(96, dilim_dk=15, baslangic="2026-01-01")
        fon = fonlama_tablosu(["2025-12-31 16:00", "2026-01-01 00:00", "2026-01-01 08:00", "2026-01-01 16:00"],
                              [0.01, 0.03, -0.05, 0.02])
        tablo = k.gosterge_ekle(df, self.kural(), {"fonlama": fon})
        zaman = pd.to_datetime(df["date"], utc=True)
        deger = dict(zip(zaman, tablo["fon"]))
        self.assertAlmostEqual(deger[pd.Timestamp("2026-01-01 07:45", tz="UTC")], 0.02)    # (0,01 + 0,03) / 2
        self.assertAlmostEqual(deger[pd.Timestamp("2026-01-01 08:00", tz="UTC")], -0.01)   # 08:00 ödemesi artık belli
        self.assertTrue(k.fonlama_gerekli(self.kural()))

    def test_veri_yoksa_bos(self):
        df = yapay_mumlar(50, dilim_dk=15)
        tablo = k.sinyal_uret(df, self.kural())
        self.assertTrue(tablo["fon"].isna().all())
        self.assertFalse(tablo["sinyal"].any())
        _ek, eksik = k.ek_veri_topla(self.kural(), lambda d: None)
        self.assertEqual(eksik, ["fonlama"])

    def test_dogrulama(self):
        for tanim in ({"tur": "fonlama", "periyot": 0}, {"tur": "fonlama", "periyot": 3, "dilim": "1h"},
                      {"tur": "fonlama", "periyot": 3, "parite": "BTC"}):
            with self.subTest(tanim=tanim), self.assertRaises(k.KuralHatasi):
                k.kural_dogrula(temel(gostergeler={"fon": tanim}, giris={"sol": "fon", "islem": ">", "sag": 0}))


class AtrStopu(unittest.TestCase):
    def kural(self):
        kural = temel(gostergeler={}, giris={"sol": "kapanis", "islem": ">", "sag": 0})
        kural["cikis"] = {"kar_hedefi_yuzde": 3.0, "zarar_durdur_yuzde": 3.5,
                          "stop_atr": {"kat": 2, "periyot": 14, "en_az_yuzde": 2.0}}
        return kural

    def test_stop_atrye_gore_kirpilir(self):
        df = yapay_mumlar(300, dilim_dk=15, oynaklik=0.004)
        tablo = k.sinyal_uret(df, self.kural())
        beklenen = (2 * g.atr_yuzde(df, 14)).clip(2.0, 3.5).fillna(3.5)
        np.testing.assert_allclose(tablo["stop_yuzde"].to_numpy(), beklenen.to_numpy())
        self.assertIn("stop 2 x ATR (%2-%3,5)", k.cikis_metni(self.kural()["cikis"]))

    def test_benzetim_islem_basina_stopu_kullanir(self):
        kural = self.kural()
        kural["giris"] = {"sol": "kapanis", "islem": "yukari_keser", "sag": 100.5}
        df = duz_mumlar([(100, 100.2, 99.8, 100)] * 20 + [(100, 100.7, 99.9, 100.6),
                        (100, 100.1, 97.4, 97.5)], dilim_dk=15)
        tablo = k.sinyal_uret(df, kural)
        tablo["stop_yuzde"] = 2.5
        i = b.benzet(df, kural, komisyon_yuzde=0.05, hazir_tablo=tablo)[0]
        self.assertEqual(i["neden"], "zarar_durdur")
        self.assertAlmostEqual(i["cikis_fiyati"], 97.5)
        self.assertAlmostEqual(i["stop_yuzde"], 2.5)

    def test_hatali_stop_atr(self):
        for stop_atr in ({"kat": 0, "en_az_yuzde": 2}, {"kat": 2, "en_az_yuzde": 5}, {"kat": 2},
                         {"kat": 2, "en_az_yuzde": 2, "dilim": "7m"}):
            kural = self.kural()
            kural["cikis"]["stop_atr"] = stop_atr
            with self.subTest(stop_atr=stop_atr), self.assertRaises(k.KuralHatasi):
                k.kural_dogrula(kural)


class PortfoyVeBilgi(unittest.TestCase):
    def test_gecerli_ve_hatali_portfoy(self):
        k.kural_dogrula(temel(portfoy={"en_fazla_pozisyon": 4, "giris_sinirlari": [{"saat": 1, "sayi": 2}],
                                       "seri_stop_muaf": True, "en_az_kayma_yuzde": 0.1}))
        for portfoy in ({"en_fazla_pozisyon": 0}, {"giris_sinirlari": [{"saat": 1}]}, {"bilinmeyen": 1},
                        {"seri_stop_muaf": "evet"}):
            with self.subTest(portfoy=portfoy), self.assertRaises(k.KuralHatasi):
                k.kural_dogrula(temel(portfoy=portfoy))

    def test_bilgi_kosullari(self):
        kural = temel(gostergeler={}, giris={"sol": "kapanis", "islem": ">", "sag": 0},
                      bilgi={"yesil": {"sol": "kapanis", "islem": ">", "sag": "acilis"}})
        df = yapay_mumlar(30, dilim_dk=15)
        seri = k.bilgi_sinyalleri(k.sinyal_uret(df, kural), kural)["yesil"]
        self.assertTrue((seri == (df["close"] > df["open"])).all())
        with self.assertRaises(k.KuralHatasi):
            k.kural_dogrula(temel(bilgi={"x": {"sol": "yok", "islem": ">", "sag": 0}}))


class AdayKurallar(unittest.TestCase):
    KODLAR = ["ZSD", "ZSDF", "ZSDT", "ZSDP", "TRG14", "TRG28", "TRG56", "TRGK14", "TRGK28", "TRGK56"]

    def test_hepsi_gecerli_ve_canli_degil(self):
        from karabasan.botlar import BOTLAR
        canli = {kod for _b, _s, kod, _p in BOTLAR}
        for kod in self.KODLAR:
            with self.subTest(kod=kod):
                kural = k.kural_yukle(kod)
                self.assertNotIn(kod, canli)
                self.assertNotIn(kod, k.tum_kurallar())
                self.assertIsNone(kural.get("giris_limiti"))   # panel: piyasa emri
                c = kural["cikis"]
                tavan = c.get("kar_hedefi_yuzde") or c["iz_suren_stop"]["tetik_yuzde"]
                self.assertLessEqual(c["zarar_durdur_yuzde"], 1.5 * tavan)   # panel: stop <= 1,5 x hedef

    def _veri(self, gun=400):
        coin = yapay_mumlar(96 * gun, dilim_dk=15, tohum=4, oynaklik=0.004)
        btc = yapay_mumlar(96 * gun, dilim_dk=15, tohum=5, oynaklik=0.004, fiyat=60000)
        return coin, btc

    def _ek(self, kural, coin, btc, n=None):
        coin = coin if n is None else coin.iloc[:n]
        btc = btc if n is None else btc.iloc[:n]
        ek = {"BTC@15m": btc, "BTC@1h": g.ust_dilime_cevir(btc, "15m", "1h"),
              "1d": g.ust_dilime_cevir(coin, "15m", "1d"),
              "fonlama": fonlama_tablosu(pd.date_range("2025-12-01", periods=1500, freq="8h"),
                                         np.random.default_rng(1).normal(0.0, 0.02, 1500))}
        return coin, ek

    def test_sinyaller_gelecege_bakmaz(self):
        coin, btc = self._veri(300)
        kesim = 96 * 200
        for kod in ("ZSD", "ZSDF", "ZSDT", "TRG28", "TRGK28"):
            kural = k.kural_yukle(kod)
            veri = coin if kural["zaman_dilimi"] == "15m" else g.ust_dilime_cevir(coin, "15m", "1h")
            ref = btc
            olcek = 1 if kural["zaman_dilimi"] == "15m" else 4
            tam_df, tam_ek = self._ek(kural, veri, ref)
            kes_df, kes_ek = self._ek(kural, veri, ref.iloc[:kesim], kesim // olcek)
            kes_ek["1d"] = g.ust_dilime_cevir(coin.iloc[:kesim], "15m", "1d")
            kes_ek["fonlama"] = tam_ek["fonlama"][tam_ek["fonlama"]["date"] < kes_df["date"].iloc[-1]]
            tam = k.sinyal_uret(tam_df, kural, tam_ek)
            kesik = k.sinyal_uret(kes_df, kural, kes_ek)
            n = len(kesik) - 1   # son mum: günlük mum o an henüz kapanmamış olabilir
            with self.subTest(kod=kod):
                pd.testing.assert_series_equal(tam["sinyal"].iloc[:n], kesik["sinyal"].iloc[:n], check_names=False)
                pd.testing.assert_series_equal(tam["cikis_sinyal"].iloc[:n], kesik["cikis_sinyal"].iloc[:n],
                                               check_names=False)
                if "stop_yuzde" in tam:
                    pd.testing.assert_series_equal(tam["stop_yuzde"].iloc[:n], kesik["stop_yuzde"].iloc[:n],
                                                   check_names=False)

    def test_zsd_sok_ve_onay_mumunda_sinyal_verir(self):
        # 200 sakin mum, sonra şok (coin ve BTC birlikte düşer, coinde hacim patlar), sonra onay mumu.
        sakin = [(100, 100.2, 99.8, 100)] * 200
        coin = duz_mumlar(sakin + [(100, 100, 99.0, 99.2), (99.2, 99.3, 97.0, 97.2), (97.2, 99.6, 97.1, 99.5),
                                   (99.5, 99.6, 99.4, 99.5)], dilim_dk=15)
        coin.loc[201, "volume"] = 1000.0
        btc = duz_mumlar(sakin + [(100, 100, 99, 99.5), (99.5, 99.5, 97.5, 97.7), (97.7, 98, 97.6, 97.9),
                                  (97.9, 98, 97.8, 97.9)], dilim_dk=15)
        kural = k.kural_yukle("ZSD")
        tablo = k.sinyal_uret(coin, kural, {"BTC@15m": btc})
        self.assertEqual(list(np.flatnonzero(tablo["sinyal"].to_numpy())), [202])
        plasebo = k.sinyal_uret(coin, k.kural_yukle("ZSDP"))
        self.assertTrue(plasebo["sinyal"].iloc[202])


class AdayIslemler(unittest.TestCase):
    def test_kisit_yokken_benzet_ile_ayni(self):
        kural = {"kod": "T", "ad": "Deneme", "yon": "alim", "zaman_dilimi": "15m",
                 "gostergeler": {"r": {"tur": "rsi", "periyot": 4}},
                 "giris": {"sol": "r", "islem": "<", "sag": 25},
                 "cikis": {"kar_hedefi_yuzde": 1.0, "zarar_durdur_yuzde": 1.0, "sure_asimi_dakika": 120,
                           "sinyal": {"sol": "r", "islem": ">", "sag": 80}}}
        df = yapay_mumlar(3000, dilim_dk=15, tohum=9)
        tablo = k.sinyal_uret(df, kural)
        beklenen = b.benzet(df, kural, komisyon_yuzde=0.05, hazir_tablo=tablo)
        adaylar = b.aday_islemler(tablo, kural, 0.05)
        secilen, sonraki = [], 0
        for a in adaylar:
            if a["sinyal_i"] >= sonraki:
                secilen.append({x: v for x, v in a.items() if x not in ("sinyal_i", "sonraki_i")})
                sonraki = a["sonraki_i"]
        self.assertGreater(len(beklenen), 20)
        self.assertEqual(secilen, beklenen)

    def test_mum_basina_kayma(self):
        kural = {"kod": "T", "ad": "Deneme", "yon": "alim", "zaman_dilimi": "15m", "gostergeler": {},
                 "giris": {"sol": "kapanis", "islem": "yukari_keser", "sag": 100.5},
                 "cikis": {"kar_hedefi_yuzde": 5.0, "zarar_durdur_yuzde": 2.0}}
        df = duz_mumlar([(100, 100.2, 99.8, 100)] * 20 + [(100, 100.7, 99.9, 100.6), (100, 100.1, 97.0, 97.5)],
                        dilim_dk=15)
        tablo = k.sinyal_uret(df, kural)
        kayma = np.zeros(len(df))
        kayma[20], kayma[21] = 0.2, 0.3
        a = b.aday_islemler(tablo, kural, 0.05, kayma)[0]
        self.assertAlmostEqual(a["giris_fiyati"], 100 * 1.002)
        self.assertAlmostEqual(a["cikis_fiyati"], 100 * 1.002 * 0.98 * 0.997)
        with self.assertRaises(ValueError):
            b.aday_islemler(tablo, {**kural, "giris_limiti": {"atr_kat": 0.5, "en_az_yuzde": 0.1,
                                                              "en_fazla_yuzde": 0.6, "sure_dakika": 15}}, 0.05)


if __name__ == "__main__":
    unittest.main()
