"""Strateji dosyasının ve bot yapılandırmalarının sınanması.

Uyarı: buradaki 'freqtrade' sahte bir kopyadır (testler/sahte). Bu testler
bağlantı katmanının kendi mantığını sınar; gerçek motorla uyumu sınamaz.
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "testler" / "sahte"))

from karabasan import botlar  # noqa: E402
from karabasan.kural import kural_yukle, sinyal_uret  # noqa: E402
from testler.veri import yapay_mumlar  # noqa: E402


def strateji_modulu():
    yol = KOK / "user_data" / "strategies" / "karabasan_stratejileri.py"
    tanim = importlib.util.spec_from_file_location("karabasan_stratejileri", yol)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


class StratejiSiniflari(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modul = strateji_modulu()

    def test_her_bot_icin_sinif_var(self):
        for bot, sinif, kural_kodu, piyasa in botlar.BOTLAR:
            with self.subTest(bot=bot):
                s = getattr(self.modul, sinif)
                self.assertEqual(s.kural_kodu, kural_kodu)
                self.assertEqual(s.piyasa, piyasa)
                # Motor, sınıfı yalnız bu dosyada tanımlıysa bulur.
                self.assertEqual(s.__module__, "karabasan_stratejileri")

    def test_sinif_ozellikleri_kural_dosyasindan(self):
        s = self.modul.S1Spot
        self.assertEqual(s.timeframe, "5m")
        self.assertAlmostEqual(s.stoploss, -0.01)
        self.assertFalse(s.can_short)
        self.assertEqual(s.startup_candle_count, 1870)
        self.assertEqual(self.modul.S3Spot.timeframe, "15m")
        self.assertAlmostEqual(self.modul.S4Vadeli.stoploss, -0.008)

    def test_yalniz_ters_yonluler_aciga_satar(self):
        for _bot, sinif, kural_kodu, _piyasa in botlar.BOTLAR:
            s = getattr(self.modul, sinif)
            self.assertEqual(s.can_short, kural_kodu.endswith("K"))
            if s.can_short:
                self.assertEqual(s.piyasa, "vadeli")

    def test_kar_hedefi_fiyat_hareketine_karsilik_gelir(self):
        # Spot, komisyon %0,075: fiyat %1,2 yükseldiğinde komisyon sonrası kâr
        roi = self.modul.S1Spot.minimal_roi["0"]
        self.assertAlmostEqual(roi, 1.012 * (1 - 0.00075) / (1 + 0.00075) - 1)
        self.assertTrue(0.0104 < roi < 0.0106)
        # Vadelide komisyon daha düşük olduğu için aynı fiyat hedefi daha yüksek net kâr demektir
        self.assertGreater(self.modul.S1Vadeli.minimal_roi["0"], roi)

    def test_zararda_ekleme_kapali(self):
        for _bot, sinif, _k, _p in botlar.BOTLAR:
            self.assertFalse(getattr(self.modul, sinif).position_adjustment_enable)

    def test_spotta_aciga_satis_reddedilir(self):
        with self.assertRaises(ValueError):
            type("Yanlis", (self.modul.KarabasanTaban,), {"kural_kodu": "S1K", "piyasa": "spot"})

    def test_giris_sinyalleri_cekirdekle_ayni(self):
        df5 = yapay_mumlar(5000, dilim_dk=5, tohum=21)
        df15 = yapay_mumlar(2500, dilim_dk=15, tohum=21)
        for _bot, sinif, kural_kodu, _piyasa in botlar.BOTLAR:
            with self.subTest(sinif=sinif):
                s = getattr(self.modul, sinif)()
                df = df15 if s.timeframe == "15m" else df5
                tablo = s.populate_indicators(df.copy(), {"pair": "TEST/USDT"})
                tablo = s.populate_entry_trend(tablo, {"pair": "TEST/USDT"})
                tablo = s.populate_exit_trend(tablo, {"pair": "TEST/USDT"})
                beklenen = sinyal_uret(df, kural_yukle(kural_kodu))["sinyal"]
                sutun = "enter_short" if s.can_short else "enter_long"
                self.assertEqual((tablo[sutun] == 1).tolist(), beklenen.tolist())
                # enter_long sütunu her zaman bulunmalı; ters yönlüde hep sıfır
                self.assertIn("enter_long", tablo.columns)
                if s.can_short:
                    self.assertEqual(int(tablo["enter_long"].sum()), 0)
                self.assertEqual(int(tablo["exit_long"].sum()), 0)
                if beklenen.any():
                    self.assertTrue((tablo.loc[beklenen, "enter_tag"] == kural_kodu).all())

    def test_sure_asimi(self):
        s = self.modul.S1Spot()
        acilis = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        islem = sys.modules["freqtrade.persistence"].Trade(acilis)
        self.assertIsNone(s.custom_exit("X/USDT", islem, acilis + timedelta(minutes=239), 1.0, 0.0))
        self.assertEqual(
            s.custom_exit("X/USDT", islem, acilis + timedelta(minutes=240), 1.0, 0.0), "sure_asimi"
        )

    def test_kaldirac_her_zaman_bir(self):
        s = self.modul.S1KVadeli()
        simdi = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(s.leverage("X/USDT:USDT", simdi, 1.0, 5.0, 20.0, None, "short"), 1.0)

    def test_stop_sonrasi_bekleme_korumasi(self):
        koruma = self.modul.S1Spot().protections
        self.assertEqual(len(koruma), 1)
        self.assertEqual(koruma[0]["method"], "StoplossGuard")
        self.assertEqual(koruma[0]["stop_duration_candles"], 48)   # 240 dk / 5 dk
        self.assertTrue(koruma[0]["only_per_pair"])
        self.assertEqual(self.modul.S3Spot().protections[0]["stop_duration_candles"], 16)


class Ayarlar(unittest.TestCase):
    def test_net_hedef_orani(self):
        self.assertAlmostEqual(botlar.net_hedef_orani(1.0, 0.0), 0.01)
        alim = botlar.net_hedef_orani(1.2, 0.05)
        satis = botlar.net_hedef_orani(1.2, 0.05, aciga_satis=True)
        self.assertAlmostEqual(alim, 1.012 * 0.9995 / 1.0005 - 1)
        self.assertAlmostEqual(satis, 1 - 0.988 * 1.0005 / 0.9995)
        self.assertLess(abs(alim - satis), 0.0001)

    def test_dosya_yoksa_baslangic_degerleri(self):
        ayar = botlar.ayarlari_yukle(Path("/olmayan/ayarlar.json"))
        self.assertEqual(ayar["komisyon_yuzde"], {"spot": 0.075, "vadeli": 0.05})

    def test_dosyadaki_deger_baslangici_ezer(self):
        with tempfile.TemporaryDirectory() as klasor:
            yol = Path(klasor) / "ayarlar.json"
            yol.write_text(json.dumps({"komisyon_yuzde": {"spot": 0.1}}), encoding="utf-8")
            ayar = botlar.ayarlari_yukle(yol)
            self.assertEqual(ayar["komisyon_yuzde"]["spot"], 0.1)
            self.assertEqual(ayar["komisyon_yuzde"]["vadeli"], 0.05)   # verilmeyen korunur
            self.assertEqual(ayar["islem_tutari"], 50)

    def test_hatali_komisyon_reddedilir(self):
        with tempfile.TemporaryDirectory() as klasor:
            yol = Path(klasor) / "ayarlar.json"
            # Yüzde yerine oran yazılırsa (7,5) ya da eksi değer girilirse durur
            for hatali in (7.5, -0.1, "0.075", True):
                yol.write_text(json.dumps({"komisyon_yuzde": {"spot": hatali}}), encoding="utf-8")
                with self.assertRaises(botlar.AyarHatasi):
                    botlar.ayarlari_yukle(yol)


class Yapilandirma(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(KOK / "araclar"))
        import yapilandirma_uret
        cls.uret = yapilandirma_uret
        cls.ayar = json.loads(json.dumps(botlar.VARSAYILAN_AYARLAR))

    def test_her_bot_sanal_ve_anahtarsiz(self):
        for bot, _sinif, kural_kodu, piyasa in botlar.BOTLAR:
            with self.subTest(bot=bot):
                y = self.uret.bot_yapilandirmasi(bot, kural_kodu, piyasa, self.ayar)
                self.assertIs(y["dry_run"], True)
                self.assertEqual(y["exchange"]["key"], "")
                self.assertEqual(y["exchange"]["secret"], "")
                self.assertEqual(y["stake_amount"], 50)
                self.assertEqual(y["max_open_trades"], 20)
                self.assertEqual(y["dry_run_wallet"], 1000)
                self.assertFalse(y["force_entry_enable"])
                json.dumps(y)  # JSON'a çevrilebilir olmalı

    def test_piyasa_ayarlari(self):
        spot = self.uret.bot_yapilandirmasi("s1-spot", "S1", "spot", self.ayar)
        vadeli = self.uret.bot_yapilandirmasi("s1-vadeli", "S1", "vadeli", self.ayar)
        self.assertEqual(spot["trading_mode"], "spot")
        self.assertNotIn("margin_mode", spot)
        self.assertAlmostEqual(spot["fee"], 0.00075)
        self.assertEqual(vadeli["trading_mode"], "futures")
        self.assertEqual(vadeli["margin_mode"], "isolated")
        self.assertAlmostEqual(vadeli["fee"], 0.0005)

    def test_piyasa_emri_karsi_taraftan_fiyatlanir(self):
        y = self.uret.bot_yapilandirmasi("s1-spot", "S1", "spot", self.ayar)
        self.assertEqual(y["entry_pricing"]["price_side"], "other")
        self.assertEqual(y["exit_pricing"]["price_side"], "other")
        self.assertEqual(y["order_types"]["entry"], "market")

    def test_kara_liste_sabit_coinleri_tutar_ama_jup_gibi_coinleri_tutmaz(self):
        import re
        desenler = [re.compile(d) for d in self.uret.kara_liste("vadeli")]

        def haric(parite):
            return any(d.fullmatch(parite) for d in desenler)

        for parite in ("USDC/USDT", "FDUSD/USDT", "WBTC/USDT", "BNB/USDT", "XAU/USDT:USDT"):
            self.assertTrue(haric(parite), parite)
        for parite in ("BTC/USDT", "JUP/USDT", "SOL/USDT:USDT", "DOGE/USDT", "WIF/USDT", "EURC/USDT"):
            self.assertFalse(haric(parite), parite)

    def test_compose_on_bot_ve_yerel_port(self):
        metin = self.uret.compose_metni()
        for sira, (bot, sinif, _k, _p) in enumerate(botlar.BOTLAR):
            self.assertIn(f"  {bot}:", metin)
            self.assertIn(f"--strategy {sinif}", metin)
            self.assertIn(f'"127.0.0.1:{botlar.ILK_PORT + sira}:8080"', metin)
        # Hiçbir port dış ağa açılmamalı
        self.assertNotIn('"0.0.0.0:', metin)
        self.assertEqual(metin.count("127.0.0.1:"), len(botlar.BOTLAR) + 1)  # botlar ve sonuç sayfası

    def test_compose_sonuc_sayfasi_ve_haberci(self):
        metin = self.uret.compose_metni()
        self.assertIn('"127.0.0.1:8080:8080"', metin)
        self.assertIn('entrypoint: ["python3", "-m", "karabasan.panel"]', metin)
        self.assertIn('entrypoint: ["python3", "-m", "karabasan.haberci", "servis"]', metin)
        # Telegram kodunu yalnız haberci görür.
        self.assertEqual(metin.count("env_file: telegram.env"), 1)
        haberci = metin.split("  haberci:")[1].split("\n\n")[0]
        self.assertIn("env_file: telegram.env", haberci)
        self.assertNotIn("ports:", haberci)
        # Hiçbir kapı dışarıya açılmaz.
        import re

        for kapi in re.findall(r'- "([^"]+:\d+:\d+)"', metin):
            self.assertTrue(kapi.startswith("127.0.0.1:"), kapi)

    def test_uretec_pandas_olmadan_calisir(self):
        """Sunucunun kendi Python'unda pandas yok; yapılandırma yine de üretilebilmeli."""
        import subprocess
        import sys

        kod = (
            "import sys\n"
            "sys.modules['pandas'] = None\nsys.modules['numpy'] = None\n"
            "sys.path.insert(0, 'araclar')\n"
            "import yapilandirma_uret as u\n"
            "from karabasan.botlar import BOTLAR, ayarlari_yukle\n"
            "a = ayarlari_yukle()\n"
            "for bot, _s, kural, piyasa in BOTLAR:\n"
            "    assert u.bot_yapilandirmasi(bot, kural, piyasa, a)['dry_run'] is True\n"
            "assert 'kb-panel' in u.compose_metni()\n"
        )
        kok = Path(__file__).resolve().parent.parent
        sonuc = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True, cwd=kok)
        self.assertEqual(sonuc.returncode, 0, sonuc.stderr)

    def test_geri_test_sabit_liste(self):
        spot = self.uret.geri_test_yapilandirmasi("spot")
        vadeli = self.uret.geri_test_yapilandirmasi("vadeli")
        self.assertEqual(spot["pairlists"], [{"method": "StaticPairList"}])
        self.assertIn("BTC/USDT", spot["exchange"]["pair_whitelist"])
        self.assertIn("BTC/USDT:USDT", vadeli["exchange"]["pair_whitelist"])


