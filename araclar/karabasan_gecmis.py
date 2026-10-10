#!/usr/bin/env python3
"""Karabasan geçmiş ölçümü: stratejiler yalnız izinli durumda çalışsaydı ne olurdu?

Sunucudaki geçmiş mum verisinde iki iş yapar:

1. Karabasan puanını ve durumunu geçmişe dönük hesaplar (karabasan.gecmis_olcum).
2. Bağımsız benzetimin her işlemini, açıldığı andaki Karabasan durumuyla
   etiketler ve sonucu duruma göre ayırır.

Kapsayıcı içinde çalıştırılır:

    docker compose run --rm --entrypoint python3 arac /freqtrade/araclar/karabasan_gecmis.py 30

Çıktı düz metindir; araclar/analiz.sh onu user_data/logs/karabasan_gecmis.txt
dosyasına yazar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from karabasan import gecmis_olcum as go  # noqa: E402
from karabasan.benzetim import benzet  # noqa: E402
from karabasan.botlar import ayarlari_yukle  # noqa: E402
from karabasan.kural import kural_yukle  # noqa: E402
from karabasan.puan import DURUM_ADI  # noqa: E402

COINLER = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
VERI = KOK / "user_data" / "data" / "binance"

# (görünen ad, kural kodu, piyasa, coinler). Alım yönlü vadeli botlar spot ile
# neredeyse aynı sonucu verdiği için yinelenmez. Vadelide BTC yok: 50 USDT'lik
# işlem tutarıyla hazır motor BTC vadeli açmıyor.
SATIRLAR = [
    ("S1 spot", "S1", "spot", COINLER),
    ("S2 spot", "S2", "spot", COINLER),
    ("S3 spot", "S3", "spot", COINLER),
    ("S4 spot", "S4", "spot", COINLER),
    ("S1K vadeli", "S1K", "vadeli", COINLER[1:]),
    ("S2K vadeli", "S2K", "vadeli", COINLER[1:]),
]
DURUMLAR = ("YESIL", "SARI", "KIRMIZI", "SIYAH")


def dosyadan_yukle(coin: str, dilim: str, piyasa: str) -> pd.DataFrame | None:
    if piyasa == "vadeli":
        yol = VERI / "futures" / f"{coin}_USDT_USDT-{dilim}-futures.feather"
    else:
        yol = VERI / f"{coin}_USDT-{dilim}.feather"
    if not yol.exists():
        return None
    return pd.read_feather(yol)[["date", "open", "high", "low", "close", "volume"]]


def _sayi(deger, basamak=2, isaret=False) -> str:
    if deger is None:
        return "-"
    bicim = f"{{:{'+' if isaret else ''}.{basamak}f}}"
    return bicim.format(deger).replace(".", ",")


def _karne_satiri(etiket: str, k: dict) -> str:
    if k["islem_sayisi"] == 0:
        return f"  {etiket:<22} {0:>6} {'-':>9} {'-':>11} {'-':>9} {_sayi(0.0, 2, True):>10}"
    faktor = k["kar_faktoru"]
    faktor_metni = "sonsuz" if faktor == float("inf") else _sayi(faktor)
    return (
        f"  {etiket:<22} {k['islem_sayisi']:>6} {_sayi(k['kazanma_orani'], 1):>9} "
        f"{_sayi(k['net_beklenti'], 3, True):>11} {faktor_metni:>9} {_sayi(k['net_tutar'], 2, True):>10}"
    )


def rapor_uret(yukle=dosyadan_yukle, gun: int = 30, ayar: dict | None = None) -> tuple[str, int]:
    """Raporu metin olarak üretir. Dönen ikili: (metin, eksik veri dosyası sayısı)."""
    ayar = ayar or ayarlari_yukle()
    tutar, bakiye = float(ayar["islem_tutari"]), float(ayar["sanal_bakiye"])
    satirlar: list[str] = []
    yaz = satirlar.append

    spot5 = {c: yukle(c, "5m", "spot") for c in COINLER}
    eksik = sum(1 for df in spot5.values() if df is None)
    spot5 = {c: df for c, df in spot5.items() if df is not None}
    if "BTC" not in spot5:
        return "BTC verisi bulunamadı; ölçüm yapılamadı.", eksik + 1

    gecmis = go.karabasan_gecmisi(spot5)
    if gecmis.empty:
        return ("Karabasan puanı hesaplanamadı: yeterli geçmiş yok "
                "(en az 65 günlük 5 dakikalık veri gerekir)."), eksik + 1
    son = gecmis["zaman"].iloc[-1]
    baslangic = max(son - pd.Timedelta(days=gun), gecmis["zaman"].iloc[0])
    pencere = gecmis[gecmis["zaman"] >= baslangic]
    gercek_gun = (son - baslangic) / pd.Timedelta(days=1)

    yaz(f"Karabasan geçmiş ölçümü: {baslangic:%Y-%m-%d %H:%M} - {son:%Y-%m-%d %H:%M} UTC "
        f"({_sayi(gercek_gun, 1)} gün)")
    yaz(f"Coinler: {', '.join(spot5)}. Komisyon dahil, işlem başına {tutar:.0f} USDT.")
    yaz("")
    yaz("OKURKEN BİLİNMESİ GEREKENLER")
    yaz("- Bu, canlı Karabasan'ın yaklaşık bir kopyasıdır. BTC dominansı ve TOTAL2'nin geçmişi")
    yaz("  olmadığı için altcoin akışı eldeki dört altcoinin BTC'ye göre getirisinden tahmin edilir;")
    yaz("  piyasa genişliği yalnız bu beş coinden ölçülür; makro bileşeni yoktur.")
    yaz("- Ağırlıklar ve eşikler tasarım raporundaki başlangıç değerleridir; bu veriye göre")
    yaz("  ayarlanmamıştır ve ayarlanmamalıdır.")
    yaz("- Tek bir 30 günlük dönemdir. Durum başına işlem sayısı azsa sonuç şans olabilir.")
    yaz("")

    dagilim = go.sure_dagilimi(pencere)
    yaz("Zamanın durumlara dağılımı: " + ", ".join(
        f"{DURUM_ADI[d]} %{_sayi(dagilim.get(d, 0.0), 1)}" for d in DURUMLAR))
    puanlar = pencere["puan"].dropna()
    if len(puanlar):
        yaz(f"Puan: ortalama {_sayi(puanlar.mean(), 1)}, en düşük {_sayi(puanlar.min(), 1)}, "
            f"en yüksek {_sayi(puanlar.max(), 1)}")
    degisim = int((pencere["durum"] != pencere["durum"].shift()).sum()) - 1
    yaz(f"Durum değişikliği sayısı: {max(degisim, 0)}")
    yaz("")

    baslik = f"  {'':<22} {'İşlem':>6} {'Kazanma %':>9} {'Net bek. %':>11} {'Kâr fakt.':>9} {'Net USDT':>10}"
    ozet = []
    for ad, kod, piyasa, coinler in SATIRLAR:
        kural = kural_yukle(kod)
        komisyon = float(ayar["komisyon_yuzde"][piyasa])
        tum = []
        for coin in coinler:
            df = yukle(coin, kural["zaman_dilimi"], piyasa)
            if df is None:
                eksik += 1
                continue
            islemler = [i for i in benzet(df, kural, komisyon_yuzde=komisyon)
                        if i["giris_zamani"] >= baslangic]
            tum += go.islemleri_etiketle(islemler, gecmis)
        karneler = go.duruma_gore_karne(tum, tutar, bakiye)
        izinli_durumlar = list(kural.get("izinli_durumlar", []))
        izinli = go.izinli_karne(tum, izinli_durumlar, tutar, bakiye)
        izinli_adi = " ve ".join(DURUM_ADI[d] for d in izinli_durumlar)
        yaz(f"{ad}: {kural['ad']} (coinler: {', '.join(coinler)})")
        yaz(baslik)
        for durum in DURUMLAR:
            isaret = " *" if durum in izinli_durumlar else ""
            yaz(_karne_satiri(DURUM_ADI[durum] + isaret, karneler[durum]))
        yaz(_karne_satiri("Hepsi (süzgeçsiz)", karneler["HEPSI"]))
        yaz(_karne_satiri(f"Yalnız izinli ({izinli_adi})", izinli))
        yaz("")
        ozet.append((ad, izinli_adi, karneler["HEPSI"], izinli))

    yaz("ÖZET: süzgeçsiz ile tasarımdaki gibi (yalnız izinli durumlarda) karşılaştırma")
    yaz(f"  {'':<12} {'Süzgeçsiz':>22}   {'Yalnız izinli durumlarda':>30}")
    yaz(f"  {'':<12} {'işlem':>6} {'net USDT':>10} {'net bek.':>9}   {'işlem':>6} {'net USDT':>10} {'net bek.':>9}  izinli")
    for ad, izinli_adi, hepsi, izinli in ozet:
        yaz(f"  {ad:<12} {hepsi['islem_sayisi']:>6} {_sayi(hepsi['net_tutar'], 2, True):>10} "
            f"{_sayi(hepsi['net_beklenti'], 3, True):>9}   {izinli['islem_sayisi']:>6} "
            f"{_sayi(izinli['net_tutar'], 2, True):>10} {_sayi(izinli['net_beklenti'], 3, True):>9}  {izinli_adi}")
    yaz("")
    yaz("* işareti, stratejinin tasarımda izinli olduğu durumu gösterir.")
    yaz("\"Yalnız izinli\" satırı bir yaklaşıktır: gerçekte bir işlem atlanınca sonraki işlemlerin")
    yaz("sırası da değişebilir.")
    if eksik:
        yaz(f"UYARI: {eksik} veri dosyası bulunamadı ({VERI}).")
    return "\n".join(satirlar), eksik


def main() -> int:
    gun = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    metin, eksik = rapor_uret(gun=gun)
    print(metin)
    return 1 if eksik else 0


if __name__ == "__main__":
    raise SystemExit(main())
