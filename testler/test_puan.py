import unittest
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from karabasan import puan as p
from testler.veri import yapay_mumlar

T0 = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)


def an(dakika):
    return T0 + timedelta(minutes=dakika)


class Bilesenler(unittest.TestCase):
    def test_agirliklar_toplami_bir(self):
        self.assertAlmostEqual(sum(p.AGIRLIKLAR.values()), 1.0)

    def test_btc_trend_yukselen_ve_dusen(self):
        artan_4s = pd.Series(np.linspace(100, 200, 300))
        # 1 saatlik eğim 6 saatte %1'in üstünde: eğim puanı tam (30)
        hizli_artan_1s = pd.Series(np.linspace(150, 200, 100))
        self.assertEqual(p.btc_trend_puani(artan_4s, hizli_artan_1s), 100.0)
        # Yavaş yükseliş: konum puanları tam (70), eğim puanı kısmi
        yavas_artan_1s = pd.Series(np.linspace(190, 200, 100))
        yavas = p.btc_trend_puani(artan_4s, yavas_artan_1s)
        self.assertTrue(85.0 < yavas < 100.0, yavas)
        azalan_4s = pd.Series(np.linspace(200, 100, 300))
        azalan_1s = pd.Series(np.linspace(150, 100, 100))
        self.assertEqual(p.btc_trend_puani(azalan_4s, azalan_1s), 0.0)

    def test_btc_trend_veri_azsa_yok(self):
        self.assertIsNone(p.btc_trend_puani(pd.Series([1.0] * 50), pd.Series([1.0] * 50)))

    def test_sakinlik(self):
        sakin = yapay_mumlar(800, dilim_dk=60, oynaklik=0.003, tohum=2)
        puan_sakin = p.btc_sakinlik_puani(sakin)
        self.assertIsNotNone(puan_sakin)
        # Son 20 saatte oynaklığı beş katına çıkar
        firtina = sakin.copy()
        orta = (firtina["high"] + firtina["low"]) / 2
        son = firtina.index[-20:]
        firtina.loc[son, "high"] = orta[son] * 1.04
        firtina.loc[son, "low"] = orta[son] * 0.96
        puan_firtina = p.btc_sakinlik_puani(firtina)
        self.assertLess(puan_firtina, puan_sakin)
        self.assertEqual(puan_firtina, 0.0)
        self.assertIsNone(p.btc_sakinlik_puani(sakin.iloc[:100]))

    def test_altcoin_akisi_matrisi(self):
        beklenen = [
            (3.0, -0.5, 100.0), (0.2, -0.5, 85.0), (3.0, 0.5, 55.0),
            (0.2, 0.5, 30.0), (-3.0, -0.5, 15.0), (-3.0, 0.5, 0.0),
        ]
        for btc, dominans, puan in beklenen:
            with self.subTest(btc=btc, dominans=dominans):
                self.assertEqual(p.altcoin_akisi_puani(btc, dominans, True)[0], puan)

    def test_altcoin_akisi_total2_cezasi(self):
        self.assertEqual(p.altcoin_akisi_puani(3.0, -0.5, False)[0], 80.0)
        self.assertEqual(p.altcoin_akisi_puani(-3.0, 0.5, False)[0], 0.0)  # sıfırın altına inmez
        self.assertIsNone(p.altcoin_akisi_puani(None, 0.5, True)[0])

    def test_genislik(self):
        self.assertEqual(p.genislik_puani(30, 60), 50.0)
        self.assertIsNone(p.genislik_puani(0, 0))

    def test_makro(self):
        self.assertIsNone(p.makro_puani(None))
        self.assertEqual(p.makro_puani(0.0), 50.0)
        self.assertEqual(p.makro_puani(2.0), 75.0)
        self.assertEqual(p.makro_puani(-2.0), 25.0)
        # Altın yükselirken NASDAQ düşüyorsa riskten kaçış cezası
        self.assertEqual(p.makro_puani(-1.0, altin_degisim_yuzde=1.5), 0.0)
        self.assertEqual(p.makro_puani(-1.0, altin_degisim_yuzde=0.2), 25.0)


