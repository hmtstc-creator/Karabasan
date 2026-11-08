"""Kriter ayar laboratuvarı (/ayar): kriter listesi, sayı değiştirme, geçmişe sarma, sayfa (7 Kasım 2026)."""

import copy
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from karabasan import ayar as a
from karabasan import ayar_kayit
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


class Aciklamalar(unittest.TestCase):
    def test_rsi_aciklamasi_grafik_dilimini_ve_kapsami_soyler(self):
        kural = a.kural_hazirla("smk-vadeli")
        metin = a.gosterge_aciklamasi(kural, "rsi14_1s")
        self.assertIn("RSI 14", metin)
        self.assertIn("1 saatlik", metin)
        self.assertIn("son 14 saat", metin)
        self.assertIn("son 70 dakika", a.gosterge_aciklamasi(kural, "rsi14"))   # 5 dakikalık grafik

    def test_etiketlerde_grafik_dilimi_hep_yazar(self):
        kural = a.kural_hazirla("smk-vadeli")
        self.assertEqual(a.sutun_etiketi(kural, "rsi14"), "RSI 14 (5 dakikalık)")
        self.assertEqual(a.sutun_etiketi(kural, "ema20_1g"), "EMA 20 (günlük)")

    def test_her_kriter_ve_her_sayinin_aciklamasi_var(self):
        for bot in BOT_ADLARI:
            kural = a.kural_hazirla(bot)
            for k in a.kriterler(kural):
                bilgi = a.kriter_bilgisi(kural, k["sira"])
                self.assertTrue(bilgi["anlam"].endswith("."))
                self.assertNotIn("..", bilgi["anlam"])
                self.assertTrue(bilgi["sozluk"], f"{bot} {k['sira']}")
            for yol, ad, _ in a.tum_sayilar(kural):
                self.assertTrue(a.sayi_aciklamasi(kural, yol), f"{bot} {yol}")

    def test_esik_yonu_dogru_soylenir(self):
        kural = a.kural_hazirla("smk-vadeli")
        # 2. şart: RSI(1 saatlik) > 20 : eşiği büyütmek zorlaştırır
        self.assertIn("zorlaşır (giriş sayısı azalır)", a.sayi_aciklamasi(kural, "giris.hepsi.2.sag"))
        # 5. şart: RSI(5 dk) < 50 : eşiği büyütmek kolaylaştırır
        self.assertIn("kolaylaşır (giriş sayısı artar)", a.sayi_aciklamasi(kural, "giris.hepsi.5.sag"))


