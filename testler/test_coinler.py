import unittest

from araclar.yapilandirma_uret import SABIT_COINLER
from karabasan import coinler as c

BILGI = {"symbols": [
    {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING", "contractType": "PERPETUAL"},
    {"symbol": "ETHUSDT", "baseAsset": "ETH", "quoteAsset": "USDT", "status": "TRADING", "contractType": "PERPETUAL"},
    {"symbol": "USDCUSDT", "baseAsset": "USDC", "quoteAsset": "USDT", "status": "TRADING", "contractType": "PERPETUAL"},
    {"symbol": "XYZUSDT", "baseAsset": "XYZ", "quoteAsset": "USDT", "status": "BREAK", "contractType": "PERPETUAL"},
    {"symbol": "BTCUSDT_261225", "baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING", "contractType": "CURRENT_QUARTER"},
    {"symbol": "ABCUSDT", "baseAsset": "ABC", "quoteAsset": "USDT", "status": "TRADING", "contractType": "PERPETUAL"},
]}


def t(s, h, f=1.0, d=0.5):
    return {"symbol": s, "quoteVolume": str(h), "lastPrice": str(f), "priceChangePercent": str(d)}


TICK = [t("BTCUSDT", 9e9, 60000), t("ETHUSDT", 4e9, 3000), t("USDCUSDT", 8e9), t("XYZUSDT", 9e9),
        t("BTCUSDT_261225", 9e9), t("ABCUSDT", 2e6)]


class CoinlerTesti(unittest.TestCase):
    def test_stable_ve_islemde_olmayanlar_cikar(self):
        adlar = {x["coin"] for x in c.birlestir(BILGI, TICK)}
        self.assertEqual(adlar, {"BTC", "ETH", "ABC"})

    def test_hacim_siniri_ve_siralama(self):
        liste = c.suz(c.birlestir(BILGI, TICK), 5e6)
        self.assertEqual([x["coin"] for x in liste], ["BTC", "ETH"])
        self.assertEqual(len(c.suz(c.birlestir(BILGI, TICK), 1e6)), 3)

    def test_botlarin_stable_listesi_kapsanir(self):
        for ad in SABIT_COINLER.split("|"):
            self.assertTrue(c.stable_mi(ad), ad)

    def test_hacim_girisi(self):
        self.assertEqual(c.hacim_oku({"hacim": ["10"]}), 10.0)
        self.assertEqual(c.hacim_oku({"hacim": ["2,5"]}), 2.5)
        self.assertEqual(c.hacim_oku({"hacim": ["abc"]}), c.VARSAYILAN_HACIM_MILYON)
        self.assertEqual(c.hacim_oku({"hacim": ["-3"]}), c.VARSAYILAN_HACIM_MILYON)
        self.assertEqual(c.hacim_oku({}), c.VARSAYILAN_HACIM_MILYON)

    def test_sayfa(self):
        o = c.Onbellek()
        o._veri, o._zaman = c.birlestir(BILGI, TICK), __import__("time").time()
        html = c.sayfa_uret({"hacim": ["5"]}, o)
        self.assertIn("BTC", html)
        self.assertNotIn("USDC", html)
        self.assertNotIn(">ABC<", html)


if __name__ == "__main__":
    unittest.main()
