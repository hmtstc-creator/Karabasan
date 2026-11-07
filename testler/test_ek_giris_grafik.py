"""Zararda ek giriş yapılmış işlemde grafik ve stop İLK giriş fiyatına göre çizilir (8 Kasım 2026).

Hata: hazır motor ek girişten sonra 'open_rate'e ORTALAMA girişi yazar. Grafik bunu ilk girişin zamanına koyunca
giriş işareti mumların çok üstünde (hiç işlem görmemiş bir fiyatta) duruyor, stop da yanlış yerde çiziliyordu.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from karabasan import islem_grafik as ig
from karabasan import sonuc
from karabasan.kural import kural_yukle
from testler.veri import eski_bot_listesi_baslat, sahte_islem_db

T0 = datetime(2026, 11, 6, 9, 37, tzinfo=timezone.utc)
ORDERS = """CREATE TABLE orders (id INTEGER PRIMARY KEY, ft_trade_id INTEGER, ft_order_side VARCHAR, status VARCHAR,
price FLOAT, average FLOAT, safe_price FLOAT, filled FLOAT, amount FLOAT, order_date DATETIME, order_filled_date DATETIME)"""


def db_kur(klasor: Path, ek_giris: bool, orders: bool = True) -> Path:
    yol = klasor / "db" / "smdk2-vadeli.sqlite"
    sahte_islem_db(yol, [("SPCX/USDT:USDT", T0, T0 + timedelta(hours=17), -20.0, "stop_loss", True)])
    b = sqlite3.connect(yol)
    # Motorun yazdığı gibi: ek girişten sonra open_rate = ortalama (126,4 ilk, 136,512 ek, iki kat büyüklük → ~133,14)
    ortalama = (126.4 + 2 * 126.4 * 1.08) / 3 if ek_giris else 126.4
    b.execute("UPDATE trades SET open_rate=?, stake_amount=?", (ortalama, 150.0 if ek_giris else 50.0))
    if orders:
        b.execute(ORDERS)
        zaman = T0.strftime("%Y-%m-%d %H:%M:%S.%f")
        b.execute("INSERT INTO orders (ft_trade_id, ft_order_side, status, price, average, filled, amount, order_date,"
                  " order_filled_date) VALUES (1, 'sell', 'closed', 126.4, 126.4, 1, 1, ?, ?)", (zaman, zaman))
        if ek_giris:
            z2 = (T0 + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S.%f")
            b.execute("INSERT INTO orders (ft_trade_id, ft_order_side, status, price, average, filled, amount, order_date,"
                      " order_filled_date) VALUES (1, 'sell', 'closed', 136.512, 136.512, 2, 2, ?, ?)", (z2, z2))
        z3 = (T0 + timedelta(hours=17)).strftime("%Y-%m-%d %H:%M:%S.%f")   # çıkış emri (alış): giriş sayılmamalı
        b.execute("INSERT INTO orders (ft_trade_id, ft_order_side, status, price, average, filled, amount, order_date,"
                  " order_filled_date) VALUES (1, 'buy', 'closed', 137.5, 137.5, 3, 3, ?, ?)", (z3, z3))
    b.commit()
    b.close()
    return yol


class EkGirisliIslem(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.klasor = Path(self.gecici.name)

    def tearDown(self):
        self.gecici.cleanup()

    def test_ilk_giris_ve_ek_giris_emirlerden_okunur(self):
        yol = db_kur(self.klasor, ek_giris=True)
        islem = sonuc.islemleri_oku(yol)["kapali"][0]
        self.assertAlmostEqual(islem["ilk_giris_fiyati"], 126.4)
        self.assertGreater(islem["giris_fiyati"], 130)            # open_rate = ortalama
        self.assertEqual(len(islem["ek_girisler"]), 1)             # çıkış emri (buy) giriş sayılmadı
        self.assertAlmostEqual(islem["ek_girisler"][0]["fiyat"], 136.512)
        self.assertEqual(islem["ek_girisler"][0]["zaman"], T0 + timedelta(hours=5))

    def test_emir_tablosu_yoksa_open_rate_kullanilir(self):
        yol = db_kur(self.klasor, ek_giris=False, orders=False)
        islem = sonuc.islemleri_oku(yol)["kapali"][0]
        self.assertAlmostEqual(islem["ilk_giris_fiyati"], 126.4)
        self.assertEqual(islem["ek_girisler"], [])

    def test_stop_ilk_girise_gore_tetik_ortalamaya_gore(self):
        islem = {"yon": "aciga_satis", "giris_fiyati": 133.14, "ilk_giris_fiyati": 126.4}
        kural = {"cikis": {"zarar_durdur_yuzde": 9.0, "iz_suren_stop": {"tetik_yuzde": 1.2, "mesafe_yuzde": 0.3}}}
        sev = ig.seviyeler(islem, kural)
        self.assertAlmostEqual(sev["giris"], 126.4)
        self.assertAlmostEqual(sev["ortalama"], 133.14)
        self.assertAlmostEqual(sev["stop"], 126.4 * 1.09)          # 137,78: işlem gerçekte bunda kapandı
        self.assertAlmostEqual(sev["tetik"], 133.14 * (1 - 0.012))

    def test_ek_girissiz_islemde_ortalama_cizgisi_yok(self):
        islem = {"yon": "aciga_satis", "giris_fiyati": 100.0, "ilk_giris_fiyati": 100.0}
        self.assertNotIn("ortalama", ig.seviyeler(islem, {"cikis": {"zarar_durdur_yuzde": 3.0}}))
        self.assertNotIn("ortalama", ig.seviyeler({"yon": "alim", "giris_fiyati": 100.0}, {"cikis": {}}))

    def test_acik_risk_stop_fiyati_ilk_girisle(self):
        kural = kural_yukle("SMDK2")
        islem = {"yon": "aciga_satis", "giris_fiyati": 133.14, "ilk_giris_fiyati": 126.4, "tutar": 150.0}
        r = sonuc.acik_risk(islem, kural, 50.0)
        self.assertAlmostEqual(r["stop_fiyati"], 126.4 * 1.09)

    def test_sayfa_ilk_giris_ek_giris_ve_ortalamayi_gosterir(self):
        yol = db_kur(self.klasor, ek_giris=True)
        geri = eski_bot_listesi_baslat()
        try:
            from karabasan import botlar
            orijinal = list(botlar.BOTLAR)
            botlar.BOTLAR[:] = orijinal + [("smdk2-vadeli", "SMDK2Vadeli", "SMDK2", "vadeli")]
            try:
                def mumlar(parite, piyasa, aralik, bas, son):
                    dk = dict(ig.ARALIKLAR)[aralik]
                    m, t = [], bas
                    while t <= son:
                        m.append((t, 126.0, 127.0, 125.0, 126.5))
                        t += timedelta(minutes=dk)
                    return m

                html = ig.islem_sayfasi(self.klasor, "smdk2-vadeli", 1, getir=mumlar,
                                        simdi=T0 + timedelta(days=1))
            finally:
                botlar.BOTLAR[:] = orijinal
        finally:
            geri()
        self.assertIn("İlk giriş", html)
        self.assertIn("Zararda ek giriş", html)
        self.assertIn("Ortalama giriş", html)
        self.assertIn("137,78", html)          # stop ilk girişe göre (126,4 × 1,09)
        self.assertNotIn("145,1", html)        # ortalamadan hesaplanan yanlış stop


if __name__ == "__main__":
    unittest.main()
