"""Vadeli işlemlerin fonlama oranı geçmişi: indirme ve okuma.

Fonlama, vadeli fiyatı spot fiyata bağlamak için alım ve açığa satış tarafları
arasında düzenli aralıklarla (çoğunlukla 8 saatte bir) ödenen ücrettir. Oran
artıysa alım tarafı öder, açığa satış tarafı alır. Panel sınaması bunu iki yerde
kullanır: bir gösterge olarak (kalabalık hangi yönde) ve işlemin maliyeti olarak
(açık tutulan her ödeme anında).

Veri Binance'in herkese açık, anahtarsız adresinden gelir:
    GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=ETHUSDT&startTime=...&limit=1000
Yanıt: [{"symbol", "fundingTime" (ms), "fundingRate" (oran, metin), "markPrice"}, ...]

İndirme yalnız standart kütüphaneyle çalışır (sunucunun kendi Python'unda pandas yok);
okuma pandas ister (geçmiş testi kapsayıcısında).

    python3 -m karabasan.fonlama user_data/data/fonlama 1500 ETH SOL ...
"""

from __future__ import annotations

import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

ADRES = "https://fapi.binance.com/fapi/v1/fundingRate"
SAYFA = 1000
GUN_MS = 86_400_000
BASLIK = ("zaman_ms", "oran")


def dosya_yolu(klasor: Path, coin: str) -> Path:
    return Path(klasor) / f"{coin}.csv"


def _son_zaman(yol: Path) -> int | None:
    if not yol.exists():
        return None
    son = None
    with yol.open(encoding="utf-8") as f:
        for satir in csv.DictReader(f):
            son = int(satir["zaman_ms"])
    return son


def _getir_varsayilan(adres: str) -> list:
    istek = urllib.request.Request(adres, headers={"User-Agent": "karabasan-bot"})
    with urllib.request.urlopen(istek, timeout=30) as yanit:
        return json.loads(yanit.read().decode("utf-8"))


def indir(coin: str, klasor, gun: int, simdi_ms: int | None = None, getir=None, bekle: float = 0.3) -> int:
    """Bir coinin fonlama geçmişini CSV dosyasına indirir; yeni satır sayısını döndürür.

    Dosya varsa yalnız son kayıttan sonrası istenir (yeniden çalıştırılabilir).
    Dosya yoksa 'gun' gün geriden başlar. Hata olursa o ana kadar inenler kalır.
    """
    getir = getir or _getir_varsayilan
    simdi_ms = simdi_ms if simdi_ms is not None else int(time.time() * 1000)
    yol = dosya_yolu(klasor, coin)
    yol.parent.mkdir(parents=True, exist_ok=True)
    son = _son_zaman(yol)
    baslangic = son + 1 if son is not None else simdi_ms - int(gun) * GUN_MS
    yeni = 0
    yeni_dosya = not yol.exists()
    with yol.open("a", encoding="utf-8", newline="") as f:
        yazar = csv.writer(f)
        if yeni_dosya:
            yazar.writerow(BASLIK)
        while baslangic < simdi_ms:
            adres = f"{ADRES}?symbol={coin}USDT&startTime={baslangic}&limit={SAYFA}"
            kayitlar = getir(adres)
            if not isinstance(kayitlar, list) or not kayitlar:
                break
            en_son = baslangic - 1
            for k in sorted(kayitlar, key=lambda k: int(k["fundingTime"])):
                zaman = int(k["fundingTime"])
                if zaman < baslangic:
                    continue
                yazar.writerow((zaman, k["fundingRate"]))
                yeni += 1
                en_son = zaman
            if len(kayitlar) < SAYFA or en_son < baslangic:
                break
            baslangic = en_son + 1
            if bekle:
                time.sleep(bekle)
    return yeni


def oku(coin: str, klasor):
    """Fonlama geçmişi tablosu: 'date' (UTC) ve 'oran_yuzde'. Dosya yoksa None."""
    import pandas as pd

    yol = dosya_yolu(klasor, coin)
    if not yol.exists():
        return None
    tablo = pd.read_csv(yol)
    if tablo.empty:
        return None
    sonuc = pd.DataFrame({
        "date": pd.to_datetime(tablo["zaman_ms"].astype("int64"), unit="ms", utc=True),
        "oran_yuzde": tablo["oran"].astype(float) * 100.0,
    })
    return sonuc.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Kullanım: python3 -m karabasan.fonlama KLASÖR GÜN COIN...")
        return 2
    klasor, gun, coinler = Path(argv[0]), int(argv[1]), argv[2:]
    hata = 0
    for coin in coinler:
        try:
            print(f"{coin}: {indir(coin, klasor, gun)} yeni fonlama kaydı")
        except Exception as e:  # ağ hatası: o coin eksik kalır, öbürleri sürer
            print(f"{coin}: indirilemedi ({e})")
            hata += 1
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
