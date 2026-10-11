"""Haberci: Telegram mesajları, sahibin kaydı, komutlar. Ağa çıkmaz; Telegram taklit edilir."""

import io
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import haberci, sonuc
from testler.veri import sahte_sinav_klasoru

SIMDI = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)
KOD = "123456:GIZLI-KOD"


class SahteYanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class SahteTelegram:
    """urlopen yerine geçer; gelen istekleri saklar, sıradaki yanıtı döndürür."""

    def __init__(self):
        self.istekler = []
        self.guncellemeler = []
        self.hata = None

    def __call__(self, istek, timeout=None):
        yontem = istek.full_url.rsplit("/", 1)[1]
        govde = istek.data or b""
        self.istekler.append((yontem, govde, istek.full_url))
        if self.hata is not None:
            raise self.hata
        sonuc_ = self.guncellemeler if yontem == "getUpdates" else {"message_id": 1}
        return SahteYanit(json.dumps({"ok": True, "result": sonuc_}).encode("utf-8"))

    def gonderilenler(self):
        metinler = []
        for yontem, govde, _ in self.istekler:
            if yontem == "sendMessage":
                metinler.append(urllib.parse.parse_qs(govde.decode("utf-8"))["text"][0])
        return metinler

    def belgeler(self):
        return [govde for yontem, govde, _ in self.istekler if yontem == "sendDocument"]


def ozel_mesaj(sira, sohbet, metin, tur="private"):
    return {"update_id": sira, "message": {"chat": {"id": sohbet, "type": tur}, "text": metin}}


