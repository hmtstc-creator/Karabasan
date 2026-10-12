import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

from karabasan.eslestirme import (
    benzetim_islemleri, eslestir, motor_islemleri, motor_sonuclari_oku, rapor_satirlari,
)

MUM = pd.Timedelta(minutes=5)


def motor_islemi(pair, acilis, kapanis, neden, short=True):
    # Hazır motorun sonuç dosyasındaki işlem kaydının ilgili alanları.
    return {"pair": pair, "open_date": acilis, "close_date": kapanis,
            "exit_reason": neden, "is_short": short}


def benz_islemi(giris, cikis, neden):
    return {"giris_zamani": pd.Timestamp(giris, tz="UTC"),
            "cikis_zamani": pd.Timestamp(cikis, tz="UTC"), "neden": neden, "yon": "aciga_satis"}


class SonucOkumaTestleri(unittest.TestCase):
    def test_zip_icindeki_sonucu_okur_en_yeniyi_secer(self):
        with tempfile.TemporaryDirectory() as d:
            klasor = Path(d)
            eski = {"strategy": {"S1KVadeli": {"trades": [motor_islemi("ETH/USDT:USDT", "2026-10-01 00:00:00+00:00",
                                                                        "2026-10-01 01:00:00+00:00", "roi")]}}}
            yeni = {"strategy": {"S1KVadeli": {"trades": []}}}
            (klasor / "backtest-result-1.json").write_text(json.dumps(eski))
            with zipfile.ZipFile(klasor / "backtest-result-2.zip", "w") as z:
                z.writestr("backtest-result-2_config.json", json.dumps({"strategy": "S1KVadeli"}))
                z.writestr("backtest-result-2.json", json.dumps(yeni))
            os.utime(klasor / "backtest-result-1.json", (1, 1))
            (klasor / ".last_result.json").write_text("{}")
            sonuc = motor_sonuclari_oku(klasor)
            self.assertEqual(sonuc, {"S1KVadeli": []})

    def test_klasor_yoksa_bos(self):
        self.assertEqual(motor_sonuclari_oku(Path("/yok/boyle/bir/klasor")), {})


class EslestirmeTestleri(unittest.TestCase):
    def test_cikis_mumu_iki_tarafta_ayni_anlami_tasir(self):
        # Kâr hedefi: benzetim mumun kapanışını yazar, motor açılışını.
        b = benzetim_islemleri([benz_islemi("2026-10-01 00:05", "2026-10-01 00:20", "kar_hedefi")], "ETH", MUM)
        m = motor_islemleri([motor_islemi("ETH/USDT:USDT", "2026-10-01 00:05:00+00:00",
                                          "2026-10-01 00:15:00+00:00", "roi")])
        self.assertEqual(b[0]["cikis_mumu"], m[0]["cikis_mumu"])
        self.assertEqual(m[0]["neden"], "kar_hedefi")
        # Süre aşımı: ikisi de bir sonraki mumun açılışını yazar.
        b = benzetim_islemleri([benz_islemi("2026-10-01 00:05", "2026-10-01 01:05", "sure_asimi")], "ETH", MUM)
        self.assertEqual(b[0]["cikis_mumu"], pd.Timestamp("2026-10-01 01:05", tz="UTC"))

    def test_fark_ve_nedeni_gorunur(self):
        # Motor ilk işlemi stopla erken kapatıp ikinci bir işlem açıyor;
        # benzetim aynı işlemi süre aşımına kadar tutuyor.
        motor = motor_islemleri([
            motor_islemi("SOL/USDT:USDT", "2026-10-01 00:05:00+00:00", "2026-10-01 00:10:00+00:00", "stop_loss"),
            motor_islemi("SOL/USDT:USDT", "2026-10-01 00:20:00+00:00", "2026-10-01 00:30:00+00:00", "roi"),
        ])
        benz = benzetim_islemleri([benz_islemi("2026-10-01 00:05", "2026-10-01 01:05", "sure_asimi")], "SOL", MUM)
        s = eslestir(motor, benz)
        self.assertEqual((s["motor"], s["benzetim"], s["eslesen"]), (2, 1, 1))
        self.assertEqual(s["neden_farki"], {("zarar_durdur", "sure_asimi"): 1})
        self.assertEqual(len(s["yalniz_motor"]), 1)
        metin = "\n".join(rapor_satirlari("s1k-vadeli", motor, benz))
        self.assertIn("yalnız motor 1", metin)
        self.assertIn("benzetimde o an: 10-01 00:05 → 10-01 01:05 sure_asimi", metin)

    def test_birebir_tutunca_fark_satiri_yok(self):
        motor = motor_islemleri([motor_islemi("XRP/USDT:USDT", "2026-10-01 00:05:00+00:00",
                                              "2026-10-01 00:15:00+00:00", "stop_loss")])
        benz = benzetim_islemleri([benz_islemi("2026-10-01 00:05", "2026-10-01 00:20", "zarar_durdur")], "XRP", MUM)
        satirlar = rapor_satirlari("s5k-vadeli", motor, benz)
        self.assertEqual(len(satirlar), 3)
        self.assertIn("eşleşen 1", satirlar[0])

    def test_eslesenlerin_net_sonucu_ve_iz_suren_stop_zamani(self):
        # 16. uyum denemesi: motor iz süren stopu mumun tepesiyle aynı mumda taşır,
        # benzetim bir sonraki mumdan; aynı işlem iki tarafta farklı net ile kapanır.
        ham = [motor_islemi("ETH/USDT:USDT", "2026-10-01 00:05:00+00:00", "2026-10-01 00:30:00+00:00",
                            "trailing_stop_loss", short=False),
               motor_islemi("SOL/USDT:USDT", "2026-10-01 00:05:00+00:00", "2026-10-01 00:30:00+00:00",
                            "stop_loss", short=False)]
        ham[0]["profit_ratio"], ham[1]["profit_ratio"] = 0.0115, -0.031
        motor = motor_islemleri(ham)
        b1 = benz_islemi("2026-10-01 00:05", "2026-10-01 00:45", "iz_suren_stop")
        b2 = benz_islemi("2026-10-01 00:05", "2026-10-01 00:35", "zarar_durdur")
        b1["net_yuzde"], b2["net_yuzde"] = 1.4, -3.1
        benz = (benzetim_islemleri([b1], "ETH", MUM) + benzetim_islemleri([b2], "SOL", MUM))
        n = eslestir(motor, benz)["net"]
        self.assertEqual((n["sayi"], n["iz_sayi"], n["iz_gec"], n["iz_erken"]), (2, 1, 1, 0))
        self.assertAlmostEqual(n["motor"], -1.95)
        self.assertAlmostEqual(n["benzetim"], -1.7)
        metin = "\n".join(rapor_satirlari("sm-vadeli", motor, benz, tutar=50))
        self.assertIn("eşleşen 2 işlemin net toplamı (komisyon dahil): motor %-1,95 = -0,98 USDT, "
                      "benzetim %-1,70 = -0,85 USDT", metin)
        self.assertIn("iz süren stopla kapanan 1: benzetim 1 tanesini daha geç, 0 tanesini daha erken", metin)
        self.assertIn("ortalama net motor %+1,15, benzetim %+1,40", metin)


if __name__ == "__main__":
    unittest.main()
