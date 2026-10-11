#!/usr/bin/env python3
"""Hazır motorun geçmiş testi ile bağımsız benzetimi işlem işlem karşılaştırır.

Uyum denemesinin 4. adımı motorun işlem listelerini user_data/backtest_results/
altına yazar; bu betik onları okur, aynı veride benzetimi çalıştırır ve farkı
bot bot yazar (bkz. karabasan/eslestirme.py). Yalnız okur.

Kapsayıcı içinde çalıştırılır:

    docker compose run --rm --entrypoint python3 arac /freqtrade/araclar/islem_eslestir.py 20260911
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "araclar"))

from karabasan import gostergeler as g  # noqa: E402
from karabasan.benzetim import benzet  # noqa: E402
from karabasan.botlar import BOTLAR, ayarlari_yukle  # noqa: E402
from karabasan.eslestirme import (  # noqa: E402
    benzetim_islemleri, motor_islemleri, motor_sonuclari_oku, rapor_satirlari,
)
from karabasan.kural import ek_veri_topla, kural_yukle  # noqa: E402
from karsilastir import COINLER, mumlari_oku  # noqa: E402

SONUCLAR = KOK / "user_data" / "backtest_results"


def main() -> int:
    if len(sys.argv) < 2:
        print("Kullanım: islem_eslestir.py BASLANGIC (YYYYAAGG, motorun timerange başı)")
        return 2
    baslangic = pd.Timestamp(sys.argv[1], tz="UTC")
    ayar = ayarlari_yukle()
    motor_tum = motor_sonuclari_oku(SONUCLAR)
    print(f"İşlem işlem eşleştirme (motor / bağımsız benzetim), giriş {baslangic:%Y-%m-%d} ve sonrası")
    print("Vadeli botlarda BTC düşülür (motor orada en küçük emir tutarı yüzünden işlem açmıyor).")
    print("Uçlar düşülür: motorun dönem sonunda zorla kapattığı işlemler ve son 'süre aşımı' kadar")
    print("içinde açılanlar.")
    eksik = 0
    for bot, sinif, kural_kodu, piyasa in BOTLAR:
        print("")
        if sinif not in motor_tum:
            print(f"{bot}: motorun işlem listesi bulunamadı ({SONUCLAR}).")
            eksik += 1
            continue
        kural = kural_yukle(kural_kodu)
        komisyon = float(ayar["komisyon_yuzde"][piyasa])
        mum = pd.Timedelta(minutes=g.dilim_dakika(kural["zaman_dilimi"]))
        # Süre sınırı yoksa uçta bir günlük pay bırakılır (açık kalan işlemler iki tarafta da düşer).
        dakika = kural["cikis"].get("sure_asimi_dakika")
        sure = pd.Timedelta(minutes=int(dakika)) if dakika is not None else pd.Timedelta(days=1)
        coinler = [c for c in COINLER if not (piyasa == "vadeli" and c == "BTC")]
        benz = []
        son = None
        for coin in coinler:
            df = mumlari_oku(coin, kural["zaman_dilimi"], piyasa)
            if df is None:
                continue
            ek_veri, bulunamayan = ek_veri_topla(kural, lambda dilim: mumlari_oku(coin, dilim, piyasa))
            if bulunamayan:
                print(f"{bot}: {coin} için {', '.join(bulunamayan)} verisi bulunamadı; "
                      "benzetim o dilimi 5 dakikalık mumlardan topladı, fark bundan olabilir.")
            bitis = pd.Timestamp(df["date"].max())
            bitis = bitis.tz_localize("UTC") if bitis.tzinfo is None else bitis
            son = bitis if son is None else min(son, bitis)
            benz += benzetim_islemleri(
                benzet(df, kural, komisyon_yuzde=komisyon, ek_veri=ek_veri), coin, mum)
        if son is None:
            print(f"{bot}: veri dosyası bulunamadı.")
            eksik += 1
            continue
        sinir = son - sure - mum
        motor = [t for t in motor_islemleri(motor_tum[sinif])
                 if t["coin"] in coinler and t["neden"] != "zorla_kapatma"]

        def pencerede(t):
            return baslangic <= t["giris"] <= sinir

        for satir in rapor_satirlari(bot, [t for t in motor if pencerede(t)],
                                     [t for t in benz if pencerede(t)]):
            print(satir)
    return 1 if eksik else 0


if __name__ == "__main__":
    sys.exit(main())