class Taban(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.klasor = Path(self.gecici.name)
        self.sahte = SahteTelegram()
        self.tg = haberci.Telegram(KOD, ac=self.sahte)

    def tearDown(self):
        self.gecici.cleanup()


class TelegramTesti(Taban):
    def test_kod_olmadan_kurulmaz(self):
        with self.assertRaises(haberci.TelegramHatasi):
            haberci.Telegram("")

    def test_mesaj_gonderme(self):
        self.tg.mesaj(42, "Merhaba Ahmet")
        yontem, govde, adres = self.sahte.istekler[0]
        self.assertEqual(yontem, "sendMessage")
        self.assertEqual(adres, f"https://api.telegram.org/bot{KOD}/sendMessage")
        alanlar = urllib.parse.parse_qs(govde.decode("utf-8"))
        self.assertEqual(alanlar["chat_id"], ["42"])
        self.assertEqual(alanlar["text"], ["Merhaba Ahmet"])

    def test_uzun_mesaj_bolunur(self):
        self.tg.mesaj(42, "\n".join(f"satır {i} " + "x" * 80 for i in range(120)))
        parcalar = self.sahte.gonderilenler()
        self.assertGreater(len(parcalar), 1)
        self.assertTrue(all(len(p) <= haberci.MESAJ_SINIRI for p in parcalar))
        self.assertTrue(parcalar[0].startswith("satır 0 "))
        self.assertTrue(parcalar[-1].startswith("satır") and "satır 119 " in parcalar[-1])

    def test_belge_gonderme(self):
        self.tg.belge(42, "rapor.txt", "çıktı".encode("utf-8"), "Not")
        govde = self.sahte.belgeler()[0]
        self.assertIn(b'filename="rapor.txt"', govde)
        self.assertIn("çıktı".encode("utf-8"), govde)
        self.assertIn(b'name="caption"', govde)

    def test_hata_metninde_kod_gorunmez(self):
        self.sahte.hata = urllib.error.URLError(f"baglanti koptu https://api.telegram.org/bot{KOD}/x")
        with self.assertRaises(haberci.TelegramHatasi) as hata:
            self.tg.mesaj(42, "x")
        self.assertNotIn(KOD, str(hata.exception))
        self.assertIn("***", str(hata.exception))

    def test_http_hatasi_telegram_hatasina_cevrilir(self):
        self.sahte.hata = urllib.error.HTTPError(
            "adres", 401, "Unauthorized", {}, io.BytesIO(b'{"ok":false,"description":"Unauthorized"}'))
        with self.assertRaises(haberci.TelegramHatasi) as hata:
            self.tg.guncellemeler()
        self.assertIn("401", str(hata.exception))


class SahipTesti(Taban):
    def test_ozelden_start_yazan_sahip_olur(self):
        self.sahte.guncellemeler = [
            ozel_mesaj(1, -500, "/start", tur="group"),
            ozel_mesaj(2, 77, "selam"),
            ozel_mesaj(3, 42, "/start"),
        ]
        self.assertEqual(haberci.sahibi_ogren(self.tg, self.klasor), 42)
        self.assertEqual(haberci.sohbet_oku(self.klasor), 42)

    def test_kayitli_sahip_varken_telegrama_sorulmaz(self):
        haberci.sohbet_yaz(self.klasor, 42)
        self.assertEqual(haberci.sahibi_ogren(self.tg, self.klasor), 42)
        self.assertEqual(self.sahte.istekler, [])

    def test_sahip_yokken_mesaj_siraya_girer_sonra_topluca_gider(self):
        self.assertFalse(haberci.gonder(self.tg, self.klasor, "1/9 Sistem güncelleniyor"))
        self.assertFalse(haberci.gonder(self.tg, self.klasor, "2/9 Güvenlik duvarı"))
        self.assertEqual(self.sahte.gonderilenler(), [])
        self.sahte.guncellemeler = [ozel_mesaj(1, 42, "/start")]
        self.assertTrue(haberci.gonder(self.tg, self.klasor, "3/9 Docker"))
        (metin,) = self.sahte.gonderilenler()
        self.assertIn("1/9 Sistem güncelleniyor", metin)
        self.assertIn("2/9 Güvenlik duvarı", metin)
        self.assertTrue(metin.endswith("3/9 Docker"))
        self.assertFalse(haberci.bekleyen_yolu(self.klasor).exists())

    def test_telegrama_ulasilamazsa_mesaj_kaybolmaz(self):
        self.sahte.hata = urllib.error.URLError("ag yok")
        self.assertFalse(haberci.gonder(self.tg, self.klasor, "önemli"))
        self.assertIn("önemli", haberci.bekleyen_yolu(self.klasor).read_text(encoding="utf-8"))


class ServisTesti(Taban):
    def setUp(self):
        super().setUp()
        sahte_sinav_klasoru(self.klasor, SIMDI)
        self.simdi = SIMDI
        self.servis = haberci.Servis(self.tg, self.klasor, simdi=lambda: self.simdi)

    def _sahip_ol(self):
        haberci.sohbet_yaz(self.klasor, 42)

    def test_ilk_start_sahibi_kaydeder_ve_karsilar(self):
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, "/start"))
        self.assertEqual(haberci.sohbet_oku(self.klasor), 42)
        self.assertIn("sahibim olarak kaydettim", self.sahte.gonderilenler()[0])

    def test_sahip_belli_olunca_baskasi_dinlenmez(self):
        self._sahip_ol()
        self.servis.guncelleme_isle(ozel_mesaj(1, 99, "/start"))
        self.servis.guncelleme_isle(ozel_mesaj(2, 99, "/durum"))
        self.assertEqual(self.sahte.istekler, [])
        self.assertEqual(haberci.sohbet_oku(self.klasor), 42)

    def test_dersler_komutu(self):
        self._sahip_ol()
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, "/dersler"))
        self.assertIn("Henüz izlenmiş stop yok", self.sahte.gonderilenler()[0])
        # İzlenmiş iki stop: biri 1,5 katla hedefe ulaşırdı, diğeri her seçenekte yine stop.
        from karabasan import stop_sonrasi

        def kayit(giris, gercek, fark):
            return {"bot": "s1-vadeli", "kod": "S1", "parite": "SOL/USDT", "yon": "alim",
                    "giris_zamani": giris, "cikis_zamani": giris, "gercek_net_yuzde": gercek,
                    "hedefi_gordu": fark > 0, "en_kotu_yuzde": -1.3,
                    "alternatif": {c: {"sonuc": "hedef" if fark > 0 else "stop", "net_yuzde": gercek + fark}
                                   for c in ("1.5", "2", "3")}}

        zaman = (SIMDI - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        stop_sonrasi.dosya_yaz(stop_sonrasi.dosya_yolu(self.klasor), {
            "surum": 1, "basarisiz": {}, "dersler": [], "son_tur": zaman,
            "islemler": {"s1-vadeli#900": kayit(zaman, -1.15, 2.2), "s1-vadeli#901": kayit(zaman, -1.15, -0.5)},
        })
        self.servis.guncelleme_isle(ozel_mesaj(2, 42, "/dersler"))
        metin = self.sahte.gonderilenler()[-1]
        self.assertIn("Yükselişte düşüşü al [S1]: 2 stop izlendi, 1 tanesinde", metin)
        self.assertIn("1,5 kat +0,85 USDT", metin)          # (2,2 − 0,5) × 50 / 100
        self.assertIn("Karar için en az 30 izlenmiş stop gerekiyor; şimdilik 2 var.", metin)
        self.assertIn("Hiçbir ayar kendiliğinden değişmez.", metin)

    def test_komut_olmayan_mesaja_yanit_yok(self):
        self._sahip_ol()
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, "naber"))
        self.assertEqual(self.sahte.istekler, [])

    def test_durum_komutu(self):
        self._sahip_ol()
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, "/durum"))
        (metin,) = self.sahte.gonderilenler()
        self.assertIn("Sınavın 12. günü, 18 gün kaldı.", metin)
        self.assertIn("Kapanan işlem: 580", metin)
        self.assertIn("En iyi: Yükselişte düşüşü al (s1-vadeli) +19,31 USDT", metin)
        self.assertIn("En kötü: Sert düşüşten dönüşü al (s4-vadeli) −9,26 USDT", metin)
        self.assertIn("hepsi sanal", metin)

    def test_botlar_komutu_her_bota_bir_satir(self):
        from karabasan.botlar import BOTLAR

        self._sahip_ol()
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, "/botlar@KarabasanBot"))
        (metin,) = self.sahte.gonderilenler()
        self.assertEqual(sum(1 for s in metin.splitlines() if ":" in s), len(BOTLAR))
        self.assertIn("Smartmoney: geri çekilme sonrası yapı kırılımıyla alım [sm-vadeli", metin)
        self.assertIn("Momentum vuruşu (MACD + RSI) [s5-vadeli, ses yok]: henüz kapanan işlem yok", metin)
        self.assertIn("Yükselişte düşüşü al [s1-vadeli, ses yok]: 130 işlem", metin)

    def test_sayfa_komutu_html_belgesi_yollar(self):
        self._sahip_ol()
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, "/sayfa"))
        govde = self.sahte.belgeler()[0]
        self.assertIn(b'filename="karabasan-sonuc.html"', govde)
        self.assertIn("Sınavın 12. günü.".encode("utf-8"), govde)

    def test_gunluk_komutu(self):
        self._sahip_ol()
        (self.klasor / "logs").mkdir()
        (self.klasor / "logs" / "s1-vadeli.log").write_text("\n".join(f"satir {i}" for i in range(500)))
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, "/gunluk"))
        toplu = self.sahte.belgeler()[0]
        self.assertIn(b"===== s1-vadeli =====", toplu)
        self.assertIn(b"satir 499", toplu)
        self.assertNotIn(b"satir 400\n", toplu)
        self.assertIn("(kayıt yok)".encode("utf-8"), toplu)
        self.servis.guncelleme_isle(ozel_mesaj(2, 42, "/gunluk s1-vadeli"))
        self.assertIn(b"satir 250", self.sahte.belgeler()[1])

    def test_gunluk_komutu_baska_dosya_okutmaz(self):
        self._sahip_ol()
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, "/gunluk ../../.env"))
        self.assertEqual(self.sahte.belgeler(), [])
        self.assertIn("Böyle bir bot yok", self.sahte.gonderilenler()[0])

    def test_uyum_raporu_yoksa_soyler(self):
        self._sahip_ol()
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, "/uyum"))
        self.assertIn("henüz çalışmadı", self.sahte.gonderilenler()[0])

    def test_bilinmeyen_komut(self):
        self._sahip_ol()
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, "/sat"))
        self.assertIn("tanımıyorum", self.sahte.gonderilenler()[0])

    def test_komut_hatasi_servisi_dusurmez(self):
        self._sahip_ol()
        self.servis._ozet_al = lambda: 1 / 0
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, "/durum"))
        self.assertIn("ZeroDivisionError", self.sahte.gonderilenler()[0])