class ToplamPuan(unittest.TestCase):
    def test_tam_puan(self):
        puan, _ = p.karabasan_puani({k: 100 for k in "TSAGM"})
        self.assertEqual(puan, 100.0)

    def test_formul(self):
        puan, agirlik = p.karabasan_puani({"T": 80, "S": 60, "A": 40, "G": 50, "M": 70})
        self.assertAlmostEqual(puan, 0.30 * 80 + 0.20 * 60 + 0.25 * 40 + 0.15 * 50 + 0.10 * 70)
        self.assertAlmostEqual(sum(agirlik.values()), 1.0)

    def test_eksik_bilesenin_agirligi_dagitilir(self):
        puan, agirlik = p.karabasan_puani({"T": 80, "S": 60, "A": 40, "G": 50, "M": None})
        self.assertNotIn("M", agirlik)
        self.assertAlmostEqual(sum(agirlik.values()), 1.0)
        beklenen = (0.30 * 80 + 0.20 * 60 + 0.25 * 40 + 0.15 * 50) / 0.90
        self.assertAlmostEqual(puan, round(beklenen, 1))

    def test_btc_trendi_yoksa_puan_yok(self):
        self.assertIsNone(p.karabasan_puani({"T": None, "S": 60})[0])

    def test_puandan_durum(self):
        self.assertEqual(p.puandan_durum(65), "YESIL")
        self.assertEqual(p.puandan_durum(64.9), "SARI")
        self.assertEqual(p.puandan_durum(45), "SARI")
        self.assertEqual(p.puandan_durum(44.9), "KIRMIZI")


class Vetolar(unittest.TestCase):
    def test_veto_yok(self):
        self.assertEqual(p.veto_kontrol(T0, {"btc_15dk_degisim_yuzde": -0.5}), [])

    def test_btc_ani_dusus(self):
        v = p.veto_kontrol(T0, {"btc_15dk_degisim_yuzde": -1.8})
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0].gerekce, "BTC 15 dakikada %1,8 düştü")
        self.assertEqual(v[0].bitis, an(120))
        self.assertEqual(len(p.veto_kontrol(T0, {"btc_1s_degisim_yuzde": -3.0})), 1)

    def test_gunluk_zarar_gun_sonuna_kadar(self):
        v = p.veto_kontrol(T0, {"gunluk_zarar_doldu": True})[0]
        self.assertEqual(v.bitis, datetime(2026, 1, 11, 0, 0, tzinfo=timezone.utc))

    def test_diger_vetolar(self):
        self.assertEqual(p.veto_kontrol(T0, {"art_arda_stop": 4})[0].bitis, an(60))
        self.assertEqual(p.veto_kontrol(T0, {"art_arda_stop": 3}), [])
        self.assertIsNone(p.veto_kontrol(T0, {"veri_yasi_saniye": 45})[0].bitis)
        self.assertEqual(p.veto_kontrol(T0, {"veri_yasi_saniye": 10}), [])
        self.assertEqual(len(p.veto_kontrol(T0, {"sabit_coin_fiyati": 0.993})), 1)
        self.assertEqual(p.veto_kontrol(T0, {"sabit_coin_fiyati": 0.999}), [])
        self.assertEqual(len(p.veto_kontrol(T0, {"nasdaq_seans_degisim_yuzde": -2.1})), 1)
        self.assertEqual(len(p.veto_kontrol(T0, {"acil_stop": True})), 1)

    def test_takvim_penceresi(self):
        olay = an(20)
        self.assertEqual(len(p.veto_kontrol(T0, {"takvim_olaylari": [olay]})), 1)       # 20 dk önce
        self.assertEqual(p.veto_kontrol(an(-30), {"takvim_olaylari": [olay]}), [])       # 50 dk önce
        self.assertEqual(len(p.veto_kontrol(an(70), {"takvim_olaylari": [olay]})), 1)   # 50 dk sonra
        self.assertEqual(p.veto_kontrol(an(90), {"takvim_olaylari": [olay]}), [])        # 70 dk sonra


