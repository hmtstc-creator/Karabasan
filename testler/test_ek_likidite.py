"""Likidite ekranı: ayrıştırma, etiket, ağ bayrağı, arka plan işi ve çizim. Gerçek ağ YOK."""

from __future__ import annotations

import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import sayfa_likidite as sl
from karabasan import sonuc_likidite as l

SIMDI = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
MS = lambda z: int(z.timestamp() * 1000)  # noqa: E731


def af_serisi(son: datetime, adet: int = 97, baslangic: float = 100e6, artis: float = 0.002):
    return [{"symbol": "X", "timestamp": MS(son - timedelta(minutes=15 * (adet - 1 - k))),
             "sumOpenInterest": "1", "sumOpenInterestValue": str(baslangic * (1 + artis) ** k)} for k in range(adet)]


class SahteGetir:
    """Yol -> yanıt; yanıt bir istisna ise fırlatılır. Çağrılar kaydedilir."""

    def __init__(self, yanitlar):
        self.yanitlar, self.cagrilar = yanitlar, []

    def __call__(self, yol, parametreler=None):
        self.cagrilar.append((yol, parametreler))
        y = self.yanitlar.get(yol)
        if callable(y):
            y = y(parametreler)
        if isinstance(y, Exception):
            raise y
        return y


def tam_yanitlar():
    return {
        "/fapi/v1/premiumIndex": [
            {"symbol": "BTCUSDT", "markPrice": "90000", "lastFundingRate": "0.00010000", "nextFundingTime": MS(SIMDI)},
            {"symbol": "SOLUSDT", "markPrice": "150", "lastFundingRate": "-0.00080000", "nextFundingTime": MS(SIMDI)},
            {"symbol": "ETHUSDT", "lastFundingRate": "0.0001"},
        ],
        "/fapi/v1/ticker/24hr": [
            {"symbol": "BTCUSDT", "quoteVolume": "9000000000", "priceChangePercent": "1.2"},
            {"symbol": "SOLUSDT", "quoteVolume": "3000000", "priceChangePercent": "9.5"},
        ],
        "/fapi/v1/ticker/bookTicker": [
            {"symbol": "BTCUSDT", "bidPrice": "89999.9", "askPrice": "90000.0"},
            {"symbol": "SOLUSDT", "bidPrice": "149.70", "askPrice": "150.00"},
        ],
        "/futures/data/openInterestHist": lambda p: af_serisi(SIMDI - timedelta(minutes=5),
                                                              artis=0.003 if p["symbol"] == "SOLUSDT" else 0.0),
    }


def baglam(klasor=".", acik=None, islemler=None):
    return {"veri_klasoru": Path(klasor), "simdi": SIMDI, "acik": acik or [], "islemler": islemler or []}


class Temel(unittest.TestCase):
    def setUp(self):
        l.sifirla()

    def tearDown(self):
        l.sifirla()