class ClaudeKomutuTesti(Taban):
    """/claude komutu sunucuda komut çalıştırmaz; yalnız istek dosyası bırakır."""

    def setUp(self):
        super().setUp()
        self.servis = haberci.Servis(self.tg, self.klasor, simdi=lambda: SIMDI)
        haberci.sohbet_yaz(self.klasor, 42)

    def _yaz(self, metin):
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, metin))
        return self.sahte.gonderilenler()[-1]

    def _durum(self, **alanlar):
        (self.klasor / "claude_durum.json").write_text(json.dumps(alanlar))

    def _istekler(self):
        return sorted(d.name for d in self.klasor.glob("claude_*.istek"))

    def test_kurulmadan_once(self):
        self.assertIn("henüz kurulmadı", self._yaz("/claude"))
        self.assertEqual(self._istekler(), [])

    def test_giris_yoksa_baglanti_istenir(self):
        self._durum(kurulu=True, giris=False, oturum=False, adres="")
        self.assertIn("Giriş bağlantısını birazdan", self._yaz("/claude"))
        self.assertEqual(self._istekler(), ["claude_giris.istek"])

    def test_oturum_aciksa_adres_verilir_istek_birakilmaz(self):
        self._durum(kurulu=True, giris=True, oturum=True, adres="https://claude.ai/code/abc")
        yanit = self._yaz("/claude")
        self.assertIn("Karabasan sunucu", yanit)
        self.assertIn("https://claude.ai/code/abc", yanit)
        self.assertEqual(self._istekler(), [])

    def test_giris_var_oturum_kapaliysa_yeniden_acma_istenir(self):
        self._durum(kurulu=True, giris=True, oturum=False, adres="")
        self.assertIn("Yeniden açıyorum", self._yaz("/claude"))
        self.assertEqual(self._istekler(), ["claude_giris.istek"])

    def test_kod_dosyaya_birakilir(self):
        self.assertIn("Kodu aldım", self._yaz("/claude Ab12_cd-34#Ef56.gh~78"))
        dosya = self.klasor / "claude_kod.istek"
        self.assertEqual(dosya.read_text(), "Ab12_cd-34#Ef56.gh~78\n")
        self.assertEqual(dosya.stat().st_mode & 0o777, 0o600)

    def test_koda_benzemeyen_metin_dosyaya_yazilmaz(self):
        for metin in ("/claude kısa", "/claude $(reboot)", "/claude a;b|c&d>e`f`gh", "/claude " + "x" * 600,
                      "/claude ../../etc/passwd"):
            self.assertIn("benzemiyor", self._yaz(metin), metin)
        self.assertEqual(self._istekler(), [])

    def test_baskasi_istek_birakamaz(self):
        self._durum(kurulu=True, giris=False, oturum=False, adres="")
        self.servis.guncelleme_isle(ozel_mesaj(1, 99, "/claude"))
        self.servis.guncelleme_isle(ozel_mesaj(2, 99, "/claude Ab12_cd-34#Ef56"))
        self.assertEqual(self._istekler(), [])


