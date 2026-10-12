"""Panel sınaması (karabasan/sinama.py): portföy kuralları, maliyetler, ölçümler, plasebo, karar."""

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from karabasan import fonlama as f
from karabasan import gostergeler as g
from karabasan import sinama as s
from testler.veri import yapay_mumlar

KOK = Path(__file__).resolve().parent.parent
T0 = pd.Timestamp("2026-01-01", tz="UTC")


def aday(coin, giris_saat, sure_saat, net_yuzde=1.0, neden="kar_hedefi", stop=2.0, i=None, sonraki=None,
         yon="alim"):
    i = i if i is not None else int(giris_saat * 4)
    return {"coin": coin, "yon": yon, "giris_zamani": T0 + pd.Timedelta(hours=giris_saat),
            "cikis_zamani": T0 + pd.Timedelta(hours=giris_saat + sure_saat), "net_yuzde": net_yuzde,
            "brut_yuzde": net_yuzde + 0.1, "neden": neden, "stop_yuzde": stop, "sinyal_i": i,
            "sonraki_i": sonraki if sonraki is not None else i + int(sure_saat * 4) + 1,
            "sure_dakika": sure_saat * 60, "fonlama_yuzde": 0.0, "bilgi": {}}


def gecir(adaylar, **portfoy):
    kural = {"portfoy": portfoy}
    return s.portfoy_gecisi([("B", kural, adaylar)])["B"]


class PortfoyGecisi(unittest.TestCase):
    def test_tutar_riske_gore(self):
        k = gecir([aday("ETH", 0, 1, net_yuzde=-2.1, neden="zarar_durdur", stop=2.0),
                   aday("SOL", 0, 1, stop=0.5)])
        self.assertAlmostEqual(k[0]["tutar"], 50.0)
        self.assertAlmostEqual(k[0]["net_usdt"], -1.05)
        self.assertAlmostEqual(k[1]["tutar"], 100.0)   # 1 / %0,5 = 200, tavan 100

    def test_ayni_coinde_ust_uste_binmez(self):
        k = gecir([aday("ETH", 0, 5), aday("ETH", 1, 1), aday("ETH", 6, 1)])
        self.assertEqual([a["giris_zamani"].hour for a in k], [0, 6])

    def test_en_fazla_pozisyon_ve_giris_siniri(self):
        adaylar = [aday(c, 0, 10) for c in ("ETH", "SOL", "XRP")]
        self.assertEqual(len(gecir(adaylar, en_fazla_pozisyon=2)), 2)
        adaylar = [aday(c, 0.25 * n, 0.1) for n, c in enumerate(("ETH", "SOL", "XRP", "DOGE"))]
        self.assertEqual(len(gecir(adaylar, giris_sinirlari=[{"saat": 1, "sayi": 2}])), 2)

    def test_gunluk_fren(self):
        # 25 stop x ~0,9 USDT > 20 USDT (bakiyenin %2'si): fren devreye girer, 24 saat yeni giriş yok.
        coinler = s.COINLER
        adaylar = [aday(coinler[n % len(coinler)], n * 0.5, 0.25, net_yuzde=-1.8, stop=2.0, neden="kar_hedefi")
                   for n in range(30)]
        k = gecir(adaylar, en_fazla_pozisyon=20)
        self.assertLess(len(k), 30)
        son = k[-1]["giris_zamani"]
        self.assertGreater(sum(a["net_usdt"] for a in k), -22)
        sonra = gecir(adaylar + [aday("ETH", son.hour + 30, 1)], en_fazla_pozisyon=20)
        self.assertEqual(sonra[-1]["coin"], "ETH")

    def test_coin_ve_seri_stop_kilidi(self):
        stop = dict(net_yuzde=-2.1, neden="zarar_durdur")
        adaylar = [aday("ETH", 0, 1, **stop), aday("ETH", 2, 1, **stop), aday("ETH", 4, 1)]
        self.assertEqual(len(gecir(adaylar)), 2)                    # 2 stop: ETH 24 saat kilitli
        adaylar = [aday(c, n, 0.5, **stop) for n, c in enumerate(("ETH", "SOL", "XRP", "DOGE"))]
        adaylar.append(aday("ADA", 5, 1))
        self.assertEqual(len(gecir(adaylar)), 4)                    # 4 stop: bot 12 saat bekler
        self.assertEqual(len(gecir(adaylar, seri_stop_muaf=True)), 5)

    def test_ortak_portfoy_ayni_yon_siniri(self):
        botlar = [(f"B{n}", {"portfoy": {"en_fazla_pozisyon": 10}},
                   [aday(c, 0, 10) for c in s.COINLER[n * 6:(n + 1) * 6]]) for n in range(2)]
        ayri = s.portfoy_gecisi(botlar)
        ortak = s.portfoy_gecisi(botlar, ortak=True)
        self.assertEqual(sum(len(v) for v in ayri.values()), 12)
        self.assertEqual(sum(len(v) for v in ortak.values()), s.AYNI_YON_ORTAK_SINIR)


