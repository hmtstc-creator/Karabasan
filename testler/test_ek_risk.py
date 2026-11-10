"""Risk ekranı: sonuc_risk.hesapla ve sayfa_risk.ekran (10 Kasım 2026)."""

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import sayfa, sonuc
from karabasan import sayfa_risk as sr
from karabasan import sonuc_risk as rk

KOK = Path(__file__).resolve().parent.parent
T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
SIMDI = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)


def kapali(saat_g, saat_c, net, kod="SMK", bot="smk-vadeli", tutar=50.0, parite="SOL/USDT:USDT", ek=None, yuzde=None):
    return {"bot": bot, "kod": kod, "kimlik": int(saat_c * 10), "parite": parite, "yon": "aciga_satis",
            "giris_zamani": T0 + timedelta(hours=saat_g), "cikis_zamani": T0 + timedelta(hours=saat_c),
            "giris_fiyati": 100.0, "ilk_giris_fiyati": 100.0, "ek_girisler": ek or [], "tutar": tutar,
            "net_tutar": net, "net_yuzde": yuzde if yuzde is not None else net / tutar * 100.0,
            "neden": "stop", "sure_dakika": (saat_c - saat_g) * 60}


def acik(bot, kod, parite, tutar=50.0, kayip=-4.5, ek=None, stop=109.0, giris_saat=200):
    return {"bot": bot, "kod": kod, "kimlik": 99, "parite": parite, "yon": "aciga_satis",
            "giris_zamani": T0 + timedelta(hours=giris_saat), "giris_fiyati": 100.0, "ilk_giris_fiyati": 100.0,
            "ek_girisler": ek or [], "tutar": tutar, "stop_fiyati": stop, "stopta_kayip": kayip}


BOTLAR = [
    {"bot": "smk-vadeli", "kod": "SMK", "kaldirac": 1.0},
    {"bot": "smdk-vadeli", "kod": "SMDK", "kaldirac": 1.0},
    {"bot": "smk2-vadeli", "kod": "SMK2", "kaldirac": 2.0},
    {"bot": "smdk2-vadeli", "kod": "SMDK2", "kaldirac": 2.0},
]
AYAR = {"sanal_bakiye": 1000, "islem_tutari": 50, "komisyon_yuzde": {"vadeli": 0.05}}


def baglam(islemler=(), aciklar=(), simdi=SIMDI):
    bi = {}
    for i in islemler:
        bi.setdefault(i["kod"], []).append(i)
    return {"veri_klasoru": Path("/yok"), "simdi": simdi, "donem": {"donem": "sinav"}, "ayar": AYAR,
            "botlar": BOTLAR, "islemler": list(islemler), "bot_islemleri": bi, "acik": list(aciklar),
            "gecmis_test": {}, "izleme": {}}


class DususTesti(unittest.TestCase):
    def test_bos(self):
        d = rk.dusus_olcumu([], SIMDI, 4000)
        self.assertIsNone(d["simdiki"])
        self.assertEqual(d["islem_sayisi"], 0)

    def test_degerler(self):
        # +10, -4 (dip 6), -3 (dip 3 -> düşüş -7), +8 (yeni tepe 11), -2
        isl = [kapali(0, 1, 10), kapali(1, 2, -4), kapali(2, 3, -3), kapali(3, 27, 8), kapali(27, 28, -2)]
        d = rk.dusus_olcumu(isl, T0 + timedelta(hours=52), 1000)
        self.assertAlmostEqual(d["en_derin"], -7.0)
        self.assertAlmostEqual(d["en_derin_yuzde"], -0.7)
        self.assertAlmostEqual(d["simdiki"], -2.0)
        self.assertTrue(d["su_altinda"])
        # tepe 1. saatte, 27. saatte geri geldi: 26 saat; şimdiki su altı 27->52 = 25 saat
        self.assertAlmostEqual(d["en_uzun_su_alti_gun"], 26 / 24)
        self.assertAlmostEqual(d["su_alti_gun"], 25 / 24)

    def test_tepede(self):
        d = rk.dusus_olcumu([kapali(0, 1, 1), kapali(1, 2, 2)], SIMDI, 1000)
        self.assertEqual(d["simdiki"], 0.0)
        self.assertFalse(d["su_altinda"])
        self.assertEqual(d["en_uzun_su_alti_gun"], 0.0)

    def test_ilk_islem_zararsa_sifirdan_dusus(self):
        d = rk.dusus_olcumu([kapali(0, 1, -5)], T0 + timedelta(days=2), 1000)
        self.assertAlmostEqual(d["en_derin"], -5.0)
        self.assertAlmostEqual(d["su_alti_gun"], 2.0)

    def test_gelecege_bakmaz(self):
        isl = [kapali(k, k + 0.5, (3 if k % 3 == 0 else -1.5)) for k in range(40)]
        tam = rk.dusus_olcumu(isl, SIMDI, 1000)["noktalar"]
        for kes in (5, 17, 30):
            ilk = rk.dusus_olcumu(isl[:kes], SIMDI, 1000)["noktalar"]
            self.assertEqual(ilk, tam[:kes])


