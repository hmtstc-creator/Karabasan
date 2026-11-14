import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import saglama, site_gezinti
from karabasan.sonuc import islemleri_oku

BAS = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)


def kur(yol: Path, satirlar, emirsiz=()):
    """Hazır motorun tablolarına benzer küçük bir kayıt. Açığa satış: giriş 'sell', çıkış 'buy'."""
    vt = sqlite3.connect(yol)
    vt.execute("CREATE TABLE trades (id INTEGER, pair TEXT, is_open INT, is_short INT, open_date TEXT, close_date TEXT,"
               " stake_amount REAL, open_rate REAL, close_rate REAL, close_profit_abs REAL, close_profit REAL,"
               " fee_open REAL, fee_close REAL, fee_open_cost REAL, fee_close_cost REAL, funding_fees REAL, exit_reason TEXT)")
    vt.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, ft_trade_id INT, ft_order_side TEXT, status TEXT,"
               " amount REAL, filled REAL, average REAL, price REAL, order_filled_date TEXT, order_date TEXT)")
    for s in satirlar:
        vt.execute("INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", s)
    vt.commit()
    vt.close()


def emir(yol, kimlik, giris, cikis, adet=10.0):
    vt = sqlite3.connect(yol)
    vt.execute("INSERT INTO orders (ft_trade_id,ft_order_side,status,amount,filled,average,price,order_filled_date) "
               "VALUES (?,?,?,?,?,?,?,?)", (kimlik, "sell", "closed", adet, adet, giris, giris, "2026-11-01 10:00:00"))
    vt.execute("INSERT INTO orders (ft_trade_id,ft_order_side,status,amount,filled,average,price,order_filled_date) "
               "VALUES (?,?,?,?,?,?,?,?)", (kimlik, "buy", "closed", adet, adet, cikis, cikis, "2026-11-01 11:00:00"))
    vt.commit()
    vt.close()


def islem(kimlik, giris, cikis, kar, neden="roi", pair="AAA/USDT:USDT"):
    # 10 adet, açığa satış, komisyon her yönde 0,04 USDT
    return (kimlik, pair.replace("AAA", f"C{kimlik}"), 0, 1, f"2026-11-01 10:0{kimlik}:00", "2026-11-01 11:00:00", 50.0, giris, cikis, kar, 0.0,
            0.0004, 0.0004, 0.04, 0.04, 0.0, neden)


