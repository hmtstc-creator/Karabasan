"""Küresel piyasa kaydedicisi.

BTC dominansı ve TOTAL2'nin geçmiş verisi ücretsiz kaynaklarda bulunmadığı
için, sınavın ilk gününden itibaren bu değerler 10 dakikada bir kaydedilir.
Karabasan'ın "altcoin akışı" bileşeni ve sınav sonundaki etiketleme bu
kayıttan beslenir.

Yalnız Python standart kütüphanesini kullanır. Çalıştırma:

    python3 -m karabasan.kayitci

Çıktı: user_data/kayit/kuresel.csv
"""

from __future__ import annotations

import csv
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ADRES = "https://api.coingecko.com/api/v3/global"
ARALIK_SANIYE = 600
SUTUNLAR = ["zaman", "toplam_deger_usd", "btc_dominans_yuzde", "total2_usd", "hacim_24s_usd"]

gunluk = logging.getLogger("karabasan.kayitci")


def kayit_yolu() -> Path:
    ortam = os.environ.get("KARABASAN_KAYIT")
    if ortam:
        return Path(ortam)
    return Path(__file__).resolve().parent.parent / "user_data" / "kayit" / "kuresel.csv"


def satir_cikar(yanit: dict, simdi: datetime) -> dict:
    """CoinGecko yanıtından kayıt satırını çıkarır.

    TOTAL2 = toplam piyasa değeri x (1 - BTC dominansı)
    """
    veri = yanit["data"]
    toplam = float(veri["total_market_cap"]["usd"])
    dominans = float(veri["market_cap_percentage"]["btc"])
    hacim = float(veri["total_volume"]["usd"])
    if toplam <= 0 or not 0 < dominans < 100:
        raise ValueError(f"Beklenmeyen değer: toplam={toplam}, dominans={dominans}")
    return {
        "zaman": simdi.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "toplam_deger_usd": round(toplam, 2),
        "btc_dominans_yuzde": round(dominans, 4),
        "total2_usd": round(toplam * (1.0 - dominans / 100.0), 2),
        "hacim_24s_usd": round(hacim, 2),
    }


def satir_ekle(yol: Path, satir: dict) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yeni = not yol.exists() or yol.stat().st_size == 0
    with yol.open("a", newline="", encoding="utf-8") as dosya:
        yazici = csv.DictWriter(dosya, fieldnames=SUTUNLAR)
        if yeni:
            yazici.writeheader()
        yazici.writerow(satir)


def veri_cek(adres: str = ADRES, zaman_asimi: int = 20) -> dict:
    istek = urllib.request.Request(adres, headers={"User-Agent": "karabasan-bot", "Accept": "application/json"})
    anahtar = os.environ.get("COINGECKO_ANAHTAR")
    if anahtar:
        istek.add_header("x-cg-demo-api-key", anahtar)
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
        return json.loads(yanit.read().decode("utf-8"))


def bir_kez(yol: Path | None = None) -> dict:
    satir = satir_cikar(veri_cek(), datetime.now(timezone.utc))
    satir_ekle(yol or kayit_yolu(), satir)
    return satir


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    yol = kayit_yolu()
    gunluk.info("Küresel piyasa kaydı başladı: %s (her %s saniyede bir)", yol, ARALIK_SANIYE)
    while True:
        try:
            satir = bir_kez(yol)
            gunluk.info("Dominans %%%.2f, TOTAL2 %.0f milyar USD",
                        satir["btc_dominans_yuzde"], satir["total2_usd"] / 1e9)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as hata:
            # Bir ölçüm kaçarsa sorun değil; döngü sürer.
            gunluk.warning("Ölçüm alınamadı: %s", hata)
        time.sleep(ARALIK_SANIYE)


if __name__ == "__main__":
    main()
