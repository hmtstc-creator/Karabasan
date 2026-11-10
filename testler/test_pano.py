"""Yeni pano (10 Kasım 2026): Karabasan Uzayı hesabı, geçmiş test, ajan ve /api/ adresleri.

Buradaki ortamda Binance'e, Anthropic'e ve sunucunun mum dosyası biçimine (feather / pyarrow) erişim yoktur:
mumlar yapay, Anthropic yanıtı sahte, dosya okuyucu taklittir. Gerçek uyum sunucuda görülür.
"""

import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pandas as pd

from karabasan import ajan, ayar as a, ayar_kayit, gecmis_test as gt, pano, panel, uzay
from testler.test_ayar import SIMDI, sahte_getir
from testler.veri import sahte_sinav_klasoru, yapay_mumlar

KOK = Path(__file__).resolve().parent.parent
ANAHTAR = "sk-ant-" + "a" * 40
GEMINI = "AIzaSy" + "b" * 33


def mum_dosyalari(klasor: Path, coinler=("ETH", "SOL")) -> None:
    hedef = klasor / "data" / "binance" / "futures"
    hedef.mkdir(parents=True, exist_ok=True)
    for i, coin in enumerate(coinler):
        for dilim, dk in (("5m", 5), ("1d", 1440)):
            yapay_mumlar(adet=int(150 * 1440 / dk), dilim_dk=dk, tohum=3 + i, baslangic="2026-06-01", fiyat=100.0,
                         oynaklik=0.004 * (dk / 5) ** 0.5).to_pickle(hedef / f"{coin}_USDT_USDT-{dilim}-futures.feather")


def bekle(kosul, sure=60.0):
    son = time.time() + sure
    while time.time() < son:
        deger = kosul()
        if deger:
            return deger
        time.sleep(0.05)
    raise AssertionError("zaman doldu")


class Uzay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.depo = uzay.MumDeposu(sahte_getir)
        cls.veri = uzay.hesapla("smk-vadeli", None, None, cls.depo, SIMDI, coinler=["ETH", "SOL"])

    def test_bicim(self):
        v = self.veri
        self.assertEqual(v["adim"], 288)
        self.assertEqual(v["adim_dakika"], 5)
        self.assertFalse(v["degisti"])
        self.assertEqual(len(v["sartlar"]), len(a.kural_hazirla("smk-vadeli")["giris"]["hepsi"]))
        for c in v["coinler"]:
            self.assertEqual(len(c["eksik"]), 288)
            self.assertEqual(len(c["fiyat"]), 288)
            self.assertTrue(all(0 <= m < 2 ** len(v["sartlar"]) for m in c["eksik"]))
            self.assertNotIn("canli", c)

    def test_maske_sinyalle_tutarli(self):
        """Maskesi 0 olan mum, kural motorunun sinyal verdiği mumdur."""
        kural = a.kural_hazirla("smk-vadeli")
        bitis = uzay._yuvarla(SIMDI)
        df, ek = a.veri_topla(kural, "ETH", "vadeli", bitis, 1, self.depo.al, None)
        tablo = uzay.sinyal_uret(df, kural, ek)
        sinyal = tablo["sinyal"].to_numpy(dtype=bool)[-288:]
        self.assertEqual([m == 0 for m in self.veri["coinler"][0]["eksik"]], list(sinyal))

    def test_gelecege_bakmaz(self):
        """Altı saat sonra hesaplanınca, ortak mumların şart durumu değişmez."""
        sonra = uzay.hesapla("smk-vadeli", None, None, uzay.MumDeposu(sahte_getir), SIMDI + timedelta(hours=6), coinler=["ETH"])
        kayma = 6 * 12
        self.assertEqual(self.veri["coinler"][0]["eksik"][kayma:], sonra["coinler"][0]["eksik"][:-kayma])

    def test_denenen_ayar_ve_pasif(self):
        v = uzay.hesapla("smk-vadeli", {"giris.hepsi.2.sag": 40, "yok.boyle.yol": 5}, ["k4", "uydurma"], self.depo, SIMDI, coinler=["ETH"])
        self.assertTrue(v["degisti"])
        self.assertEqual(v["ayar"], {"degerler": {"giris.hepsi.2.sag": 40.0}, "pasif": ["k4"]})
        c = v["coinler"][0]
        self.assertTrue(all(not (m >> 4) & 1 for m in c["eksik"]))      # pasif şart hiçbir mumda eksik sayılmaz
        self.assertEqual(c["canli"], self.veri["coinler"][0]["eksik"])  # karşılaştırma canlı ayarın kendisi
        self.assertTrue(v["sartlar"][4]["pasif"])

    def test_gecersiz_ayar_reddedilir(self):
        with self.assertRaises(a.AyarHatasi):
            uzay.kural_kur("smk-vadeli", {"cikis.zarar_durdur_yuzde": -3}, [])
        with self.assertRaises(a.AyarHatasi):
            uzay.kural_kur("yok-bot", {}, [])

    def test_gruplar_ve_sema(self):
        kural = a.kural_hazirla("smk-vadeli")
        self.assertEqual([uzay.sart_grubu(kural, k) for k in kural["giris"]["hepsi"]], [0, 0, 0, 1, 2, 2, 2, 2, 1, 3])
        for bot in uzay.bot_adlari():
            sema = uzay.bot_semasi(bot)
            yollar = [s["yol"] for x in sema["sartlar"] for s in x["sayilar"]]
            yollar += [s["yol"] for alan in ("gostergeler", "giris_emri", "cikis", "pozisyon") for s in sema[alan]]
            self.assertEqual(sorted(yollar), sorted(y for y, _ad, _d in a.tum_sayilar(a.kural_hazirla(bot))))
            self.assertEqual(len(yollar), len(set(yollar)))
            json.dumps(sema)

    def test_bir_coin_dusunce_otekiler_gelir(self):
        def bozuk(parite, *kalan):
            if parite.startswith("SOL"):
                raise OSError("ağ yok")
            return sahte_getir(parite, *kalan)

        v = uzay.hesapla("smk-vadeli", None, None, uzay.MumDeposu(bozuk), SIMDI, coinler=["ETH", "SOL"])
        self.assertIn("eksik", v["coinler"][0])
        self.assertIn("hata", v["coinler"][1])

    def test_depo_yalniz_eksik_kismi_indirir(self):
        cagrilar = []

        def say(parite, piyasa, aralik, bas, son):
            cagrilar.append((aralik, bas, son))
            return sahte_getir(parite, piyasa, aralik, bas, son)

        depo = uzay.MumDeposu(say)
        bas = SIMDI - timedelta(days=2)
        ilk = depo.al("ETH/USDT", "vadeli", "5m", bas, SIMDI)
        depo.al("ETH/USDT", "vadeli", "5m", bas, SIMDI)                      # aynı pencere: yeni istek yok
        self.assertEqual(len(cagrilar), 1)
        ikinci = depo.al("ETH/USDT", "vadeli", "5m", bas, SIMDI + timedelta(minutes=30))
        self.assertEqual(len(cagrilar), 2)
        self.assertGreater(cagrilar[1][1], SIMDI - timedelta(minutes=10))   # yalnız son mumdan sonrası istendi
        self.assertEqual(len(ikinci), len(ilk) + 6)
        self.assertFalse(ikinci["date"].duplicated().any())


class GecmisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        cls.klasor = Path(cls.gecici.name)
        mum_dosyalari(cls.klasor)

        def ag_yok(*_):
            raise OSError("ağ yok")

        cls.y = gt.TestYoneticisi(cls.klasor, getir=ag_yok, oku=pd.read_pickle)

    @classmethod
    def tearDownClass(cls):
        cls.gecici.cleanup()

    def test_hazir_coinler(self):
        self.assertEqual(self.y.hazir_coinler(), ["ETH", "SOL"])

    def test_canli_ayar(self):
        r = self.y.simdi_calistir("smk-vadeli", {}, [], ["ETH", "SOL"], 90)
        self.assertNotIn("canli", r)                                   # ayar değişmedi: karşılaştırma yok
        self.assertEqual(r["ozet"]["islem"], r["secim"]["islem"] + r["dogrulama"]["islem"])
        self.assertEqual(r["ozet"]["islem"], sum(c["islem"] for c in r["coinler"]))
        self.assertEqual(sum(c["islem"] for c in r["ceyrekler"]), r["ozet"]["islem"])
        self.assertAlmostEqual(r["ozet"]["net_usdt"], sum(c["net_usdt"] for c in r["coinler"]), places=6)
        self.assertEqual(r["gun"], 90)
        json.dumps(r)                                                  # sayfaya olduğu gibi gider

    def test_denenen_ayar_canliyla_karsilastirilir(self):
        r = self.y.simdi_calistir("smk-vadeli", {"cikis.zarar_durdur_yuzde": 5}, ["k9"], ["ETH"], 30)
        self.assertIn("canli", r)
        self.assertEqual(r["ayar"], {"degerler": {"cikis.zarar_durdur_yuzde": 5.0}, "pasif": ["k9"]})
        canli = self.y.simdi_calistir("smk-vadeli", {}, [], ["ETH"], 30)
        self.assertEqual(r["canli"]["ozet"], canli["ozet"])            # aynı dönem, aynı coin, canlı kural
        self.assertGreaterEqual(r["ozet"]["en_kotu_yuzde"] or 0, -5.2)  # stop %5: tek işlemde daha büyük kayıp olmaz (komisyon payı)
        json.dumps(gt.ajan_ozeti(r))

    def test_verisi_olmayan_coin_not_dusulur(self):
        r = self.y.simdi_calistir("smk-vadeli", {}, [], ["ETH", "XRP"], 30)
        self.assertEqual([c["coin"] for c in r["coinler"]], ["ETH"])
        self.assertTrue(any("XRP" in n for n in r["notlar"]))
        with self.assertRaises(gt.TestHatasi):
            self.y.simdi_calistir("smk-vadeli", {}, [], ["XRP"], 30)

    def test_gecersiz_istek(self):
        for bot, coinler, gun in (("smk-vadeli", ["ETH"], 45), ("smk-vadeli", [], 30), ("yok", ["ETH"], 30),
                                  ("smk-vadeli", ["../x"], 30)):
            with self.assertRaises(gt.TestHatasi):
                self.y.baslat(bot, {}, [], coinler, gun)
        with self.assertRaises(gt.TestHatasi):
            self.y.baslat("smk-vadeli", {"cikis.zarar_durdur_yuzde": -1}, [], ["ETH"], 30)
        with self.assertRaises(gt.TestHatasi):
            self.y.baslat("smk2-vadeli", {"kaldirac": 3}, [], ["ETH"], 30)   # sınavda kaldıraç en çok 2 kat (6. kural)

    def test_arka_planda_calisir(self):
        kimlik = self.y.baslat("smk-vadeli", {}, [], ["ETH"], 30)
        durum = bekle(lambda: (d := self.y.durum(kimlik))["durum"] in ("bitti", "hata") and d)
        self.assertEqual(durum["durum"], "bitti")
        self.assertIn("ozet", durum["sonuc"])
        self.assertIsNone(self.y.durum("yok"))

    def test_canli_kural_dosyalari_degismez(self):
        klasor = KOK / "karabasan" / "stratejiler"
        once = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in klasor.glob("*.json")}
        self.y.simdi_calistir("smk2-vadeli", {"kaldirac": 1, "cikis.zarar_durdur_yuzde": 4}, ["zararda_ekleme"], ["ETH"], 30)
        self.assertEqual(once, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in klasor.glob("*.json")})


class SahteTestler:
    def __init__(self):
        self.cagrilar = []

    def hazir_coinler(self):
        return ["ETH", "SOL"]

    def simdi_calistir(self, bot, degerler, pasif, coinler, gun, ilerleme=None):
        self.cagrilar.append((bot, dict(degerler), list(pasif), list(coinler), gun))
        bos = {"islem": 40, "net_usdt": -3.0}
        return {"baslangic": "2026-08-01", "bitis": "2026-11-01 00:00", "gun": gun, "ozet": bos, "secim": bos, "dogrulama": bos,
                "dogrulama_baslangic": "2026-10-01", "ceyrekler": [], "coinler": [], "notlar": [], "uyarilar": []}