class Ayristirma(Temel):
    def test_fonlama_metin_sayi_ve_eksik_alan(self):
        r = l.fonlama_ayristir(tam_yanitlar()["/fapi/v1/premiumIndex"], ["BTCUSDT", "SOLUSDT", "XRPUSDT"])
        self.assertAlmostEqual(r["BTCUSDT"]["oran_yuzde"], 0.01)
        self.assertAlmostEqual(r["SOLUSDT"]["oran_yuzde"], -0.08)
        self.assertNotIn("XRPUSDT", r)
        self.assertNotIn("ETHUSDT", r)  # istenmeyen sembol süzülür
        bozuk = [{"symbol": "BTCUSDT", "lastFundingRate": "abc"}, {"symbol": "SOLUSDT"}, "metin", None,
                 {"symbol": "ADAUSDT", "lastFundingRate": "NaN"}, {"symbol": "DOTUSDT", "lastFundingRate": "5"}]
        self.assertEqual(l.fonlama_ayristir(bozuk, ["BTCUSDT", "SOLUSDT", "ADAUSDT", "DOTUSDT"]), {})

    def test_tek_sozluk_yanit_ve_hata_yaniti(self):
        r = l.fonlama_ayristir({"symbol": "BTCUSDT", "lastFundingRate": 0.0001}, ["BTCUSDT"])
        self.assertIn("BTCUSDT", r)
        with self.assertRaises(l.VeriHatasi):
            l.fonlama_ayristir({"code": -1121, "msg": "Invalid symbol."}, ["BTCUSDT"])
        with self.assertRaises(l.VeriHatasi):
            l.hacim_ayristir("beklenmeyen", ["BTCUSDT"])

    def test_spread_ve_hacim(self):
        sp = l.spread_ayristir(tam_yanitlar()["/fapi/v1/ticker/bookTicker"], ["BTCUSDT", "SOLUSDT"])
        self.assertAlmostEqual(sp["SOLUSDT"]["spread_bps"], 0.30 / 149.85 * 10000)
        self.assertLess(sp["BTCUSDT"]["spread_bps"], 0.02)
        ters = l.spread_ayristir([{"symbol": "X1", "bidPrice": "2", "askPrice": "1"},
                                  {"symbol": "X2", "bidPrice": "0", "askPrice": "1"}], ["X1", "X2"])
        self.assertEqual(ters, {})
        h = l.hacim_ayristir(tam_yanitlar()["/fapi/v1/ticker/24hr"], ["SOLUSDT"])
        self.assertEqual(h["SOLUSDT"], {"hacim_usdt": 3e6, "fiyat_degisim_yuzde": 9.5})

    def test_acik_faiz_degisimi(self):
        seri = l.acik_faiz_ayristir(af_serisi(SIMDI, artis=0.01) + [{"timestamp": "x"}, {"sumOpenInterestValue": "1"}])
        self.assertEqual(len(seri), 97)
        o = l.acik_faiz_degisimi(seri, SIMDI)
        self.assertAlmostEqual(o["degisim"]["1s"], (1.01 ** 4 - 1) * 100)
        self.assertAlmostEqual(o["degisim"]["24s"], (1.01 ** 96 - 1) * 100)
        self.assertEqual(o["zaman"], SIMDI)
        # Kısa seri: 24 saatlik değişim hesaplanamaz.
        kisa = l.acik_faiz_degisimi(seri[-10:], SIMDI)
        self.assertIsNone(kisa["degisim"]["24s"])
        self.assertIsNotNone(kisa["degisim"]["1s"])
        self.assertIsNone(l.acik_faiz_degisimi([], SIMDI))

    def test_acik_faiz_gelecege_bakmaz(self):
        """Sonradan gelen nokta geçmiş andaki değişimi değiştirmez."""
        seri = l.acik_faiz_ayristir(af_serisi(SIMDI, artis=0.007))
        an = SIMDI - timedelta(hours=3)
        ilk = [n for n in seri if n[0] <= an]
        self.assertEqual(l.acik_faiz_degisimi(ilk, an), l.acik_faiz_degisimi(seri, an))
        # 'simdi'den sonraki noktalar hiç kullanılmaz.
        self.assertEqual(l.acik_faiz_degisimi(seri, an)["zaman"], ilk[-1][0])


class Etiket(Temel):
    def test_yuksek_orta_dusuk_veri_yok(self):
        self.assertEqual(l.sikisma_riski({"fonlama": -0.08, "af_24s": 30.0, "spread_bps": 1, "hacim_usdt": 1e9})["etiket"],
                         "yuksek")
        self.assertEqual(l.sikisma_riski({"fonlama": -0.02, "af_24s": 12.0, "spread_bps": 1, "hacim_usdt": 1e9})["etiket"],
                         "orta")
        r = l.sikisma_riski({"fonlama": 0.01, "af_24s": 1.0, "spread_bps": 1, "hacim_usdt": 1e9})
        self.assertEqual((r["etiket"], r["puan"]), ("dusuk", 0))
        self.assertEqual(l.sikisma_riski({"fonlama": -0.08})["etiket"], "veri_yok")
        self.assertEqual(l.sikisma_riski({})["etiket"], "veri_yok")

    def test_incelik_ve_fiyat_puani(self):
        r = l.sikisma_riski({"fonlama": 0.0, "af_24s": 0.0, "spread_bps": 20.0, "hacim_usdt": 1e9, "fiyat_24s": 10.0})
        self.assertEqual(r["puan"], 3)
        self.assertTrue(r["ince"])
        self.assertEqual({n["olcu"] for n in r["nedenler"]}, {"fonlama", "acik_faiz", "fiyat", "incelik"})
        self.assertEqual(l.sikisma_riski({"fonlama": 0.0, "af_24s": 0.0, "hacim_usdt": 1e6})["puan"], 2)


