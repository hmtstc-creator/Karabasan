import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from karabasan import kayitci

ORNEK = {"data": {
    "total_market_cap": {"usd": 3_200_000_000_000.0, "btc": 40_000_000.0},
    "total_volume": {"usd": 120_000_000_000.0},
    "market_cap_percentage": {"btc": 57.5, "eth": 11.2},
    "updated_at": 1791640000,
}}
AN = datetime(2026, 10, 10, 15, 30, tzinfo=timezone.utc)


class KayitciTestleri(unittest.TestCase):
    def test_satir_cikar(self):
        satir = kayitci.satir_cikar(ORNEK, AN)
        self.assertEqual(satir["zaman"], "2026-10-10T15:30:00Z")
        self.assertEqual(satir["btc_dominans_yuzde"], 57.5)
        self.assertAlmostEqual(satir["total2_usd"], 3.2e12 * 0.425)
        self.assertEqual(list(satir), kayitci.SUTUNLAR)

    def test_bozuk_yanit_reddedilir(self):
        with self.assertRaises(KeyError):
            kayitci.satir_cikar({"data": {}}, AN)
        bozuk = {"data": {**ORNEK["data"], "market_cap_percentage": {"btc": 0.0}}}
        with self.assertRaises(ValueError):
            kayitci.satir_cikar(bozuk, AN)

    def test_dosyaya_eklenir_baslik_bir_kez_yazilir(self):
        with tempfile.TemporaryDirectory() as klasor:
            yol = Path(klasor) / "alt" / "kuresel.csv"
            satir = kayitci.satir_cikar(ORNEK, AN)
            kayitci.satir_ekle(yol, satir)
            kayitci.satir_ekle(yol, satir)
            with yol.open(encoding="utf-8") as dosya:
                satirlar = list(csv.reader(dosya))
            self.assertEqual(satirlar[0], kayitci.SUTUNLAR)
            self.assertEqual(len(satirlar), 3)


if __name__ == "__main__":
    unittest.main()
