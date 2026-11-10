"""Rejim ekranı (10 Kasım 2026): Karabasan kuralları, küresel kayıt, kayıttan kurulan art arda stop."""

import ast
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import kayitci, sayfa, sayfa_rejim, sonuc, sonuc_rejim as r

KOK = Path(__file__).resolve().parent.parent
SIMDI = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def csv_yaz(yol, satirlar):
    yol.parent.mkdir(parents=True, exist_ok=True)
    with yol.open("w", encoding="utf-8") as d:
        d.write(",".join(kayitci.SUTUNLAR) + "\n")
        for z, dom, t2 in satirlar:
            d.write(f"{z.strftime('%Y-%m-%dT%H:%M:%SZ')},{t2 / (1 - dom / 100):.2f},{dom},{t2},1000\n")


def seri(bas, adet, adim_dk=10, dom0=55.0, t2=1.0e12):
    return [(bas + timedelta(minutes=adim_dk * k), dom0 + k * 0.001, t2 * (1 + k * 1e-4)) for k in range(adet)]


def islem(dk, neden, kod="SMK", giris_dk=None, net=-1.0):
    cikis = SIMDI - timedelta(minutes=dk)
    return {"cikis_zamani": cikis, "giris_zamani": cikis - timedelta(minutes=30) if giris_dk is None
            else SIMDI - timedelta(minutes=giris_dk), "neden": neden, "kod": kod, "net_tutar": net}


def baglam(klasor, islemler=(), acik=()):
    return {"veri_klasoru": Path(klasor), "simdi": SIMDI, "islemler": list(islemler), "acik": list(acik),
            "botlar": [{"kod": "SMK", "ad": "SMK", "izinli_durumlar": ["KIRMIZI", "SARI"]}]}


class Kurallar(unittest.TestCase):
    def test_puan_dosyasiyla_ayni(self):
        """Sayfa kodun söylediğini söyler: sabitler puan.py metninden aynen gelir."""
        k = r.kurallari_oku()
        agac = ast.parse(r.PUAN_DOSYASI.read_text(encoding="utf-8"))
        sabit = {d.targets[0].id: ast.literal_eval(d.value) for d in agac.body
                 if isinstance(d, ast.Assign) and isinstance(d.targets[0], ast.Name) and d.targets[0].id in r.PUAN_SABITLERI}
        self.assertEqual({b["kod"]: b["agirlik_yuzde"] / 100 for b in k["bilesenler"]}, sabit["AGIRLIKLAR"])
        self.assertEqual(k["esik_yesil"], sabit["ESIK_YESIL"])
        self.assertEqual(k["esik_sari"], sabit["ESIK_SARI"])
        self.assertEqual(k["veto_esikleri"], {a: float(v) for a, v in sabit["VETO_ESIKLERI"].items()})
        self.assertAlmostEqual(sum(b["agirlik_yuzde"] for b in k["bilesenler"]), 100.0)

    def test_bilesen_kayit_etiketleri(self):
        k = r.kurallari_oku()
        self.assertEqual({b["kod"]: b["kayit"] for b in k["bilesenler"]},
                         {"T": "yok", "S": "yok", "A": "kismen", "G": "yok", "M": "yok"})

    def test_okunamazsa_veri_yok(self):
        with tempfile.TemporaryDirectory() as t:
            yol = Path(t) / "puan.py"
            self.assertIsNone(r.kurallari_oku(yol))  # dosya yok
            yol.write_text("AGIRLIKLAR = {'T': 0.3}\n")
            self.assertIsNone(r.kurallari_oku(yol))  # eksik sabit
            yol.write_text("def (:\n")
            self.assertIsNone(r.kurallari_oku(yol))  # bozuk

    def test_izinli_durumlar_canlida_kullanilmiyor(self):
        """Ekrandaki "canlıda uygulanmıyor" cümlesinin dayanağı: bağlantı katmanı alana hiç bakmaz."""
        metin = (KOK / "user_data" / "strategies" / "karabasan_stratejileri.py").read_text(encoding="utf-8")
        self.assertNotIn("izinli_durumlar", metin)
        self.assertNotIn("DurumMakinesi", metin)
        self.assertNotIn("DurumMakinesi", (KOK / "karabasan" / "kural.py").read_text(encoding="utf-8"))

    def test_aralik_kaydediciyle_ayni(self):
        self.assertEqual(r.ARALIK_DAKIKA * 60, kayitci.ARALIK_SANIYE)