class CoinListesi(Temel):
    def test_sira_sinir_ve_dogrulama(self):
        islemler = [{"parite": f"C{k}/USDT:USDT"} for k in range(10) for _ in range(k + 1)]
        islemler += [{"parite": "kötü&ad/USDT:USDT"}] * 50
        acik = [{"parite": "ZZZ/USDT:USDT", "kod": "SMK"}, {"parite": "C0/USDT:USDT", "kod": "SMDK2"},
                {"parite": "<b>/USDT"}]
        liste = l.coin_listesi(baglam(acik=acik, islemler=islemler))
        adlar = [c["sembol"] for c in liste]
        self.assertEqual(adlar[:2], ["C0USDT", "ZZZUSDT"])  # açıklar önde (işlem sayısına göre)
        self.assertTrue(all(c["acik"] for c in liste[:2]))
        self.assertIn("BTCUSDT", adlar)
        self.assertEqual(sum(1 for c in liste if not c["acik"] and c["sembol"] != "BTCUSDT"), 8)
        self.assertTrue(all(l.SEMBOL_KALIBI.match(a) for a in adlar))
        self.assertEqual(liste[0]["acik_botlar"], ["SMDK2"])

    def test_bos(self):
        self.assertEqual([c["sembol"] for c in l.coin_listesi({})], ["BTCUSDT"])


