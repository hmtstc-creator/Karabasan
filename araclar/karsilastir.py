#!/usr/bin/env python3
"""Bağımsız karşılaştırma: indirilen geçmiş veride kendi benzetimimizi çalıştırır.

Hazır motorun geçmiş testi ile aynı veride, aynı kurallarla, ayrı yazılmış
bir hesap yapar. İki sonuç birbirine yakın çıkmalıdır; çıkmıyorsa bağlantı
katmanında bir hata vardır.

Kapsayıcı içinde çalıştırılır:

    docker compose run --rm --entrypoint python3 arac /freqtrade/araclar/karsilastir.py 30
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from karabasan.benzetim import benzet  # noqa: E402
from karabasan.botlar import BOTLAR, ayarlari_yukle  # noqa: E402
from karabasan.karne import karne  # noqa: E402
from karabasan.kural import kural_yukle  # noqa: E402

COINLER = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
VERI = KOK / "user_data" / "data" / "binance"


def veri_dosyasi(coin: str, dilim: str, piyasa: str) -> Path | None:
    if piyasa == "vadeli":
        adaylar = [VERI / "futures" / f"{coin}_USDT_USDT-{dilim}-futures.feather"]
    else:
        adaylar = [VERI / f"{coin}_USDT-{dilim}.feather"]
    return next((a for a in adaylar if a.exists()), None)


def main() -> int:
    gun = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    ayar = ayarlari_yukle()
    print(f"Bağımsız benzetim, son {gun} gün, pariteler: {', '.join(COINLER)}")
    print(f"{'Bot':<12} {'İşlem':>6} {'Kazanma %':>10} {'Net bek. %':>11} {'Kâr fakt.':>10} {'Net USDT':>9}")
    eksik = 0
    for bot, _sinif, kural_kodu, piyasa in BOTLAR:
        kural = kural_yukle(kural_kodu)
        komisyon = float(ayar["komisyon_yuzde"][piyasa])
        tum = []
        coin_basina = []
        for coin in COINLER:
            dosya = veri_dosyasi(coin, kural["zaman_dilimi"], piyasa)
            if dosya is None:
                eksik += 1
                continue
            df = pd.read_feather(dosya)[["date", "open", "high", "low", "close", "volume"]]
            baslangic = df["date"].max() - pd.Timedelta(days=gun)
            islemler = [i for i in benzet(df, kural, komisyon_yuzde=komisyon)
                        if i["giris_zamani"] >= baslangic]
            tum += islemler
            coin_basina.append(f"{coin} {len(islemler)}")
        k = karne(tum, float(ayar["islem_tutari"]), float(ayar["sanal_bakiye"]))
        if k["islem_sayisi"] == 0:
            print(f"{bot:<12} {0:>6} {'-':>10} {'-':>11} {'-':>10} {0.0:>9.2f}")
            continue
        faktor = k["kar_faktoru"]
        faktor_metni = "sonsuz" if faktor == float("inf") else f"{faktor:.2f}"
        print(
            f"{bot:<12} {k['islem_sayisi']:>6} {k['kazanma_orani']:>10.1f} "
            f"{k['net_beklenti']:>11.3f} {faktor_metni:>10} {k['net_tutar']:>9.2f}"
            f"   ({', '.join(coin_basina)})"
        )
    print("Not: bu hesap borsanın en küçük emir tutarını bilmez. Vadelide BTC için en küçük tutar")
    print("işlem tutarımızdan büyükse hazır motor BTC'de işlem açmaz; karşılaştırırken BTC'yi düş.")
    if eksik:
        print(f"UYARI: {eksik} veri dosyası bulunamadı ({VERI}).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
