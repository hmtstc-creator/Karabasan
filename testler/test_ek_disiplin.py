"""Disiplin ekranı: sonuc_disiplin (veri) ve sayfa_disiplin (görünüm)."""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import sonuc_disiplin as sd

SIMDI = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)
T0 = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)   # Bükreş 11:00, Salı


def islem(bot="smk-vadeli", kimlik=1, parite="SOL/USDT:USDT", giris=T0, dakika=60, net_yuzde=1.0,
          neden="iz süren stop", tutar=50.0, ek=None, kod="SMK"):
    return {"bot": bot, "kod": kod, "kimlik": kimlik, "parite": parite, "yon": "aciga_satis",
            "giris_zamani": giris, "cikis_zamani": giris + timedelta(minutes=dakika),
            "net_yuzde": net_yuzde, "net_tutar": net_yuzde / 100 * tutar, "neden": neden, "tutar": tutar,
            "sure_dakika": float(dakika), "ek_girisler": ek or [], "ilk_giris_fiyati": 1.0}


def bot(bot="smk-vadeli", kod="SMK", kaldirac=1.0, ekleme="", calisiyor=True, yas=1.0, stop=9.0):
    return {"bot": bot, "kod": kod, "kaldirac": kaldirac, "ekleme_metni": ekleme, "calisiyor": calisiyor,
            "gunluk_yasi_dakika": yas, "stop_yuzde": stop, "piyasa": "vadeli",
            "stop_sonrasi": {"stop_sayisi": 0, "karar": {"kod": "yetersiz", "metin": "az"}}}


def baglam(islemler=(), botlar=None, acik=(), izleme=None):
    return {"veri_klasoru": Path("/yok"), "simdi": SIMDI,
            "donem": {"donem": "sinav", "gun": 5, "baslangic": None, "bitis": None},
            "ayar": {"sanal_bakiye": 1000, "islem_tutari": 50, "komisyon_yuzde": {"vadeli": 0.05}},
            "botlar": [bot()] if botlar is None else botlar, "islemler": list(islemler), "bot_islemleri": {},
            "acik": list(acik), "gecmis_test": {}, "izleme": izleme or {"dersler": []}}


class SabitTesti(unittest.TestCase):
    def test_sabitler_kaynakla_ayni(self):
        from karabasan import karne, sonuc
        self.assertEqual(sd.EK_KAYMA_YUZDE, karne.SINAV_ESIKLERI["ek_kayma_yuzde"])
        self.assertEqual(sd.SESSIZLIK_DAKIKA, sonuc.SESSIZLIK_DAKIKA)
        self.assertEqual(sd.SAAT_DILIMI, sonuc.SAAT_DILIMI)
        self.assertEqual(sd._yerel(T0), sonuc._yerel(T0))

    def test_pandas_olmadan_calisir(self):
        kod = ("import sys\nsys.modules['pandas']=None\nsys.modules['numpy']=None\n"
               "from datetime import datetime, timezone\n"
               "from karabasan import sonuc_disiplin, sayfa_disiplin\n"
               "b={'simdi':datetime(2026,11,2,tzinfo=timezone.utc),'ayar':{'sanal_bakiye':1000,'komisyon_yuzde':{'vadeli':0.05}},"
               "'botlar':[],'islemler':[],'acik':[]}\n"
               "v=sonuc_disiplin.hesapla(b)\n"
               "print(sayfa_disiplin.ekran({'ek':{'disiplin':v}},'Europe/Bucharest')[:20])\n")
        s = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True,
                           cwd=Path(__file__).resolve().parent.parent)
        self.assertEqual(s.returncode, 0, s.stderr)


class StopDilimiTesti(unittest.TestCase):
    def test_az_veride_yuksek_yok(self):
        d = sd.stop_dilimleri([islem(neden="stop", net_yuzde=-9.1)] * 5)
        self.assertFalse(d["yeterli"])
        self.assertEqual(d["yuksek"], [])
        self.assertEqual(d["genel_oran"], 100.0)

    def test_belirgin_yuksek_dilim(self):
        liste = []
        for k in range(40):   # SOL: 12 işlemin 10'u stop; öbürleri 28 işlemin 2'si
            sol = k < 12
            stop = (sol and k < 10) or (not sol and k in (20, 30))
            liste.append(islem(kimlik=k, parite="SOL/USDT:USDT" if sol else "XRP/USDT:USDT",
                               giris=T0 + timedelta(hours=k), neden="stop" if stop else "iz süren stop",
                               net_yuzde=-9.1 if stop else 1.0))
        d = sd.stop_dilimleri(liste)
        self.assertTrue(d["yeterli"])
        self.assertAlmostEqual(d["genel_oran"], 30.0)
        yuksek = [(r["tur"], r["anahtar"]) for r in d["yuksek"]]
        self.assertIn(("coin", "SOL/USDT"), yuksek)
        self.assertNotIn(("coin", "XRP/USDT"), yuksek)

    def test_saat_bukres_saatinde(self):
        d = sd.stop_dilimleri([islem()])
        self.assertEqual(d["turler"]["saat"][0]["anahtar"], 8)   # 08:00 UTC = 11:00 Bükreş -> 08-12 dilimi
        self.assertEqual(d["turler"]["gun"][0]["anahtar"], 1)    # Salı
        self.assertEqual(sd.dilim_adi({"tur": "saat", "anahtar": 8}), "08:00–12:00")