class GunlukTeminatTesti(unittest.TestCase):
    def test_ust_uste_binme(self):
        poz = [{"giris_zamani": T0 + timedelta(hours=1), "cikis_zamani": T0 + timedelta(hours=5), "tutar": 50},
               {"giris_zamani": T0 + timedelta(hours=2), "cikis_zamani": T0 + timedelta(hours=3), "tutar": 100},
               {"giris_zamani": T0 + timedelta(hours=3), "cikis_zamani": T0 + timedelta(hours=4), "tutar": 50}]
        g = rk.gunluk_teminat(poz, T0 + timedelta(days=1, hours=6), gun_sayisi=2)
        self.assertEqual(g[0]["gun"], "2026-11-01")
        self.assertEqual(g[0]["en_cok"], 150.0)   # 3. saatte çıkış önce sayılır: 150 değil 200
        self.assertEqual(g[1]["en_cok"], 0.0)
        self.assertTrue(g[0]["tamam"])
        self.assertFalse(g[1]["tamam"])

    def test_gece_yarisini_gecen_ve_acik(self):
        poz = [{"giris_zamani": T0 + timedelta(hours=22), "cikis_zamani": T0 + timedelta(hours=26), "tutar": 50},
               {"giris_zamani": T0 + timedelta(hours=30), "cikis_zamani": None, "tutar": 70}]
        g = rk.gunluk_teminat(poz, T0 + timedelta(hours=40), gun_sayisi=2)
        self.assertEqual(g[0]["en_cok"], 50.0)
        self.assertEqual(g[1]["en_cok"], 70.0)

    def test_gelecege_bakmaz(self):
        """T anında bilinenle (o an açık olanlar açık sayılır) hesaplanan tamamlanmış günler, sonradan değişmez."""
        tum = []
        for k in range(60):
            g = T0 + timedelta(hours=k * 3.3)
            tum.append({"giris_zamani": g, "cikis_zamani": g + timedelta(hours=1 + k % 7), "tutar": 50 + k % 3 * 25})
        son = T0 + timedelta(days=9)
        tam = rk.gunluk_teminat(tum, son, gun_sayisi=10)
        for kes_gun in (3, 5, 7):
            kes = T0 + timedelta(days=kes_gun, hours=7)
            o_an = [{**p, "cikis_zamani": p["cikis_zamani"] if p["cikis_zamani"] <= kes else None}
                    for p in tum if p["giris_zamani"] <= kes]
            ilk = rk.gunluk_teminat(o_an, kes, gun_sayisi=10)
            tam_s = {g["gun"]: g for g in tam}
            for g in ilk:
                if g["tamam"] and g["gun"] in tam_s:
                    self.assertEqual(g["en_cok"], tam_s[g["gun"]]["en_cok"], g["gun"])