def metin_yaniti(metin, neden="end_turn"):
    return {"stop_reason": neden, "usage": {"input_tokens": 1000, "output_tokens": 100}, "content": [{"type": "text", "text": metin}]}


class AjanTesti(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.klasor = Path(self.gecici.name)
        self.testler = SahteTestler()
        self.depo = ayar_kayit.Depo(self.klasor)
        self.istekler = []
        self.yanitlar = []

        def cagir(govde, anahtar, **_):
            self.istekler.append((json.loads(json.dumps(govde)), anahtar))
            return self.yanitlar.pop(0)

        self.oa_istekler = []
        self.oa_yanitlar = []
        self.model_listesi = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3-flash-preview", "gemini-2.5-pro"]

        def oa(govde, anahtar, adres, ad="", **_):
            self.oa_istekler.append((json.loads(json.dumps(govde)), anahtar, adres))
            yanit = self.oa_yanitlar.pop(0)
            if isinstance(yanit, Exception):
                raise yanit
            return yanit

        def modeller(anahtar, adres, ad=""):
            return list(self.model_listesi)

        self.ajan = ajan.Ajan(self.klasor, ozet_al=lambda: {"botlar": [], "toplam": {}}, testler=self.testler,
                              kayitlar=self.depo, saat=lambda: SIMDI, cagir=cagir, oa_cagir=oa, modeller=modeller)

    def tearDown(self):
        self.gecici.cleanup()

    def sor(self, mesaj, baglam=None):
        kimlik = self.ajan.sor(mesaj, baglam)
        return bekle(lambda: (d := self.ajan.is_durumu(kimlik))["durum"] != "calisiyor" and d)

    def test_anahtar(self):
        self.assertIsNone(ajan.anahtar_oku(self.klasor))
        with self.assertRaises(ajan.AjanHatasi):
            ajan.anahtar_yaz(self.klasor, "parola123")
        with self.assertRaises(ajan.AjanHatasi):
            self.ajan.sor("merhaba")                                   # anahtar yokken soru alınmaz
        ajan.anahtar_yaz(self.klasor, "  " + ANAHTAR + "\n")
        self.assertEqual(ajan.anahtar_oku(self.klasor), ANAHTAR)
        yol = self.klasor / "gizli" / "ajan_anahtar"
        self.assertEqual(os.stat(yol).st_mode & 0o777, 0o600)
        self.assertNotIn("kayit", yol.parts)                           # sunucudaki oturumun onaysız okuduğu klasörde değil
        self.ajan.ayar_yaz("anthropic")
        self.assertNotIn(ANAHTAR, json.dumps(self.ajan.durum()))
        self.assertTrue(self.ajan.durum()["anahtar_var"])
        ajan.anahtar_sil(self.klasor)
        self.assertFalse(self.ajan.durum()["anahtar_var"])

    def test_gizli_klasor_depoya_ve_sunucu_oturumuna_kapali(self):
        self.assertIn("user_data/gizli/", (KOK / ".gitignore").read_text(encoding="utf-8").split())
        ayarlar = json.loads((KOK / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertIn("Read(./user_data/gizli/**)", ayarlar["permissions"]["deny"])

    def test_arac_dongusu_kayit_ve_hafiza(self):
        ajan.anahtar_yaz(self.klasor, ANAHTAR)
        self.ajan.ayar_yaz("anthropic")
        dusunme = {"type": "thinking", "thinking": "", "signature": "imza"}
        self.yanitlar = [
            {"stop_reason": "tool_use", "usage": {"input_tokens": 2000, "output_tokens": 50}, "content": [
                dusunme, {"type": "tool_use", "id": "t1", "name": "gecmis_testi",
                          "input": {"bot": "smk-vadeli", "degerler": {"cikis.zarar_durdur_yuzde": 6}, "gun": 90}}]},
            {"stop_reason": "tool_use", "usage": {"input_tokens": 2500, "output_tokens": 50}, "content": [
                {"type": "tool_use", "id": "t2", "name": "ayar_kaydet", "input": {"bot": "smk-vadeli", "ad": "Stop 6", "degerler": {"cikis.zarar_durdur_yuzde": 6}}},
                {"type": "tool_use", "id": "t3", "name": "ders_yaz", "input": {"metin": "Ahmet önce riski görmek istiyor."}},
                {"type": "tool_use", "id": "t4", "name": "ayar_kaydet", "input": {"bot": "smk-vadeli", "ad": "Bozuk", "degerler": {"cikis.zarar_durdur_yuzde": -1}}}]},
            metin_yaniti("Stopu **%6** yapıp denedim ve kaydettim."),
        ]
        d = self.sor("Stopu küçültelim mi?", {"ekran": "Ayar ve geçmiş test", "bot": "smk-vadeli"})
        self.assertEqual(d["durum"], "bitti")
        self.assertIn("%6", d["yanit"])
        self.assertEqual(self.testler.cagrilar, [("smk-vadeli", {"cikis.zarar_durdur_yuzde": 6}, [], ["ETH", "SOL"], 90)])
        kayitlar = self.depo.listele("smk-vadeli")
        self.assertEqual([(k["ad"], k["degerler"]) for k in kayitlar], [("Ajan: Stop 6", {"cikis.zarar_durdur_yuzde": 6})])
        self.assertEqual(d["eylemler"], [{"tur": "kayit", "bot": "smk-vadeli", "kimlik": kayitlar[0]["id"], "ad": "Ajan: Stop 6"}])

        ilk, _ = self.istekler[0]
        self.assertEqual(ilk["model"], "claude-opus-5-5")
        self.assertEqual(ilk["output_config"], {"effort": "low"})
        for yasak in ("temperature", "top_p", "top_k", "thinking", "tool_choice"):
            self.assertNotIn(yasak, ilk)
        self.assertEqual(self.istekler[0][1], ANAHTAR)
        self.assertNotIn(ANAHTAR, json.dumps([g for g, _ in self.istekler]))
        # Araç turunda yanıtın içeriği (düşünme bloğu dahil) değiştirilmeden geri gönderilir.
        ikinci = self.istekler[1][0]["messages"]
        self.assertEqual(ikinci[1], {"role": "assistant", "content": self.istekler and [dusunme, {"type": "tool_use", "id": "t1", "name": "gecmis_testi", "input": {"bot": "smk-vadeli", "degerler": {"cikis.zarar_durdur_yuzde": 6}, "gun": 90}}]})
        self.assertEqual(ikinci[2]["content"][0]["tool_use_id"], "t1")
        ucuncu = self.istekler[2][0]["messages"][4]["content"]
        self.assertEqual([s["tool_use_id"] for s in ucuncu], ["t2", "t3", "t4"])   # üç sonuç tek mesajda
        self.assertTrue(ucuncu[2].get("is_error"))                                  # geçersiz ayar kaydedilmedi, hata modele söylendi

        # Hafıza: arşiv dosyaları ve bir sonraki soruda ders ile önceki konuşma.
        kok = self.klasor / "kayit" / "ajan"
        gun = (kok / "konusmalar" / "2026-11-07.md").read_text(encoding="utf-8")
        self.assertIn("· Ahmet", gun)
        self.assertIn("Stopu küçültelim mi?", gun)
        self.assertIn("· Ajan", gun)
        self.assertIn("Ahmet önce riski görmek istiyor.", (kok / "dersler.md").read_text(encoding="utf-8"))
        self.assertIn("konusmalar/2026-11-07.md", (kok / "README.md").read_text(encoding="utf-8"))
        self.yanitlar = [metin_yaniti("Hatırlıyorum.")]
        self.sor("Dün ne konuşmuştuk?")
        giris = self.istekler[-1][0]["messages"][0]["content"]
        self.assertIn("Ahmet önce riski görmek istiyor.", giris)
        self.assertIn("Stopu küçültelim mi?", giris)
        self.assertEqual(giris.count("Dün ne konuşmuştuk?"), 1)       # yeni soru "önceki konuşma"da yinelenmez
        self.assertEqual(self.ajan.arsiv.ara("riski görmek")[0].split(":")[0], "dersler")
        self.assertEqual(self.ajan.durum()["bugun_mesaj"], 2)
        self.assertGreater(self.ajan.durum()["bugun_yaklasik_usd"], 0)

    def test_ret_sinir_ve_hata(self):
        ajan.anahtar_yaz(self.klasor, ANAHTAR)
        self.ajan.ayar_yaz("anthropic")
        self.yanitlar = [{"stop_reason": "refusal", "usage": {}, "content": []}]
        self.assertIn("yanıtlayamıyorum", self.sor("x")["yanit"])
        self.yanitlar = [{"stop_reason": "tool_use", "usage": {}, "content": [{"type": "tool_use", "id": f"t{i}", "name": "arsivde_ara", "input": {"sorgu": "stop"}}]}
                         for i in range(ajan.EN_FAZLA_TUR + 1)]
        self.assertIn("çok fazla adım", self.sor("y")["yanit"])         # sonsuz araç döngüsü olmaz
        with self.assertRaises(ajan.AjanHatasi):
            self.ajan.sor("z" * (ajan.EN_FAZLA_MESAJ + 1))
        self.ajan.arsiv.sayac_artir(mesaj=ajan.GUNLUK_MESAJ_SINIRI)
        with self.assertRaises(ajan.AjanHatasi):
            self.ajan.sor("bir daha")                                  # günlük sınır

    def test_araclar_yalniz_okur_ya_da_kayit_yazar(self):
        adlar = {t["name"] for t in ajan.ARACLAR}
        self.assertEqual(adlar, {"canli_sonuclar", "parametreler", "uzay_durumu", "gecmis_testi", "ayar_kaydet",
                                 "kayitlari_listele", "ders_yaz", "arsivde_ara", "tum_kayitlar", "rapor_yaz"})
        kaynak = (KOK / "karabasan" / "ajan.py").read_text(encoding="utf-8")
        for yasak in ("subprocess", "os.system", "dry_run", "docker", "create_order"):
            self.assertNotIn(yasak, kaynak)


    # -- ücretsiz sağlayıcı (Gemini) ve geliştirme raporu ------------------------
    def test_varsayilan_saglayici_gemini_ve_anahtarlar_ayri(self):
        self.assertEqual(self.ajan.ayar()["saglayici"], "gemini")
        d = self.ajan.durum()
        self.assertTrue(d["ucretsiz"])
        self.assertFalse(d["anahtar_var"])
        with self.assertRaises(ajan.AjanHatasi):
            ajan.anahtar_yaz(self.klasor, ANAHTAR, "gemini")              # Claude anahtarı Gemini'ye yazılmaz
        with self.assertRaises(ajan.AjanHatasi):
            ajan.anahtar_yaz(self.klasor, "sk-" + "c" * 32, "gemini")
        ajan.anahtar_yaz(self.klasor, GEMINI, "gemini")
        ajan.anahtar_yaz(self.klasor, "sk-" + "d" * 32, "deepseek")
        self.assertEqual(ajan.anahtar_oku(self.klasor, "gemini"), GEMINI)
        self.assertIsNone(ajan.anahtar_oku(self.klasor, "anthropic"))
        self.assertEqual(os.stat(self.klasor / "gizli" / "ajan_anahtar_gemini").st_mode & 0o777, 0o600)
        self.assertNotIn(GEMINI, json.dumps(self.ajan.durum()))
        self.assertTrue(self.ajan.durum()["anahtar_var"])
        with self.assertRaises(ajan.AjanHatasi):
            self.ajan.ayar_yaz("baska")
        with self.assertRaises(ajan.AjanHatasi):
            self.ajan.ayar_yaz("gemini", "../x y")
        self.assertEqual(self.ajan.ayar_yaz("gemini", "models/gemini-9-flash")["model"]["gemini"], "gemini-9-flash")

    def test_model_secimi(self):
        self.assertEqual(ajan.gemini_model_sec(["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-2.5-flash-lite"]), "gemini-2.5-flash")
        self.assertEqual(ajan.gemini_model_sec(["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.5-flash-image"]), "gemini-3.5-flash")
        self.assertEqual(ajan.gemini_model_sec(["gemini-3-flash-preview", "gemini-2.5-pro"]), "gemini-3-flash-preview")
        self.assertIsNone(ajan.gemini_model_sec(["text-embedding-004"]))
        for arac in ajan.araclar_oa():
            metin = json.dumps(arac)
            self.assertNotIn("additionalProperties", metin)                # bazı sağlayıcılar reddeder
            self.assertNotIn('"enum"', metin)

    def test_gemini_arac_dongusu_ve_rapor(self):
        ajan.anahtar_yaz(self.klasor, GEMINI, "gemini")
        self.depo.kaydet("smk-vadeli", "Ahmet stop 7", {"cikis.zarar_durdur_yuzde": 7}, ["k9"])
        imzali = {"id": "c1", "type": "function", "function": {"name": "tum_kayitlar", "arguments": "{}"},
                  "extra_content": {"google": {"thought_signature": "imza"}}}
        rapor_metni = "## Özet\nKayıtlarını grupladım; stop 7 adayı doğrulamada canlıdan iyi değil. Öneri yok."
        self.oa_yanitlar = [
            ajan.AjanHatasi("çaba tanınmadı", 400),                        # model çaba ayarını tanımazsa onsuz yeniden denenir
            {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [imzali]}}],
             "usage": {"prompt_tokens": 900, "completion_tokens": 40}},
            {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c2", "type": "function", "function": {"name": "gecmis_testi", "arguments": json.dumps(
                    {"bot": "smk-vadeli", "degerler": [{"yol": "cikis.zarar_durdur_yuzde", "deger": 7}], "pasif": ["k9"], "gun": 90})}},
                {"id": "c3", "type": "function", "function": {"name": "rapor_yaz", "arguments": json.dumps({"baslik": "Geliştirme raporu", "metin": rapor_metni})}},
                {"id": "c4", "type": "function", "function": {"name": "ayar_kaydet", "arguments": "{bozuk"}}]}}]},
            {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Raporu yazdım: öneri yok."}}]},
        ]
        d = self.sor("Geliştirme raporu hazırla")
        self.assertEqual(d["durum"], "bitti", d.get("hata"))
        self.assertEqual(d["yanit"], "Raporu yazdım: öneri yok.")
        ilk, anahtar, adres = self.oa_istekler[0]
        self.assertEqual(anahtar, GEMINI)
        self.assertIn("generativelanguage.googleapis.com", adres)
        self.assertEqual(ilk["model"], "gemini-2.5-flash")                 # kararlı en yeni flash
        self.assertEqual(ilk["reasoning_effort"], "low")
        self.assertNotIn("reasoning_effort", self.oa_istekler[1][0])
        self.assertEqual(ilk["messages"][0]["role"], "system")
        mesajlar = self.oa_istekler[2][0]["messages"]
        self.assertEqual(mesajlar[2]["tool_calls"][0]["extra_content"], {"google": {"thought_signature": "imza"}})  # imza korunur
        kayitlar = json.loads(mesajlar[3]["content"])
        self.assertEqual(kayitlar[0]["degisiklikler"], [{"yol": "cikis.zarar_durdur_yuzde", "ad": "Stop %", "canli": 9.0, "kayit": 7}])
        sonuclar = self.oa_istekler[3][0]["messages"][-3:]
        self.assertEqual([m["tool_call_id"] for m in sonuclar], ["c2", "c3", "c4"])
        self.assertTrue(sonuclar[2]["content"].startswith("HATA"))         # bozuk girdi modele hata olarak döner
        self.assertEqual(self.testler.cagrilar, [("smk-vadeli", {"cikis.zarar_durdur_yuzde": 7}, ["k9"], ["ETH", "SOL"], 90)])
        self.assertEqual(self.depo.listele("smk-vadeli")[0]["ad"], "Ahmet stop 7")   # Ahmet'in kaydı değişmedi
        raporlar = self.ajan.arsiv.raporlar()
        self.assertEqual(len(raporlar), 1)
        self.assertEqual(d["eylemler"], [{"tur": "rapor", "ad": raporlar[0]["ad"], "baslik": "Geliştirme raporu"}])
        metin = self.ajan.arsiv.gun_oku("rapor:" + raporlar[0]["ad"])
        self.assertIn("canlı botlar değişmedi", metin)
        self.assertIn("Öneri yok.", metin)
        self.assertIn("raporlar/", (self.klasor / "kayit" / "ajan" / "README.md").read_text(encoding="utf-8"))
        self.assertIsNone(self.ajan.arsiv.gun_oku("rapor:../../gizli/ajan_anahtar"))
        self.assertTrue(self.ajan.arsiv.ara("stop 7 adayı"))
        self.assertEqual(self.ajan.durum()["bugun_token"], 940)
        self.assertIsNone(self.ajan.durum()["bugun_yaklasik_usd"])        # ücretsiz katmanda dolar tahmini yok

    def test_gemini_model_kaldirilinca_listeden_yenisi(self):
        ajan.anahtar_yaz(self.klasor, GEMINI, "gemini")
        bitti = {"choices": [{"finish_reason": "stop", "message": {"content": "tamam"}}]}
        self.oa_yanitlar = [bitti]
        self.sor("a")
        self.model_listesi = ["gemini-3-flash"]                             # eski model kaldırıldı
        self.ajan._oto_model["gemini"] = (0.0, "gemini-2.5-flash")          # bellekteki ad eskidi
        self.oa_yanitlar = [ajan.AjanHatasi("yok", 404), bitti]
        self.ajan._oto_model["gemini"] = (time.monotonic(), "gemini-2.5-flash")
        self.assertEqual(self.sor("b")["yanit"], "tamam")
        self.assertEqual(self.oa_istekler[-1][0]["model"], "gemini-3-flash")
        self.ajan.ayar_yaz("gemini", "gemini-elle")                           # elle yazılan ad kendiliğinden değişmez
        self.oa_yanitlar = [ajan.AjanHatasi("yok", 404)]
        self.assertEqual(self.sor("c")["durum"], "hata")
        self.assertEqual(self.oa_istekler[-1][0]["model"], "gemini-elle")

    def test_kota_dolunca_anlasilir_hata(self):
        ajan.anahtar_yaz(self.klasor, GEMINI, "gemini")
        self.oa_yanitlar = [ajan.AjanHatasi("Google Gemini kotası doldu ya da çok sık soru soruldu. Biraz sonra yeniden dene.", 429)]
        d = self.sor("x")
        self.assertEqual(d["durum"], "hata")
        self.assertIn("kotası", d["hata"])


