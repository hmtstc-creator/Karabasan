"""Karabasan'ın geçmişe dönük ölçümü: geleceğe bakmıyor mu, etiketler doğru mu?"""

import unittest

import pandas as pd

from karabasan import gecmis_olcum as go
from karabasan import puan as p
from testler.veri import yapay_mumlar

GUN = 75
ADET = GUN * 288


def _mumlar(adet=ADET, egim=0.0):
    return {
        "BTC": yapay_mumlar(adet, tohum=11, fiyat=60000.0, oynaklik=0.0015, egim=egim),
        "ETH": yapay_mumlar(adet, tohum=12, fiyat=2500.0, oynaklik=0.002, egim=egim),
        "SOL": yapay_mumlar(adet, tohum=13, fiyat=150.0, oynaklik=0.003, egim=egim),
    }


class GecmisOlcumTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mumlar = _mumlar()
        cls.gecmis = go.karabasan_gecmisi(cls.mumlar)

    def test_sutunlar_ve_degerler(self):
        g = self.gecmis
        self.assertEqual(list(g.columns), ["zaman", "puan", "durum", "T", "S", "A", "G", "veto"])
        self.assertGreater(len(g), 288 * 20)
        self.assertTrue(set(g["durum"]) <= {"YESIL", "SARI", "KIRMIZI", "SIYAH"})
        self.assertTrue(g["puan"].dropna().between(0, 100).all())
        self.assertTrue(g["zaman"].is_monotonic_increasing)

    def test_trend_icin_yeterli_gecmis_olmadan_puan_uretilmez(self):
        # T için 200 kapanmış 4 saatlik mum gerekir: ilk 33 gün ölçüm dışıdır.
        ilk = self.gecmis["zaman"].iloc[0]
        baslangic = pd.Timestamp(self.mumlar["BTC"]["date"].iloc[0])
        self.assertGreaterEqual(ilk - baslangic, pd.Timedelta(hours=800))

    def test_gelecege_bakmaz(self):
        """Verinin sonu kesilince, kalan dönemdeki puan ve durumlar değişmemeli."""
        kesim = ADET - 288 * 6 - 37  # son 6 günü ve yarım bir saati at
        kisa = {ad: df.iloc[:kesim].copy() for ad, df in self.mumlar.items()}
        kisa_gecmis = go.karabasan_gecmisi(kisa)
        tam = self.gecmis[self.gecmis["zaman"] <= kisa_gecmis["zaman"].iloc[-1]].reset_index(drop=True)
        self.assertEqual(len(tam), len(kisa_gecmis))
        self.assertTrue((tam["zaman"] == kisa_gecmis["zaman"]).all())
        self.assertEqual(list(tam["durum"]), list(kisa_gecmis["durum"]))
        pd.testing.assert_series_equal(tam["puan"], kisa_gecmis["puan"], check_exact=False, atol=1e-9)
        for sutun in ("T", "S", "A", "G"):
            pd.testing.assert_series_equal(tam[sutun], kisa_gecmis[sutun], check_exact=False,
                                           atol=1e-9, check_dtype=False)

    def test_gelecekteki_fiyat_degisince_gecmis_degismez(self):
        """Son günün fiyatları bozulursa önceki günlerin ölçümü aynı kalmalı."""
        bozuk = {ad: df.copy() for ad, df in self.mumlar.items()}
        sinir = ADET - 288
        for df in bozuk.values():
            for sutun in ("open", "high", "low", "close"):
                df.loc[df.index >= sinir, sutun] = df.loc[df.index >= sinir, sutun] * 0.7
        bozuk_gecmis = go.karabasan_gecmisi(bozuk)
        sinir_ani = pd.Timestamp(self.mumlar["BTC"]["date"].iloc[sinir])
        once_tam = self.gecmis[self.gecmis["zaman"] <= sinir_ani]
        once_bozuk = bozuk_gecmis[bozuk_gecmis["zaman"] <= sinir_ani]
        self.assertEqual(list(once_tam["durum"]), list(once_bozuk["durum"]))
        self.assertEqual(list(once_tam["puan"]), list(once_bozuk["puan"]))
        # Çöküşün kendisi ise görülmeli: sonraki dönemde Siyah (veto) var.
        sonra = bozuk_gecmis[bozuk_gecmis["zaman"] > sinir_ani]
        self.assertIn("SIYAH", set(sonra["durum"]))

    def test_puan_ayni_formulle_hesaplanir(self):
        satir = self.gecmis.dropna(subset=["S", "A", "G"]).iloc[-1]
        beklenen, _ = p.karabasan_puani({"T": satir["T"], "S": satir["S"], "A": satir["A"],
                                         "G": satir["G"], "M": None})
        self.assertAlmostEqual(satir["puan"], beklenen, places=6)

    def test_iyilesme_yavas_kotulesme_hizli(self):
        """Durum bir üst basamağa ancak üç ölçüm sonra çıkar; hiçbir zaman iki basamak atlamaz."""
        sira = p.DURUM_SIRASI
        durumlar = list(self.gecmis["durum"])
        for once, sonra in zip(durumlar, durumlar[1:]):
            if once != "SIYAH":
                self.assertLessEqual(sira[sonra] - sira[once], 1, (once, sonra))

    def test_btc_olmadan_calismaz(self):
        with self.assertRaises(ValueError):
            go.karabasan_gecmisi({"ETH": self.mumlar["ETH"]})

    def test_yalniz_btc_ile_de_calisir(self):
        yalniz = go.karabasan_gecmisi({"BTC": self.mumlar["BTC"].iloc[: 288 * 40]})
        self.assertGreater(len(yalniz), 0)
        self.assertTrue(yalniz["A"].isna().all())   # altcoin yoksa akış bileşeni yok
        self.assertTrue(yalniz["puan"].notna().all())