class DurumMakinesi(unittest.TestCase):
    def test_acilmasi_yavas(self):
        m = p.DurumMakinesi()
        self.assertEqual(m.durum, "KIRMIZI")
        durumlar = [m.guncelle(an(5 * i), 80, [])["durum"] for i in range(6)]
        # Üç ölçüm sonra Sarı, üç ölçüm daha sonra Yeşil
        self.assertEqual(durumlar, ["KIRMIZI", "KIRMIZI", "SARI", "SARI", "SARI", "YESIL"])

    def test_kapanmasi_hizli(self):
        m = p.DurumMakinesi(durum="YESIL")
        self.assertEqual(m.guncelle(an(0), 30, [])["durum"], "KIRMIZI")

    def test_esik_ustunde_kalmazsa_sayac_sifirlanir(self):
        m = p.DurumMakinesi(durum="SARI")
        m.guncelle(an(0), 70, [])
        m.guncelle(an(5), 70, [])
        m.guncelle(an(10), 60, [])   # eşiğin altına indi: sayaç sıfırlanır
        m.guncelle(an(15), 70, [])
        self.assertEqual(m.guncelle(an(20), 70, [])["durum"], "SARI")
        self.assertEqual(m.guncelle(an(25), 70, [])["durum"], "YESIL")

    def test_sureli_veto_suresi_dolana_kadar_siyah(self):
        m = p.DurumMakinesi(durum="YESIL")
        veto = p.veto_kontrol(an(0), {"btc_15dk_degisim_yuzde": -2.0})
        kayit = m.guncelle(an(0), 80, veto)
        self.assertEqual(kayit["durum"], "SIYAH")
        self.assertIn("BTC 15 dakikada", kayit["veto"])
        # Koşul geçti ama 2 saat dolmadı: hâlâ Siyah
        self.assertEqual(m.guncelle(an(60), 80, [])["durum"], "SIYAH")
        self.assertEqual(m.guncelle(an(119), 80, [])["durum"], "SIYAH")
        # Süre doldu: Kırmızı'dan başlar, yavaş açılır
        self.assertEqual(m.guncelle(an(120), 80, [])["durum"], "KIRMIZI")
        self.assertEqual(m.guncelle(an(125), 80, [])["durum"], "KIRMIZI")
        self.assertEqual(m.guncelle(an(130), 80, [])["durum"], "SARI")

    def test_suresiz_veto_kosul_duzelince_kalkar(self):
        m = p.DurumMakinesi(durum="SARI")
        veto = p.veto_kontrol(an(0), {"veri_yasi_saniye": 90})
        self.assertEqual(m.guncelle(an(0), 60, veto)["durum"], "SIYAH")
        self.assertEqual(m.guncelle(an(1), 60, [])["durum"], "KIRMIZI")

    def test_puan_yoksa_siyah(self):
        m = p.DurumMakinesi(durum="YESIL")
        kayit = m.guncelle(an(0), None, [])
        self.assertEqual(kayit["durum"], "SIYAH")
        self.assertIn("veri eksik", kayit["veto"])

    def test_yeni_veto_sureyi_uzatir(self):
        m = p.DurumMakinesi(durum="YESIL")
        m.guncelle(an(0), 80, p.veto_kontrol(an(0), {"btc_15dk_degisim_yuzde": -2.0}))
        m.guncelle(an(90), 80, p.veto_kontrol(an(90), {"btc_15dk_degisim_yuzde": -2.0}))
        self.assertEqual(m.guncelle(an(150), 80, [])["durum"], "SIYAH")   # ikinci veto 210. dakikaya kadar
        self.assertEqual(m.guncelle(an(210), 80, [])["durum"], "KIRMIZI")

    def test_gerekce_metni(self):
        metin = p.gerekce_metni(72.5, "YESIL", {"T": 100, "S": 60, "A": 55, "G": 70, "M": None})
        self.assertTrue(metin.startswith("Yeşil: puan 72,5"))
        self.assertIn("BTC trendi 100", metin)
        self.assertNotIn("Makro", metin)
        siyah = p.gerekce_metni(80, "SIYAH", {}, veto="BTC 15 dakikada %1,8 düştü")
        self.assertEqual(siyah, "Siyah: BTC 15 dakikada %1,8 düştü. Yeni alım yok.")

    def test_durum_ayarlari(self):
        self.assertEqual(p.durum_ayarlari("YESIL")["pozisyon_carpani"], 1.0)
        self.assertEqual(p.durum_ayarlari("SARI")["pozisyon_carpani"], 0.5)
        self.assertFalse(p.durum_ayarlari("KIRMIZI")["yeni_alim"])
        self.assertFalse(p.durum_ayarlari("SIYAH")["yeni_alim"])


if __name__ == "__main__":
    unittest.main()