class Katmanlar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kural = a.kural_hazirla("smk-vadeli")
        cls.df, cls.ek = a.veri_topla(cls.kural, "ETH", "vadeli", SIMDI, 5, sahte_getir)
        cls.bas = pd.Timestamp(SIMDI - timedelta(days=5))

    def test_fiyat_ustu_katmanlar_fiyatla_ayni_olcekli_olanlardir(self):
        tablo = a.sinyal_uret(self.df, self.kural, self.ek)
        katmanlar = a.fiyat_katmanlari(self.kural, tablo)
        adlar = [k["ad"] for k in katmanlar]
        self.assertTrue(any("EMA 20" in x for x in adlar))
        self.assertTrue(any("denge çizgisi" in x for x in adlar))
        self.assertTrue(any(k["tur"] == "bant" and "bölgesi" in k["ad"] for k in katmanlar))
        for k in katmanlar:   # RSI / hacim fiyat grafiğine çizilmez
            self.assertNotIn("rsi", k["sutun"])
            self.assertNotIn("hacim", k["sutun"])

    def test_katman_verisi_sinyalle_tutarli(self):
        sonuc = a.calistir(self.kural, self.df, self.ek, self.bas, kriter_olc=True)
        kat = sonuc["katman"]
        self.assertEqual(int(kat["hepsi"].sum()), sonuc["sinyal_sayisi"])
        self.assertEqual(len(kat["kosullar"]), len(self.kural["giris"]["hepsi"]))
        self.assertEqual(len(kat["tarih"]), len(kat["hepsi"]))
        # Kesişim = bütün şartların aynı anda doğru olduğu mumlar (şart başına son_n_mumda dahil değil: üst düzey şartlar).
        hepsi = kat["kosullar"][0].copy()
        for k in kat["kosullar"][1:]:
            hepsi &= k
        self.assertTrue((kat["hepsi"] == hepsi).all())


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
            self.assertEqual(html.count("<script>"), 1)    # tek satır içi betik (canlı güncelleme)
            self.assertIn('class="ay-ac"', html)           # her kriter açılır kutu
            self.assertIn("data-adim", html)               # + / − düğmeleri
            self.assertIn('id="ay-sabit"', html)           # grafik sabit duran blokta
            self.assertIn("Bu şart ne diyor?", html)       # her kriterde düz Türkçe açıklama
            self.assertIn("ay-ipucu", html)                # her sayının altında ne işe yaradığı
            self.assertIn("<svg", html)
            self.assertIn("Canlı botlar değişmez", html)

    def test_grafikte_giris_bolgesi_yesil_mumlar_tek_renk(self):
        import unittest.mock as mock

        kural = a.kural_hazirla("smk-vadeli")
        kural["giris"]["hepsi"][0] = {"sol": "kapanis", "islem": ">", "sag": 0}   # yapay veride sinyal çıksın
        for i in (1, 4, 5):
            kural["giris"]["hepsi"][i]["sag"] = 100
        kural["giris"]["hepsi"][9]["sag"]["carpan"] = 0.0
        with mock.patch.object(a, "kural_hazirla", side_effect=lambda b: copy.deepcopy(kural)):
            html = self.sayfa(bot="smk-vadeli", gun=3)
        self.assertIn('class="ay-bolge" x', html)
        self.assertIn("Giriş bölgesi", html)
        self.assertIn("ay-serit-dolu", html)   # şart şeritleri
        self.assertIn("ay-cizgi", html)        # fiyat üstü çizgi
        self.assertNotIn('class="ig-mum', html)  # yön rengi (yeşil / kırmızı mum) yok
        self.assertIn('class="ay-mum"', html)

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

    def test_canli_yanit_tarama_ve_goster(self):
        import json

        kural = a.kural_hazirla("smk-vadeli")
        idx = [yol for yol, _a, _d in a.tum_sayilar(kural)].index("giris.hepsi.8.sag")
        ham = {"bot": ["smk-vadeli"], "bot0": ["smk-vadeli"], "tara": [str(idx)], "goster": ["0"]}
        v = json.loads(s.ayar_json(s.sorgu_coz(ham), a.VeriOnbellegi(), sahte_getir, SIMDI))
        self.assertIn("ezberdir", v["tara"])
        self.assertIn("ay-engel", v["grafik"])     # 1. şart (günlük kapanış < EMA) çok mum engelliyor
        self.assertEqual(len(v["rozet"]), len(kural["giris"]["hepsi"]))
        self.assertIn("engel", "".join(v["rozet"]))
        for anahtar in ("grafik", "ozet", "anahtar", "islemler", "secim", "mesaj"):
            self.assertIn(anahtar, v)

    def test_canli_yanit_degisikligi_yansitir(self):
        import json

        kural = a.kural_hazirla("smk-vadeli")
        idx = [yol for yol, _a, _d in a.tum_sayilar(kural)].index("cikis.zarar_durdur_yuzde")
        ham = {"bot": ["smk-vadeli"], "bot0": ["smk-vadeli"], f"p{idx}": ["4,5"]}
        v = json.loads(s.ayar_json(s.sorgu_coz(ham), a.VeriOnbellegi(), sahte_getir, SIMDI))
        self.assertIn("Senin ayarın", v["ozet"])
        self.assertIn("Canlı ayar", v["ozet"])
        v0 = json.loads(s.ayar_json(s.sorgu_coz({"bot": ["smk-vadeli"]}), a.VeriOnbellegi(), sahte_getir, SIMDI))
        self.assertNotIn("Senin ayarın", v0["ozet"])

    def test_veri_hatasinda_grafik_none_son_grafik_kalir(self):
        import json

        def bozuk(*_):
            raise OSError("ağ yok")

        v = json.loads(s.ayar_json(s.sorgu_coz({}), a.VeriOnbellegi(), bozuk, SIMDI))
        self.assertIsNone(v["grafik"])
        self.assertIn("alınamadı", v["mesaj"])

    def test_adim_buyuklugu(self):
        self.assertEqual(s._adim(14), 1)
        self.assertEqual(s._adim(120), 5)
        self.assertEqual(s._adim(0.3), 0.05)
        self.assertEqual(s._adim(1.2), 0.1)
        self.assertEqual(s._adim(9.0), 0.5)

    def test_csp_ozeti_sayfadaki_betikle_tutar(self):
        import base64
        import hashlib
        import re

        html = self.sayfa(bot="smk-vadeli", gun=3)
        betik = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        ozet = base64.b64encode(hashlib.sha256(betik.encode("utf-8")).digest()).decode("ascii")
        self.assertIn(f"'sha256-{ozet}'", s.guvenlik_basligi())

    def test_veri_alinamazsa_sayfa_dusmez(self):
        def bozuk(*_):
            raise OSError("ağ yok")

        html = s.ayar_sayfasi(s.sorgu_coz({}), a.VeriOnbellegi(), bozuk, SIMDI)
        self.assertIn("alınamadı", html)
        self.assertIn("Çalıştır", html)

    def test_az_islem_uyarisi(self):
        self.assertIn("30'dan az işlem", self.sayfa(bot="smk-vadeli", gun=3))