class EtiketlemeTesti(unittest.TestCase):
    def setUp(self):
        zaman = pd.date_range("2026-10-01 00:05", periods=6, freq="5min", tz="UTC")
        self.gecmis = pd.DataFrame({
            "zaman": zaman,
            "puan": [70.0, 70.0, 50.0, 30.0, 30.0, None],
            "durum": ["YESIL", "YESIL", "SARI", "KIRMIZI", "KIRMIZI", "SIYAH"],
        })

    def _islem(self, giris, net=1.0):
        giris = pd.Timestamp(giris, tz="UTC")
        return {"giris_zamani": giris, "cikis_zamani": giris + pd.Timedelta(minutes=30),
                "net_yuzde": net, "sure_dakika": 30.0}

    def test_islem_acildigi_andaki_durumu_alir(self):
        islemler = [
            self._islem("2026-10-01 00:05"),      # tam ilk ölçüm anı
            self._islem("2026-10-01 00:12"),      # 00:10 ölçümü geçerli
            self._islem("2026-10-01 00:15"),      # 00:15 ölçümü: Sarı
            self._islem("2026-10-01 00:29"),      # 00:25: Kırmızı
            self._islem("2026-10-01 02:00"),      # son ölçüm: Siyah
        ]
        etiketli = go.islemleri_etiketle(islemler, self.gecmis)
        self.assertEqual([i["karabasan_durumu"] for i in etiketli],
                         ["YESIL", "YESIL", "SARI", "KIRMIZI", "SIYAH"])
        self.assertEqual(etiketli[2]["karabasan_puani"], 50.0)
        self.assertIsNone(etiketli[4]["karabasan_puani"])

    def test_olcumden_onceki_islem_bilinmiyor_olur(self):
        etiketli = go.islemleri_etiketle([self._islem("2026-09-30 23:00")], self.gecmis)
        self.assertEqual(etiketli[0]["karabasan_durumu"], "BILINMIYOR")

    def test_saat_dilimi_olmayan_zaman_utc_sayilir(self):
        islem = self._islem("2026-10-01 00:15")
        islem["giris_zamani"] = islem["giris_zamani"].tz_localize(None)
        self.assertEqual(go.islemleri_etiketle([islem], self.gecmis)[0]["karabasan_durumu"], "SARI")

    def test_duruma_gore_ve_izinli_karne(self):
        islemler = go.islemleri_etiketle([
            self._islem("2026-10-01 00:06", 1.0), self._islem("2026-10-01 00:11", 1.0),
            self._islem("2026-10-01 00:16", -1.0), self._islem("2026-10-01 00:21", -1.0),
            self._islem("2026-10-01 00:26", -1.0),
        ], self.gecmis)
        karne = go.duruma_gore_karne(islemler)
        self.assertEqual(karne["HEPSI"]["islem_sayisi"], 5)
        self.assertEqual(karne["YESIL"]["islem_sayisi"], 2)
        self.assertEqual(karne["YESIL"]["kazanma_orani"], 100.0)
        self.assertEqual(karne["KIRMIZI"]["islem_sayisi"], 2)
        self.assertEqual(karne["SIYAH"]["islem_sayisi"], 0)
        self.assertNotIn("BILINMIYOR", karne)
        izinli = go.izinli_karne(islemler, ["YESIL", "SARI"])
        self.assertEqual(izinli["islem_sayisi"], 3)
        self.assertAlmostEqual(izinli["net_tutar"], 0.5)   # (1 + 1 - 1) * %1 * 50 USDT

    def test_sure_dagilimi_yuzde_toplami_yuz(self):
        dagilim = go.sure_dagilimi(self.gecmis)
        self.assertAlmostEqual(sum(dagilim.values()), 100.0)
        self.assertAlmostEqual(dagilim["YESIL"], 2 / 6 * 100)


