"""Sonuç sayfası ve sunucusu."""

import base64
import hashlib
import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import panel, sayfa, sonuc
from testler.veri import ESKI_BOTLAR as BOTLAR
from testler.veri import eski_bot_listesi_baslat, sahte_sinav_klasoru

SIMDI = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)

def setUpModule():
    # Bu testler on iki botluk eski listeyle kurulur (bkz. testler.veri.ESKI_BOTLAR).
    global _geri_al
    _geri_al = eski_bot_listesi_baslat()


def tearDownModule():
    _geri_al()



class BicimTesti(unittest.TestCase):
    def test_turkce_sayi_bicimi(self):
        self.assertEqual(sayfa.sayi(1234.5), "1.234,50")
        self.assertEqual(sayfa.sayi(-0.75), "−0,75")
        self.assertEqual(sayfa.sayi(None), "–")
        self.assertEqual(sayfa.sayi(float("inf")), "sonsuz")

    def test_isaretli_sayi(self):
        self.assertEqual(sayfa.isaretli(19.31), "+19,31")
        self.assertEqual(sayfa.isaretli(-9.256), "−9,26")
        self.assertEqual(sayfa.isaretli(0.001), "0,00")   # eksi sıfır ya da artı sıfır yazılmaz
        self.assertEqual(sayfa.isaretli(-0.001), "0,00")

    def test_yuzde_isareti_basta(self):
        self.assertEqual(sayfa.yuzde(64.62), "%64,6")

    def test_isaretli_yuzde_isaret_onde(self):
        self.assertEqual(sayfa.isaretli_yuzde(1.05), "+%1,05")
        self.assertEqual(sayfa.isaretli_yuzde(-1.14), "−%1,14")
        self.assertEqual(sayfa.isaretli_yuzde(0.0), "%0,00")

    def test_kisa_yuzde_gereksiz_sifir_yazmaz(self):
        self.assertEqual(sayfa.kisa_yuzde(1.2), "%1,2")
        self.assertEqual(sayfa.kisa_yuzde(1.0), "%1")
        self.assertEqual(sayfa.kisa_yuzde(0.75), "%0,75")

    def test_selam_saate_gore(self):
        self.assertEqual(sayfa.selam(7), "Günaydın efendim.")
        self.assertEqual(sayfa.selam(14), "İyi günler efendim.")
        self.assertEqual(sayfa.selam(20), "İyi akşamlar efendim.")
        self.assertEqual(sayfa.selam(2), "İyi geceler efendim.")

    def test_yerel_saat_bukres(self):
        yerel, ad = sayfa.yerel_zaman(SIMDI)
        self.assertEqual(yerel.hour, 11)  # kasımda UTC+2
        self.assertEqual(ad, "Bükreş saati")


class SayfaTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gecici = tempfile.TemporaryDirectory()
        cls.klasor = sahte_sinav_klasoru(Path(cls.gecici.name) / "veri", SIMDI)

    @classmethod
    def tearDownClass(cls):
        cls.gecici.cleanup()

    def test_sinav_sayfasi(self):
        html = sayfa.html_uret(sonuc.genel_ozet(self.klasor, SIMDI))
        self.assertIn("Sınavın 12. günü.", html)
        self.assertIn("18 gün kaldı", html)
        for bot in ("s1-vadeli", "s5k-vadeli", "s7-vadeli"):
            self.assertIn(bot, html)
        # Botlar düz adlarıyla görünür.
        self.assertIn("Yükselişte düşüşü al", html)
        self.assertIn("Yükselişte aşırı düşüşü al (RSI 2)", html)
        self.assertEqual(html.count('class="gun gecti'), 11)
        self.assertEqual(html.count('class="gun bugun'), 1)

    def test_dis_kaynak_yok(self):
        html = sayfa.html_uret(sonuc.genel_ozet(self.klasor, SIMDI))
        # Tek dış adres: Kriterler ekranındaki düzenleme sayfası bağlantısı (gezinme, kaynak yüklemez).
        from karabasan.kriterler import DUZENLEME_ADRESI
        self.assertEqual(html.count(DUZENLEME_ADRESI), html.count(f'<a href="{DUZENLEME_ADRESI}">'))
        html = html.replace(DUZENLEME_ADRESI, "")
        for yasak in ("http://", "https://", "@import", "url(", " src=", "<link", "<iframe", "<object"):
            self.assertNotIn(yasak, html)
        # Tek bir satır içi betik vardır ve o da sayfa.betik()'in ürettiği metindir.
        self.assertEqual(re.findall(r"<script>(.*?)</script>", html, re.S), [sayfa.betik(60)])

    def test_dosya_hali_betiksizdir_ve_kendini_yenilemez(self):
        html = sayfa.html_uret(sonuc.genel_ozet(self.klasor, SIMDI), yenile_saniye=0)
        self.assertNotIn("<script", html)
        self.assertNotIn("http-equiv", html)
        self.assertIn("kendini tazelemez", html)

    def test_ekranlar_ve_gezinti(self):
        html = sayfa.html_uret(sonuc.genel_ozet(self.klasor, SIMDI))
        for kimlik, _ad in sayfa.EKRANLAR:
            self.assertEqual(html.count(f'<section id="{kimlik}" class="ekran">'), 1)
            self.assertIn(f'<a href="#{kimlik}">', html)
            self.assertIn(f"'{kimlik}'", sayfa.betik(60))   # betik de aynı ekranları tanır

    def test_dersler_ekrani_bosken_ne_bekledigini_soyler(self):
        ozet = sonuc.genel_ozet(self.klasor, SIMDI)
        html = sayfa.html_uret(ozet)
        self.assertEqual([k for k, _ in sayfa.EKRANLAR], ["ana", "botlar", "islemler", "dersler", "rapor", "sinav", "kriterler"])
        self.assertIn("Henüz izlenmiş stop yok.", html)
        sirada = sum(b["nedenler"].get("stop", 0) for b in ozet["botlar"])
        self.assertIn(f"Şu an {sirada} stop sırada.", html)
        self.assertIn("Henüz ders yok. Bir botun 30 stopu izlenince", html)
        self.assertIn("Karar hiçbir ayarı değiştirmez.", html)
        self.assertNotIn("Son ders,", html)

    def test_dersler_ekrani_izlenen_stoplari_ve_dersi_gosterir(self):
        from karabasan import stop_sonrasi as ss

        def kayit(k, fark):
            zaman = (SIMDI - timedelta(days=3, minutes=-k)).strftime("%Y-%m-%dT%H:%M:%SZ")
            return {"bot": "s2-vadeli", "kod": "S2", "parite": "SOL/USDT", "yon": "alim",
                    "giris_zamani": zaman, "cikis_zamani": zaman, "gercek_net_yuzde": -1.15,
                    "hedefi_gordu": fark > 0, "en_kotu_yuzde": -1.6,
                    "alternatif": {c: {"sonuc": "hedef" if fark > 0 else "stop", "net_yuzde": -1.15 + fark}
                                   for c in ("1.5", "2", "3")}}

        with tempfile.TemporaryDirectory() as gecici:
            klasor = sahte_sinav_klasoru(Path(gecici) / "veri", SIMDI)
            ss.dosya_yaz(ss.dosya_yolu(klasor), {
                "surum": 1, "basarisiz": {"s2-vadeli#7": 3}, "son_tur": "2026-11-02T09:20:00Z",
                "islemler": {f"s2-vadeli#{900 + k}": kayit(k, 2.7 if k % 3 else -0.5) for k in range(12)},
                "dersler": [{"zaman": "2026-11-01T08:00:00Z", "bot": "s1-vadeli", "kod": "S1",
                             "ad": "Yükselişte düşüşü al", "karar": "yerinde", "carpan": None,
                             "stop_sayisi": 44, "metin": "Stop yerinde görünüyor. <b>örnek</b>"}],
            })
            html = sayfa.html_uret(sonuc.genel_ozet(klasor, SIMDI))
        duz = " ".join(html.split())
        self.assertIn("12 stop izlendi; 8 tanesinde fiyat, işlemin süresi dolmadan kâr hedefini gördü.", duz)
        self.assertIn("1 stop için fiyat verisi alınamadı; hesaba girmiyor.", duz)
        self.assertIn("Stop 1,5 kat geniş olsaydı (%4,5)", duz)
        self.assertIn("8 tanesi hedefe ulaşır, 4 tanesi yine stop olur, 0 tanesinde süre dolardı", duz)
        # 12 stop karar için az: fark soluk yazılır, artı diye renklendirilmez.
        self.assertIn('<span class="secenek-net erken">+9,80', duz)        # (8×2,7 − 4×0,5) × 50 / 100
        self.assertIn('<span class="karar yetersiz">Veri yetersiz</span>', duz)
        # Ders kaydı ve ana ekrandaki şerit; ders metni HTML olarak çalışmaz.
        self.assertIn("<strong>Son ders, 01.11 10:00:</strong> S1 Yükselişte düşüşü al.", duz)
        self.assertIn("Stop yerinde görünüyor. &lt;b&gt;örnek&lt;/b&gt;", duz)
        self.assertNotIn("<b>örnek", html)
        self.assertIn("Son izleme turu: 02.11 11:20.", duz)
        self.assertIn("Stop sonrası: izlenen 12 stopun 8 tanesinde", duz)           # bot kartı

    def test_stop_olan_islemin_sonrasi_satirinda_yazar(self):
        ozet = sonuc.genel_ozet(self.klasor, SIMDI)
        stop = next(i for i in ozet["son_islemler"] if i["neden"] == "stop")
        stop["stop_sonrasi"] = "stop 1,5 kat geniş olsaydı hedefe ulaşırdı"
        html = sayfa.html_uret(ozet)
        self.assertIn('<span class="alt sonra">Sonrası: stop 1,5 kat geniş olsaydı hedefe ulaşırdı</span>', html)

    def test_halkada_her_bot_bir_dilimdir(self):
        ozet = sonuc.genel_ozet(self.klasor, SIMDI)
        html = sayfa.html_uret(ozet)
        self.assertEqual(html.count('class="r-bot '), len(BOTLAR))
        self.assertEqual(html.count('class="r-gun'), 30)
        self.assertEqual(html.count('class="r-gun gecti"'), 11)
        self.assertEqual(html.count('class="r-gun bugun"'), 1)
        for b in ozet["botlar"]:
            self.assertIn(f'<a href="#bot-{b["bot"]}" tabindex="-1">', html)
            self.assertIn(f'<article class="kart kose" id="bot-{b["bot"]}">', html)
        # Kaydı olmayan bot artıda ya da ekside görünmez.
        self.assertIn('class="r-bot yok"', html)
        # Ortadaki sayı toplam sanal sonuçtur.
        self.assertIn(f'>{sayfa.isaretli(ozet["toplam"]["net_tutar"])}</text>', html)

    def test_isinmada_sinav_halkasi_bostur(self):
        with tempfile.TemporaryDirectory() as gecici:
            klasor = Path(gecici)
            (klasor / "isinma_baslangici.txt").write_text((SIMDI - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            html = sayfa.html_uret(sonuc.genel_ozet(klasor, SIMDI))
        self.assertEqual(html.count('class="r-gun"'), 30)
        self.assertIn("Sınav başlayınca her botun yedi ölçütteki durumu", html)

    def test_strateji_ayrintisi_bot_kartinda(self):
        html = sayfa.html_uret(sonuc.genel_ozet(self.klasor, SIMDI))
        self.assertIn("MACD yukarı kesip", html)                      # S5'in açıklaması
        self.assertIn("<dt>Kâr hedefi</dt><dd>%0,8</dd>", html)        # bütün botlarda hedef
        self.assertIn("<dt>Stop</dt><dd>%3</dd>", html)
        self.assertIn("Tasarlandığı piyasa durumu: Kırmızı, Sarı.", html)

    def test_karabasan_olculmedigi_acikca_yazar(self):
        duz = " ".join(sayfa.html_uret(sonuc.genel_ozet(self.klasor, SIMDI)).split())
        self.assertIn("henüz canlı ölçülmüyor", duz)
        self.assertIn("botlar şimdilik her piyasa durumunda işlem açıyor", duz)

    def test_acik_pozisyonlar_ve_vadeli_parite_adi(self):
        ozet = sonuc.genel_ozet(self.klasor, SIMDI)
        html = sayfa.html_uret(ozet)
        self.assertEqual(html.count("önce açıldı"), ozet["toplam"]["acik_pozisyon"])
        self.assertNotIn(":USDT", html)   # SOL/USDT:USDT yerine SOL/USDT yazar

    def test_bos_sunucu_sayfasi(self):
        with tempfile.TemporaryDirectory() as bos:
            html = sayfa.html_uret(sonuc.genel_ozet(Path(bos), SIMDI))
        self.assertIn("Botlar henüz kurulmadı.", html)
        self.assertIn("Henüz kapanmış işlem yok", html)

    def test_isinma_sayfasi_sinav_saati_baslamadi_der(self):
        with tempfile.TemporaryDirectory() as gecici:
            klasor = Path(gecici)
            (klasor / "isinma_baslangici.txt").write_text((SIMDI - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            html = sayfa.html_uret(sonuc.genel_ozet(klasor, SIMDI))
        self.assertIn("Isınma dönemi, 3. gün.", html)
        self.assertIn("sınava sayılmıyor", html)
        self.assertEqual(html.count('class="gun gecti'), 0)

    def test_bitis_sayfasi_gercek_paraya_gecilmedigini_soyler(self):
        html = sayfa.html_uret(sonuc.genel_ozet(self.klasor, SIMDI + timedelta(days=25)))
        self.assertIn("Sınav bitti.", html)
        self.assertIn("Gerçek paraya geçilmiyor", html)

    def test_parite_adi_html_olarak_calismaz(self):
        ozet = sonuc.genel_ozet(self.klasor, SIMDI)
        ozet["son_islemler"][0]["parite"] = "<img src=x onerror=alert(1)>"
        html = sayfa.html_uret(ozet)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)

    def test_yenileme_kapatilabilir(self):
        ozet = sonuc.genel_ozet(self.klasor, SIMDI)
        self.assertIn('http-equiv="refresh"', sayfa.html_uret(ozet))
        self.assertNotIn('http-equiv="refresh"', sayfa.html_uret(ozet, yenile_saniye=0))


class SunucuTesti(unittest.TestCase):
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

    def _al(self, yol):
        with urllib.request.urlopen(self.adres + yol, timeout=5) as yanit:
            return yanit.status, yanit.headers, yanit.read().decode("utf-8")

    def test_ana_sayfa(self):
        kod, baslik, govde = self._al("/")
        self.assertEqual(kod, 200)
        self.assertIn("text/html", baslik["Content-Type"])
        self.assertIn("Sınavın 12. günü.", govde)
        self.assertEqual(baslik["Cache-Control"], "no-store")

    def test_veri_json(self):
        _kod, _baslik, govde = self._al("/veri.json")
        veri = json.loads(govde)
        self.assertEqual(veri["donem"], "sinav")
        self.assertEqual(len(veri["botlar"]), len(BOTLAR))

    def test_guvenlik_basligi_yalniz_sayfadaki_betige_izin_verir(self):
        _kod, baslik, govde = self._al("/")
        betik = re.findall(r"<script>(.*?)</script>", govde, re.S)
        self.assertEqual(len(betik), 1)
        ozet = base64.b64encode(hashlib.sha256(betik[0].encode("utf-8")).digest()).decode("ascii")
        izin = baslik["Content-Security-Policy"]
        self.assertIn(f"script-src 'sha256-{ozet}'", izin)
        self.assertIn("default-src 'none'", izin)
        self.assertIn("connect-src 'self'", izin)
        self.assertNotIn("unsafe-eval", izin)
        self.assertNotIn("script-src 'unsafe-inline'", izin)

    def test_saglik(self):
        self.assertEqual(self._al("/saglik")[2], "tamam\n")

    def test_bilinmeyen_adres_404(self):
        with self.assertRaises(urllib.error.HTTPError) as hata:
            self._al("/../.env")
        self.assertEqual(hata.exception.code, 404)

    def test_yazma_istegi_kabul_edilmez(self):
        istek = urllib.request.Request(self.adres + "/", data=b"x=1", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as hata:
            urllib.request.urlopen(istek, timeout=5)
        self.assertEqual(hata.exception.code, 501)


if __name__ == "__main__":
    unittest.main()