if __name__ == "__main__":
    unittest.main()


class BagimsizKarsilastirma(unittest.TestCase):
    def test_karsilastirma_tablosu_uretilir(self):
        import contextlib
        import io
        from unittest import mock

        sys.path.insert(0, str(KOK / "araclar"))
        import karsilastir

        veri = {
            "5m": yapay_mumlar(12000, dilim_dk=5, tohum=31, oynaklik=0.0035),
            "15m": yapay_mumlar(4000, dilim_dk=15, tohum=31, oynaklik=0.006),
        }

        def sahte_dosya(coin, dilim, piyasa):
            return Path(f"/sahte/{coin}-{dilim}-{piyasa}.feather")

        def sahte_oku(yol):
            return veri["15m" if "-15m-" in str(yol) else "5m"]

        cikti = io.StringIO()
        with mock.patch.object(karsilastir, "veri_dosyasi", sahte_dosya), \
                mock.patch.object(karsilastir.pd, "read_feather", sahte_oku), \
                mock.patch.object(sys, "argv", ["karsilastir.py", "30"]), \
                contextlib.redirect_stdout(cikti):
            kod = karsilastir.main()
        self.assertEqual(kod, 0)
        metin = cikti.getvalue()
        for bot, _s, _k, _p in botlar.BOTLAR:
            self.assertIn(bot, metin)

    def test_veri_yoksa_uyarir(self):
        import contextlib
        import io
        from unittest import mock

        sys.path.insert(0, str(KOK / "araclar"))
        import karsilastir

        cikti = io.StringIO()
        with mock.patch.object(karsilastir, "veri_dosyasi", lambda *a: None), \
                mock.patch.object(sys, "argv", ["karsilastir.py"]), \
                contextlib.redirect_stdout(cikti):
            self.assertEqual(karsilastir.main(), 1)
        self.assertIn("UYARI", cikti.getvalue())


