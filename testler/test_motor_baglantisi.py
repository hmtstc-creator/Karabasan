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
from karabasan import gostergeler as g  # noqa: E402
from karabasan.kural import kural_yukle, sinyal_uret  # noqa: E402
from testler.veri import yapay_mumlar  # noqa: E402


def strateji_modulu():
    yol = KOK / "user_data" / "strategies" / "karabasan_stratejileri.py"
    tanim = importlib.util.spec_from_file_location("karabasan_stratejileri", yol)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


class SahteSaglayici:
    """Hazır motorun veri sağlayıcısının (DataProvider) burada kullanılan iki işi."""

    def __init__(self, pariteler, tablolar, hata=False):
        self.pariteler, self.tablolar, self.hata = pariteler, tablolar, hata
        self.istekler = []

    def current_whitelist(self):
        return list(self.pariteler)

    def get_pair_dataframe(self, pair, timeframe=None, candle_type=""):
        self.istekler.append((pair, timeframe))
        if self.hata:
            raise RuntimeError("veri yok")
        import pandas as pd

        return self.tablolar.get((pair, timeframe), pd.DataFrame())


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
        s = self.modul.S1Vadeli
        self.assertEqual(s.timeframe, "5m")
        self.assertAlmostEqual(s.stoploss, -0.03)
        self.assertFalse(s.can_short)
        self.assertEqual(s.startup_candle_count, 1870)
        self.assertEqual(self.modul.S3Vadeli.timeframe, "15m")
        self.assertEqual(self.modul.S7Vadeli.timeframe, "15m")
        self.assertAlmostEqual(self.modul.S4Vadeli.stoploss, -0.03)
        self.assertAlmostEqual(self.modul.S6KVadeli.stoploss, -0.03)
        self.assertTrue(self.modul.S6KVadeli.can_short)

    def test_yalniz_ters_yonluler_aciga_satar(self):
        for _bot, sinif, kural_kodu, _piyasa in botlar.BOTLAR:
            s = getattr(self.modul, sinif)
            self.assertEqual(s.can_short, kural_kodu.endswith("K"))
            if s.can_short:
                self.assertEqual(s.piyasa, "vadeli")

    def test_kar_hedefi_fiyat_hareketine_karsilik_gelir(self):
        # Vadeli, komisyon %0,05: fiyat %0,8 yükseldiğinde komisyon sonrası kâr
        roi = self.modul.S1Vadeli.minimal_roi["0"]
        self.assertAlmostEqual(roi, 1.008 * (1 - 0.0005) / (1 + 0.0005) - 1)
        self.assertTrue(0.0069 < roi < 0.0071, roi)
        # Açığa satışta formül farklıdır; %0,05 komisyonla %0,8 hedef yine %0,7 civarı net verir.
        kisa = self.modul.S1KVadeli.minimal_roi["0"]
        self.assertAlmostEqual(kisa, 1 - 0.992 * (1 + 0.0005) / (1 - 0.0005))
        self.assertTrue(0.0069 < kisa < 0.0071, kisa)

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
            if kural_yukle(kural_kodu).get("borsa_dilimleri"):
                continue   # günlük mum isteyenler aşağıda, veri sağlayıcıyla birlikte sınanır
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

    def test_gunluk_mumlar_motordan_istenir(self):
        """Smartmoney günlük trendi borsadan ayrıca ister; diğer botlar bir şey istemez."""
        pariteler = ["ETH/USDT:USDT", "SOL/USDT:USDT"]
        s = self.modul.SMVadeli()
        self.assertEqual(s.informative_pairs(), [])           # veri sağlayıcı henüz yokken
        s.dp = SahteSaglayici(pariteler, {})
        self.assertEqual(s.informative_pairs(), [(p, "1d") for p in pariteler])
        self.assertEqual(self.modul.SMVadeli.startup_candle_count, 1810)
        self.assertTrue(self.modul.SMKVadeli.can_short)
        for sinif in ("S1Vadeli", "S3Vadeli", "S5Vadeli", "S6KVadeli", "S7Vadeli"):
            eski = getattr(self.modul, sinif)()
            eski.dp = SahteSaglayici(pariteler, {})
            self.assertEqual(eski.informative_pairs(), [], sinif)

    def test_smartmoney_sinyalleri_cekirdekle_ayni(self):
        df = yapay_mumlar(60 * 288, dilim_dk=5, tohum=11, oynaklik=0.003)
        gunluk = g.ust_dilime_cevir(df, "5m", "1d")
        parite = "ETH/USDT:USDT"
        for sinif, kural_kodu, sutun in (("SMVadeli", "SM", "enter_long"), ("SMKVadeli", "SMK", "enter_short")):
            with self.subTest(sinif=sinif):
                s = getattr(self.modul, sinif)()
                s.dp = SahteSaglayici([parite], {(parite, "1d"): gunluk})
                tablo = s.populate_indicators(df.copy(), {"pair": parite})
                tablo = s.populate_entry_trend(tablo, {"pair": parite})
                beklenen = sinyal_uret(df, kural_yukle(kural_kodu), {"1d": gunluk})["sinyal"]
                self.assertEqual((tablo[sutun] == 1).tolist(), beklenen.tolist())
                self.assertGreater(int(beklenen.sum()), 5)
                self.assertEqual(s.dp.istekler, [(parite, "1d")])

    def test_gunluk_veri_gelmezse_bot_durmaz_islem_de_acmaz(self):
        """Motor günlük mumu veremezse (hata, boş tablo, sağlayıcı yok) sinyal çıkmaz."""
        # 60 günlük veri: günlük mumlar 5 dakikalıklardan toplanabilirdi ve sinyal çıkardı.
        # Motor tarafında bu yapılmaz; günlük veri borsadan gelmediyse işlem açılmaz.
        df = yapay_mumlar(60 * 288, dilim_dk=5, tohum=11, oynaklik=0.003)
        parite = "ETH/USDT:USDT"
        self.assertGreater(int(sinyal_uret(df, kural_yukle("SM"))["sinyal"].sum()), 5)
        for saglayici in (None, SahteSaglayici([parite], {}), SahteSaglayici([parite], {}, hata=True)):
            s = self.modul.SMVadeli()
            s.dp = saglayici
            with self.assertLogs("karabasan_stratejileri", level="WARNING") as kayit:
                tablo = s.populate_indicators(df.copy(), {"pair": parite})
                s.populate_indicators(df.copy(), {"pair": parite})
            tablo = s.populate_entry_trend(tablo, {"pair": parite})
            self.assertEqual(int(tablo["enter_long"].sum()), 0)
            self.assertTrue(tablo["ema20_1g"].isna().all())
            # Eksik veri kayda yazılır, ama her mumda yeniden değil: parite başına bir kez.
            self.assertEqual(len(kayit.output), 1)
            self.assertIn("SM ETH/USDT:USDT: 1d mumları alınamadı", kayit.output[0])

    def test_parite_listesi_hazir_degilse_bot_durmaz(self):
        class Hazirlanmamis(SahteSaglayici):
            def current_whitelist(self):
                raise RuntimeError("parite listesi yok")

        s = self.modul.SMVadeli()
        s.dp = Hazirlanmamis([], {})
        with self.assertLogs("karabasan_stratejileri", level="WARNING"):
            self.assertEqual(s.informative_pairs(), [])

    def test_sure_asimi(self):
        s = self.modul.S1Vadeli()
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
        koruma = self.modul.S1Vadeli().protections
        self.assertEqual(len(koruma), 1)
        self.assertEqual(koruma[0]["method"], "StoplossGuard")
        self.assertEqual(koruma[0]["stop_duration_candles"], 48)   # 240 dk / 5 dk
        self.assertTrue(koruma[0]["only_per_pair"])
        self.assertEqual(self.modul.S3Vadeli().protections[0]["stop_duration_candles"], 16)


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
        vadeli = self.uret.bot_yapilandirmasi("s5-vadeli", "S5", "vadeli", self.ayar)
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
            # Betiklerin hangi günlük veriyi indireceğini öğrendiği iş de pandas istemez.
            "from karabasan.botlar import ek_dilimler\n"
            "assert ek_dilimler('vadeli') == ['1d'] and ek_dilimler('spot') == []\n"
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

        bes = yapay_mumlar(60 * 288, dilim_dk=5, tohum=11, oynaklik=0.003)
        veri = {
            "5m": bes,
            "15m": yapay_mumlar(4000, dilim_dk=15, tohum=31, oynaklik=0.006),
            "1d": g.ust_dilime_cevir(bes, "5m", "1d"),
        }
        okunan = []

        def sahte_dosya(coin, dilim, piyasa):
            return Path(f"/sahte/{coin}-{dilim}-{piyasa}.feather")

        def sahte_oku(yol):
            okunan.append(Path(yol).name)
            return veri[Path(yol).name.split("-")[1]]

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
        # Günlük mum yalnız onu isteyen botlar (Smartmoney, vadeli) için okunur.
        self.assertEqual(sum(1 for ad in okunan if "-1d-" in ad), 2 * len(karsilastir.COINLER))
        self.assertTrue(all(ad.endswith("-vadeli.feather") for ad in okunan if "-1d-" in ad))
        # Smartmoney botları bu veride işlem açtı (günlük veri gerçekten kullanıldı).
        for bot in ("sm-vadeli", "smk-vadeli"):
            satir = next(s for s in metin.splitlines() if s.startswith(bot))
            self.assertGreater(int(satir.split()[1]), 0, satir)

    def test_gunluk_dosya_yoksa_eksik_sayilir(self):
        import contextlib
        import io
        from unittest import mock

        sys.path.insert(0, str(KOK / "araclar"))
        import karsilastir

        bes = yapay_mumlar(3000, dilim_dk=5, tohum=11)
        cikti = io.StringIO()
        with mock.patch.object(karsilastir, "veri_dosyasi",
                               lambda coin, dilim, piyasa: None if dilim == "1d" else Path(f"/sahte/{dilim}")), \
                mock.patch.object(karsilastir.pd, "read_feather", lambda yol: bes), \
                mock.patch.object(sys, "argv", ["karsilastir.py", "30"]), \
                contextlib.redirect_stdout(cikti):
            self.assertEqual(karsilastir.main(), 1)
        self.assertIn(f"UYARI: {2 * len(karsilastir.COINLER)} veri dosyası bulunamadı", cikti.getvalue())

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