class CoinGunluk(unittest.TestCase):
    def test_coin_basina_gunde_bir(self):
        adaylar = [aday("ETH", 1, 0.5), aday("ETH", 3, 0.5), aday("SOL", 3, 0.5), aday("ETH", 25, 0.5)]
        k = gecir(adaylar, coin_gunde_en_fazla=1)
        self.assertEqual([(a["coin"], a["giris_zamani"].hour) for a in k], [("ETH", 1), ("SOL", 3), ("ETH", 1)])


class FonlamaSayimi(unittest.TestCase):
    def test_ard_arda_odemeler_tek_olay(self):
        oran = [0.01] * 5 + [0.06, 0.07, 0.08] + [0.01] * 5 + [-0.06, -0.07, -0.05] + [0.01] * 3
        fon = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=len(oran), freq="8h", tz="UTC"),
                            "oran_yuzde": oran})
        o = s.fonlama_olaylari(fon, T0, T0 + pd.Timedelta(days=30))
        self.assertEqual(o, {"alim_kalabalik": 1, "satis_kalabalik": 1})
        dort = fon.assign(date=pd.date_range("2026-01-01", periods=len(oran), freq="4h", tz="UTC"),
                          oran_yuzde=[x / 2 for x in oran])
        self.assertEqual(s.fonlama_olaylari(dort, T0, T0 + pd.Timedelta(days=30)), o)   # 8 saate çevrilir


class MaliyetVeOlcum(unittest.TestCase):
    def test_fonlama_maliyeti(self):
        fon = pd.DataFrame({"date": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 08:00", "2026-01-01 16:00"],
                                                   utc=True), "oran_yuzde": [0.01, 0.02, 0.05]})
        giris, cikis = T0, T0 + pd.Timedelta(hours=16)
        self.assertAlmostEqual(s.fonlama_maliyeti(fon, giris, cikis, True), 0.07)
        self.assertAlmostEqual(s.fonlama_maliyeti(fon, giris, cikis, False), -0.07)
        self.assertEqual(s.fonlama_maliyeti(None, giris, cikis, True), 0.0)

    def test_kayma_dizisi(self):
        tablo = pd.DataFrame({"high": [101.0, 100.1], "low": [99.0, 100.0], "close": [100.0, 100.0]})
        np.testing.assert_allclose(s.kayma_dizisi(tablo, 0.05), [0.2, 0.05])

    def test_olcumler(self):
        islemler = [dict(aday("ETH", 24 * n, 1), net_usdt=v) for n, v in enumerate([3.0, -1.0, 2.0, -1.0, 1.0])]
        o = s.olcumler(islemler, T0, T0 + pd.Timedelta(days=365))
        self.assertEqual(o["islem"], 5)
        self.assertAlmostEqual(o["net"], 4.0)
        self.assertAlmostEqual(o["kazanma"], 60.0)
        self.assertEqual(len(o["yillar"]), 1)
        self.assertAlmostEqual(o["en_iyi_3_gun_payi"], 1.5)
        self.assertAlmostEqual(o["en_iyi_3_islem_haric"], -2.0)
        self.assertAlmostEqual(o["dusus"], 1.0)
        self.assertGreater(o["t"], 0)

    def test_karar(self):
        aile = s.ADAYLAR[0]
        iyi = {"islem": 300, "gun_sayisi": 60, "net": 50.0, "net_yuzde": 0.5, "brut_yuzde": 0.7, "t": 3.0,
               "yillar": [10, 20, 20], "artida_yil": 3, "en_iyi_3_gun_payi": 0.2, "artida_coin": 10,
               "en_iyi_3_islem_haric": 40.0, "btc_iliski": 0.1}
        self.assertEqual(s.karar(aile, iyi, {"net": 10.0}, 3.0, {"ZSDP": 0.3}, {})[0], "GEÇTİ")
        hukum, nedenler = s.karar(aile, {**iyi, "t": 1.0}, {"net": -1.0}, 1.0, {"ZSDP": 0.0}, {})
        self.assertEqual(hukum, "KALDI")
        self.assertEqual(len(nedenler), 4)
        self.assertEqual(s.karar(aile, {**iyi, "gun_sayisi": 5}, {"net": 1}, 3, {}, {})[0], "HÜKÜM YOK")
        trend = s.ADAYLAR[1]
        hukum, nedenler = s.karar(trend, {**iyi, "islem": 150}, {"net": 1.0}, 3.0, {}, {"a": 5, "b": -1, "c": -2})
        self.assertIn("kanal uzunluklarının yalnız 1 / 3 tanesi artıda", nedenler)