class KurulumBetikleriTesti(unittest.TestCase):
    """Sunucu betikleri burada çalıştırılamaz; yalnız yazım ve temel güvenlik denetlenir."""

    BETIKLER = ["kur.sh", "guncelle.sh", "araclar/oto_guncelle.sh", "araclar/ozel_ag.sh",
                "araclar/uyum_denemesi.sh", "araclar/claude_sunucu.sh", "kurulum/sunucu_blogu.sh"]

    def test_betikler_yazim_denetiminden_gecer(self):
        import subprocess

        for betik in self.BETIKLER:
            sonuc = subprocess.run(["bash", "-n", str(KOK / betik)], capture_output=True, text=True)
            self.assertEqual(sonuc.returncode, 0, f"{betik}: {sonuc.stderr}")

    def test_sunucu_blogunda_gercek_kod_yok(self):
        metin = (KOK / "kurulum" / "sunucu_blogu.sh").read_text(encoding="utf-8")
        self.assertIn("TELEGRAM_TOKEN=BURAYA_TELEGRAM_KODU\n", metin)
        self.assertTrue(metin.startswith("#!/bin/bash\n"))  # sağlayıcı bunu ilk açılışta betik olarak çalıştırır

    def test_betiklerde_gercek_para_ayari_yok(self):
        for betik in self.BETIKLER:
            metin = (KOK / betik).read_text(encoding="utf-8").lower()
            for yasak in ("dry_run", "api_key", "binance_key", "secret="):
                self.assertNotIn(yasak, metin, f"{betik}: {yasak}")

    def test_claude_betigi_telegramdan_geleni_komut_olarak_calistirmaz(self):
        """Giriş kodu yalnız harfi harfine yazılır; kabukta yorumlanacak bir yere konmaz."""
        metin = (KOK / "araclar" / "claude_sunucu.sh").read_text(encoding="utf-8")
        self.assertIn('send-keys -t giris -l -- "$KOD"', metin)
        self.assertIn("grep -Eq '^[A-Za-z0-9_#.~-]{8,512}$'", metin)
        for yasak in ("eval ", 'bash -c "$KOD', "sh -c \"$KOD", "$($KOD", "`$KOD"):
            self.assertNotIn(yasak, metin)
        # Kod, ekranında yalnız giriş programı çalışan oturuma yazılır (kabuk açık değildir).
        self.assertIn('new-session -d -s giris -x 600 -y 50 "claude auth login --claudeai"', metin)

    def test_hicbir_betik_disariya_kapi_acmaz(self):
        import re

        for betik in self.BETIKLER:
            metin = (KOK / betik).read_text(encoding="utf-8")
            for satir in re.findall(r"^\s*ufw allow.*$", metin, flags=re.M):
                self.assertTrue("tailscale0" in satir or "22/tcp" in satir, f"{betik}: {satir.strip()}")