class TakasAlaniTesti(unittest.TestCase):
    """araclar/takas.sh sahte fallocate / mkswap / swapon / sysctl / df ile çalıştırılır."""

    SAHTE = {
        "fallocate": 'echo "fallocate $*" >> "$SAHTE_KAYIT"; [ "${SAHTE_MOD:-}" = "fallocate_yok" ] && exit 1; : > "$3"',
        "dd": 'echo "dd $*" >> "$SAHTE_KAYIT"; for a in "$@"; do case "$a" in of=*) : > "${a#of=}";; esac; done',
        "mkswap": 'echo "mkswap $*" >> "$SAHTE_KAYIT"; echo TAKAS > "$1"',
        "swapon": ('if [ "$1" = "--show=NAME" ]; then cat "$SAHTE_ETKIN" 2> /dev/null; exit 0; fi\n'
                   'echo "swapon $*" >> "$SAHTE_KAYIT"; grep -q TAKAS "$1" || exit 1; echo "$1" >> "$SAHTE_ETKIN"'),
        "sysctl": 'echo "sysctl $*" >> "$SAHTE_KAYIT"',
        "df": 'echo "Avail"; echo "${SAHTE_BOS:-50000}"',
    }

    def _calistir(self, kok, **ek):
        import os
        import subprocess

        ortam = {**os.environ, "PATH": f"{kok / 'bin'}:{os.environ['PATH']}",
                 "TAKAS_DOSYASI": str(kok / "swapfile"), "TAKAS_FSTAB": str(kok / "fstab"),
                 "TAKAS_SYSCTL": str(kok / "sysctl.conf"), "SAHTE_KAYIT": str(kok / "kayit"),
                 "SAHTE_ETKIN": str(kok / "etkin"), **ek}
        return subprocess.run(["bash", str(KOK / "araclar" / "takas.sh")], capture_output=True,
                              text=True, env=ortam)

    def _kok(self, gecici):
        kok = Path(gecici)
        (kok / "bin").mkdir()
        for ad, govde in self.SAHTE.items():
            yol = kok / "bin" / ad
            yol.write_text("#!/bin/bash\n" + govde + "\n", encoding="utf-8")
            yol.chmod(0o755)
        (kok / "fstab").write_text("UUID=abc / ext4 defaults 0 1\n", encoding="utf-8")
        return kok

    def test_kurar_ve_ikinci_calismada_atlar(self):
        with tempfile.TemporaryDirectory() as gecici:
            kok = self._kok(gecici)
            ilk = self._calistir(kok)
            self.assertEqual(ilk.returncode, 0, ilk.stdout + ilk.stderr)
            self.assertIn("Takas alanı açıldı.", ilk.stdout)
            ikinci = self._calistir(kok)
            self.assertEqual(ikinci.returncode, 0, ikinci.stdout + ikinci.stderr)
            self.assertIn("zaten açık, atlandı", ikinci.stdout)
            kayit = (kok / "kayit").read_text(encoding="utf-8")
            self.assertEqual(kayit.count("fallocate -l 2048M"), 1)
            self.assertEqual(kayit.count("mkswap"), 1)
            fstab = (kok / "fstab").read_text(encoding="utf-8").splitlines()
            self.assertEqual(fstab.count(f"{kok / 'swapfile'} none swap sw 0 0"), 1)
            self.assertEqual(len(fstab), 2)
            self.assertEqual((kok / "sysctl.conf").read_text(encoding="utf-8").strip(), "vm.swappiness=10")
            self.assertIn("sysctl -q -w vm.swappiness=10", kayit)
            self.assertEqual(oct((kok / "swapfile").stat().st_mode & 0o777), "0o600")
            self.assertFalse((kok / "swapfile.yeni").exists())

    def test_fallocate_yoksa_dd_ile_kurar(self):
        with tempfile.TemporaryDirectory() as gecici:
            kok = self._kok(gecici)
            sonuc = self._calistir(kok, SAHTE_MOD="fallocate_yok")
            self.assertEqual(sonuc.returncode, 0, sonuc.stdout + sonuc.stderr)
            self.assertIn("dd if=/dev/zero", (kok / "kayit").read_text(encoding="utf-8"))

    def test_disk_doluysa_kurmaz_uyarir(self):
        with tempfile.TemporaryDirectory() as gecici:
            kok = self._kok(gecici)
            sonuc = self._calistir(kok, SAHTE_BOS="3000")
            self.assertEqual(sonuc.returncode, 1)
            self.assertIn("yeterli boş yer yok", sonuc.stdout)
            self.assertFalse((kok / "swapfile").exists())
            self.assertEqual(len((kok / "fstab").read_text(encoding="utf-8").splitlines()), 1)

    def test_bozuk_dosya_silinir(self):
        with tempfile.TemporaryDirectory() as gecici:
            kok = self._kok(gecici)
            (kok / "swapfile").write_text("bozuk", encoding="utf-8")
            sonuc = self._calistir(kok)
            self.assertEqual(sonuc.returncode, 1)
            self.assertFalse((kok / "swapfile").exists())
            # Sonraki çalışma baştan kurar.
            self.assertEqual(self._calistir(kok).returncode, 0)

    def test_kur_sh_hatayi_yutar(self):
        metin = (KOK / "kur.sh").read_text(encoding="utf-8")
        self.assertIn('bash araclar/takas.sh || echo "UYARI', metin)


