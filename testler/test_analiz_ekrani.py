"""Analiz ekranı (6 Kasım 2026): yalnız okuma; bot karşılaştırma, kazanma, çıkış nedenleri, süre."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from karabasan import sayfa, sonuc
from testler.veri import ESKI_BOTLAR, eski_bot_listesi_baslat, sahte_sinav_klasoru

SIMDI = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)


def setUpModule():
    global _geri_al
    _geri_al = eski_bot_listesi_baslat()


def tearDownModule():
    _geri_al()


class AnalizEkrani(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        klasor = sahte_sinav_klasoru(Path(cls.gecici.name) / "veri", SIMDI)
        cls.ozet = sonuc.genel_ozet(klasor, SIMDI)
        cls.html = sayfa.html_uret(cls.ozet)

    @classmethod
    def tearDownClass(cls):
        cls.gecici.cleanup()

    def test_ekran_listede_ve_sayfada(self):
        self.assertIn(("analiz", "Analiz"), sayfa.EKRANLAR)
        self.assertIn('id="analiz"', self.html)
        self.assertIn('href="#analiz"', self.html)

    def test_her_bot_gorunur(self):
        bolum = sayfa._analiz_ekrani(self.ozet)
        for b in self.ozet["botlar"]:
            self.assertIn(b["kod"], bolum)

    def test_yalniz_okur(self):
        # Ekran hiçbir ayar ya da kayıt yazmaz; üretilen metin sayfa dışına çıkmaz.
        self.assertNotIn("<form", sayfa._analiz_ekrani(self.ozet))
        self.assertNotIn("<script", sayfa._analiz_ekrani(self.ozet))

    def test_bos_ozet_cokmez(self):
        self.assertIn("Henüz bot yok", sayfa._analiz_ekrani({"botlar": []}))

    def _bot(self, **ek):
        return {**self.ozet["botlar"][0], **ek}

    def test_yuzde_birimi_bir_kez(self):
        # Kazanma ve başa baş oranları zaten yüzde olarak gelir; ekranda %64,6 olmalı, %6461 değil.
        b = self._bot(kazanma_orani=64.6, basabas_orani=50.0, kayip_sayisi=10)
        html = sayfa._analiz_ekrani({"botlar": [b]})
        self.assertIn("%64,6", html)
        self.assertIn("başa baş %50,0", html)
        self.assertNotIn("6460", html)

    def test_beklenti_yuzde_islem_basi_usdt(self):
        # net_beklenti işlem başına yüzdedir; USDT değeri net_tutar / işlem sayısından gelir.
        b = self._bot(net_beklenti=-0.05, net_tutar=-2.0, islem_sayisi=40)
        html = sayfa._analiz_karti(b)
        self.assertIn("−%0,050", html)
        self.assertIn("−0,050", html)  # -2 / 40 USDT

    def test_az_kayipla_basabas_boyanmaz(self):
        b = self._bot(kazanma_orani=90.0, basabas_orani=10.0, kayip_sayisi=2)
        self.assertIn("en az 5 kayıp", sayfa._analiz_karti(b))

    def test_turkce_neden_adlari(self):
        b = self._bot(nedenler={"iz süren stop": 12, "stop": 5, "kâr hedefi": 2, "yeni neden": 1})
        html = sayfa._analiz_ekrani({"botlar": [b]})
        self.assertIn("İz süren stop 12", html)
        self.assertNotIn("Iz süren", html)
        self.assertLess(html.index("Kâr hedefi 2"), html.index("Stop 5"))
        self.assertIn("Yeni neden 1", html)

    def test_sure_isaretsiz_ve_birimli(self):
        b = self._bot(ort_sure_dakika=312.0)
        html = sayfa._analiz_ekrani({"botlar": [b]})
        self.assertIn("5 saat", html)
        self.assertNotIn("+5,20", html)

    def test_islemsiz_bot_sifir_gibi_gorunmez(self):
        b = self._bot(islem_sayisi=0, kazanma_orani=None, net_beklenti=None, net_tutar=0.0)
        html = sayfa._analiz_karti(b)
        self.assertIn("Henüz kapanmış işlem yok", html)
        self.assertNotIn("%0,0", html)

    def test_kaçış_yapilir(self):
        ozet = {**self.ozet, "botlar": [{**self.ozet["botlar"][0], "kod": "<b>x</b>"}]}
        self.assertNotIn("<b>x</b>", sayfa._analiz_ekrani(ozet))


if __name__ == "__main__":
    unittest.main()
