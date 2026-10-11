"""Emir defteri denemesi: hesap, servis, sayfa ve bağlantılar. Veri yapaydır."""

import math
import random
import re
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from karabasan import defter as d
from karabasan import defter_sayfa
from karabasan.defter_servisi import Servis

KOK = Path(__file__).resolve().parent.parent


def defter_kur(orta, egim=0.0, kademe=100, adim=0.1):
    """Yapay emir defteri. egim > 0: alış tarafı daha kalabalık."""
    alislar = [(orta - adim / 2 - k * adim, 1.0 + max(egim, 0) * (1 + (k < 5))) for k in range(kademe)]
    satislar = [(orta + adim / 2 + k * adim, 1.0 + max(-egim, 0) * (1 + (k < 5))) for k in range(kademe)]
    return alislar, satislar


class DefterOzetiTesti(unittest.TestCase):
    def test_dengesizlik_mikro_fiyat_makas(self):
        alislar, satislar = defter_kur(60000.0, egim=2.0)
        o = d.defter_ozeti(alislar, satislar)
        self.assertAlmostEqual(o["orta"], 60000.0)
        self.assertGreater(o["dengesizlik_5"], 0)          # alış tarafı kalabalık
        self.assertGreater(o["mikro_bps"], 0)              # mikro fiyat yukarı çekilir
        self.assertAlmostEqual(o["makas_bps"], 0.1 / 60000.0 * 1e4)
        ters = d.defter_ozeti(*defter_kur(60000.0, egim=-2.0))
        self.assertLess(ters["dengesizlik_5"], 0)
        self.assertLess(ters["mikro_bps"], 0)

    def test_bos_ya_da_ters_defter_reddedilir(self):
        with self.assertRaises(ValueError):
            d.defter_ozeti([], [(1.0, 1.0)])
        with self.assertRaises(ValueError):
            d.defter_ozeti([(101.0, 1.0)], [(100.0, 1.0)])

    def test_duvar_uzakligi(self):
        alislar, satislar = defter_kur(1000.0)
        alislar[10] = (alislar[10][0], 50.0)
        o = d.defter_ozeti(alislar, satislar)
        self.assertAlmostEqual(o["duvar_alis_bps"], (1000.0 - alislar[10][0]) / 1000.0 * 1e4)

    def test_rsi(self):
        self.assertEqual(d.rsi(list(range(1, 20))), 100.0)
        self.assertEqual(d.rsi(list(range(20, 1, -1))), 0.0)
        self.assertIsNone(d.rsi([1, 2, 3]))
        self.assertAlmostEqual(d.rsi([1, 2] * 15), 50.0, delta=5)


def mumlar_uret(fiyatlar: dict, bas: int, son: int) -> list:
    """Saniyelik fiyatlardan 1 dakikalık mumlar (kapanmış ve o anki açık mum)."""
    mumlar = []
    for m in range(bas - bas % 60, son + 1, 60):
        icindeki = [fiyatlar[t] for t in range(m, min(m + 60, son + 1)) if t in fiyatlar]
        if not icindeki:
            continue
        mumlar.append({"acilis_zamani": m, "acilis": icindeki[0], "yuksek": max(icindeki), "dusuk": min(icindeki),
                       "kapanis": icindeki[-1], "hacim": float(len(icindeki)), "kapanis_zamani": m + 60})
    return mumlar


class GelecegeBakmazTesti(unittest.TestCase):
    """5. kural: bir anın özellikleri sonradan gelen veriyle değişmez; model olgunlaşmamış örnek görmez."""

    def test_acik_mum_kullanilmaz(self):
        mumlar = [{"kapanis_zamani": 120, "kapanis": 1.0}, {"kapanis_zamani": 180, "kapanis": 2.0}]
        self.assertEqual(len(d.kapanmis_mumlar(mumlar, 150)), 1)
        self.assertEqual(len(d.kapanmis_mumlar(mumlar, 180)), 2)

    def test_ozellikler_sonraki_veriden_etkilenmez(self):
        rastgele = random.Random(3)
        fiyatlar, f = {}, 60000.0
        for t in range(0, 7200):
            f *= 1 + rastgele.gauss(0, 2e-4)
            fiyatlar[t] = f
        an = 5000

        def ozellik(son):
            gecmis = d.FiyatGecmisi(saklama_saniye=20000)
            for t in range(0, son + 1):
                gecmis.ekle(t, fiyatlar[t])
            o = d.defter_ozeti(*defter_kur(fiyatlar[an]))
            return d.ozellik_vektoru(o, gecmis, an, mumlar_uret(fiyatlar, 0, son))

        # Aynı an, ama birinde 30 dakika sonrasının verisi de elde: sonuç aynı olmalı.
        np.testing.assert_allclose(ozellik(an), ozellik(an + 1800))

    def test_model_olgunlasmamis_ornek_gormez(self):
        kayitlar = [(t, [float(t)] * len(d.OZELLIKLER), 0.1) for t in range(0, 2000, 5)]
        X, y = d.egitim_verisi(kayitlar, 300, simdi=1000, adim=5)
        self.assertTrue(len(y) > 0)
        self.assertLessEqual(X[:, 0].max(), 700)      # 700 + 300 <= 1000
        X, _ = d.egitim_verisi(kayitlar, 900, simdi=1000, adim=5)
        self.assertLessEqual(X[:, 0].max(), 100)