class KurulumBetikleriTesti(unittest.TestCase):
    """Sunucu betikleri burada çalıştırılamaz; yalnız yazım ve temel güvenlik denetlenir."""

    BETIKLER = ["kur.sh", "guncelle.sh", "araclar/oto_guncelle.sh", "araclar/ozel_ag.sh",
                "araclar/uyum_denemesi.sh", "araclar/claude_sunucu.sh", "araclar/analiz.sh",
                "araclar/takas.sh", "kurulum/sunucu_blogu.sh"]

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
  *list-strategies*) echo "KarabasanTaban S1Vadeli S2Vadeli S3Vadeli S4Vadeli S1KVadeli S5Vadeli S5KVadeli S7Vadeli S6KVadeli SMVadeli SMKVadeli $SAHTE_SON_SINIF";;
  *"--version"*) echo "freqtrade 2026.9";;
  *download-data*) echo "docker $*" >> "$SAHTE_KAYIT"
                   [ "$SAHTE_MOD" = "gunluk_inmez" ] && case "$*" in *"--timeframes 1d"*) echo "freqtrade - ERROR - veri yok"; exit 1;; esac
                   echo "Downloaded data";;
  *karsilastir.py*) echo "Bot  İşlem"; echo "s1-vadeli 73";;
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

    BOT_SAYISI = len(botlar.BOTLAR)

    def _calistir(self, mod, cagrilar=False):
        import os
        import shutil
        import subprocess

        with tempfile.TemporaryDirectory() as gecici:
            kok = Path(gecici)
            (kok / "araclar").mkdir()
            (kok / "bin").mkdir()
            (kok / "karabasan").mkdir()
            shutil.copy(KOK / "araclar" / "uyum_denemesi.sh", kok / "araclar" / "uyum_denemesi.sh")
            # Betik bot listesini ve borsadan istenen dilimleri karabasan/botlar.py'den okur;
            # o da kural dosyalarına bakar.
            for dosya in ("__init__.py", "botlar.py"):
                shutil.copy(KOK / "karabasan" / dosya, kok / "karabasan" / dosya)
            shutil.copytree(KOK / "karabasan" / "stratejiler", kok / "karabasan" / "stratejiler")
            docker = kok / "bin" / "docker"
            docker.write_text(self.SAHTE_DOCKER, encoding="utf-8")
            docker.chmod(0o755)
            ortam = {**os.environ, "PATH": f"{kok / 'bin'}:{os.environ['PATH']}", "SAHTE_MOD": mod,
                     "SAHTE_KAYIT": str(kok / "cagrilar.txt"),
                     "SAHTE_SON_SINIF": "" if mod == "sinif_eksik" else "S7KVadeli"}
            sonuc = subprocess.run(["bash", str(kok / "araclar" / "uyum_denemesi.sh")],
                                   capture_output=True, text=True, env=ortam)
            rapor = (kok / "user_data" / "logs" / "uyum_denemesi.txt").read_text(encoding="utf-8")
            if cagrilar:
                return sonuc.returncode, rapor, (kok / "cagrilar.txt").read_text(encoding="utf-8")
            return sonuc.returncode, rapor

    def test_her_sey_yolundaysa_gecer(self):
        kod, rapor = self._calistir("iyi")
        self.assertEqual(kod, 0, rapor)
        self.assertIn("SONUÇ: Tüm adımlar geçti.", rapor)
        self.assertEqual(rapor.count("geçmiş testi tamamlandı"), self.BOT_SAYISI)
        self.assertIn("> │ TOTAL │ 73", rapor)

    def test_bot_listesi_tek_yerden_gelir(self):
        kod, rapor = self._calistir("iyi")
        for bot, sinif, _k, _p in botlar.BOTLAR:
            self.assertIn(f"--- {bot} ({sinif}) ---", rapor)
        self.assertIn(f"{self.BOT_SAYISI} strateji sınıfı bulundu ve yüklendi", rapor)

    def test_gunluk_mumlar_yalniz_isteyen_piyasa_icin_indirilir(self):
        """Smartmoney botları vadelidedir ve günlük mum ister; spot botları istemez."""
        kod, rapor, cagrilar = self._calistir("iyi", cagrilar=True)
        self.assertEqual(kod, 0, rapor)
        indirmeler = cagrilar.splitlines()
        self.assertEqual(len(indirmeler), 3)
        gunluk = [c for c in indirmeler if "--timeframes 1d" in c]
        self.assertEqual(len(gunluk), 1)
        self.assertIn("--trading-mode futures", gunluk[0])
        self.assertIn("ETH/USDT:USDT", gunluk[0])
        self.assertIn("--days 200", gunluk[0])
        self.assertIn("[GEÇTİ] Vadeli verisi indirildi (1d, 200 gün)", rapor)
        self.assertEqual(sum(1 for c in indirmeler if "--timeframes 5m 15m --days 45" in c), 2)

    def test_gunluk_veri_inmezse_kalir(self):
        kod, rapor = self._calistir("gunluk_inmez")
        self.assertEqual(kod, 1)
        self.assertIn("[KALDI] Vadeli verisi indirilemedi (1d): freqtrade - ERROR - veri yok", rapor)
        self.assertIn("SONUÇ: 1 adım kaldı.", rapor)

    def test_eksik_sinif_yakalanir(self):
        # "S7Vadeli" çıktıda var ama "S7KVadeli" yok: biri diğerinin yerine sayılmamalı.
        kod, rapor = self._calistir("sinif_eksik")
        self.assertEqual(kod, 1)
        self.assertIn("Bulunamayan sınıflar: S7KVadeli", rapor)

    def test_ayar_hatasi_cikis_kodu_temiz_olsa_da_kalir(self):
        kod, rapor = self._calistir("ayar_hatasi")
        self.assertEqual(kod, 1)
        self.assertEqual(rapor.count("[KALDI]"), self.BOT_SAYISI)
        self.assertIn(f"SONUÇ: {self.BOT_SAYISI} adım kaldı.", rapor)
        self.assertNotIn("geçmiş testi tamamlandı", rapor)
        # Betik botların durumu hakkında konuşmaz; onu çağıran bilir.
        self.assertNotIn("BAŞLATILMADI", rapor)

    def test_hatali_cikis_kodu_kalir(self):
        kod, rapor = self._calistir("cikis_kodu")
        self.assertEqual(kod, 1)
        self.assertEqual(rapor.count("[KALDI]"), self.BOT_SAYISI)

    def test_sonuc_tablosu_yoksa_gecti_sayilmaz(self):
        kod, rapor = self._calistir("tablo_yok")
        self.assertEqual(kod, 1)
        self.assertIn("sonuç tablosu çıktıda bulunamadı", rapor)

    def test_hic_islem_acmayan_strateji_hata_degildir(self):
        kod, rapor = self._calistir("islem_yok")
        self.assertEqual(kod, 0, rapor)
        self.assertEqual(rapor.count("ama hiç işlem açmadı"), self.BOT_SAYISI)

    def test_arac_servisi_env_okumaz_gecmis_testi_yer_tutucusu_gecerlidir(self):
        """İki ders bir arada.

        1. Bot dosyasındaki kısa yer tutucularla hazır motor geçmiş testini başlatmaz.
           Geçmiş testi yapılandırması bu alanları geçerli uzunlukta değerlerle ezer.
        2. arac servisi .env okursa, yapılandırma dosyası verilmeden çalışan komutlar
           (strateji listesi, veri indirme) yarım bir ekran ayarı yüzünden reddedilir.
        """
        sys.path.insert(0, str(KOK / "araclar"))
        import yapilandirma_uret

        arac = yapilandirma_uret.compose_metni().split("  arac:")[1].split("\n\n")[0]
        self.assertNotIn("\n    env_file", arac)
        for piyasa in ("spot", "vadeli"):
            ekran = yapilandirma_uret.geri_test_yapilandirmasi(piyasa)["api_server"]
            self.assertIs(ekran["enabled"], False)
            for alan in ("jwt_secret_key", "ws_token", "password"):
                self.assertGreaterEqual(len(ekran[alan]), 32, alan)


