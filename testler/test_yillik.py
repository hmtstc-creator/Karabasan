import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from karabasan import gostergeler as g
from karabasan import yillik as y
from testler.veri import ESKI_BOTLAR as BOTLAR
from karabasan.kural import kural_yukle
from testler.veri import eski_bot_listesi_baslat, yapay_mumlar

AYAR = {"komisyon_yuzde": {"spot": 0.075, "vadeli": 0.05}, "islem_tutari": 50, "sanal_bakiye": 1000}

def setUpModule():
    # Bu testler on iki botluk eski listeyle kurulur (bkz. testler.veri.ESKI_BOTLAR).
    global _geri_al
    _geri_al = eski_bot_listesi_baslat()


def tearDownModule():
    _geri_al()



def yukleyici(gun=120, eksik=()):
    """Yapay veriden mum yükleyici: her coin ve dilim için ayrı ama tekrarlanabilir veri."""
    onbellek = {}

    def yukle(coin, dilim, piyasa):
        if (coin, dilim) in eksik:
            return None
        anahtar = (coin, dilim, piyasa)
        if anahtar not in onbellek:
            tohum = sum(map(ord, coin))
            df5 = yapay_mumlar(gun * 288, dilim_dk=5, tohum=tohum, oynaklik=0.003)
            onbellek[anahtar] = df5 if dilim == "5m" else g.ust_dilime_cevir(df5, "5m", dilim)
        return onbellek[anahtar]

    return yukle


class YillikRaporTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Hızlı olsun diye 120 günlük veride 100 günlük dönem.
        cls.metin, cls.json, cls.eksik = y.rapor_uret(yukleyici(), gun=100, ayar=AYAR)

    def test_her_bot_ve_ozet_var(self):
        for bot, _s, kod, _p in BOTLAR:
            self.assertIn(f"{bot}: {kod} ", self.metin)
        self.assertIn("\nÖZET\n", self.metin)
        self.assertIn("Artıda biten çeyrek:", self.metin)
        self.assertIn("ayar önerisi değildir", self.metin)
        self.assertEqual(self.eksik, 0)

    def test_json_sinav_olcutunun_okudugu_bicimde(self):
        from karabasan.sonuc import _gecmis_test_oku

        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "gecmis_test.json"
            yol.write_text(json.dumps(self.json), encoding="utf-8")
            okunan = _gecmis_test_oku(yol)
        islem_olan = [b[0] for b in BOTLAR if b[0] in self.json]
        self.assertGreater(len(islem_olan), 6)
        self.assertEqual(sorted(okunan), sorted(islem_olan))     # "_bilgi" düşer
        self.assertEqual(self.json["_bilgi"]["gun"], 100)

    def test_ceyreklerin_toplami_yilin_netine_esit(self):
        kural = kural_yukle("S5")
        bas = pd.Timestamp("2026-01-20", tz="UTC")
        son = pd.Timestamp("2026-04-30", tz="UTC")
        islemler, _ = y.islemleri_topla(kural, "vadeli", yukleyici(), 0.05, bas, son)
        self.assertGreater(len(islemler), 20)
        self.assertEqual({i["coin"] for i in islemler} & {"BTC"}, set())    # vadelide BTC yok
        ceyrekler = y.ceyreklere_bol(islemler, bas, son, 50.0)
        self.assertEqual(len(ceyrekler), 4)
        self.assertEqual(sum(c["islem"] for c in ceyrekler), len(islemler))
        self.assertAlmostEqual(sum(c["net"] for c in ceyrekler),
                               sum(i["net_yuzde"] for i in islemler) * 0.5, places=6)

    def test_karsilastirma_yalniz_stopu_degistirir(self):
        kural = kural_yukle("S1")
        kopya = y.stop_hedefe_esit(kural)
        self.assertEqual(kopya["cikis"]["zarar_durdur_yuzde"], kural["cikis"]["kar_hedefi_yuzde"])
        self.assertEqual(kural["cikis"]["zarar_durdur_yuzde"], 3.0)            # asıl kural değişmedi
        self.assertEqual({k: v for k, v in kopya.items() if k != "cikis"},
                         {k: v for k, v in kural.items() if k != "cikis"})

    def test_kisa_veri_uyarilir_eksik_dosya_sayilir(self):
        metin, _json, eksik = y.rapor_uret(yukleyici(gun=40, eksik={("DOGE", "15m")}), gun=60, ayar=AYAR)
        self.assertIn("tam kapsamıyor", metin)
        self.assertGreater(eksik, 0)
        self.assertIn("veri yok: DOGE 15m", metin)


class YillikAraciTesti(unittest.TestCase):
    def test_betik_yazim_denetimi_ve_kur_sh_baglantisi(self):
        import subprocess

        kok = Path(__file__).resolve().parent.parent
        self.assertEqual(subprocess.run(["bash", "-n", str(kok / "araclar" / "yillik_test.sh")]).returncode, 0)
        kur = (kok / "kur.sh").read_text(encoding="utf-8")
        self.assertIn("bash araclar/yillik_test.sh", kur)
        self.assertIn("YILLIK_SURUMU=", kur)


if __name__ == "__main__":
    unittest.main()