class MaliyetTesti(unittest.TestCase):
    def test_komisyon_kaldiracla(self):
        b = [bot(), bot("smk2-vadeli", "SMK2", kaldirac=2.0)]
        liste = [islem(net_yuzde=1.0), islem(bot="smk2-vadeli", kod="SMK2", net_yuzde=2.0)]
        m = sd.maliyet(liste, b, {"vadeli": 0.05}, 0.05)
        # 50 × 1 × 0,05% × 2 = 0,05 ; 50 × 2 × 0,05% × 2 = 0,10
        self.assertAlmostEqual(m["komisyon"], 0.15)
        self.assertAlmostEqual(m["net"], 1.5)
        self.assertAlmostEqual(m["brut"], 1.65)
        self.assertAlmostEqual(m["pay_yuzde"], 0.15 / 1.65 * 100)
        self.assertAlmostEqual(m["ek_kayma_tutar"], 0.05)
        self.assertAlmostEqual(m["botlar"][1]["gidis_donus_yuzde"], 0.2)

    def test_brut_eksi_ise_pay_yok(self):
        m = sd.maliyet([islem(net_yuzde=-2.0)], [bot()], {"vadeli": 0.05}, 0.05)
        self.assertIsNone(m["pay_yuzde"])


class SureTesti(unittest.TestCase):
    def test_kaybeden_uzun(self):
        liste = [islem(kimlik=k, dakika=30, net_yuzde=1.0) for k in range(5)]
        liste += [islem(kimlik=10 + k, dakika=120, net_yuzde=-9.1, neden="stop") for k in range(5)]
        su = sd.sureler(liste)
        self.assertEqual(su["kazanan_ort"], 30)
        self.assertEqual(su["kaybeden_ort"], 120)
        self.assertAlmostEqual(su["kat"], 4.0)
        self.assertEqual({r["neden"] for r in su["nedenler"]}, {"stop", "iz süren stop"})

    def test_az_veride_kat_yok(self):
        su = sd.sureler([islem(), islem(net_yuzde=-1)])
        self.assertFalse(su["yeterli"])
        self.assertIsNone(su["kat"])


