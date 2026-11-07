"""Kriter ayar laboratuvarı (/ayar): kriter listesi, sayı değiştirme, geçmişe sarma, sayfa (7 Kasım 2026)."""

import copy
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from karabasan import ayar as a
from karabasan import ayar_sayfa as s
from karabasan import botlar, panel
from testler.veri import sahte_sinav_klasoru, yapay_mumlar

SIMDI = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
BOT_ADLARI = [b[0] for b in botlar.BOTLAR]


def sahte_getir(parite, piyasa, aralik, bas, son):
    """Tek bir uzun yapay seriden dilim keser: farklı bitişlerde aynı mumlar çıkar (geleceğe bakma sınaması için)."""
    dk = {"5m": 5, "15m": 15, "1h": 60, "1d": 1440}[aralik]
    baslangic = datetime(2026, 1, 1, tzinfo=timezone.utc)
    adet = int((datetime(2026, 12, 31, tzinfo=timezone.utc) - baslangic).total_seconds() / 60 / dk)
    tablo = yapay_mumlar(adet=adet, dilim_dk=dk, tohum=7, baslangic="2026-01-01", fiyat=100.0, oynaklik=0.004 * (dk / 5) ** 0.5)
    t = tablo["date"]
    return tablo[(t >= pd.Timestamp(bas)) & (t <= pd.Timestamp(son))].reset_index(drop=True)


class Kriterler(unittest.TestCase):
    def test_her_botun_kriterleri_okunur(self):
        for bot in BOT_ADLARI:
            kural = a.kural_hazirla(bot)
            kriterler = a.kriterler(kural)
            self.assertEqual(len(kriterler), len(kural["giris"]["hepsi"]))
            for k in kriterler:
                self.assertTrue(k["yazi"])
            # Her sayı için yol gerçekten kuralda var.
            for yol, ad, deger in a.tum_sayilar(kural):
                self.assertEqual(a._al(kural, yol), deger)
                self.assertTrue(ad)

    def test_bilinmeyen_bot_hata(self):
        with self.assertRaises(a.AyarHatasi):
            a.kural_hazirla("yok-vadeli")

    def test_uygula_kopyayi_degistirir_asliyi_degil(self):
        kural = a.kural_hazirla("smk-vadeli")
        once = copy.deepcopy(kural)
        kopya = a.uygula(kural, {"giris.hepsi.8.sag": 40, "cikis.zarar_durdur_yuzde": 5.5})
        self.assertEqual(kopya["giris"]["hepsi"][8]["sag"], 40)
        self.assertEqual(kopya["cikis"]["zarar_durdur_yuzde"], 5.5)
        self.assertEqual(kural, once)
        # Kural dosyasını yeniden yükleyince de canlı değer aynı (hiçbir yere yazılmadı).
        self.assertEqual(a.kural_hazirla("smk-vadeli"), once)

    def test_gecersiz_deger_reddedilir(self):
        kural = a.kural_hazirla("smk-vadeli")
        with self.assertRaises(a.AyarHatasi):
            a.uygula(kural, {"cikis.zarar_durdur_yuzde": -3})
        with self.assertRaises(a.AyarHatasi):
            a.uygula(kural, {"gostergeler.rsi14.periyot": 7.5})   # tam sayı olmalı

    def test_sayi_oku(self):
        self.assertEqual(a.sayi_oku("1,5"), 1.5)
        for kotu in ("abc", "", "nan", "1e99"):
            with self.assertRaises(a.AyarHatasi):
                a.sayi_oku(kotu)

    def test_tarama_degerleri(self):
        self.assertIn(20, a.tarama_degerleri(20))
        self.assertTrue(all(isinstance(v, int) for v in a.tarama_degerleri(20)))
        self.assertIn(1.2, a.tarama_degerleri(1.2))
        self.assertGreater(len(a.tarama_degerleri(1.2)), 3)

    def test_sutun_etiketi(self):
        kural = a.kural_hazirla("smk-vadeli")
        self.assertEqual(a.sutun_etiketi(kural, "rsi14_1s"), "RSI 14 (1 saatlik)")
        self.assertEqual(a.sutun_etiketi(kural, "hacim"), "Hacim")
        self.assertEqual(a.sutun_etiketi(kural, "bilinmeyen_x"), "bilinmeyen_x")


