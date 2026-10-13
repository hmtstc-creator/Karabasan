"""Ahmet Özel kriter listesi (karabasan/kriterler.py) ve sonuç sayfasındaki Kriterler ekranı."""

import json
import unittest
from unittest import mock

from karabasan import kriterler as kr
from karabasan import sayfa
from karabasan import sinama


def _kural(kod):
    return json.loads((kr.ADAY_KLASORU / f"{kod}.json").read_text(encoding="utf-8"))


class KriterListesi(unittest.TestCase):
    def test_degerler_kural_dosyalarindan_okunur(self):
        degerler = {k["kimlik"]: k for k in kr.liste()}
        alim = _kural("AHMETOZEL")
        self.assertEqual(degerler["sma"]["alim"], alim["gostergeler"]["sma200"]["periyot"])
        self.assertEqual(degerler["hedef_r"]["alim"], alim["cikis"]["kar_hedefi_r"])
        self.assertEqual(degerler["sure"]["alim"], alim["cikis"]["sure_asimi_dakika"] / 1440)
        self.assertEqual(degerler["coin_sayisi"]["alim"], len(sinama.COINLER))
        self.assertEqual(degerler["en_az_islem"]["satis"],
                         next(a for a in sinama.ADAYLAR if a["ad"] == "AHMETOZELK")["en_az_islem"])
        self.assertEqual(len(degerler), len(kr.KURAL_KRITERLERI) + len(kr.SINAMA_KRITERLERI))

    def test_alim_ve_satis_ayni_degerleri_tasir(self):
        # Kriter sayfası tek değer gösterir; iki yön ayrışırsa sayfa ikisini birden yazar.
        for k in kr.liste():
            with self.subTest(kriter=k["kimlik"]):
                self.assertEqual(k["alim"], k["satis"])

    def test_iki_seviye_ayni_yaklasma_ayarini_kullanir(self):
        # Sayfa ilk seviyeyi okur; ikinci seviye (FVG) aynı pay ve gün sayısını taşımalı.
        for kod in ("AHMETOZEL", "AHMETOZEL2", "AHMETOZEL3", "AHMETOZELP2",
                    "AHMETOZELK", "AHMETOZELK2", "AHMETOZELK3", "AHMETOZELKP2"):
            grup = next(k for k in _kural(kod)["giris"]["hepsi"] if "herhangi" in k)["herhangi"]
            ilk, ikinci = grup[0]["hepsi"][0], grup[1]["hepsi"][0]
            with self.subTest(kod=kod):
                self.assertEqual(ilk["son_n_mumda"], ikinci["son_n_mumda"])
                self.assertEqual(ilk["sag"]["ekle"]["carpan"], ikinci["sag"]["ekle"]["carpan"])

    def test_pandas_yoksa_sinama_grubu_duser(self):
        with mock.patch.dict("sys.modules", {"karabasan.sinama": None}):
            liste = kr.liste()
        self.assertEqual(len(liste), len(kr.KURAL_KRITERLERI))

    def test_ekran_degerleri_gosterir_ve_duzenleme_sayfasina_baglanir(self):
        html = sayfa._kriterler_ekrani()
        self.assertIn('<section id="kriterler" class="ekran">', html)
        self.assertIn("Bot kriterleri", html)
        self.assertIn(kr.DUZENLEME_ADRESI, html)
        self.assertTrue(kr.DUZENLEME_ADRESI.startswith("https://claude.ai/"))
        self.assertIn("Kısa EMA", html)
        self.assertIn("0,15", html)                       # ondalık virgülle
        self.assertIn("buradan değişiklik yapılmaz", html)
        self.assertNotIn("<form", html)
        self.assertNotIn("<input", html)


if __name__ == "__main__":
    unittest.main()