class UyumDenemesiTesti(unittest.TestCase):
    """Uyum denemesi betiği taklit bir 'docker' ile çalıştırılır.

    İlk kurulumda hazır motor on geçmiş testinde de ayar hatası verdi, ama çıkış
    kodu temiz göründüğü için betik "geçti" yazdı. Bu testler o deliği kapalı tutar.
    """

    SAHTE_DOCKER = r'''#!/bin/bash
case "$*" in
  *list-strategies*) echo "S1Spot S2Spot S3Spot S4Spot S1Vadeli S2Vadeli S3Vadeli S4Vadeli S1KVadeli S2KVadeli";;
  *"--version"*) echo "freqtrade 2026.9";;
  *download-data*) echo "Downloaded data";;
  *karsilastir.py*) echo "Bot  İşlem"; echo "s1-spot 73";;
  *backtesting*)
    case "$SAHTE_MOD" in
      ayar_hatasi) echo "freqtrade.configuration.config_validation - CRITICAL - Invalid configuration. Reason: 'X' is too short"
                   echo "freqtrade - ERROR - Configuration error: 'X' is too short"; exit 0;;
      cikis_kodu) echo "bir seyler ters gitti"; exit 1;;
      tablo_yok) echo "freqtrade - INFO - bitti";;
      islem_yok) echo "No trades made. Your starting balance was 1000 USDT";;
      *) echo "                 BACKTESTING REPORT"; echo "│ TOTAL │ 73 │ -0.29 │ -10.7 │";;
    esac;;
esac
exit 0
'''

    def _calistir(self, mod):
        import os
        import shutil
        import subprocess

        with tempfile.TemporaryDirectory() as gecici:
            kok = Path(gecici)
            (kok / "araclar").mkdir()
            (kok / "bin").mkdir()
            shutil.copy(KOK / "araclar" / "uyum_denemesi.sh", kok / "araclar" / "uyum_denemesi.sh")
            docker = kok / "bin" / "docker"
            docker.write_text(self.SAHTE_DOCKER, encoding="utf-8")
            docker.chmod(0o755)
            ortam = {**os.environ, "PATH": f"{kok / 'bin'}:{os.environ['PATH']}", "SAHTE_MOD": mod}
            sonuc = subprocess.run(["bash", str(kok / "araclar" / "uyum_denemesi.sh")],
                                   capture_output=True, text=True, env=ortam)
            rapor = (kok / "user_data" / "logs" / "uyum_denemesi.txt").read_text(encoding="utf-8")
            return sonuc.returncode, rapor

    def test_her_sey_yolundaysa_gecer(self):
        kod, rapor = self._calistir("iyi")
        self.assertEqual(kod, 0, rapor)
        self.assertIn("SONUÇ: Tüm adımlar geçti.", rapor)
        self.assertEqual(rapor.count("geçmiş testi tamamlandı"), 10)
        self.assertIn("> │ TOTAL │ 73", rapor)

    def test_ayar_hatasi_cikis_kodu_temiz_olsa_da_kalir(self):
        kod, rapor = self._calistir("ayar_hatasi")
        self.assertEqual(kod, 1)
        self.assertEqual(rapor.count("[KALDI]"), 10)
        self.assertIn("SONUÇ: 10 adım kaldı.", rapor)
        self.assertNotIn("geçmiş testi tamamlandı", rapor)

    def test_hatali_cikis_kodu_kalir(self):
        kod, rapor = self._calistir("cikis_kodu")
        self.assertEqual(kod, 1)
        self.assertEqual(rapor.count("[KALDI]"), 10)

    def test_sonuc_tablosu_yoksa_gecti_sayilmaz(self):
        kod, rapor = self._calistir("tablo_yok")
        self.assertEqual(kod, 1)
        self.assertIn("sonuç tablosu çıktıda bulunamadı", rapor)

    def test_hic_islem_acmayan_strateji_hata_degildir(self):
        kod, rapor = self._calistir("islem_yok")
        self.assertEqual(kod, 0, rapor)
        self.assertEqual(rapor.count("ama hiç işlem açmadı"), 10)

    def test_arac_servisi_gizli_degerleri_okur(self):
        """Yer tutucu parolalarla hazır motor yapılandırmayı reddeder; arac da .env okumalı."""
        sys.path.insert(0, str(KOK / "araclar"))
        import yapilandirma_uret

        arac = yapilandirma_uret.compose_metni().split("  arac:")[1].split("\n\n")[0]
        self.assertIn("env_file: .env", arac)