class Ag(Temel):
    def test_bayrak_kapaliyken_hic_istek_yok(self):
        sahte = SahteGetir(tam_yanitlar())
        l.getir = sahte
        v = l.hesapla(baglam())
        self.assertEqual(v["durum"], "kapali")
        time.sleep(0.05)
        self.assertEqual(sahte.cagrilar, [])
        self.assertEqual(l._durum["baslatilan"], 0)

    def test_varsayilan_getirici_izinsiz_adresi_reddeder(self):
        with self.assertRaises(l.VeriHatasi):
            l.varsayilan_getir("/fapi/v1/order", {"symbol": "BTCUSDT"})
        self.assertTrue(l.TABAN.startswith("https://fapi.binance.com"))
        self.assertLessEqual(l.ZAMAN_ASIMI, 10)

    def test_hesapla_beklemez_ve_tek_is_baslatir(self):
        serbest = threading.Event()

        def yavas(yol, parametreler=None):
            serbest.wait(5)
            return SahteGetir(tam_yanitlar())(yol, parametreler)

        l.getir = yavas
        l.ag_ac()
        bas = time.monotonic()
        v = l.hesapla(baglam())
        for _ in range(5):
            l.hesapla(baglam())
        self.assertLess(time.monotonic() - bas, 1.0)
        self.assertEqual(v["durum"], "bekliyor")
        self.assertEqual(l._durum["baslatilan"], 1)
        is_ = l._durum["is"]
        self.assertTrue(is_.daemon)
        serbest.set()
        is_.join(10)
        v = l.hesapla(baglam())
        self.assertEqual(v["durum"], "hazir")
        btc = [c for c in v["coinler"] if c["sembol"] == "BTCUSDT"][0]
        self.assertAlmostEqual(btc["fonlama"]["oran_yuzde"], 0.01)
        # Önbellek taze: hemen yeniden istenmez.
        self.assertEqual(l._durum["baslatilan"], 1)

    def test_yenile_degerler_ve_etiket(self):
        l.ag_ac()
        sahte = SahteGetir(tam_yanitlar())
        r = l.yenile(["BTCUSDT", "SOLUSDT", "kötü"], getirici=sahte, simdi=SIMDI, ara=0)
        self.assertEqual(r, {"basarili": 5, "hatali": 0})
        self.assertNotIn({"symbol": "kötü", "period": "15m", "limit": 97}, [p for _, p in sahte.cagrilar])
        l._durum["son_deneme"] = time.monotonic()
        v = l.hesapla(baglam(acik=[{"parite": "SOL/USDT:USDT", "kod": "SMK"}]))
        sol = v["coinler"][0]
        self.assertEqual(sol["sembol"], "SOLUSDT")
        self.assertAlmostEqual(sol["acik_faiz"]["degisim"]["24s"], (1.003 ** 96 - 1) * 100)
        # fonlama −%0,08 (2) + açık faiz %33 (2) + fiyat %9,5 (1) + ince (hacim 3 milyon: 2)
        self.assertEqual((sol["risk"]["etiket"], sol["risk"]["puan"]), ("yuksek", 7))
        self.assertEqual(v["coinler"][1]["risk"]["etiket"], "dusuk")

    def test_hata_alinamadi_eski_deger_ve_bekleme_uzar(self):
        l.ag_ac()
        l.yenile(["BTCUSDT"], getirici=SahteGetir(tam_yanitlar()), simdi=SIMDI - timedelta(minutes=10), ara=0)
        y = tam_yanitlar()
        y["/fapi/v1/premiumIndex"] = urllib.error.HTTPError("u", 451, "x", {}, io.BytesIO())
        y["/fapi/v1/ticker/24hr"] = {"code": -1003, "msg": "Too many requests"}
        l.yenile(["BTCUSDT"], getirici=SahteGetir(y), simdi=SIMDI, ara=0)
        l._durum["son_deneme"] = time.monotonic()
        btc = l.hesapla(baglam())["coinler"][0]
        self.assertEqual(btc["fonlama_hata"], "HTTP 451")
        self.assertIn("-1003", btc["hacim_hata"])
        self.assertAlmostEqual(btc["fonlama"]["yas_dakika"], 10.0)  # son başarılı değer, yaşıyla
        self.assertEqual(l._durum["ardisik_hata"], 0)  # bir kısmı başarılı
        hepsi = {k: TimeoutError("zaman aşımı") for k in y}
        l.yenile(["BTCUSDT"], getirici=SahteGetir(hepsi), simdi=SIMDI, ara=0)
        l.yenile(["BTCUSDT"], getirici=SahteGetir(hepsi), simdi=SIMDI, ara=0)
        self.assertEqual(l._durum["ardisik_hata"], 2)
        self.assertGreater(l.bekleme_saniye(2), l.bekleme_saniye(0))
        self.assertEqual(l.bekleme_saniye(50), l.EN_UZUN_BEKLEME)

    def test_eski_deger_etikete_katilmaz(self):
        l.ag_ac()
        l.yenile(["BTCUSDT"], getirici=SahteGetir(tam_yanitlar()), simdi=SIMDI - timedelta(hours=2), ara=0)
        l._durum["son_deneme"] = time.monotonic()
        btc = l.hesapla(baglam())["coinler"][0]
        self.assertTrue(btc["fonlama"]["eski"])
        self.assertEqual(btc["risk"]["etiket"], "veri_yok")


class Defter(Temel):
    def test_defter_kaydi(self):
        with tempfile.TemporaryDirectory() as g:
            self.assertFalse(l.defter_ozeti(g, SIMDI)["var"])
            (Path(g) / "kayit").mkdir()
            vt = sqlite3.connect(Path(g) / "kayit" / "defter.sqlite")
            vt.execute("CREATE TABLE ornek_v1 (zaman INTEGER PRIMARY KEY, dengesizlik_20 REAL, dengesizlik_tum REAL, "
                       "makas_bps REAL)")
            vt.executemany("INSERT INTO ornek_v1 VALUES (?,?,?,?)",
                           [(int(SIMDI.timestamp()) - 60, -0.1, 0.0, 0.2), (int(SIMDI.timestamp()) - 30, -0.35, -0.1, 0.1)])
            vt.commit()
            vt.close()
            d = l.defter_ozeti(g, SIMDI)
            self.assertEqual((d["var"], d["dengesizlik_20"], d["yas_saniye"], d["bayat"]), (True, -0.35, 30.0, False))
            html = sl._defter_karti(d, "Europe/Bucharest")
            self.assertIn("Satış tarafı ağır", html)
            self.assertIn('href="/defter"', html)

    def test_bozuk_defter_dusurmez(self):
        with tempfile.TemporaryDirectory() as g:
            (Path(g) / "kayit").mkdir()
            (Path(g) / "kayit" / "defter.sqlite").write_bytes(b"bozuk")
            self.assertFalse(l.defter_ozeti(g, SIMDI)["var"])