class Pasif(unittest.TestCase):
    """Etkili / pasif seçenekleri (9 Kasım 2026)."""

    def test_pasif_sart_her_zaman_dogru_olur_sira_korunur(self):
        kural = a.kural_hazirla("smk-vadeli")
        kopya = a.pasifla(kural, {"k0"})
        self.assertEqual(kopya["giris"]["hepsi"][0], a.KAPALI_KOSUL)
        self.assertEqual(kopya["giris"]["hepsi"][1:], kural["giris"]["hepsi"][1:])
        self.assertNotEqual(kural["giris"]["hepsi"][0], a.KAPALI_KOSUL)   # asıl kural dokunulmadı

    def test_pasif_secenek_kuraldan_kalkar(self):
        kural = a.kural_hazirla("smk2-vadeli")
        kopya = a.pasifla(kural, {"giris_limiti", "zararda_ekleme", "bekleme_dakika"})
        for alan in ("giris_limiti", "zararda_ekleme", "bekleme_dakika"):
            self.assertNotIn(alan, kopya)
            self.assertIn(alan, kural)

    def test_tek_cikis_yolu_kapatilamaz_ve_bilinmeyen_anahtar_yok_sayilir(self):
        kural = a.kural_hazirla("smk-vadeli")
        with self.assertRaises(a.AyarHatasi):
            a.pasifla(kural, {"iz_suren_stop"})
        with self.assertRaises(a.AyarHatasi):
            a.pasifla(kural, {f"k{i}" for i in range(len(kural["giris"]["hepsi"]))})
        self.assertEqual(a.pasifla(kural, {"yok_boyle_bir_sey"}), kural)

    def test_her_botun_pasif_sartlari_hesaplanir(self):
        for bot in BOT_ADLARI:
            kural = a.kural_hazirla(bot)
            a.pasifla(kural, {"k1"})   # doğrulamadan geçer

    def test_pasif_sart_giris_sayisini_azaltmaz(self):
        kural = a.kural_hazirla("smk-vadeli")
        istek = s.sorgu_coz({"bot": ["smk-vadeli"], "bot0": ["smk-vadeli"], "gun": ["10"], "pasif": ["k4", "k9"]})
        ctx = s.hesapla(istek, a.VeriOnbellegi(), sahte_getir, SIMDI)
        self.assertIsNone(ctx["hata"], ctx["hata"])
        self.assertTrue(ctx["degisti"])
        self.assertGreaterEqual(ctx["yeni"]["sinyal_sayisi"], ctx["eski"]["sinyal_sayisi"])
        self.assertEqual(len(ctx["yeni"]["kriterler"]), len(kural["giris"]["hepsi"]))

    def test_pasif_sayfada_isaretli_gelir(self):
        istek = s.sorgu_coz({"bot": ["smk-vadeli"], "bot0": ["smk-vadeli"], "gun": ["5"], "pasif": ["k2", "giris_limiti"]})
        html = s.ayar_sayfasi(istek, a.VeriOnbellegi(), sahte_getir, SIMDI)
        self.assertIn('name="pasif" value="k2" checked', html)
        self.assertIn('name="pasif" value="giris_limiti" checked', html)
        self.assertIn('class="ay-ac pasif" id="k2"', html)
        self.assertIn("(pasif)", html)

    def test_pasif_baska_bottan_gelirse_yok_sayilir(self):
        istek = s.sorgu_coz({"bot": ["smk-vadeli"], "bot0": ["smdk-vadeli"], "gun": ["5"], "pasif": ["k2"]})
        c = s.cozumle(istek)
        self.assertEqual(c["pasif"], set())

    def test_kaldirac_ve_ek_giris_sayilari_ayarlanabilir(self):
        yollar = [y for y, _ad, _e in a.tum_sayilar(a.kural_hazirla("smk2-vadeli"))]
        for y in ("kaldirac", "zararda_ekleme.kat", "zararda_ekleme.stopa_kala_yuzde"):
            self.assertIn(y, yollar)
        self.assertNotIn("kaldirac", [y for y, _ad, _e in a.tum_sayilar(a.kural_hazirla("smk-vadeli"))])