class DenetimTesti(unittest.TestCase):
    def _bul(self, sonuc, ad):
        return next(d for d in sonuc if d["ad"] == ad)

    def test_temiz_veri_temiz(self):
        liste = [islem(kimlik=k, giris=T0 + timedelta(hours=3 * k)) for k in range(5)]
        sonuc = sd.denetimler(baglam(liste))
        for d in sonuc:
            self.assertEqual(d["durum"], "temiz", d)

    def test_ust_uste_pozisyon(self):
        a, b = islem(kimlik=1, dakika=60), islem(kimlik=2, giris=T0 + timedelta(minutes=30), dakika=20)
        c = islem(kimlik=3, giris=T0 + timedelta(minutes=60))   # tam kapanışta açılan çakışma değildir
        o = sd.ust_uste_pozisyonlar([a, b, c], SIMDI)
        self.assertEqual([x["kimlik"] for x in o], [2])

    def test_bekleme(self):
        stop = islem(kimlik=1, neden="stop", net_yuzde=-9.1, dakika=10)
        erken = islem(kimlik=2, giris=stop["cikis_zamani"] + timedelta(minutes=30))
        gec = islem(kimlik=3, giris=stop["cikis_zamani"] + timedelta(minutes=118), dakika=5)   # tolerans içinde
        baska = islem(kimlik=4, parite="XRP/USDT:USDT", giris=stop["cikis_zamani"] + timedelta(minutes=5))
        o = sd.bekleme_ihlalleri([stop, erken, gec, baska], {"smk-vadeli": 120})
        self.assertEqual([x["kimlik"] for x in o], [2])
        self.assertEqual(sd.bekleme_ihlalleri([stop, erken], {"smk-vadeli": 0}), [])

    def test_bekleme_kural_dosyasindan(self):
        stop = islem(kimlik=1, neden="stop", net_yuzde=-9.1, dakika=10)
        erken = islem(kimlik=2, giris=stop["cikis_zamani"] + timedelta(minutes=30))
        d = self._bul(sd.denetimler(baglam([stop, erken])), "Stoptan sonra bekleme")
        self.assertEqual(d["durum"], "ihlal")
        self.assertIn("120", d["aciklama"])

    def test_ek_giris(self):
        b = [bot(), bot("smk2-vadeli", "SMK2", kaldirac=2.0, ekleme="kaldıraç 2 kat, fiyat %8 aleyhe gidince ilk tutarın 2 katı ek giriş")]
        e = [{"zaman": T0, "fiyat": 1.0, "miktar": 1.0}]
        liste = [islem(kimlik=1, ek=e), islem(bot="smk2-vadeli", kod="SMK2", kimlik=2, ek=e),
                 islem(bot="smk2-vadeli", kod="SMK2", kimlik=3, parite="XRP/USDT:USDT", ek=e * 2)]
        sonuc = sd.denetimler(baglam(liste, b))
        self.assertEqual([o["kimlik"] for o in self._bul(sonuc, "1 kat botta ek giriş")["ornekler"]], [1])
        self.assertEqual([o["kimlik"] for o in self._bul(sonuc, "Tek ek giriş hakkı")["ornekler"]], [3])

    def test_ek_giris_bilgisi_yoksa_denetlenemedi(self):
        i = islem()
        del i["ek_girisler"]
        d = self._bul(sd.denetimler(baglam([i])), "1 kat botta ek giriş")
        self.assertEqual(d["durum"], "denetlenemedi")

    def test_stop_tasmasi(self):
        b = [bot(), bot("smk2-vadeli", "SMK2", kaldirac=2.0)]
        liste = [islem(kimlik=1, neden="stop", net_yuzde=-9.1), islem(kimlik=2, neden="stop", net_yuzde=-12.0),
                 islem(bot="smk2-vadeli", kod="SMK2", kimlik=3, neden="stop", net_yuzde=-18.2)]
        o = sd.stop_tasmalari(liste, b, {"vadeli": 0.05})
        self.assertEqual([x["kimlik"] for x in o], [2])

    def test_butce(self):
        liste = [islem(kimlik=k, parite=f"C{k}/USDT:USDT", tutar=300.0) for k in range(4)]
        d = self._bul(sd.denetimler(baglam(liste)), "Günlük bütçe")
        self.assertEqual(d["durum"], "ihlal")
        self.assertEqual(sd.butce_tepesi(liste)[0]["en_cok"], 1200.0)

    def test_sessiz(self):
        d = self._bul(sd.denetimler(baglam([], [bot(calisiyor=False, yas=None)])), "Sessiz bot")
        self.assertEqual(d["durum"], "ihlal")
        self.assertIn("kayıt dosyası yok", d["ornekler"][0]["ayrinti"])

    def test_guncel_seri(self):
        liste = [islem(kimlik=1, net_yuzde=1.0), islem(kimlik=2, giris=T0 + timedelta(hours=2), net_yuzde=-1.0),
                 islem(kimlik=3, giris=T0 + timedelta(hours=4), net_yuzde=-2.0)]
        s = sd.guncel_seri(liste)
        self.assertEqual(s["adet"], 2)
        self.assertAlmostEqual(s["toplam"], -1.5)


class DikkatTesti(unittest.TestCase):
    def test_oncelik_sirasi(self):
        adaylar = [{"tur": t, "agirlik": 1, "ne": t, "sayi": "", "yapmali": ""}
                   for t in ("stop_dilimi", "maliyet", "seri", "acik_risk", "sessiz", "ihlal")]
        self.assertEqual([a["tur"] for a in sd.dikkat_sec(adaylar)], ["ihlal", "sessiz", "acik_risk"])

    def test_esitlikte_agirlik_sonra_sira(self):
        adaylar = [{"tur": "seri", "agirlik": 3, "ne": "a"}, {"tur": "seri", "agirlik": 5, "ne": "b"},
                   {"tur": "seri", "agirlik": 3, "ne": "c"}]
        self.assertEqual([a["ne"] for a in sd.dikkat_sec(adaylar)], ["b", "a", "c"])

    def test_bos(self):
        self.assertEqual(sd.dikkat_sec([]), [])

    def test_adaylar_veriden(self):
        b = [bot(calisiyor=False, yas=40.0)]
        acik = [{"bot": "smk-vadeli", "kimlik": 99, "parite": "ADA/USDT:USDT", "giris_zamani": SIMDI - timedelta(hours=1),
                 "tutar": 50.0, "stopta_kayip": -30.0}]
        liste = [islem(kimlik=k, giris=T0 + timedelta(hours=k), net_yuzde=-1.0, neden="süre aşımı") for k in range(4)]
        v = sd.hesapla(baglam(liste, b, acik))
        self.assertEqual([m["tur"] for m in v["dikkat"]], ["sessiz", "acik_risk", "seri"])
        self.assertIn("4", v["dikkat"][2]["sayi"])
        for m in v["dikkat"]:
            self.assertNotIn("ayarı değiştir", m["yapmali"])

    def test_temiz_veride_dikkat_yok(self):
        from karabasan import sayfa_disiplin
        v = sd.hesapla(baglam([islem()]))
        self.assertEqual(v["dikkat"], [])
        h = sayfa_disiplin.ekran({"ek": {"disiplin": v}}, "Europe/Bucharest")
        self.assertIn("Bugün dikkat gerektiren bir şey görünmüyor", h)