class HesapTesti(unittest.TestCase):
    def test_bos_baglam(self):
        r = rk.hesapla(baglam())
        self.assertEqual(r["acik"]["adet"], 0)
        self.assertEqual(r["acik"]["stopta_kayip"], 0.0)
        self.assertIsNone(r["dusus"]["toplam"]["simdiki"])
        self.assertIsNone(r["senaryo"])
        self.assertEqual(r["butce"]["toplam"], 4000.0)

    def test_acik_risk_ve_payda(self):
        a = [acik("smk-vadeli", "SMK", "SOL/USDT:USDT", kayip=-4.5),
             acik("smk2-vadeli", "SMK2", "SOL/USDT:USDT", kayip=-11.0),
             acik("smdk-vadeli", "SMDK", "XRP/USDT:USDT", kayip=None, stop=None)]
        r = rk.hesapla(baglam(aciklar=a))
        self.assertAlmostEqual(r["acik"]["stopta_kayip"], -15.5)
        self.assertEqual(r["acik"]["bilinmeyen"], 1)
        self.assertAlmostEqual(r["acik"]["butce_yuzde"], -15.5 / 4000 * 100)
        smk2 = next(b for b in r["acik"]["botlar"] if b["kod"] == "SMK2")
        self.assertAlmostEqual(smk2["butce_yuzde"], -1.1)   # kendi 1000'ine göre
        smdk = next(b for b in r["acik"]["botlar"] if b["kod"] == "SMDK")
        self.assertIsNone(smdk["stopta_kayip"])             # tahmin yok

    def test_senaryo(self):
        isl = [kapali(0, 1, 10), kapali(1, 2, -4)]
        r = rk.hesapla(baglam(isl, [acik("smk-vadeli", "SMK", "SOL/USDT", kayip=-4.5)]))
        self.assertAlmostEqual(r["senaryo"]["dusus"], -8.5)
        self.assertTrue(r["senaryo"]["en_derinden_derin"])

    def test_yogunlasma(self):
        a = [acik("smk-vadeli", "SMK", "SOL/USDT:USDT"), acik("smk2-vadeli", "SMK2", "SOL/USDT:USDT", kayip=-11),
             acik("smdk-vadeli", "SMDK", "XRP/USDT:USDT")]
        y = rk.hesapla(baglam(aciklar=a))["yogunlasma"]
        self.assertAlmostEqual(y["nominal_toplam"], 50 + 100 + 50)     # SMK2 2 kat
        self.assertAlmostEqual(y["aciga_satis_pay"], 100.0)
        self.assertEqual(y["en_buyuk_coin"]["parite"], "SOL/USDT")
        self.assertAlmostEqual(y["en_buyuk_coin"]["pay"], 75.0)
        self.assertEqual([c["parite"] for c in y["ortak_coinler"]], ["SOL/USDT"])
        self.assertEqual(y["ortak_coinler"][0]["botlar"], ["SMK", "SMK2"])

    def test_ekleme_yapilan_bekleyen(self):
        a = [acik("smk2-vadeli", "SMK2", "SOL/USDT", tutar=50, kayip=-11.0),
             acik("smdk2-vadeli", "SMDK2", "ADA/USDT", tutar=150, kayip=-11.0,
                  ek=[{"zaman": T0, "fiyat": 108.0, "miktar": 1}]),
             acik("smk-vadeli", "SMK", "XRP/USDT")]
        e = rk.hesapla(baglam(aciklar=a))["ekleme"]
        self.assertEqual(e["botlar"], ["SMK2", "SMDK2"])
        self.assertEqual(len(e["yapilan"]), 1)
        self.assertEqual(e["yapilan"][0]["ek_giris_fiyati"], 108.0)
        self.assertEqual(len(e["bekleyen"]), 1)
        self.assertAlmostEqual(e["bekleyen"][0]["ek_giris_fiyati"], 108.0)   # ilk 100, %8 aleyhe (açığa satış)
        self.assertEqual(e["bekleyen_ek_teminat"], 100.0)
        self.assertEqual(e["ayar"]["SMK2"], {"stopa_kala_yuzde": 1.0, "kat": 2.0, "stop_yuzde": 9.0, "kaldirac": 2.0})

    def test_kapanan_ekli_karne_farki(self):
        isl = [kapali(0, 1, -22.0, kod="SMK2", bot="smk2-vadeli", tutar=150, yuzde=-14.67),
               kapali(1, 2, 1.0, kod="SMK2", bot="smk2-vadeli")]
        e = rk.hesapla(baglam(isl))["ekleme"]
        self.assertEqual(e["kapanan_ekli_adet"], 1)
        self.assertAlmostEqual(e["kapanan_ekli_net"], -22.0)
        self.assertAlmostEqual(e["kapanan_ekli_karne"], -14.67 / 100 * 50)

    def test_json_icin(self):
        import json
        isl = [kapali(0, 1, 10), kapali(1, 2, -4)]
        r = rk.hesapla(baglam(isl, [acik("smk-vadeli", "SMK", "SOL/USDT")]))
        json.dumps(sonuc.json_icin(r))