class Gecmis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kural = a.kural_hazirla("smk-vadeli")
        cls.bitis = SIMDI
        cls.gun = 14
        cls.df, cls.ek = a.veri_topla(cls.kural, "ETH", "vadeli", cls.bitis, cls.gun, sahte_getir)
        cls.bas = pd.Timestamp(cls.bitis - timedelta(days=cls.gun))

    def test_pencerenin_otesi_veri_gelmez(self):
        # Kapanışı bitişten sonra olan mum yok (ne taban ne günlük).
        son = self.df["date"].iloc[-1] + pd.Timedelta(minutes=5)
        self.assertLessEqual(son, pd.Timestamp(self.bitis))
        for dilim, tablo in self.ek.items():
            self.assertLessEqual(tablo["date"].iloc[-1] + pd.Timedelta(minutes=1440), pd.Timestamp(self.bitis))

    def test_pencereden_once_acilan_islem_sayilmaz(self):
        sonuc = a.calistir(self.kural, self.df, self.ek, self.bas)
        for i in sonuc["islemler"]:
            self.assertGreaterEqual(pd.Timestamp(i["giris_zamani"]), self.bas)

    def test_gecmis_sonradan_gelen_veriyle_degismez(self):
        """Pencereyi iki gün ileri uzatmak, önceki pencerede kapanmış işlemleri değiştirmemeli."""
        kisa = a.calistir(self.kural, self.df, self.ek, self.bas)["islemler"]
        df2, ek2 = a.veri_topla(self.kural, "ETH", "vadeli", self.bitis + timedelta(days=2), self.gun + 2, sahte_getir)
        uzun = a.calistir(self.kural, df2, ek2, self.bas)["islemler"]
        sinir = pd.Timestamp(self.bitis)
        ilk = [(i["giris_zamani"], i["cikis_zamani"], round(i["giris_fiyati"], 8)) for i in kisa if i["cikis_zamani"] <= sinir]
        ikinci = [(i["giris_zamani"], i["cikis_zamani"], round(i["giris_fiyati"], 8)) for i in uzun if i["cikis_zamani"] <= sinir]
        self.assertEqual(ilk, ikinci)

    def test_kriter_olcumu_tutarli(self):
        """Bir şartı her zaman doğru yapınca, eklenen sinyal sayısı tam o şartın tek başına engellediği mum sayısıdır."""
        taban = a.calistir(self.kural, self.df, self.ek, self.bas, kriter_olc=True)
        self.assertEqual(len(taban["kriterler"]), len(self.kural["giris"]["hepsi"]))
        # 0. şartı (günlük kapanış < EMA 20) her zaman doğru bir şartla değiştir: bu yapay veride
        # yalnız o şart girişi engelliyor.
        sira = max(taban["kriterler"], key=lambda k: k["engel_sayisi"])["sira"]
        gevsek = copy.deepcopy(self.kural)
        gevsek["giris"]["hepsi"][sira] = {"sol": "kapanis", "islem": ">", "sag": 0}
        yeni = a.calistir(gevsek, self.df, self.ek, self.bas)
        engel = taban["kriterler"][sira]["engel_sayisi"]
        self.assertGreater(engel, 0)
        self.assertEqual(yeni["sinyal_sayisi"], taban["sinyal_sayisi"] + engel)
        for k in taban["kriterler"]:
            self.assertEqual(len(k["engel_zamanlari"]), min(k["engel_sayisi"], 400))
            self.assertTrue(0.0 <= k["dogru_oran"] <= 1.0)

    def test_ayni_ayar_ayni_sonuc(self):
        bir = a.calistir(self.kural, self.df, self.ek, self.bas)["ozet"]
        iki = a.calistir(copy.deepcopy(self.kural), self.df, self.ek, self.bas)["ozet"]
        self.assertEqual(bir, iki)