class GelecegeBakmazTesti(unittest.TestCase):
    def _liste(self):
        out = []
        for k in range(30):
            neden = "stop" if k % 4 == 0 else "iz süren stop"
            out.append(islem(kimlik=k, parite=["SOL", "XRP"][k % 2] + "/USDT:USDT", giris=T0 + timedelta(minutes=50 * k),
                             dakika=20, neden=neden, net_yuzde=-9.1 if neden == "stop" else 1.0))
        return out

    def test_bekleme_ve_butce_sonradan_degismez(self):
        tum = self._liste()
        ilk = tum[:15]
        kesim = ilk[-1]["cikis_zamani"]
        ilk_ihlal = sd.bekleme_ihlalleri(ilk, {"smk-vadeli": 120})
        tum_ihlal = [o for o in sd.bekleme_ihlalleri(tum, {"smk-vadeli": 120}) if o["zaman"] <= kesim]
        self.assertEqual(ilk_ihlal, tum_ihlal)
        self.assertTrue(ilk_ihlal)
        gun = kesim.date().isoformat()
        b1 = [g for g in sd.butce_tepesi(ilk) if g["gun"] < gun]
        b2 = [g for g in sd.butce_tepesi(tum) if g["gun"] < gun]
        self.assertEqual(b1, b2)

    def test_seri_ve_ust_uste_sonradan_degismez(self):
        tum = self._liste()
        ilk = tum[:15]
        self.assertEqual(sd.ust_uste_pozisyonlar(ilk, SIMDI),
                         [o for o in sd.ust_uste_pozisyonlar(tum, SIMDI) if o["kimlik"] in {i["kimlik"] for i in ilk}])
        self.assertEqual(sd.stop_tasmalari(ilk, [bot()], {"vadeli": 0.05}),
                         [o for o in sd.stop_tasmalari(tum, [bot()], {"vadeli": 0.05}) if o["kimlik"] < 15])


class EkranTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from karabasan import sonuc
        from testler.veri import sahte_sinav_klasoru
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ozet = sonuc.genel_ozet(sahte_sinav_klasoru(Path(cls.tmp.name) / "ud", SIMDI), SIMDI)
        cls.bos = sonuc.genel_ozet(Path(cls.tmp.name) / "bos", SIMDI)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_veri_json_olur(self):
        from karabasan import sonuc
        self.assertNotIn("hata", self.ozet["ek"]["disiplin"])
        json.dumps(sonuc.json_icin(self.ozet["ek"]["disiplin"]))

    def test_betiksiz_render(self):
        from karabasan import sayfa
        h = sayfa.html_uret(self.ozet, yenile_saniye=0)
        self.assertEqual(h.count('<section id="disiplin"'), 1)
        self.assertNotIn("<script", h)
        bolum = h.split('<section id="disiplin"')[1]
        self.assertNotIn("hazırlanamadı", bolum[:500])
        self.assertIn("Bugün dikkat edilecek 3 şey", bolum)
        self.assertIn("/islem?bot=", bolum)
        self.assertIn('href="#dersler"', bolum)
        self.assertIn("veri yok", bolum)

    def test_bos_veri(self):
        from karabasan import sayfa
        h = sayfa.html_uret(self.bos, yenile_saniye=0)
        bolum = h.split('<section id="disiplin"')[1].split("</section>")[0]
        self.assertIn("Henüz kapanmış işlem yok", bolum)
        self.assertIn("Bugün dikkat edilecek 3 şey", bolum)
        self.assertEqual(bolum.count("Sessiz bot:"), 1)   # dört sessiz bot tek madde

    def test_kacis(self):
        from karabasan import sayfa_disiplin
        v = sd.hesapla(baglam([islem(parite="<b>X/USDT", kod="<i>")], [bot(kod="<i>")]))
        h = sayfa_disiplin.ekran({"ek": {"disiplin": v}}, "Europe/Bucharest")
        self.assertNotIn("<b>X", h)
        self.assertNotIn("<i>", h)


if __name__ == "__main__":
    unittest.main()
