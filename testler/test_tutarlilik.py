"""Ana sayfa, Rapor ve bot kartı aynı cüzdan rakamını göstermeli (9 Kasım 2026)."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from karabasan import sonuc
from testler.veri import sahte_sinav_klasoru

SIMDI = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)


class Tutarlilik(unittest.TestCase):
    def test_bot_toplami_gercek_usdt_ile_ayni(self):
        with tempfile.TemporaryDirectory() as g:
            klasor = sahte_sinav_klasoru(Path(g) / "veri", SIMDI)
            ozet = sonuc.genel_ozet(klasor, SIMDI)
            for bot in ozet["botlar"]:
                kayit = sonuc.islemleri_oku(klasor / "db" / f"{bot['bot']}.sqlite")
                d = sonuc.donem_bilgisi(SIMDI, sonuc.zaman_dosyasi_oku(klasor / "isinma_baslangici.txt"),
                                        sonuc.zaman_dosyasi_oku(klasor / "sinav_baslangici.txt"))
                gercek = sum(float(i["net_tutar"]) for i in kayit["kapali"]
                             if (d["baslangic"] is None or i["giris_zamani"] >= d["baslangic"])
                             and (d["bitis"] is None or i["cikis_zamani"] <= d["bitis"]))
                self.assertAlmostEqual(bot["net_tutar"], gercek, places=6, msg=bot["bot"])
            self.assertAlmostEqual(
                ozet["toplam"]["net_tutar"], sum(b["net_tutar"] for b in ozet["botlar"]), places=6)
            # Rapor ekranı günlük toplamları gerçek USDT'den: aynı rakam olmalı.
            gunluk = sum(g["net_tutar"] for g in ozet["gunluk_toplam"])
            self.assertAlmostEqual(gunluk, ozet["toplam"]["net_tutar"], places=4)


if __name__ == "__main__":
    unittest.main()