class Kayitlar(unittest.TestCase):
    """Adlı ayar kayıtları (9 Kasım 2026)."""

    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.depo = ayar_kayit.Depo(Path(self.gecici.name))

    def tearDown(self):
        self.gecici.cleanup()

    def _istek(self, **ek):
        sorgu = {"bot": ["smk-vadeli"], "bot0": ["smk-vadeli"], "gun": ["5"]}
        sorgu.update({k: v for k, v in ek.items()})
        return s.sorgu_coz(sorgu)

    def test_kaydet_listele_adlandir_sil(self):
        k = self.depo.kaydet("smk-vadeli", "Deneme 1", {"cikis.zarar_durdur_yuzde": 6, "x.y": 0.5}, ["k1"])
        self.assertEqual(self.depo.listele("smk-vadeli")[0]["ad"], "Deneme 1")
        self.assertEqual(self.depo.listele("smdk-vadeli"), [])
        self.assertEqual(self.depo.getir(k["id"])["degerler"]["cikis.zarar_durdur_yuzde"], 6)
        self.depo.adlandir(k["id"], "  Yeni   ad ")
        self.assertEqual(self.depo.getir(k["id"])["ad"], "Yeni ad")
        self.depo.sil(k["id"])
        self.assertIsNone(self.depo.getir(k["id"]))

    def test_ayni_bota_birden_cok_kayit_ve_ust_uste_yazma(self):
        k1 = self.depo.kaydet("smk-vadeli", "A", {"a": 1}, [])
        self.depo.kaydet("smk-vadeli", "B", {"a": 2}, [])
        self.assertEqual(len(self.depo.listele("smk-vadeli")), 2)
        self.depo.kaydet("smk-vadeli", "", {"a": 3}, ["k0"], kimlik=k1["id"])
        guncel = self.depo.getir(k1["id"])
        self.assertEqual((guncel["ad"], guncel["degerler"]["a"], guncel["pasif"]), ("A", 3, ["k0"]))
        self.assertEqual(len(self.depo.listele("smk-vadeli")), 2)

    def test_gecersiz_girdiler_reddedilir(self):
        with self.assertRaises(ayar_kayit.KayitHatasi):
            self.depo.kaydet("smk-vadeli", "   ", {}, [])
        with self.assertRaises(ayar_kayit.KayitHatasi):
            self.depo.kaydet("yok-bot", "A", {}, [])
        with self.assertRaises(ayar_kayit.KayitHatasi):
            self.depo.kaydet("smk-vadeli", "A", {"a": "sayı değil"}, [])
        with self.assertRaises(ayar_kayit.KayitHatasi):
            self.depo.sil("deadbeef")
        uzun = self.depo.kaydet("smk-vadeli", "x" * 500, {}, [])
        self.assertEqual(len(uzun["ad"]), ayar_kayit.EN_FAZLA_AD)

    def test_bozuk_dosya_yedeklenir_ve_sayfa_calisir(self):
        yol = Path(self.gecici.name) / ayar_kayit.DOSYA
        yol.parent.mkdir(parents=True)
        yol.write_text("{bozuk", encoding="utf-8")
        self.assertEqual(self.depo.listele("smk-vadeli"), [])
        self.assertTrue(yol.with_suffix(".bozuk").exists())

    def test_kayit_islemi_butun_sayilari_ve_pasifleri_saklar(self):
        istek = self._istek(p0=["7"], pasif=["k1", "iz_suren_stop"])
        kapali = s.kayit_islemi(self.depo, self._istek(pasif=["iz_suren_stop"]), "yeni", "", "Olmaz")
        self.assertFalse(kapali["ok"])   # tek çıkış yolu kapatılamaz: kayıt da açılmaz
        istek = self._istek(p0=["7"], pasif=["k1"])
        sonuc = s.kayit_islemi(self.depo, istek, "yeni", "", "Denemem")
        self.assertTrue(sonuc["ok"], sonuc["mesaj"])
        kayit = self.depo.getir(sonuc["id"])
        kural = a.kural_hazirla("smk-vadeli")
        self.assertEqual(set(kayit["degerler"]), {y for y, _ad, _e in a.tum_sayilar(kural)})   # bütün sayılar
        self.assertEqual(kayit["pasif"], ["k1"])
        self.assertEqual(kayit["degerler"][a.tum_sayilar(kural)[0][0]], 7)   # p0 = ilk sayı
        self.assertIn("Denemem", sonuc["liste"])

    def test_kayit_acilinca_degerler_ve_pasifler_forma_gelir(self):
        istek = self._istek(p0=["7"], pasif=["k1"])
        kimlik = s.kayit_islemi(self.depo, istek, "yeni", "", "Açılacak")["id"]
        acilis = s.sorgu_coz({"bot": ["smk-vadeli"], "kayit": [kimlik], "gun": ["5"]})
        html = s.ayar_sayfasi(acilis, a.VeriOnbellegi(), sahte_getir, SIMDI, depo=self.depo)
        self.assertIn('name="pasif" value="k1" checked', html)
        self.assertIn('value="7"', html)
        self.assertIn(f'name="kayit" value="{kimlik}"', html)
        self.assertIn("Üstüne yaz: Açılacak", html)

    def test_baska_botun_kaydi_acilmaz(self):
        kimlik = s.kayit_islemi(self.depo, self._istek(), "yeni", "", "SMK kaydı")["id"]
        istek = s.sorgu_coz({"bot": ["smdk-vadeli"], "kayit": [kimlik]})
        c = s.cozumle(istek, self.depo)
        self.assertIsNone(c["kayit"])

    def test_eski_sayfadan_kayit_gelmez(self):
        istek = s.sorgu_coz({"bot": ["smk-vadeli"], "bot0": ["smdk-vadeli"]})
        sonuc = s.kayit_islemi(self.depo, istek, "yeni", "", "X")
        self.assertFalse(sonuc["ok"])
        self.assertEqual(self.depo.listele("smk-vadeli"), [])

    def test_kayit_canli_kural_dosyasini_degistirmez(self):
        import json
        yol = Path(__file__).resolve().parent.parent / "karabasan" / "stratejiler" / "SMK.json"
        once = yol.read_bytes()
        s.kayit_islemi(self.depo, self._istek(p0=["7"], pasif=["k1"]), "yeni", "", "Güvenli")
        self.assertEqual(yol.read_bytes(), once)
        json.loads(once)