class Sayfa(unittest.TestCase):
    def sayfa(self, **sorgu):
        ham = {k: [str(v)] for k, v in sorgu.items()}
        return s.ayar_sayfasi(s.sorgu_coz(ham), a.VeriOnbellegi(), sahte_getir, SIMDI)

    def test_varsayilan_her_bot_acilir(self):
        for bot in BOT_ADLARI:
            html = self.sayfa(bot=bot, gun=5)
            self.assertIn("Kriter ayarı", html)
            self.assertIn("Çalıştır", html)
            self.assertIn('method="get"', html)
            self.assertNotIn("<script", html)
            self.assertIn("<svg", html)
            self.assertIn("Canlı botlar değişmez", html)

    def test_sorgu_guvenligi(self):
        i = s.sorgu_coz({"bot": ["../../etc"], "coin": ["<script>"], "gun": ["999"], "once": ["-5"],
                         "p0": ["1"], "pX": ["1"], "goster": ["abc"], "tara": ["99999"]})
        self.assertEqual(i["bot"], BOT_ADLARI[0])
        self.assertEqual(i["coin"], s.VARSAYILAN_COIN)
        self.assertEqual(i["gun"], a.EN_FAZLA_GUN)
        self.assertEqual(i["once"], 0)
        self.assertEqual(i["p"], {0: "1"})
        self.assertIsNone(i["goster"])
        self.assertIsNone(i["tara"])

    def test_degisiklik_senin_ayarin_olarak_gorunur(self):
        kural = a.kural_hazirla("smk-vadeli")
        idx = [yol for yol, _a, _d in a.tum_sayilar(kural)].index("cikis.zarar_durdur_yuzde")
        html = self.sayfa(bot="smk-vadeli", bot0="smk-vadeli", gun=7, **{f"p{idx}": "4,5"})
        self.assertIn("Senin ayarın", html)
        self.assertIn('value="4,5"', html)

    def test_baska_botun_alanlari_yok_sayilir(self):
        html = self.sayfa(bot="smdk-vadeli", bot0="smk-vadeli", p0="99")
        self.assertNotIn("Senin ayarın", html)

    def test_gecersiz_deger_hata_gosterir_canli_ayara_doner(self):
        kural = a.kural_hazirla("smk-vadeli")
        idx = [yol for yol, _a, _d in a.tum_sayilar(kural)].index("cikis.zarar_durdur_yuzde")
        html = self.sayfa(bot="smk-vadeli", bot0="smk-vadeli", **{f"p{idx}": "-3"})
        self.assertIn("ay-hata", html)
        self.assertNotIn("Senin ayarın", html)
        html = self.sayfa(bot="smk-vadeli", bot0="smk-vadeli", **{f"p{idx}": "abc"})
        self.assertIn("bir sayı değil", html)

    def test_tarama_ve_goster(self):
        kural = a.kural_hazirla("smk-vadeli")
        idx = [yol for yol, _a, _d in a.tum_sayilar(kural)].index("giris.hepsi.8.sag")
        html = self.sayfa(bot="smk-vadeli", bot0="smk-vadeli", tara=idx, goster=4)
        self.assertIn("Tarama:", html)
        self.assertIn("ezberdir", html)
        self.assertIn("ay-engel", html)   # 4. şart (yapı kırılımı) çok mum engelliyor

    def test_veri_alinamazsa_sayfa_dusmez(self):
        def bozuk(*_):
            raise OSError("ağ yok")

        html = s.ayar_sayfasi(s.sorgu_coz({}), a.VeriOnbellegi(), bozuk, SIMDI)
        self.assertIn("alınamadı", html)
        self.assertIn("Çalıştır", html)

    def test_az_islem_uyarisi(self):
        self.assertIn("Az işlem", self.sayfa(bot="smk-vadeli", gun=3))


class Sunucu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        klasor = sahte_sinav_klasoru(Path(cls.gecici.name) / "veri", datetime.now(timezone.utc))
        cls.sunucu = panel.sunucu_kur(klasor, adres="127.0.0.1", port=0)
        cls.adres = f"http://127.0.0.1:{cls.sunucu.server_address[1]}"
        threading.Thread(target=cls.sunucu.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()
        cls.sunucu.server_close()
        cls.gecici.cleanup()

    def test_ayar_sayfasi_form_gonderebilir_betik_calistiramaz(self):
        import unittest.mock as mock

        def sahte(istek, *a_, **k):
            return "<html>tamam</html>"

        with mock.patch.object(s, "ayar_sayfasi", side_effect=sahte):
            with urllib.request.urlopen(self.adres + "/ayar?bot=smk-vadeli", timeout=5) as y:
                baslik = y.headers["Content-Security-Policy"]
                metin = y.read().decode("utf-8")
        self.assertIn("tamam", metin)
        self.assertIn("form-action 'self'", baslik)
        self.assertNotIn("script-src", baslik)
        self.assertIn("default-src 'none'", baslik)

    def test_ana_sayfa_formu_hala_yasak(self):
        with urllib.request.urlopen(self.adres + "/", timeout=5) as y:
            baslik = y.headers["Content-Security-Policy"]
            metin = y.read().decode("utf-8")
        self.assertIn("form-action 'none'", baslik)
        self.assertIn('href="/ayar"', metin)


if __name__ == "__main__":
    unittest.main()