if __name__ == "__main__":
    unittest.main()


class RaporTesti(unittest.TestCase):
    """araclar/karabasan_gecmis.py: sahte veriyle baştan sona çalışıyor mu?"""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        from pathlib import Path

        yol = Path(__file__).resolve().parent.parent / "araclar" / "karabasan_gecmis.py"
        tanim = importlib.util.spec_from_file_location("karabasan_gecmis", yol)
        cls.modul = importlib.util.module_from_spec(tanim)
        tanim.loader.exec_module(cls.modul)
        tohum = {"BTC": 21, "ETH": 22, "SOL": 23, "XRP": 24, "DOGE": 25}
        fiyat = {"BTC": 60000.0, "ETH": 2500.0, "SOL": 150.0, "XRP": 0.6, "DOGE": 0.1}
        bes = {c: yapay_mumlar(ADET, tohum=tohum[c], fiyat=fiyat[c], oynaklik=0.003) for c in tohum}

        def yukle(coin, dilim, piyasa):
            if coin == "DOGE" and piyasa == "vadeli":
                return None  # eksik dosya durumunu da sına
            df = bes[coin]
            if dilim == "15m":
                from karabasan import gostergeler as g
                return g.ust_dilime_cevir(df, "5m", "15m")
            return df

        cls.metin, cls.eksik = cls.modul.rapor_uret(yukle=yukle, gun=30)

    def test_her_bot_ve_ozet_var(self):
        from karabasan.botlar import BOTLAR

        for _bot, _sinif, kod, piyasa in BOTLAR:
            self.assertIn(f"{kod} {piyasa}:", self.metin)
        self.assertIn("zarar etmemek için gereken kazanma oranı %", self.metin)
        self.assertIn("ÖZET: süzgeçsiz ile tasarımdaki gibi", self.metin)
        self.assertIn("Zamanın durumlara dağılımı: Yeşil %", self.metin)

    def test_uyarilar_basta_yazar(self):
        self.assertIn("yaklaşık bir kopyasıdır", self.metin)
        self.assertIn("ayarlanmamalıdır", self.metin)

    def test_izinli_durum_isaretlenir(self):
        s1 = self.metin.split("S1 spot:")[1].split("S2 spot:")[0]
        self.assertIn("Yeşil *", s1)
        self.assertNotIn("Sarı *", s1)
        self.assertIn("Yalnız izinli (Yeşil)", s1)
        s1k = self.metin.split("S1K vadeli:")[1].split("S2K vadeli:")[0]
        self.assertIn("Kırmızı *", s1k)
        self.assertIn("coinler: ETH, SOL, XRP, DOGE", s1k)   # vadelide BTC yok

    def test_eksik_dosya_sayilir_ve_bildirilir(self):
        from karabasan.botlar import BOTLAR

        vadeli = sum(1 for b in BOTLAR if b[3] == "vadeli")   # her vadeli stratejide DOGE eksik
        self.assertEqual(self.eksik, vadeli)
        self.assertIn(f"UYARI: {vadeli} veri dosyası bulunamadı", self.metin)

    def test_durumlarin_toplami_hepsine_esit(self):
        import re

        s2 = self.metin.split("S2 spot:")[1].split("S3 spot:")[0]
        sayilar = {}
        for satir in s2.splitlines():
            e = re.match(r"\s+(Yeşil|Sarı|Kırmızı|Siyah|Hepsi)[^\d-]*\s(\d+)\s", satir)
            if e:
                sayilar[e.group(1)] = int(e.group(2))
        self.assertEqual(sayilar["Yeşil"] + sayilar["Sarı"] + sayilar["Kırmızı"] + sayilar["Siyah"],
                         sayilar["Hepsi"])
        self.assertGreater(sayilar["Hepsi"], 0)

    def test_stop_genisligi_bolumu(self):
        import re

        bolum = self.metin.split("STOP GENİŞLİĞİ:")[1]
        self.assertIn("geçmişe ezberdir", bolum)
        s1 = bolum.split("S1 spot:")[1].split("S2 spot:")[0]
        satirlar = [x for x in s1.splitlines() if re.match(r"\s+%", x)]
        self.assertEqual([x.split()[0] for x in satirlar], ["%1", "%1,5", "%2", "%3"])
        self.assertIn("(şimdiki)", satirlar[0])
        self.assertIn("Sonuç: ", s1)
        # Şimdiki stopun satırı, yukarıdaki süzgeçsiz sonuçla aynı işlem sayısını ve neti verir.
        ust = self.metin.split("S1 spot:")[1].split("S2 spot:")[0]
        hepsi = next(x for x in ust.splitlines() if "Hepsi (süzgeçsiz)" in x).split()
        simdiki = satirlar[0].split()
        self.assertEqual(simdiki[2], hepsi[2])        # işlem sayısı
        self.assertEqual(simdiki[4], hepsi[-1])       # net USDT
        # İki yarının toplamı dönemin netine eşittir.
        net, ilk, son = (float(x.replace(",", ".")) for x in simdiki[4:7])
        self.assertAlmostEqual(ilk + son, net, places=1)

    def test_genis_stoplu_kopya_yalniz_stopu_degistirir(self):
        from karabasan.kural import kural_yukle

        kural = kural_yukle("S4")
        kopya = self.modul.genis_stoplu(kural, 1.5)
        self.assertAlmostEqual(kopya["cikis"]["zarar_durdur_yuzde"], 1.2)
        self.assertEqual(kural["cikis"]["zarar_durdur_yuzde"], 0.8)            # asıl kural değişmedi
        self.assertEqual({k: v for k, v in kopya.items() if k != "cikis"},
                         {k: v for k, v in kural.items() if k != "cikis"})
        self.assertEqual(kopya["cikis"]["kar_hedefi_yuzde"], kural["cikis"]["kar_hedefi_yuzde"])

    def test_stop_degerlendirmesi(self):
        def satir(carpan, net, ilk, son):
            return {"carpan": carpan, "net": net, "ilk": ilk, "son": son}

        d = self.modul.stop_degerlendirmesi
        simdiki = satir(1.0, -10.0, -5.0, -5.0)
        self.assertIn("en az 30 stop gerekir", d([simdiki, satir(1.5, 0.0, 0.0, 0.0)], 12, 50.0))
        dar = d([simdiki, satir(1.5, -4.0, -2.0, -2.0), satir(2.0, -12.0, -6.0, -6.0)], 40, 50.0)
        self.assertIn("Stop dar görünüyor: 1,5 kat stop", dar)
        self.assertIn("+6,00 USDT", dar)
        self.assertIn("Yine de sonuç ekside kalıyor.", dar)
        self.assertIn("Stop yerinde", d([simdiki, satir(1.5, -11.0, -5.5, -5.5), satir(2.0, -15.0, -8.0, -7.0)], 40, 50.0))
        # Toplamda iyi ama yalnız ilk yarıda: şans olabilir.
        self.assertIn("Kararsız", d([simdiki, satir(1.5, -4.0, 2.0, -6.0)], 40, 50.0))

    def test_veri_yetmezse_soyler(self):
        kisa = yapay_mumlar(288 * 20, tohum=1)
        metin, eksik = self.modul.rapor_uret(yukle=lambda c, d, p: kisa, gun=30)
        self.assertIn("yeterli geçmiş yok", metin)
        self.assertGreater(eksik, 0)