class KureselKayit(unittest.TestCase):
    def setUp(self):
        r._onbellek.clear()

    def test_dosya_yok(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertIsNone(r.kuresel_oku(Path(t) / "yok.csv", SIMDI))
            self.assertEqual(r.kuresel_ozet(None, SIMDI), {"var": False, "olcum": 0})

    def test_son_30_gun_ve_degisimler(self):
        with tempfile.TemporaryDirectory() as t:
            yol = Path(t) / "kuresel.csv"
            satirlar = seri(SIMDI - timedelta(days=40), 40 * 144)
            csv_yaz(yol, satirlar)
            okunan = r.kuresel_oku(yol, SIMDI - timedelta(days=30))
            self.assertEqual(okunan[0][0], SIMDI - timedelta(days=30))
            o = r.kuresel_ozet(okunan, SIMDI)
            son = satirlar[-1]
            self.assertAlmostEqual(o["dominans"], son[1])
            self.assertAlmostEqual(o["dominans_24s"], 144 * 0.001, places=6)
            self.assertAlmostEqual(o["dominans_7g"], 7 * 144 * 0.001, places=6)
            once = satirlar[-1 - 144][2]
            self.assertAlmostEqual(o["total2_24s"], (son[2] / once - 1) * 100, places=6)
            self.assertEqual(o["bosluk_sayisi"], 0)
            self.assertFalse(o["bayat"])
            self.assertAlmostEqual(o["yas_dakika"], 10.0)
            self.assertAlmostEqual(o["kapsama_yuzde"], 100.0)
            # Seyrek: 30 gün / 6 saat ~ 120 nokta (+1 başlangıç dilimi).
            self.assertLessEqual(len(o["dominans_seri"]), 122)

    def test_sondan_okuma_buyuyerek_tamamlar(self):
        """İlk okunan parça 30 güne yetmezse geriye doğru büyütür; yarım ilk satır atılır."""
        eski = r.ILK_OKUMA_BAYT
        r.ILK_OKUMA_BAYT = 500
        try:
            with tempfile.TemporaryDirectory() as t:
                yol = Path(t) / "kuresel.csv"
                csv_yaz(yol, seri(SIMDI - timedelta(days=3), 3 * 144))
                okunan = r.kuresel_oku(yol, SIMDI - timedelta(days=2))
                self.assertEqual(len(okunan), 2 * 144 - 1 + 1)
                self.assertEqual(okunan[0][0], SIMDI - timedelta(days=2))
        finally:
            r.ILK_OKUMA_BAYT = eski

    def test_onbellek_degisince_yenilenir(self):
        with tempfile.TemporaryDirectory() as t:
            yol = Path(t) / "kuresel.csv"
            csv_yaz(yol, seri(SIMDI - timedelta(days=1), 100))
            self.assertEqual(len(r.kuresel_oku(yol, SIMDI - timedelta(days=2))), 100)
            csv_yaz(yol, seri(SIMDI - timedelta(days=1), 120))
            os.utime(yol, ns=(1, 10**18))
            self.assertEqual(len(r.kuresel_oku(yol, SIMDI - timedelta(days=2))), 120)

    def test_bozuk_satir_atlanir(self):
        with tempfile.TemporaryDirectory() as t:
            yol = Path(t) / "kuresel.csv"
            csv_yaz(yol, seri(SIMDI - timedelta(hours=1), 3))
            with yol.open("a") as d:
                d.write("2026-11-10T11:5")  # yarım yazılmış son satır
            self.assertEqual(len(r.kuresel_oku(yol, SIMDI - timedelta(days=1))), 3)

    def test_bosluk_ve_bayat(self):
        satirlar = seri(SIMDI - timedelta(hours=10), 20) + seri(SIMDI - timedelta(hours=5), 10)
        o = r.kuresel_ozet(satirlar, SIMDI)
        self.assertEqual(o["bosluk_sayisi"], 1)
        self.assertAlmostEqual(o["en_uzun_bosluk_dakika"], 5 * 60 - 190)
        self.assertTrue(o["bayat"])  # son ölçüm 3,5 saat önce
        self.assertIsNone(o["dominans_7g"])  # 7 gün önce ölçüm yok

    def test_pencerede_olcum_yok(self):
        o = r.kuresel_ozet(seri(SIMDI - timedelta(days=50), 10), SIMDI)
        self.assertEqual((o["var"], o["olcum"]), (True, 0))

    def test_gelecege_bakmaz(self):
        """Sonradan gelen ölçüm, bitmiş dilimlerin grafik noktasını ve geçmiş boşlukları değiştirmez."""
        tum = seri(SIMDI - timedelta(days=5), 5 * 144)
        ilk = tum[: 3 * 144]
        kesim = ilk[-1][0]
        a, b = r.seyrek_seri(ilk, 1), r.seyrek_seri(tum, 1)
        biten = [p for p in a if p[0] < (kesim.timestamp() // (6 * 3600)) * 6 * 3600]
        self.assertEqual(biten, b[: len(biten)])
        self.assertEqual(r.bosluklar(ilk), [x for x in r.bosluklar(tum) if x["bitis"] <= kesim])


class ArtArdaStop(unittest.TestCase):
    def test_esige_varinca_pencere(self):
        islemler = [islem(300, "stop"), islem(290, "stop"), islem(280, "stop"), islem(270, "stop"),
                    islem(265, "stop"), islem(200, "kâr hedefi", giris_dk=400), islem(100, "stop")]
        # Pencere içinde (270..205 dk önce) açılan bir işlem:
        islemler.append(islem(5, "kâr hedefi", kod="SMDK", giris_dk=240, net=0.5))
        a = r.art_arda_stop(islemler, [], 4, 60, SIMDI)
        self.assertEqual(a["pencere_sayisi"], 1)
        p = a["pencereler"][0]
        self.assertEqual(p["baslangic"], SIMDI - timedelta(minutes=270))
        self.assertEqual(p["bitis"], SIMDI - timedelta(minutes=265) + timedelta(minutes=60))
        self.assertEqual(p["art_arda"], 5)
        self.assertAlmostEqual(p["dakika"], 65)
        self.assertEqual(a["en_uzun_seri"], 5)
        self.assertEqual(a["simdiki_seri"], 0)
        self.assertEqual(p["acan_botlar"], ["SMDK"])
        self.assertEqual(p["acilan_islem"], 1)
        self.assertAlmostEqual(a["acilan_net"], 0.5)

    def test_acik_islem_sayilir_ve_suruyor(self):
        islemler = [islem(40, "stop"), islem(30, "stop"), islem(20, "stop"), islem(10, "stop")]
        acik = [{"giris_zamani": SIMDI - timedelta(minutes=5), "kod": "SMK2"}]
        a = r.art_arda_stop(islemler, acik, 4, 60, SIMDI)
        self.assertTrue(a["suruyor"])
        self.assertEqual(a["acilan_islem"], 1)
        self.assertEqual(a["acilan_kapanan"], 0)
        self.assertAlmostEqual(a["pencereler"][0]["dakika"], 10)

    def test_esik_altinda_pencere_yok(self):
        a = r.art_arda_stop([islem(30, "stop"), islem(20, "stop"), islem(10, "stop")], [], 4, 60, SIMDI)
        self.assertEqual((a["pencere_sayisi"], a["en_uzun_seri"], a["simdiki_seri"]), (0, 3, 3))

    def test_30_gunden_eski_dusulur(self):
        eski = [islem(60 * 24 * 40 + k, "stop") for k in range(4)]
        self.assertEqual(r.art_arda_stop(eski, [], 4, 60, SIMDI)["pencere_sayisi"], 0)

    def test_gelecege_bakmaz(self):
        """Sonradan kapanan işlemler, önceki tetiklerin başlangıcını değiştirmez."""
        tum = [islem(500 - 10 * k, "stop" if k % 6 else "kâr hedefi") for k in range(40)]
        kesim = SIMDI - timedelta(minutes=300)
        ilk = [i for i in tum if i["cikis_zamani"] <= kesim]
        a = r.art_arda_stop(ilk, [], 4, 60, kesim)
        b = r.art_arda_stop(tum, [], 4, 60, SIMDI)
        bas_a = sorted(p["baslangic"] for p in a["pencereler"])
        bas_b = sorted(p["baslangic"] for p in b["pencereler"] if p["baslangic"] <= kesim)
        self.assertTrue(bas_a)
        self.assertEqual(bas_a, bas_b)


class Hesapla(unittest.TestCase):
    def test_bos_bagl(self):
        with tempfile.TemporaryDirectory() as t:
            v = r.hesapla(baglam(t))
            self.assertFalse(v["canli_kayit"])
            self.assertIsNone(v["puan"])
            self.assertFalse(v["kuresel"]["var"])
            self.assertFalse(v["gecmis_raporu"]["var"])
            self.assertEqual(v["art_arda_stop"]["kapanan_islem"], 0)
            sonuc.json_icin(v)

    def test_gecmis_rapor_tarihi(self):
        with tempfile.TemporaryDirectory() as t:
            yol = Path(t) / "logs" / "karabasan_gecmis.txt"
            yol.parent.mkdir()
            yol.write_text("rapor")
            zaman = (SIMDI - timedelta(days=2)).timestamp()
            os.utime(yol, (zaman, zaman))
            g = r.hesapla(baglam(t))["gecmis_raporu"]
            self.assertTrue(g["var"])
            self.assertAlmostEqual(g["yas_gun"], 2.0, places=3)

    def test_pandas_olmadan_calisir(self):
        kod = ("import sys\nsys.modules['pandas'] = None\nsys.modules['numpy'] = None\n"
               "import tempfile\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n"
               "from karabasan import sonuc_rejim, sayfa_rejim\n"
               "with tempfile.TemporaryDirectory() as t:\n"
               "    v = sonuc_rejim.hesapla({'veri_klasoru': Path(t), 'simdi': datetime.now(timezone.utc), 'islemler': [],"
               " 'acik': [], 'botlar': []})\n"
               "    assert v['kurallar'] is not None\n"
               "    h = sayfa_rejim.ekran({'ek': {'rejim': v}}, 'Europe/Bucharest')\n"
               "    assert h.count('<section id=\"rejim\"') == 1\n")
        s = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True, cwd=KOK)
        self.assertEqual(s.returncode, 0, s.stderr)


class Ekran(unittest.TestCase):
    def setUp(self):
        r._onbellek.clear()

    def _html(self, klasor, **kw):
        v = r.hesapla(baglam(klasor, **kw))
        return sayfa_rejim.ekran({"ek": {"rejim": v}}, "Europe/Bucharest")

    def test_bos_veri_dusmez(self):
        with tempfile.TemporaryDirectory() as t:
            h = self._html(t)
            self.assertIn("Canlı Karabasan puanı kaydı yok", h)
            self.assertIn("Veri yok: küresel kayıt dosyası", h)
            self.assertIn("Henüz kapanmış işlem yok", h)
            self.assertIn("geçmiş ölçüm raporu (karabasan_gecmis.txt) yok", h)
            self.assertIn("Canlıda uygulanmıyor", h)
            self.assertNotIn("<script", h)

    def test_dolu_veri(self):
        with tempfile.TemporaryDirectory() as t:
            csv_yaz(Path(t) / "kayit" / "kuresel.csv", seri(SIMDI - timedelta(days=10), 10 * 144))
            islemler = [islem(100 + k, "stop") for k in range(5)]
            h = self._html(t, islemler=islemler)
            self.assertIn("Kaydedici çalışıyor", h)
            self.assertIn('role="img"', h)
            self.assertIn("Veto penceresi", h)
            self.assertIn("işlem açılmadı", h)

    def test_kuralsiz_veri_yok(self):
        h = sayfa_rejim.ekran({"ek": {"rejim": {"kurallar": None, "art_arda_stop": None}}}, "UTC")
        self.assertIn("kural dosyası (puan.py) okunamadı", h)
        self.assertIn("veto eşiği kural dosyasından okunamadı", h)

    def test_metin_kacirilir(self):
        with tempfile.TemporaryDirectory() as t:
            v = r.hesapla(baglam(t))
            v["botlar"] = [{"kod": "<b>", "ad": "<i>x</i>", "izinli_durumlar": ["<s>"]}]
            h = sayfa_rejim.ekran({"ek": {"rejim": v}}, "UTC")
            self.assertNotIn("<i>x</i>", h)
            self.assertNotIn("<s>", h)

    def test_sayfada_betiksiz_bir_kez(self):
        from testler.veri import sahte_sinav_klasoru

        with tempfile.TemporaryDirectory() as t:
            klasor = sahte_sinav_klasoru(Path(t) / "user_data", SIMDI)
            csv_yaz(klasor / "kayit" / "kuresel.csv", seri(SIMDI - timedelta(days=35), 35 * 144))
            ozet = sonuc.genel_ozet(klasor, SIMDI)
            self.assertNotIn("hata", ozet["ek"]["rejim"])
            h = sayfa.html_uret(ozet, yenile_saniye=0)
            self.assertEqual(h.count('<section id="rejim"'), 1)
            self.assertNotIn("<script", h)
            self.assertNotIn("Bu ekran şu an hazırlanamadı. Botlar", h.split('<section id="rejim"')[1].split("</section>")[0])


if __name__ == "__main__":
    unittest.main()