class SaglamaTesti(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.TemporaryDirectory()
        self.yol = Path(self.klasor.name) / "x.sqlite"
        # 10 adet; giriş 100 çıkış 99 -> brüt 10, komisyon 0,08 -> net 9,92
        satirlar = [islem(1, 100.0, 99.0, 9.92), islem(2, 100.0, 98.0, 19.92), islem(3, 100.0, 101.0, -10.08, "stop_loss")]
        kur(self.yol, satirlar)
        emir(self.yol, 1, 100.0, 99.0)
        emir(self.yol, 2, 100.0, 98.0)
        emir(self.yol, 3, 100.0, 101.0)

    def tearDown(self):
        self.klasor.cleanup()

    def sagla(self, sayfa_toplami=19.76, mum_fn=None):
        kayit = saglama._kayit_oku(self.yol)
        return saglama.bot_sagla("x", "vadeli", kayit, None, None, sayfa_toplami, mum_fn)

    def durum(self, sonuc, kimlik):
        return next(d["durum"] for d in sonuc["denetimler"] if d["kimlik"] == kimlik)

    def test_temiz_kayit_tutar(self):
        s = self.sagla()
        self.assertEqual(self.durum(s, "toplam"), "ok")
        self.assertEqual(self.durum(s, "emir"), "ok")
        self.assertEqual(self.durum(s, "mantik"), "ok")
        self.assertAlmostEqual(s["toplam"], 19.76, places=6)

    def test_sayfa_ile_ayni_yoldan_okununca_ayni_toplam(self):
        sayfa = islemleri_oku(self.yol)
        self.assertAlmostEqual(sum(i["net_tutar"] for i in sayfa["kapali"]), self.sagla()["toplam"], places=9)

    def test_sisirilmis_kar_emirden_yakalanir(self):
        vt = sqlite3.connect(self.yol)
        vt.execute("UPDATE trades SET close_profit_abs = 59.92 WHERE id = 2")
        vt.commit()
        vt.close()
        s = self.sagla(sayfa_toplami=59.76)
        self.assertEqual(self.durum(s, "toplam"), "ok")   # sayfa ile kayıt uyuşuyor...
        self.assertEqual(self.durum(s, "emir"), "hata")   # ...ama emirlerden hesaplanan kâr uyuşmuyor

    def test_sayfa_toplami_farkliysa_yakalanir(self):
        self.assertEqual(self.durum(self.sagla(sayfa_toplami=620.0), "toplam"), "hata")

    def test_sayfa_toplami_yoksa_belirsiz(self):
        self.assertEqual(self.durum(self.sagla(sayfa_toplami=None), "toplam"), "belirsiz")

    def test_emir_yoksa_yesil_denmez(self):
        vt = sqlite3.connect(self.yol)
        vt.execute("DELETE FROM orders")
        vt.commit()
        vt.close()
        self.assertEqual(self.durum(self.sagla(), "emir"), "belirsiz")

    def test_mantik_celiskileri(self):
        vt = sqlite3.connect(self.yol)
        vt.execute("UPDATE trades SET exit_reason='stop_loss' WHERE id=1")   # kârlı stop
        vt.execute("UPDATE trades SET close_date='2026-11-01 09:00:00' WHERE id=2")  # çıkış girişten önce
        vt.commit()
        vt.close()
        m = saglama.mantik_denetimi(saglama.kapali_islemler(saglama._kayit_oku(self.yol)["islemler"], None, None))
        metin = " ".join(a for _k, a in m["sorunlar"])
        self.assertIn("stop ile çıkmış", metin)
        self.assertIn("girişten önce", metin)

    def test_cift_kayit(self):
        vt = sqlite3.connect(self.yol)
        vt.execute("INSERT INTO trades SELECT 9,pair,is_open,is_short,open_date,close_date,stake_amount,open_rate,"
                   "close_rate,close_profit_abs,close_profit,fee_open,fee_close,fee_open_cost,fee_close_cost,"
                   "funding_fees,exit_reason FROM trades WHERE id=1")
        vt.commit()
        vt.close()
        m = saglama.mantik_denetimi(saglama.kapali_islemler(saglama._kayit_oku(self.yol)["islemler"], None, None))
        self.assertIn("çift kayıt", " ".join(a for _k, a in m["sorunlar"]))

    def test_yogunlasma_uyarisi(self):
        satirlar = [{"close_profit_abs": 100.0, "id": 0}] + [{"close_profit_abs": -1.0, "id": i} for i in range(1, 12)]
        y = saglama.yogunlasma(satirlar)
        self.assertLess(y["en_iyiden_sonra"], 0)

    def test_fiyat_gercekligi(self):
        an = BAS
        mum_iyi = lambda *a: [(an, 100, 101.5, 97.5, 99)]  # noqa: E731
        mum_kotu = lambda *a: [(an, 50, 51, 49, 50)]  # noqa: E731
        def hata(*a):
            raise OSError("ağ yok")
        self.assertEqual(self.durum(self.sagla(mum_fn=mum_iyi), "fiyat"), "ok")
        self.assertEqual(self.durum(self.sagla(mum_fn=mum_kotu), "fiyat"), "hata")
        self.assertEqual(self.durum(self.sagla(mum_fn=hata), "fiyat"), "belirsiz")

    def test_genel_ve_sayfa(self):
        with tempfile.TemporaryDirectory() as k:
            sonuc = saglama.genel(Path(k))   # kayıt dosyaları yok: yeşil olmamalı
            self.assertEqual(sonuc["hukum"], "hata")
            html = saglama.sayfa_uret(sonuc)
            self.assertIn("kâr garanti", html)
            self.assertIn("Sağlama", html)

    def test_gezinti_baglantisi(self):
        self.assertIn('href="/sagla"', site_gezinti.serit("sagla"))


if __name__ == "__main__":
    unittest.main()