class Plasebo(unittest.TestCase):
    def test_rastgele_giris_kenarsiz_veride_sifira_yakin(self):
        df = yapay_mumlar(5000, dilim_dk=60, tohum=11)
        kayma = np.full(len(df), 0.0)
        fiyatlar = {"ETH": {"tarih": pd.to_datetime(df["date"], utc=True).dt.tz_convert(None).to_numpy(),
                            "acilis": df["open"].to_numpy(), "kapanis": df["close"].to_numpy(),
                            "kayma": kayma, "fonlama": None}}
        islemler = [dict(aday("ETH", 0, 10), net_yuzde=0.5) for _ in range(50)]
        bas, son = pd.Timestamp(df["date"].iloc[0]), pd.Timestamp(df["date"].iloc[-1])
        ort = s.rastgele_plasebo(islemler, fiyatlar, bas, son)
        self.assertLess(abs(ort + 0.1), 0.3)                         # ≈ -komisyon
        self.assertIsNone(s.rastgele_plasebo([], fiyatlar, bas, son))
        self.assertIsNone(s.plasebo_t(islemler, None))


def sentetik_kaynak(gun=330):
    """Ara sıra BTC ile birlikte çöken, sonra kısmen toparlanan yapay piyasa."""
    rng = np.random.default_rng(3)
    veri = {}
    sok = rng.choice(np.arange(500, 96 * gun - 50), size=12, replace=False)
    for n, coin in enumerate(["BTC"] + s.COINLER[:3]):
        df = yapay_mumlar(96 * gun, dilim_dk=15, tohum=20 + n, oynaklik=0.003, baslangic="2025-06-01")
        kapanis = df["close"].to_numpy().copy()
        for k in sok:
            kapanis[k:] *= 0.96
            kapanis[k + 1:] *= 1.05
        df["close"] = kapanis
        df["open"] = np.concatenate([[kapanis[0]], kapanis[:-1]])
        df["high"] = np.maximum(df["open"], df["close"]) * 1.001
        df["low"] = np.minimum(df["open"], df["close"]) * 0.999
        hacim = df["volume"].to_numpy().copy()
        hacim[sok] *= 10
        df["volume"] = hacim
        veri[coin] = {"15m": df, "1h": g.ust_dilime_cevir(df, "15m", "1h"), "1d": g.ust_dilime_cevir(df, "15m", "1d")}
    fon = pd.DataFrame({"date": pd.date_range("2025-06-01", periods=3 * gun, freq="8h", tz="UTC"),
                        "oran_yuzde": rng.normal(0.01, 0.01, 3 * gun)})

    def yukle(coin, dilim):
        return veri.get(coin, {}).get(dilim)

    return yukle, (lambda coin: fon if coin in veri else None)