class AnalizBetigiTesti(unittest.TestCase):
    """araclar/analiz.sh taklit bir 'docker' ile çalıştırılır."""

    SAHTE_DOCKER = r'''#!/bin/bash
echo "docker $*" >> "$SAHTE_KAYIT"
case "$*" in
  *download-data*--prepend*) [ "$SAHTE_MOD" = "prepend_yok" ] && { echo "freqtrade: error: unrecognized arguments: --prepend"; exit 2; }; echo "Downloaded";;
  *download-data*--erase*) echo "Downloaded";;
  *karabasan_gecmis.py*) [ "$SAHTE_MOD" = "olcum_yok" ] && { echo "Traceback (most recent call last): sahte" >&2; exit 1; }
                         echo "Karabasan geçmiş ölçümü: 2026-09-10 00:00 - 2026-10-10 00:00 UTC (30,0 gün)";;
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
            (kok / "karabasan").mkdir()
            shutil.copy(KOK / "araclar" / "analiz.sh", kok / "araclar" / "analiz.sh")
            # Borsadan istenen dilimler karabasan/botlar.py üzerinden kural dosyalarından okunur.
            for dosya in ("__init__.py", "botlar.py"):
                shutil.copy(KOK / "karabasan" / dosya, kok / "karabasan" / dosya)
            shutil.copytree(KOK / "karabasan" / "stratejiler", kok / "karabasan" / "stratejiler")
            docker = kok / "bin" / "docker"
            docker.write_text(self.SAHTE_DOCKER, encoding="utf-8")
            docker.chmod(0o755)
            ortam = {**os.environ, "PATH": f"{kok / 'bin'}:{os.environ['PATH']}", "SAHTE_MOD": mod,
                     "SAHTE_KAYIT": str(kok / "cagrilar.txt")}
            sonuc = subprocess.run(["bash", str(kok / "araclar" / "analiz.sh")],
                                   capture_output=True, text=True, env=ortam)
            rapor = (kok / "user_data" / "logs" / "karabasan_gecmis.txt").read_text(encoding="utf-8")
            cagrilar = (kok / "cagrilar.txt").read_text(encoding="utf-8")
            return sonuc.returncode, rapor, cagrilar

    def test_olagan_durum(self):
        kod, rapor, cagrilar = self._calistir("iyi")
        self.assertEqual(kod, 0)
        self.assertTrue(rapor.startswith("Karabasan geçmiş ölçümü:"))
        self.assertNotIn("UYARI", rapor)
        self.assertEqual(cagrilar.count("--prepend"), 2)   # spot ve vadeli
        self.assertNotIn("--erase", cagrilar)
        self.assertIn("--days 80", cagrilar)
        # Günlük mumlar: yalnız onu isteyen (vadeli) botlar için, ölçümden önce.
        gunluk = [c for c in cagrilar.splitlines() if "--timeframes 1d" in c]
        self.assertEqual(len(gunluk), 1)
        self.assertIn("--trading-mode futures", gunluk[0])
        self.assertIn("--days 200", gunluk[0])
        sira = cagrilar.splitlines()
        self.assertLess(sira.index(gunluk[0]), next(i for i, c in enumerate(sira) if "karabasan_gecmis.py" in c))

    def test_prepend_desteklenmezse_silip_bastan_indirir(self):
        kod, rapor, cagrilar = self._calistir("prepend_yok")
        self.assertEqual(kod, 0)
        self.assertEqual(cagrilar.count("--erase"), 2)
        self.assertNotIn("UYARI", rapor)

    def test_olcum_uretilemezse_kaydin_sonu_rapora_eklenir(self):
        kod, rapor, _ = self._calistir("olcum_yok")
        self.assertEqual(kod, 1)
        self.assertIn("ÖLÇÜM ÜRETİLEMEDİ", rapor)
        self.assertIn("Traceback", rapor)