class ModelTesti(unittest.TestCase):
    def test_egitilmemis_model_tahmin_vermez(self):
        self.assertIsNone(d.Model().tahmin([0.0] * len(d.OZELLIKLER)))

    def test_dogrusal_iliskiyi_ogrenir(self):
        rng = np.random.default_rng(1)
        X = rng.normal(size=(3000, len(d.OZELLIKLER)))
        y = 0.2 * X[:, 0] - 0.1 * X[:, 3] + rng.normal(scale=0.02, size=3000)
        m = d.Model(ceza=1.0)
        m.egit(X, y)
        x = [0.0] * len(d.OZELLIKLER)
        x[0] = 1.0
        self.assertAlmostEqual(m.tahmin(x), 0.2, delta=0.02)
        x[0] = 100.0
        self.assertEqual(m.tahmin(x), d.EN_FAZLA_TAHMIN_YUZDE)    # aşırı uç sınırlanır


class SanalIslemTesti(unittest.TestCase):
    def test_kucuk_tahminde_islem_yok(self):
        self.assertIsNone(d.islem_ac("5dk", 0.10, 100.0, 100.1, 0))
        self.assertIsNone(d.islem_ac("5dk", None, 100.0, 100.1, 0))

    def test_alim_hedef(self):
        i = d.islem_ac("5dk", 0.3, 99.9, 100.0, 1000)
        self.assertEqual((i["yon"], i["giris"]), ("alim", 100.0))          # en iyi satıştan alır
        self.assertAlmostEqual(i["hedef"], 100.3)
        self.assertAlmostEqual(i["stop"], 99.7)
        self.assertEqual(i["bitis_zamani"], 1300)
        self.assertLess(i["tasfiye"], 1.0)                                  # 1 kat: neredeyse sıfır
        self.assertIsNone(d.islem_denetle(i, 100.1, 100.2, 1010))
        s = d.islem_denetle(i, 100.35, 100.4, 1020)
        self.assertEqual(s["neden"], "hedef")
        self.assertAlmostEqual(s["net_yuzde"], 0.3 - 0.1)
        self.assertTrue(s["basarili"])
        self.assertAlmostEqual(s["net_usdt"], 0.2)

    def test_aciga_satis_stop_ve_en_kotu_an(self):
        i = d.islem_ac("15dk", -0.5, 100.0, 100.1, 0)
        self.assertEqual((i["yon"], i["giris"]), ("satis", 100.0))         # en iyi alıştan satar
        d.islem_denetle(i, 100.1, 100.3, 10)
        self.assertAlmostEqual(i["en_kotu_yuzde"], -0.3)
        s = d.islem_denetle(i, 100.5, 100.6, 20)
        self.assertEqual(s["neden"], "stop")
        self.assertAlmostEqual(s["net_yuzde"], -0.6 - 0.1)
        self.assertFalse(s["basarili"])
        self.assertGreater(i["tasfiye"], 199.0)

    def test_sure_dolunca_o_anki_fiyattan_kapanir(self):
        i = d.islem_ac("5dk", 0.3, 99.9, 100.0, 0)
        s = d.islem_denetle(i, 100.05, 100.1, 300)
        self.assertEqual(s["neden"], "sure")
        self.assertAlmostEqual(s["net_yuzde"], 0.05 - 0.1)
        self.assertFalse(s["basarili"])                                      # komisyonu karşılamadı


class Simulasyon:
    """Gizli bir eğilimin hem defterde hem fiyatta göründüğü yapay piyasa."""

    def __init__(self, bas, tohum=5):
        self.rng = random.Random(tohum)
        self.t = bas
        self.bas = bas
        self.fiyat = 60000.0
        self.egilim = 0.0
        self.fiyatlar = {}

    def ilerle(self, t):
        self.t = t
        self.egilim = 0.995 * self.egilim + self.rng.gauss(0, 0.05)
        self.fiyat *= 1 + self.egilim * 4e-5 + self.rng.gauss(0, 1e-4)
        self.fiyatlar[t] = self.fiyat

    def defter(self):
        return defter_kur(self.fiyat, egim=self.egilim * 3 + self.rng.gauss(0, 0.3))

    def mumlar(self):
        return mumlar_uret(self.fiyatlar, max(self.bas, self.t - 7200), self.t)


class ServisTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        cls.yol = Path(cls.gecici.name) / "kayit" / "defter.sqlite"
        bas = int(time.time()) - 8000
        cls.sim = sim = Simulasyon(bas)
        servis = Servis(cls.yol, getir_defter=sim.defter, getir_mumlar=sim.mumlar,
                        en_az_ogrenme=900, egitim_araligi=120)
        for t in range(bas, bas + 7200):
            sim.ilerle(t)
            servis.adim(t)
        cls.servis = servis
        servis.vt.commit()
        cls.ozet = defter_sayfa.ozet_cikar(cls.yol, simdi=bas + 7200)

    @classmethod
    def tearDownClass(cls):
        cls.servis.kapat()
        cls.gecici.cleanup()

    def test_her_saniye_kayit_ve_gerceklesen_fiyat(self):
        vt = sqlite3.connect(self.yol)
        sayi, olgun5, olgun15 = vt.execute(
            "SELECT COUNT(*), COUNT(gercek_5dk), COUNT(gercek_15dk) FROM ornek_v1").fetchone()
        self.assertEqual(sayi, 7200)
        self.assertEqual(olgun5, 7200 - 300)
        self.assertEqual(olgun15, 7200 - 900)
        # Gerçekleşen değişim, 300 saniye sonraki orta fiyattan hesaplanmış olmalı.
        z, orta, g5 = vt.execute("SELECT zaman, orta, gercek_5dk FROM ornek_v1 ORDER BY zaman LIMIT 1 OFFSET 100").fetchone()
        sonra = vt.execute("SELECT orta FROM ornek_v1 WHERE zaman = ?", (z + 300,)).fetchone()[0]
        self.assertAlmostEqual(g5, (sonra / orta - 1) * 100)
        vt.close()

    def test_model_ogrenmeden_tahmin_vermez_sonra_verir(self):
        vt = sqlite3.connect(self.yol)
        ilk_tahmin = vt.execute("SELECT MIN(zaman) FROM ornek_v1 WHERE tahmin_5dk IS NOT NULL").fetchone()[0]
        bas = vt.execute("SELECT MIN(zaman) FROM ornek_v1").fetchone()[0]
        vt.close()
        self.assertIsNotNone(ilk_tahmin)
        self.assertGreaterEqual(ilk_tahmin - bas, 300 + 900)   # 900 olgun saniye birikmeli

    def test_yapay_piyasada_ogrenir_ve_islem_acar(self):
        # Yapay piyasada defter gerçekten ipucu taşıyor: yeterince kayıt birikince (son yarım
        # saat) model "fiyat değişmez" tahmininden iyi olmalı.
        vt = sqlite3.connect(self.yol)
        hata_model, hata_sifir, yon = vt.execute(
            "SELECT AVG(ABS(gercek_5dk - tahmin_5dk)), AVG(ABS(gercek_5dk)), "
            "AVG(CASE WHEN tahmin_5dk * gercek_5dk > 0 THEN 1.0 ELSE 0.0 END) FROM ornek_v1 "
            "WHERE tahmin_5dk IS NOT NULL AND gercek_5dk IS NOT NULL AND zaman >= ?",
            (self.sim.t - 2100,)).fetchone()
        vt.close()
        self.assertLess(hata_model, hata_sifir)
        self.assertGreater(yon, 0.55)
        self.assertIsNotNone(self.ozet["ufuklar"]["5dk"]["yon_isabeti"])
        t = self.ozet["toplam"]
        self.assertGreater(t["islem"], 3)
        self.assertEqual(t["islem"], t["basarili"] + t["basarisiz"])

    def test_ayni_ufukta_ayni_anda_tek_islem(self):
        vt = sqlite3.connect(self.yol)
        for u in d.UFUKLAR:
            islemler = vt.execute("SELECT giris_zamani, COALESCE(cikis_zamani, 1e18) FROM islem_v1 "
                                  "WHERE ufuk = ? ORDER BY giris_zamani", (u,)).fetchall()
            for (_a1, c1), (a2, _c2) in zip(islemler, islemler[1:]):
                self.assertGreaterEqual(a2, c1)
        vt.close()

    def test_yeniden_baslayinca_ogrendiklerini_ve_acik_islemi_geri_alir(self):
        self.servis.vt.commit()
        ikinci = Servis(self.yol, getir_defter=self.sim.defter, getir_mumlar=self.sim.mumlar,
                        en_az_ogrenme=900, egitim_araligi=120)
        self.assertGreater(len(ikinci.kayitlar["5dk"]), 4000)
        for u in d.UFUKLAR:
            self.assertEqual(ikinci.acik[u] is None, self.servis.acik[u] is None)
        ikinci.kapat()

    def test_sayfa_ve_telegram_ozeti(self):
        html = defter_sayfa.html_uret(self.ozet)
        t = self.ozet["toplam"]
        self.assertIn(f'<b class="">{t["islem"]}</b><span>toplam işlem</span>', html)
        self.assertIn(f'{t["basarili"]}</b><span>başarılı</span>', html)
        self.assertIn(f'{t["basarisiz"]}</b><span>başarısız</span>', html)
        self.assertIn("İşlemler (en yeni 200)", html)
        self.assertIn("Yön isabeti", html)
        self.assertNotIn("<script", html)
        metin = defter_sayfa.metin_ozeti(self.ozet)
        self.assertIn(f"İşlem: {t['islem']} (başarılı {t['basarili']}, başarısız {t['basarisiz']}", metin)

    def test_bayat_kayit_uyarilir(self):
        ozet = defter_sayfa.ozet_cikar(self.yol, simdi=self.sim.t + 3600)
        self.assertTrue(ozet["bayat"])
        self.assertIn("güncellenmiyor", defter_sayfa.html_uret(ozet))