class UcTanUca(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        yukle, fon = sentetik_kaynak()
        bas = time.time()
        with mock.patch.object(s, "COINLER", s.COINLER[:3]), mock.patch.object(s, "GELISTIRME_YIL", 1), \
                mock.patch.object(s, "AYRILMIS_GUN", 30), mock.patch.object(s, "PLASEBO_TEKRAR", 3):
            cls.metin, cls.sonuc = s.sina(yukle, fon)
        cls.sure = time.time() - bas

    def test_rapor_bolumleri(self):
        for parca in ("PANEL SINAMASI", "=== ZSD", "=== TRG", "=== TRGK", "KARAR (ZSD)", "KARAR (TRG28)",
                      "Kural plasebosu ZSDP", "Rastgele giriş plasebosu", "PANEL PORTFÖYÜ", "ÖZET",
                      "ayrılmış, KAPALI", "Deneme defteri: önceki 112 + bu sınamada 13 = 125", "=== FONK", "Kural plasebosu FONP", "=== ASYA", "KARAR (ASYAK)",
                      "Kural plasebosu ASYAP2", "FONLAMA AŞIRILIĞI SAYIMI",
                      "Bilgi (onceki_gun_dibi_delindi = evet)", "dosya özeti"):
            self.assertIn(parca, self.metin)

    def test_kararlar_ve_sokta_islem(self):
        for aile in ("ZSD", "TRG", "TRGK"):
            self.assertIn(self.sonuc["aileler"][aile]["karar"], ("GEÇTİ", "KALDI", "HÜKÜM YOK"))
        self.assertGreater(self.sonuc["denemeler"]["ZSD"]["islem"], 0)
        self.assertGreater(self.sonuc["denemeler"]["ZSDP"]["islem"], 0)
        self.assertGreater(self.sonuc["denemeler"]["TRG28"]["islem"] + self.sonuc["denemeler"]["TRGK28"]["islem"], 0)

    def test_ayrilmis_yil_kullanilmaz(self):
        # Ayrılmış dönemde açılan ya da biten işlem yok: hiçbir sonuç son 30 güne dokunmuyor.
        self.assertNotIn("Son yıl AÇIK", self.metin)

    def test_makul_surede(self):
        self.assertLess(self.sure, 240)


class FonlamaIndirme(unittest.TestCase):
    def test_sayfali_indirir_ve_kaldigi_yerden_surer(self):
        gun = f.GUN_MS
        simdi = 1_800_000_000_000
        kayitlar = [{"fundingTime": simdi - 10 * gun + n * 8 * 3_600_000, "fundingRate": f"{0.0001 * n:.6f}"}
                    for n in range(30)]
        istenen = []

        def getir(adres):
            istenen.append(adres)
            bas = int(adres.split("startTime=")[1].split("&")[0])
            return [k for k in kayitlar if k["fundingTime"] >= bas][:7]

        with tempfile.TemporaryDirectory() as d, mock.patch.object(f, "SAYFA", 7):
            self.assertEqual(f.indir("ETH", d, 10, simdi_ms=simdi, getir=getir, bekle=0), 30)
            self.assertIn("symbol=ETHUSDT", istenen[0])
            kayitlar.append({"fundingTime": simdi - 3_600_000, "fundingRate": "0.0005"})
            self.assertEqual(f.indir("ETH", d, 10, simdi_ms=simdi, getir=getir, bekle=0), 1)
            tablo = f.oku("ETH", d)
            self.assertEqual(len(tablo), 31)
            self.assertAlmostEqual(tablo["oran_yuzde"].iloc[1], 0.01)
            self.assertIsNone(f.oku("SOL", d))

    def test_yalniz_standart_kutuphane(self):
        kod = (KOK / "karabasan" / "fonlama.py").read_text()
        self.assertNotIn("\nimport pandas", kod)
        self.assertNotIn("\nimport numpy", kod)


class Betikler(unittest.TestCase):
    def test_kabuk_ve_kur(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(KOK / "araclar" / "panel_sinama.sh")]).returncode, 0)
        kur = (KOK / "kur.sh").read_text()
        self.assertIn("bash araclar/panel_sinama.sh", kur)
        self.assertLess(kur.index("bash araclar/tarama.sh"), kur.index("bash araclar/panel_sinama.sh"))
        betik = (KOK / "araclar" / "panel_sinama.sh").read_text()
        for coin in s.COINLER + [s.REFERANS]:
            self.assertIn(coin, betik)


if __name__ == "__main__":
    unittest.main()