class Cizim(Temel):
    def _ozet(self, v):
        return {"ek": {"likidite": v}}

    def test_ag_kapali_ekran(self):
        v = l.hesapla(baglam(acik=[{"parite": "SOL/USDT:USDT", "kod": "<SMK>"}]))
        html = sl.ekran(self._ozet(v), "Europe/Bucharest")
        self.assertEqual(html.count('<section id="likidite"'), 1)
        self.assertIn("Bu bölüm yalnız canlı sayfada dolar", html)
        self.assertIn("yalnız defter servisi çalışırken", html)
        self.assertIn("&lt;SMK&gt;", html)
        self.assertNotIn("<SMK>", html)
        self.assertIn("Tasfiye kümeleri", html)
        self.assertIn("sınanmadı", html)

    def test_ag_acik_dolu_ve_hatali_ekran(self):
        l.ag_ac()
        y = tam_yanitlar()
        y["/fapi/v1/ticker/bookTicker"] = urllib.error.URLError("yok")
        l.yenile(["BTCUSDT", "SOLUSDT"], getirici=SahteGetir(y), simdi=SIMDI, ara=0)
        l._durum["son_deneme"] = time.monotonic()
        v = l.hesapla(baglam(acik=[{"parite": "SOL/USDT:USDT", "kod": "SMK"}]))
        html = sl.ekran(self._ozet(v), "Europe/Bucharest")
        self.assertIn("sıkışma riski: yüksek", html)
        self.assertIn("▲", html)
        self.assertIn("alınamadı", html)
        self.assertIn("short öder", html)
        self.assertIn("açık pozisyon", html)
        self.assertNotIn("<script", html)

    def test_tum_ag_hatasi_ekrani(self):
        l.ag_ac()
        hata = {k: OSError("x") for k in tam_yanitlar()}
        l.yenile(["BTCUSDT"], getirici=SahteGetir(hata), simdi=SIMDI, ara=0)
        l._durum["son_deneme"] = time.monotonic()
        v = l.hesapla(baglam())
        self.assertEqual(v["durum"], "hata")
        self.assertIn("veri alınamadı", sl.ekran(self._ozet(v), "UTC"))

    def test_bos_veri_dusmez(self):
        html = sl.ekran({"ek": {"likidite": {}}}, "UTC")
        self.assertEqual(html.count('<section id="likidite"'), 1)

    def test_tam_sayfa_betiksiz(self):
        from karabasan import sayfa, sonuc
        from testler.veri import sahte_sinav_klasoru

        with tempfile.TemporaryDirectory() as g:
            k = sahte_sinav_klasoru(Path(g) / "veri", SIMDI)
            ozet = sonuc.genel_ozet(k, SIMDI)
            self.assertFalse(ozet["ek"]["likidite"].get("hata"))
            import json
            json.dumps(sonuc.json_icin(ozet["ek"]["likidite"]))
            html = sayfa.html_uret(ozet, yenile_saniye=0)
            self.assertEqual(html.count('<section id="likidite"'), 1)
            self.assertNotIn("<script", html)
            self.assertIn("Bu bölüm yalnız canlı sayfada dolar", html)


class PandasOlmadan(unittest.TestCase):
    def test_pandas_numpy_olmadan_calisir(self):
        kod = (
            "import sys\n"
            "sys.modules['pandas'] = None\nsys.modules['numpy'] = None\n"
            "from datetime import datetime, timezone\n"
            "from karabasan import sonuc_likidite as l, sayfa_likidite as sl\n"
            "v = l.hesapla({'veri_klasoru': '.', 'simdi': datetime.now(timezone.utc), 'acik': [], 'islemler': []})\n"
            "assert v['durum'] == 'kapali'\n"
            "assert '<section id=\"likidite\"' in sl.ekran({'ek': {'likidite': v}}, 'UTC')\n"
        )
        r = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True,
                           cwd=Path(__file__).resolve().parent.parent, env=dict(os.environ))
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