class EkranTesti(unittest.TestCase):
    def _ozet(self, klasor, bos=False):
        from testler.veri import sahte_sinav_klasoru
        if not bos:
            sahte_sinav_klasoru(klasor, SIMDI)
        return sonuc.genel_ozet(Path(klasor), SIMDI)

    def test_betiksiz_render_tam_bir_kez(self):
        with tempfile.TemporaryDirectory() as k:
            ozet = self._ozet(Path(k) / "ud")
            self.assertNotIn("hata", ozet["ek"]["risk"])
            html = sayfa.html_uret(ozet, yenile_saniye=0)
        govde = sr.ekran(ozet, "Europe/Bucharest")
        self.assertEqual(html.count('<section id="risk"'), 1)
        self.assertNotIn("<script", html)
        self.assertIn("Hepsi stopa giderse", govde)
        self.assertIn("4 bot × 1.000 USDT = 4.000 USDT", govde)
        self.assertIn("Ne yapmalı", sr.STIL)
        self.assertNotIn("<script", govde)
        self.assertIn('role="img"', govde)

    def test_bos_veri(self):
        with tempfile.TemporaryDirectory() as k:
            (Path(k) / "ud").mkdir()
            ozet = self._ozet(Path(k) / "ud", bos=True)
        govde = sr.ekran(ozet, "Europe/Bucharest")
        self.assertTrue(govde.startswith('<section id="risk" class="ekran">'))
        self.assertIn("Açık pozisyon yok", govde)
        self.assertIn("Henüz kapanmış işlem yok", govde)
        self.assertIn("Veri yok", govde)

    def test_hata_verisi(self):
        govde = sr.ekran({"ek": {"risk": {"hata": True}}}, "Europe/Bucharest")
        self.assertIn("Veri yok", govde)
        self.assertEqual(govde.count('<section id="risk"'), 1)

    def test_metin_kacirilir(self):
        a = [acik("smk2-vadeli", "SMK2", "<b>X</b>/USDT")]
        r = rk.hesapla(baglam([kapali(0, 1, 1)], a))
        govde = sr.ekran({"ek": {"risk": r}}, "Europe/Bucharest")
        self.assertNotIn("<b>X</b>", govde)
        self.assertIn("&lt;b&gt;X&lt;/b&gt;", govde)

    def test_ek_girisli_metin_kuraldan(self):
        r = rk.hesapla(baglam([kapali(0, 1, 1)], [acik("smk2-vadeli", "SMK2", "SOL/USDT", kayip=-11)]))
        govde = sr.ekran({"ek": {"risk": r}}, "Europe/Bucharest")
        self.assertIn("yaklaşık 11,0 USDT kaybettirir (ilk teminatın %22 kadarı", govde)
        self.assertIn("Bilinen belirsizlik", govde)


class PandasOlmadanTesti(unittest.TestCase):
    def test_pandas_numpy_olmadan(self):
        kod = (
            "import sys\n"
            "sys.modules['pandas'] = None\nsys.modules['numpy'] = None\n"
            "from datetime import datetime, timezone\n"
            "from karabasan import sonuc_risk, sayfa_risk\n"
            "s = datetime(2026, 11, 10, tzinfo=timezone.utc)\n"
            "b = {'simdi': s, 'ayar': {'sanal_bakiye': 1000, 'islem_tutari': 50},\n"
            "     'botlar': [{'bot': 'smk2-vadeli', 'kod': 'SMK2', 'kaldirac': 2}], 'islemler': [], 'bot_islemleri': {},\n"
            "     'acik': [{'bot': 'smk2-vadeli', 'kod': 'SMK2', 'parite': 'SOL/USDT', 'yon': 'aciga_satis',\n"
            "               'giris_zamani': s, 'tutar': 50, 'stopta_kayip': -11.0, 'stop_fiyati': 109.0,\n"
            "               'giris_fiyati': 100.0, 'ilk_giris_fiyati': 100.0, 'ek_girisler': []}]}\n"
            "r = sonuc_risk.hesapla(b)\n"
            "assert r['acik']['stopta_kayip'] == -11.0\n"
            "h = sayfa_risk.ekran({'ek': {'risk': r}}, 'Europe/Bucharest')\n"
            "assert h.count('<section id=\"risk\"') == 1\n"
            "assert 'numpy' not in [m for m in sys.modules if sys.modules[m] is not None]\n"
        )
        s_ = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True, cwd=KOK, env=dict(os.environ))
        self.assertEqual(s_.returncode, 0, s_.stderr)


if __name__ == "__main__":
    unittest.main()