class KayitUcNoktasi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        klasor = sahte_sinav_klasoru(Path(cls.gecici.name) / "veri", datetime.now(timezone.utc))
        cls.klasor = klasor
        cls.sunucu = panel.sunucu_kur(klasor, adres="127.0.0.1", port=0)
        cls.adres = f"http://127.0.0.1:{cls.sunucu.server_address[1]}"
        threading.Thread(target=cls.sunucu.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()
        cls.sunucu.server_close()
        cls.gecici.cleanup()

    def _gonder(self, yol, govde, baslik=True):
        istek = urllib.request.Request(self.adres + yol, data=govde.encode("utf-8"), method="POST",
                                       headers={"Content-Type": "application/x-www-form-urlencoded",
                                                **({"X-Karabasan": "1"} if baslik else {})})
        return urllib.request.urlopen(istek, timeout=5)

    def test_baslik_olmadan_reddedilir(self):
        with self.assertRaises(urllib.error.HTTPError) as h:
            self._gonder("/ayar/kayit", "bot=smk-vadeli&eylem=yeni", baslik=False)
        self.assertEqual(h.exception.code, 403)

    def test_baska_adrese_yazilamaz(self):
        with self.assertRaises(urllib.error.HTTPError) as h:
            self._gonder("/ayar", "x=1")
        self.assertEqual(h.exception.code, 405)

    def test_kaydet_ve_dosyaya_yazilir(self):
        import json
        with self._gonder("/ayar/kayit", "bot=smk-vadeli&bot0=smk-vadeli&eylem=yeni&ad=Sunucu+denemesi&pasif=k1") as y:
            veri = json.loads(y.read().decode("utf-8"))
        self.assertTrue(veri["ok"], veri)
        dosya = self.klasor / "kayit" / "ayar_kayitlari.json"
        self.assertIn("Sunucu denemesi", dosya.read_text(encoding="utf-8"))
        with urllib.request.urlopen(self.adres + f"/ayar?bot=smk-vadeli&kayit={veri['id']}&gun=2", timeout=60) as y:
            self.assertIn("Sunucu denemesi", y.read().decode("utf-8"))

    def test_internet_kapisi_yalniz_bu_yola_yazma_izni_verir(self):
        metin = (Path(__file__).resolve().parent.parent / "araclar" / "internet.sh").read_text(encoding="utf-8")
        self.assertIn("not method GET HEAD", metin)
        self.assertIn("not path /ayar/kayit", metin)


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
        self.assertIn("script-src 'sha256-", baslik)   # yalnız bu sayfanın kendi betiği
        self.assertIn("connect-src 'self'", baslik)
        self.assertIn("default-src 'none'", baslik)

    def test_ana_sayfa_formu_hala_yasak(self):
        with urllib.request.urlopen(self.adres + "/", timeout=5) as y:
            baslik = y.headers["Content-Security-Policy"]
            metin = y.read().decode("utf-8")
        self.assertIn("form-action 'none'", baslik)
        self.assertIn('href="/ayar"', metin)


if __name__ == "__main__":
    unittest.main()