class OABaglantisi(unittest.TestCase):
    """oa_cagir / oa_modeller sahte bir sunucuya karşı."""

    @classmethod
    def setUpClass(cls):
        cls.gelen = []
        cls.kodlar = []

        class Isleyici(BaseHTTPRequestHandler):
            def _yaz(self, kod, veri):
                govde = json.dumps(veri).encode()
                self.send_response(kod)
                self.send_header("Content-Length", str(len(govde)))
                self.end_headers()
                self.wfile.write(govde)

            def do_POST(self):  # noqa: N802
                cls.gelen.append((dict(self.headers), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                kod = cls.kodlar.pop(0) if cls.kodlar else 200
                self._yaz(kod, {"choices": [{"message": {"content": "ok"}}]} if kod == 200 else [{"error": {"message": "kota"}}])

            def do_GET(self):  # noqa: N802
                cls.gelen.append((dict(self.headers), None))
                self._yaz(200, {"object": "list", "data": [{"id": "models/gemini-2.5-flash"}, {"id": "models/gemini-2.5-pro"}]})

            def log_message(self, *_):
                pass

        cls.sunucu = HTTPServer(("127.0.0.1", 0), Isleyici)
        cls.adres = f"http://127.0.0.1:{cls.sunucu.server_port}"
        threading.Thread(target=cls.sunucu.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()
        cls.sunucu.server_close()

    def test_istek_ve_hatalar(self):
        self.assertEqual(ajan.oa_cagir({"model": "m"}, GEMINI, self.adres + "/c", "Gemini", bekleme=0)["choices"][0]["message"]["content"], "ok")
        self.assertEqual({k.lower(): v for k, v in self.gelen[-1][0].items()}["authorization"], "Bearer " + GEMINI)
        self.assertEqual(ajan.oa_modeller(GEMINI, self.adres + "/m", "Gemini"), ["gemini-2.5-flash", "gemini-2.5-pro"])
        self.kodlar[:] = [429, 429]
        with self.assertRaises(ajan.AjanHatasi) as hata:
            ajan.oa_cagir({}, GEMINI, self.adres + "/c", "Google Gemini", bekleme=0)
        self.assertEqual(hata.exception.kod, 429)
        self.assertIn("kotası", str(hata.exception))
        self.kodlar[:] = [400]                                            # Google hata gövdesi liste olabilir
        with self.assertRaises(ajan.AjanHatasi) as hata:
            ajan.oa_cagir({}, GEMINI, self.adres + "/c", "Google Gemini", bekleme=0)
        self.assertEqual(hata.exception.kod, 400)
        self.assertIn("kota", str(hata.exception))
        self.kodlar[:] = [403]
        with self.assertRaises(ajan.AjanHatasi) as hata:
            ajan.oa_cagir({}, GEMINI, self.adres + "/c", "Google Gemini", bekleme=0)
        self.assertIn("anahtarı kabul edilmedi", str(hata.exception))


class AnthropicBaglantisi(unittest.TestCase):
    """api_cagir sahte bir sunucuya karşı: başlıklar, hata kodları, yeniden deneme."""

    @classmethod
    def setUpClass(cls):
        cls.gelen = []
        cls.kodlar = []

        class Isleyici(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                govde = self.rfile.read(int(self.headers["Content-Length"]))
                cls.gelen.append((dict(self.headers), json.loads(govde)))
                kod = cls.kodlar.pop(0) if cls.kodlar else 200
                yanit = json.dumps(metin_yaniti("tamam") if kod == 200 else {"error": {"message": "olmadı"}}).encode()
                self.send_response(kod)
                self.send_header("Content-Length", str(len(yanit)))
                self.end_headers()
                self.wfile.write(yanit)

            def log_message(self, *_):
                pass

        cls.sunucu = HTTPServer(("127.0.0.1", 0), Isleyici)
        cls.adres = f"http://127.0.0.1:{cls.sunucu.server_port}/v1/messages"
        threading.Thread(target=cls.sunucu.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()
        cls.sunucu.server_close()

    def test_basliklar(self):
        yanit = ajan.api_cagir({"model": ajan.MODEL}, ANAHTAR, self.adres, bekleme=0)
        self.assertEqual(yanit["content"][0]["text"], "tamam")
        baslik, govde = self.gelen[-1]
        kucuk = {k.lower(): v for k, v in baslik.items()}
        self.assertEqual(kucuk["x-api-key"], ANAHTAR)
        self.assertEqual(kucuk["anthropic-version"], "2026-10-21")
        self.assertEqual(govde["model"], "claude-opus-5-5")

    def test_hata_kodlari(self):
        self.kodlar[:] = [401]
        with self.assertRaises(ajan.AjanHatasi) as hata:
            ajan.api_cagir({}, ANAHTAR, self.adres, bekleme=0)
        self.assertIn("anahtar", str(hata.exception).lower())
        self.kodlar[:] = [529, 200]                                    # yoğunluk: bir kez yeniden dener
        self.assertEqual(ajan.api_cagir({}, ANAHTAR, self.adres, bekleme=0)["stop_reason"], "end_turn")
        self.kodlar[:] = [500, 500]
        with self.assertRaises(ajan.AjanHatasi):
            ajan.api_cagir({}, ANAHTAR, self.adres, bekleme=0)


class Sunucu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        cls.klasor = Path(cls.gecici.name)
        sahte_sinav_klasoru(cls.klasor, SIMDI)
        mum_dosyalari(cls.klasor, ("ETH",))
        cls.sunucu = panel.sunucu_kur(cls.klasor, adres="127.0.0.1", port=0, pano_ayari={
            "getir": sahte_getir, "saat": lambda: SIMDI, "oku": pd.read_pickle,
            "cagir": lambda govde, anahtar, **_: metin_yaniti("Merhaba Ahmet."),
            "oa_cagir": lambda govde, anahtar, adres, ad="", **_: {"choices": [{"finish_reason": "stop", "message": {"content": "Merhaba Ahmet."}}]},
            "modeller": lambda anahtar, adres, ad="": ["gemini-2.5-flash"]})
        cls.adres = f"http://127.0.0.1:{cls.sunucu.server_port}"
        threading.Thread(target=cls.sunucu.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()
        cls.sunucu.server_close()
        cls.gecici.cleanup()

    def al(self, yol):
        with urllib.request.urlopen(self.adres + yol, timeout=60) as y:
            return y.status, dict(y.headers), y.read()

    def gonder(self, yol, veri, baslik=True):
        istek = urllib.request.Request(self.adres + yol, data=json.dumps(veri).encode("utf-8"), method="POST",
                                       headers={"Content-Type": "application/json", **({"X-Karabasan": "1"} if baslik else {})})
        try:
            with urllib.request.urlopen(istek, timeout=60) as y:
                return y.status, json.loads(y.read())
        except urllib.error.HTTPError as hata:
            govde = hata.read()
            try:
                return hata.code, json.loads(govde)
            except ValueError:
                return hata.code, {}

    def test_ana_sayfa_pano_ve_sonuclar_sekmesi_butun_ekranlari_tasir(self):
        """10 Kasım 2026 akşamı, Ahmet: eski ve yeni bütün ekranlar tek sitede, panonun biçiminde."""
        ana = self.al("/")[2].decode("utf-8")
        self.assertIn('id="g-sonuc"', ana)
        self.assertIn('src="/klasik?gomulu=1"', ana)
        self.assertIn('href="#sonuc"', ana)
        liste = json.loads(self.al("/api/ekranlar")[2])
        kimlikler = [e["kimlik"] for e in liste]
        for k in ("ana", "rapor", "botlar", "analiz", "risk", "rejim", "likidite", "guven", "disiplin"):
            self.assertIn(k, kimlikler)
        _kod, baslik, govde = self.al("/klasik?gomulu=1")
        metin = govde.decode("utf-8")
        self.assertIn('class="gomulu"', metin)
        self.assertIn('<section id="rapor"', metin)
        self.assertEqual(baslik["X-Frame-Options"], "SAMEORIGIN")        # yalnız kendi panosunun içinde
        self.assertIn("frame-ancestors 'self'", baslik["Content-Security-Policy"])
        self.assertNotIn(' href="/klasik', metin.replace('target="_top" href="/', ""))
        _kod, baslik, _govde = self.al("/klasik")                          # tek başına hali çerçeveye girmez
        self.assertEqual(baslik["X-Frame-Options"], "DENY")
        self.assertIn("frame-src 'self'", self.al("/")[1]["Content-Security-Policy"])

    def test_pano_ve_izinler(self):
        kod, baslik, govde = self.al("/")
        metin = govde.decode("utf-8")
        self.assertEqual(kod, 200)
        self.assertIn('id="g-uzay"', metin)
        self.assertIn('id="g-lab"', metin)
        self.assertIn('id="dok"', metin)                               # ajan çubuğu her görünümde altta
        izin = baslik["Content-Security-Policy"]
        self.assertIn("default-src 'none'", izin)
        self.assertIn("script-src 'self'", izin)
        self.assertNotIn("unsafe-inline'; font", izin.split("script-src")[1].split(";")[0])
        self.assertIn("frame-ancestors 'none'", izin)
        self.assertNotIn("<script>", metin)                            # satır içi betik yok
        for dosya in ("pano.js", "pano.css", "three.min.js", "bricolage.woff2"):
            self.assertEqual(self.al("/s/" + dosya)[0], 200)

    def test_dis_kaynak_yok(self):
        for ad in ("pano.html", "pano.css", "pano.js"):
            metin = (pano.STATIK / ad).read_text(encoding="utf-8")
            self.assertNotIn("http://", metin.replace("http://www.w3.org", ""))
            self.assertNotIn("https://", metin)
        self.assertNotIn("sk-ant-a", (pano.STATIK / "pano.js").read_text(encoding="utf-8"))

    def test_bilinmeyen_dosya_ve_klasor_disi(self):
        for yol in ("/s/yok.js", "/s/../panel.py", "/s/..%2Fpanel.py", "/s/.gizli", "/api/yok"):
            with self.assertRaises(urllib.error.HTTPError) as hata:
                self.al(yol)
            self.assertEqual(hata.exception.code, 404)

    def test_eski_sayfa_klasikte(self):
        metin = self.al("/klasik")[2].decode("utf-8")
        self.assertIn("KARABASAN", metin)
        self.assertIn('data-ekran', metin)

    def test_ozet_bot_ve_uzay(self):
        ozet = json.loads(self.al("/api/ozet")[2])
        self.assertEqual(len(ozet["botlar"]), 4)
        self.assertIn("gunluk", ozet)
        sema = json.loads(self.al("/api/bot?bot=smk2-vadeli")[2])
        self.assertEqual(sema["hazir_coinler"], ["ETH"])
        self.assertEqual(sema["donemler"], [30, 90, 180, 365])
        self.assertIn("kaldirac", [s["yol"] for s in sema["pozisyon"]])
        with self.assertRaises(urllib.error.HTTPError) as hata:
            self.al("/api/bot?bot=yok")
        self.assertEqual(hata.exception.code, 404)
        with self.assertRaises(urllib.error.HTTPError) as hata:
            self.al("/api/uzay?bot=smk-vadeli&ayar=" + urllib.request.quote('{"degerler":{"cikis.zarar_durdur_yuzde":-4}}'))
        self.assertEqual(hata.exception.code, 400)

    def test_yazma_basliksiz_reddedilir(self):
        self.assertEqual(self.gonder("/api/test", {"bot": "smk-vadeli"}, baslik=False)[0], 403)
        self.assertEqual(self.gonder("/api/ajan/anahtar", {"anahtar": ANAHTAR}, baslik=False)[0], 403)
        self.assertEqual(self.gonder("/api/yok", {})[0], 405)
        self.assertEqual(self.gonder("/baska", {})[0], 405)
        istek = urllib.request.Request(self.adres + "/api/test", data=b"x" * (pano.EN_FAZLA_GOVDE + 1), method="POST",
                                       headers={"X-Karabasan": "1"})
        with self.assertRaises(urllib.error.HTTPError) as hata:
            urllib.request.urlopen(istek, timeout=5)
        self.assertEqual(hata.exception.code, 413)

    def test_gecmis_test_ve_kayit(self):
        kod, v = self.gonder("/api/test", {"bot": "smk-vadeli", "degerler": {"cikis.zarar_durdur_yuzde": 6}, "pasif": [], "coinler": ["ETH"], "gun": 30})
        self.assertEqual(kod, 200)
        durum = bekle(lambda: (d := json.loads(self.al("/api/test?id=" + v["id"])[2]))["durum"] in ("bitti", "hata") and d)
        self.assertEqual(durum["durum"], "bitti")
        self.assertIn("canli", durum["sonuc"])
        self.assertEqual(self.gonder("/api/test", {"bot": "smk-vadeli", "coinler": ["ETH"], "gun": 7})[0], 400)

        kod, v = self.gonder("/api/kayit", {"eylem": "kaydet", "bot": "smk-vadeli", "ad": "Deneme", "degerler": {"cikis.zarar_durdur_yuzde": 6}, "pasif": ["k9"]})
        self.assertEqual(kod, 200)
        kimlik = v["kayit"]["id"]
        self.assertEqual(v["kayit"]["degerler"], {"cikis.zarar_durdur_yuzde": 6})
        self.assertEqual(self.gonder("/api/kayit", {"eylem": "kaydet", "bot": "smk-vadeli", "ad": "Bozuk", "degerler": {"cikis.zarar_durdur_yuzde": -6}})[0], 400)
        self.assertEqual(self.gonder("/api/kayit", {"eylem": "adlandir", "bot": "smk-vadeli", "kimlik": kimlik, "ad": "Yeni ad"})[1]["kayit"]["ad"], "Yeni ad")
        self.assertEqual(self.gonder("/api/kayit", {"eylem": "sil", "bot": "smk-vadeli", "kimlik": kimlik})[1]["kayitlar"], [])

    def test_ajan_uctan_uca(self):
        self.assertEqual(self.gonder("/api/ajan", {"mesaj": "selam"})[0], 400)        # anahtar yok
        self.assertEqual(self.gonder("/api/ajan/anahtar", {"anahtar": "yanlis"})[0], 400)
        self.assertEqual(self.gonder("/api/ajan/anahtar", {"anahtar": ANAHTAR})[0], 400)          # varsayılan Gemini: Claude anahtarı olmaz
        kod, durum = self.gonder("/api/ajan/anahtar", {"anahtar": GEMINI, "saglayici": "gemini"})
        self.assertEqual(kod, 200)
        self.assertTrue(durum["anahtar_var"])
        self.assertEqual(durum["saglayici"], "gemini")
        self.assertNotIn(GEMINI, json.dumps(durum))
        self.assertEqual(self.gonder("/api/ajan/ayar", {"saglayici": "yok"})[0], 400)
        kod, v = self.gonder("/api/ajan", {"mesaj": "selam", "baglam": {"ekran": "Uzay", "bot": "smk-vadeli"}})
        self.assertEqual(kod, 200)
        d = bekle(lambda: (x := json.loads(self.al("/api/ajan?id=" + v["id"])[2]))["durum"] != "calisiyor" and x)
        self.assertEqual(d["yanit"], "Merhaba Ahmet.")
        gecmis = bekle(lambda: len(m := json.loads(self.al("/api/ajan/gecmis")[2])["mesajlar"]) == 2 and m)
        self.assertEqual([m["rol"] for m in gecmis], ["ahmet", "ajan"])
        arsiv = json.loads(self.al("/api/ajan/arsiv")[2])
        self.assertEqual(arsiv["gunler"][0]["gun"], "2026-11-07")
        self.assertIn("selam", json.loads(self.al("/api/ajan/arsiv?gun=2026-11-07")[2])["metin"])
        for yol in ("/api/ajan/durum", "/api/ajan/gecmis", "/api/ajan/arsiv", "/api/ozet"):
            self.assertNotIn(GEMINI.encode(), self.al(yol)[2])                        # anahtar hiçbir yanıtta görünmez
        self.assertEqual(json.loads(self.al("/api/ajan/arsiv")[2])["raporlar"], [])
        self.assertFalse(self.gonder("/api/ajan/anahtar", {"sil": True, "saglayici": "gemini"})[1]["anahtar_var"])

    def test_pano_acilamazsa_eski_sayfa_ana_sayfada_kalir(self):
        from unittest import mock

        with mock.patch.object(pano, "Pano", side_effect=RuntimeError("açılamadı")), self.assertLogs("karabasan.panel", "ERROR"):
            sunucu = panel.sunucu_kur(self.klasor, adres="127.0.0.1", port=0)
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        try:
            adres = f"http://127.0.0.1:{sunucu.server_port}"
            with urllib.request.urlopen(adres + "/", timeout=10) as y:
                self.assertIn("data-ekran", y.read().decode("utf-8"))       # eski sayfa
            for yol in ("/api/ozet", "/s/pano.js"):
                with self.assertRaises(urllib.error.HTTPError) as hata:
                    urllib.request.urlopen(adres + yol, timeout=10)
                self.assertEqual(hata.exception.code, 503)
        finally:
            sunucu.shutdown()
            sunucu.server_close()

    def test_internet_kapisi_yalniz_bilinen_yollara_yazma_izni_verir(self):
        metin = (KOK / "araclar" / "internet.sh").read_text(encoding="utf-8")
        self.assertIn("not path /ayar/kayit /api/*", metin)


if __name__ == "__main__":
    unittest.main()