class SinavBaslatmaTesti(Taban):
    def setUp(self):
        super().setUp()
        self.simdi = SIMDI
        self.servis = haberci.Servis(self.tg, self.klasor, simdi=lambda: self.simdi)
        haberci.sohbet_yaz(self.klasor, 42)

    def _yaz(self, metin):
        self.servis.guncelleme_isle(ozel_mesaj(1, 42, metin))
        return self.sahte.gonderilenler()[-1]

    def test_kurulumdan_once_baslamaz(self):
        self.assertIn("önce kurulum bitmeli", self._yaz("/sinav_baslat evet"))
        self.assertFalse((self.klasor / "sinav_baslangici.txt").exists())

    def test_onaysiz_baslamaz_ve_erken_ise_uyarir(self):
        (self.klasor / "isinma_baslangici.txt").write_text((SIMDI - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        yanit = self._yaz("/sinav_baslat")
        self.assertIn("3. günündeyiz", yanit)
        self.assertIn("/sinav_baslat evet", yanit)
        self.assertFalse((self.klasor / "sinav_baslangici.txt").exists())

    def test_onayla_baslar_ve_ikinci_kez_baslamaz(self):
        (self.klasor / "isinma_baslangici.txt").write_text((SIMDI - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertIn("30 günlük sınav başladı", self._yaz("/sinav_baslat evet"))
        self.assertEqual(sonuc.zaman_dosyasi_oku(self.klasor / "sinav_baslangici.txt"), SIMDI)
        self.simdi = SIMDI + timedelta(days=3)
        self.assertIn("zaten başladı", self._yaz("/sinav_baslat evet"))
        self.assertEqual(sonuc.zaman_dosyasi_oku(self.klasor / "sinav_baslangici.txt"), SIMDI)


class ZamanliIslerTesti(Taban):
    def setUp(self):
        super().setUp()
        sahte_sinav_klasoru(self.klasor, SIMDI)
        (self.klasor / "logs").mkdir()
        self.simdi = SIMDI
        self.servis = haberci.Servis(self.tg, self.klasor, simdi=lambda: self.simdi)
        haberci.sohbet_yaz(self.klasor, 42)

    def _gunluk_yaz(self, bot, dakika_once):
        dosya = self.klasor / "logs" / f"{bot}.log"
        dosya.write_text("x\n")
        zaman = (self.simdi - timedelta(minutes=dakika_once)).timestamp()
        os.utime(dosya, (zaman, zaman))

    def _hepsi_calisiyor(self):
        from karabasan.botlar import BOTLAR

        for bot, *_ in BOTLAR:
            self._gunluk_yaz(bot, 1)

    def test_susan_bot_bir_kez_bildirilir_donunce_bir_kez(self):
        self._hepsi_calisiyor()
        self.servis.zamanli_isler()
        self.assertEqual(self.sahte.gonderilenler(), [])
        self._gunluk_yaz("s3-vadeli", 40)
        self.servis.zamanli_isler()
        self.servis.zamanli_isler()
        mesajlar = self.sahte.gonderilenler()
        self.assertEqual(len(mesajlar), 1)
        self.assertIn("Ses vermeyen bot var: s3-vadeli.", mesajlar[0])
        self._gunluk_yaz("s3-vadeli", 1)
        self.servis.zamanli_isler()
        self.assertIn("Yeniden çalışıyor: s3-vadeli.", self.sahte.gonderilenler()[-1])

    def test_yeni_eklenen_bot_acilana_kadar_susmus_sayilmaz(self):
        """Güncellemeyle eklenen bot sırası gelene kadar hiç kayıt yazmaz; yanlış alarm olmasın."""
        from karabasan.botlar import BOTLAR

        def digerleri_calisiyor():
            for bot, *_ in BOTLAR:
                if bot != "sm-vadeli":
                    self._gunluk_yaz(bot, 1)

        digerleri_calisiyor()
        self.servis.zamanli_isler()
        self.simdi = SIMDI + timedelta(minutes=29)
        digerleri_calisiyor()
        self.servis.zamanli_isler()
        self.assertEqual(self.sahte.gonderilenler(), [])
        # Yarım saat geçti, bot hâlâ hiç yazmadı: artık gerçek bir sorundur.
        self.simdi = SIMDI + timedelta(minutes=31)
        digerleri_calisiyor()
        self.servis.zamanli_isler()
        (mesaj,) = self.sahte.gonderilenler()
        self.assertIn("Ses vermeyen bot var: sm-vadeli.", mesaj)

    def test_yazip_susan_bot_acilistan_hemen_sonra_da_bildirilir(self):
        self._hepsi_calisiyor()
        self._gunluk_yaz("s2-vadeli", 40)
        self.servis.zamanli_isler()
        (mesaj,) = self.sahte.gonderilenler()
        self.assertIn("Ses vermeyen bot var: s2-vadeli.", mesaj)

    def test_gunluk_ozet_gunde_bir_kez_ve_ilk_acilista_degil(self):
        self._hepsi_calisiyor()
        self.simdi = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)   # Bükreş 10:00
        self._hepsi_calisiyor()
        self.servis.zamanli_isler()                                     # servis yeni açıldı: özet yok
        self.assertEqual(self.sahte.gonderilenler(), [])
        self.simdi = datetime(2026, 11, 3, 6, 30, tzinfo=timezone.utc)  # Bükreş 08:30
        self._hepsi_calisiyor()
        self.servis.zamanli_isler()
        self.assertEqual(self.sahte.gonderilenler(), [])
        self.simdi = datetime(2026, 11, 3, 7, 5, tzinfo=timezone.utc)   # Bükreş 09:05
        self._hepsi_calisiyor()
        self.servis.zamanli_isler()
        self.servis.zamanli_isler()
        mesajlar = self.sahte.gonderilenler()
        self.assertEqual(len(mesajlar), 1)
        self.assertTrue(mesajlar[0].startswith("Günlük özet"))

    def test_sahip_yokken_hicbir_sey_gonderilmez(self):
        haberci.sohbet_yolu(self.klasor).unlink()
        self.servis.zamanli_isler()
        self.assertEqual(self.sahte.istekler, [])

    def _ders_yaz(self, *dersler):
        from karabasan import stop_sonrasi

        yol = stop_sonrasi.dosya_yolu(self.klasor)
        veri = stop_sonrasi.dosya_oku(yol)
        veri["dersler"] += [
            {"zaman": zaman, "bot": "s2-vadeli", "kod": "S2", "ad": "Tepe kırılımını al",
             "karar": karar, "carpan": None, "stop_sayisi": 40, "metin": metin}
            for zaman, karar, metin in dersler
        ]
        stop_sonrasi.dosya_yaz(yol, veri)

    def test_yeni_ders_bir_kez_bildirilir(self):
        self._hepsi_calisiyor()
        self.servis.zamanli_isler()
        self.assertEqual(self.sahte.gonderilenler(), [])
        self._ders_yaz(("2026-11-01T10:00:00Z", "dar", "Stop dar görünüyor. Örnek metin."))
        self.servis.zamanli_isler()
        self.servis.zamanli_isler()
        mesajlar = self.sahte.gonderilenler()
        self.assertEqual(len(mesajlar), 1)
        self.assertTrue(mesajlar[0].startswith("Yeni ders: Tepe kırılımını al [S2]"))
        self.assertIn("Stop dar görünüyor. Örnek metin.", mesajlar[0])
        self.assertIn("/dersler", mesajlar[0])
        # Servis yeniden başlasa da aynı ders yinelenmez; yenisi gelince yalnız o gider.
        servis = haberci.Servis(self.tg, self.klasor, simdi=lambda: self.simdi)
        servis.zamanli_isler()
        self.assertEqual(len(self.sahte.gonderilenler()), 1)
        self._ders_yaz(("2026-11-02T09:00:00Z", "yerinde", "Stop yerinde görünüyor."))
        servis.zamanli_isler()
        self.assertEqual(len(self.sahte.gonderilenler()), 2)
        self.assertIn("Stop yerinde görünüyor.", self.sahte.gonderilenler()[-1])


class KomutSatiriTesti(unittest.TestCase):
    def test_kod_yokken_gonder_kurulumu_durdurmaz(self):
        eski = os.environ.pop("TELEGRAM_TOKEN", None)
        try:
            self.assertEqual(haberci.main(["gonder", "merhaba"]), 0)
        finally:
            if eski is not None:
                os.environ["TELEGRAM_TOKEN"] = eski

    def test_gonder_pandas_olmadan_calisir(self):
        """Sunucunun kendi Python'unda pandas yoktur; kurulum mesajları yine de gitmeli."""
        import subprocess
        import sys

        kod = (
            "import sys\n"
            "sys.modules['pandas'] = None\nsys.modules['numpy'] = None\n"
            "from karabasan import haberci, botlar\n"
            "raise SystemExit(haberci.main(['gonder', 'x']))\n"
        )
        ortam = {k: v for k, v in os.environ.items() if k != "TELEGRAM_TOKEN"}
        sonuc_ = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True,
                                cwd=Path(__file__).resolve().parent.parent, env=ortam)
        self.assertEqual(sonuc_.returncode, 0, sonuc_.stderr)


if __name__ == "__main__":
    unittest.main()