class SayfaTesti(unittest.TestCase):
    def test_kayit_yokken(self):
        ozet = defter_sayfa.ozet_cikar(Path("/yok/defter.sqlite"))
        self.assertFalse(ozet["var"])
        self.assertIn("Henüz kayıt yok", defter_sayfa.html_uret(ozet))
        self.assertIn("henüz kayıt yazmadı", defter_sayfa.metin_ozeti(ozet))

    def test_sayi_bicimi(self):
        self.assertEqual(defter_sayfa._sayi(61234.5, 1), "61.234,5")
        self.assertEqual(defter_sayfa._sayi(-0.123, 3, True), "-0,123")


class BaglantiTesti(unittest.TestCase):
    def test_yalniz_herkese_acik_veri_okunur_emir_yok(self):
        """1. kural: servis borsaya emir gönderemez, anahtar kullanmaz."""
        for dosya in ("defter.py", "defter_servisi.py", "defter_sayfa.py"):
            metin = (KOK / "karabasan" / dosya).read_text(encoding="utf-8")
            for yasak in ("/order", "X-MBX-APIKEY", "signature", "method=\"POST\"", "api_key", "secret"):
                self.assertNotIn(yasak, metin, f"{dosya}: {yasak}")
        servis = (KOK / "karabasan" / "defter_servisi.py").read_text(encoding="utf-8")
        adresler = set(re.findall(r"https://[^\"?]+", servis))
        self.assertEqual(adresler, {"https://fapi.binance.com/fapi/v1/depth",
                                    "https://fapi.binance.com/fapi/v1/klines"})

    def test_compose_servisi(self):
        import sys

        sys.path.insert(0, str(KOK / "araclar"))
        import yapilandirma_uret

        metin = yapilandirma_uret.compose_metni()
        self.assertIn("  defter:", metin)
        self.assertIn('entrypoint: ["python3", "-m", "karabasan.defter_servisi"]', metin)
        bolum = metin.split("  defter:")[1].split("\n\n")[0]
        self.assertNotIn("ports:", bolum)          # dışarıya kapı açmaz
        self.assertNotIn("env_file", bolum)        # gizli bilgi görmez
        self.assertIn("restart kayitci panel haberci defter", (KOK / "kur.sh").read_text(encoding="utf-8"))

    def test_panel_defter_adresi(self):
        import threading
        import urllib.request

        from karabasan import panel

        with tempfile.TemporaryDirectory() as gecici:
            sunucu = panel.sunucu_kur(Path(gecici), adres="127.0.0.1", port=0)
            is_parcacigi = threading.Thread(target=sunucu.serve_forever, daemon=True)
            is_parcacigi.start()
            try:
                port = sunucu.server_address[1]
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/defter", timeout=10) as yanit:
                    self.assertEqual(yanit.status, 200)
                    self.assertIn("Emir defteri denemesi", yanit.read().decode("utf-8"))
            finally:
                sunucu.shutdown()
                sunucu.server_close()


if __name__ == "__main__":
    unittest.main()
