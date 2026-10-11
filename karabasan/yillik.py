"""12 aylık geçmiş testi: her bot son bir yılın gerçek mumlarında ne yapardı?

30 günlük ölçümler tek bir dönemdir; bir strateji o ay şans eseri iyi ya da
kötü görünebilir. Burada aynı kurallar son 365 günde, bağımsız benzetimle
(karabasan.benzetim) çalıştırılır ve sonuç dört çeyreğe bölünür. Bir strateji
dört çeyreğin çoğunda artıda değilse, tek bir iyi ayı şanstan ayırmak zordur.

Sonuçlar:
- Düz metin rapor (araclar/yillik_test.py onu user_data/logs/yillik_test.txt'e yazar).
- Bot başına işlem başına net sonuç (karne'nin 'net_beklenti'si, yüzde):
  user_data/gecmis_test.json. Sınavın 7. ölçütü ("12 aylık geçmiş testiyle aynı
  yönde") bunu okur.

Bilerek yapılmayanlar:
- Karabasan süzgeci uygulanmaz (canlıda henüz ölçülmüyor); botların bugünkü hali
  gibi her durumda işlem açılır.
- "Bilgi için" bölümündeki başka çıkış ayarı, bir ayar önerisi değildir. Bir yıla
  bakıp en iyisini seçmek geçmişe ezberdir; seçilen ayar yeni bir sanal botla
  kendi 30 gününü verir (3. kural).
"""

from __future__ import annotations

from typing import Callable

import pandas as pd

from . import karne as kr
from .benzetim import benzet
from .botlar import BOTLAR, ayarlari_yukle
from .kural import basabas_orani, cikis_metni, ek_veri_topla, kural_yukle

COINLER = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
GUN = 365
CEYREK_SAYISI = 4
# Bilgi için: aynı sinyaller, stop hedefle aynı genişlikte olsaydı.
KARSILASTIRMA_STOPU = "hedef"

Yukleyici = Callable[[str, str, str], "pd.DataFrame | None"]


def coinler(piyasa: str) -> list[str]:
    """Vadelide BTC yok: 50 USDT'lik işlem tutarıyla hazır motor BTC vadeli açmıyor."""
    return COINLER[1:] if piyasa == "vadeli" else list(COINLER)


def _zaman(deger) -> pd.Timestamp:
    z = pd.Timestamp(deger)
    return z.tz_localize("UTC") if z.tzinfo is None else z.tz_convert("UTC")


def stop_hedefe_esit(kural: dict) -> dict:
    """Kuralın, stopu kâr hedefiyle aynı olan kopyası. Başka hiçbir şey değişmez."""
    kopya = {**kural, "cikis": dict(kural["cikis"])}
    kopya["cikis"]["zarar_durdur_yuzde"] = float(kural["cikis"]["kar_hedefi_yuzde"])
    return kopya


def islemleri_topla(kural: dict, piyasa: str, yukle: Yukleyici, komisyon: float,
                    baslangic: pd.Timestamp, bitis: pd.Timestamp) -> tuple[list[dict], list[str]]:
    """Kuralı her coinde çalıştırır; girişi [baslangic, bitis) içinde olan işlemleri döndürür.

    Dönen ikili: (işlemler, eksik veri notları).
    """
    islemler: list[dict] = []
    eksikler: list[str] = []
    for coin in coinler(piyasa):
        df = yukle(coin, kural["zaman_dilimi"], piyasa)
        if df is None or df.empty:
            eksikler.append(f"{coin} {kural['zaman_dilimi']}")
            continue
        ek_veri, bulunamayan = ek_veri_topla(kural, lambda dilim, c=coin: yukle(c, dilim, piyasa))
        eksikler += [f"{coin} {d}" for d in bulunamayan]
        for i in benzet(df, kural, komisyon_yuzde=komisyon, ek_veri=ek_veri):
            if baslangic <= _zaman(i["giris_zamani"]) < bitis:
                islemler.append({**i, "coin": coin})
    return islemler, eksikler


def ceyreklere_bol(islemler: list[dict], baslangic: pd.Timestamp, bitis: pd.Timestamp,
                   tutar: float) -> list[dict]:
    """Dönemi eşit dört parçaya böler; her parçada işlem sayısı ve net USDT."""
    uzunluk = (bitis - baslangic) / CEYREK_SAYISI
    sonuc = []
    for k in range(CEYREK_SAYISI):
        bas, son = baslangic + uzunluk * k, baslangic + uzunluk * (k + 1)
        parca = [i for i in islemler if bas <= _zaman(i["giris_zamani"]) < son]
        net = sum(float(i["net_yuzde"]) for i in parca) * tutar / 100.0
        sonuc.append({"baslangic": bas, "bitis": son, "islem": len(parca), "net": net})
    return sonuc


def _sayi(deger, basamak=2, isaret=False) -> str:
    if deger is None:
        return "-"
    if deger == float("inf"):
        return "sonsuz"
    bicim = f"{{:{'+' if isaret else ''}.{basamak}f}}"
    return bicim.format(deger).replace(".", ",")


def _nedenler(islemler: list[dict]) -> dict[str, int]:
    sayac = {"kar_hedefi": 0, "zarar_durdur": 0, "sure_asimi": 0, "cikis_sinyali": 0, "iz_suren_stop": 0}
    for i in islemler:
        sayac[i["neden"]] = sayac.get(i["neden"], 0) + 1
    return sayac


def _nedenler_metni(nedenler: dict[str, int], cikis: dict) -> str:
    """Kuralın kullandığı çıkış yollarını sayılarıyla yazar."""
    parcalar = []
    if cikis.get("kar_hedefi_yuzde") is not None:
        parcalar.append(f"hedef {nedenler['kar_hedefi']}")
    if cikis.get("iz_suren_stop"):
        parcalar.append(f"iz süren stop {nedenler['iz_suren_stop']}")
    parcalar.append(f"stop {nedenler['zarar_durdur']}")
    if cikis.get("sure_asimi_dakika") is not None:
        parcalar.append(f"süre aşımı {nedenler['sure_asimi']}")
    if "sinyal" in cikis:
        parcalar.append(f"kanal sinyali {nedenler['cikis_sinyali']}")
    return ", ".join(parcalar)


def veri_donemi(yukle: Yukleyici, gun: int) -> tuple[pd.Timestamp, pd.Timestamp, list[str]]:
    """Ölçülecek dönem: elde olan en yeni ortak mumdan geriye 'gun' gün.

    Dönen üçlü: (başlangıç, bitiş, uyarılar). Veri 'gun' günü kapsamıyorsa uyarı yazılır.
    """
    bitisler, baslar = [], []
    for coin in COINLER[1:]:
        df = yukle(coin, "5m", "vadeli")
        if df is None or df.empty:
            continue
        bitisler.append(_zaman(df["date"].max()))
        baslar.append(_zaman(df["date"].min()))
    if not bitisler:
        raise RuntimeError("Vadeli 5 dakikalık veri bulunamadı.")
    bitis = min(bitisler)
    baslangic = bitis - pd.Timedelta(days=gun)
    uyarilar = []
    # Göstergelerin ısınması için başlangıçtan önce birkaç gün veri gerekir.
    en_gec_bas = max(baslar)
    if en_gec_bas > baslangic - pd.Timedelta(days=7):
        kapsanan = (bitis - en_gec_bas).days
        uyarilar.append(f"UYARI: veri {gun} günü tam kapsamıyor (en kısası {kapsanan} gün); "
                        "ilk günlerdeki işlemler eksik olabilir.")
    return baslangic, bitis, uyarilar


def rapor_uret(yukle: Yukleyici, gun: int = GUN, ayar: dict | None = None) -> tuple[str, dict, int]:
    """Raporu üretir. Dönen üçlü: (metin, gecmis_test.json içeriği, eksik veri sayısı)."""
    ayar = ayar or ayarlari_yukle()
    tutar, bakiye = float(ayar["islem_tutari"]), float(ayar["sanal_bakiye"])
    baslangic, bitis, uyarilar = veri_donemi(yukle, gun)

    satirlar: list[str] = []
    yaz = satirlar.append
    yaz(f"12 aylık geçmiş testi: {baslangic:%d.%m.%Y} - {bitis:%d.%m.%Y} ({gun} gün)")
    yaz(f"Hazırlandı: {pd.Timestamp.now(tz='UTC'):%d.%m.%Y %H:%M} UTC. Ayarlar o anki kural dosyalarından.")
    yaz("Coinler: ETH, SOL, XRP, DOGE (vadelide BTC yok). İşlem başına "
        f"{tutar:g} USDT, 1 kat kaldıraç, komisyon dahil.")
    yaz("Hesap: bağımsız benzetim. 11 Ekim 2026'da hazır motorla işlem işlem karşılaştırıldı;")
    yaz("12 botun 11'inde birebir ya da ±2 işlem tuttu. Karabasan süzgeci yok (canlıda da henüz yok).")
    yaz("Geçmiş, geleceğin garantisi değildir. Bu rapora bakıp ayar seçmek geçmişe ezberdir.")
    for u in uyarilar:
        yaz(u)
    yaz("")

    # Bilgi alanı sözlüktür: sonuc._gecmis_test_oku yalnız sayıları bot sonucu sayar.
    sonuc_json: dict = {"_bilgi": {"donem": f"{baslangic:%Y-%m-%d} / {bitis:%Y-%m-%d}", "gun": gun,
                                   "birim": "işlem başına net sonuç, yüzde"}}
    ozet: list[dict] = []
    eksik = 0
    karsilastirma: list[tuple[str, dict, dict]] = []

    for bot, _sinif, kod, piyasa in BOTLAR:
        kural = kural_yukle(kod)
        komisyon = float(ayar["komisyon_yuzde"][piyasa])
        islemler, eksikler = islemleri_topla(kural, piyasa, yukle, komisyon, baslangic, bitis)
        eksik += len(eksikler)
        k = kr.karne(islemler, tutar, bakiye)
        ceyrekler = ceyreklere_bol(islemler, baslangic, bitis, tutar)
        nedenler = _nedenler(islemler)
        c = kural["cikis"]
        # Kazancın boyu sabit değilse (kanal sinyali, iz süren stop) başa baş oranı tanımsız.
        basabas = None if "sinyal" in c else basabas_orani(kural, 2 * komisyon)
        yaz(f"{bot}: {kod} {kural['ad']}")
        sinyalle_cikar = "sinyal" in c
        if kural.get("defter_onayi"):
            yaz("  NOT: girişteki emir defteri onayı geçmişte uygulanamaz; işlem sayısı canlıdakinden fazladır.")
        yaz(f"  {cikis_metni(c)}" + ("; çıkış kanal sinyaliyle" if sinyalle_cikar else ""))
        if eksikler:
            yaz(f"  UYARI: veri yok: {', '.join(eksikler)}")
        if k["islem_sayisi"] == 0:
            yaz("  Bu dönemde hiç işlem yok.")
            yaz("")
            ozet.append({"bot": bot, "kod": kod, "islem": 0, "net": 0.0, "arti_ceyrek": 0,
                         "kazanma": None, "basabas": basabas})
            continue
        yaz(f"  İşlem {k['islem_sayisi']}, kazanma %{_sayi(k['kazanma_orani'], 1)} "
            f"(başa baş %{_sayi(basabas, 1)}), işlem başına net %{_sayi(k['net_beklenti'], 3, True)}, "
            f"kâr faktörü {_sayi(k['kar_faktoru'])}")
        yaz(f"  Net {_sayi(k['net_tutar'], 2, True)} USDT, en büyük düşüş %{_sayi(k['en_buyuk_dusus_yuzde'], 1)} "
            f"(1.000 USDT bakiyeye göre)")
        yaz("  Çıkışlar: " + _nedenler_metni(nedenler, c))
        yaz("  Çeyrekler (net USDT): " + " | ".join(
            f"{p['baslangic']:%m.%Y}: {_sayi(p['net'], 2, True)} ({p['islem']})" for p in ceyrekler))
        arti = sum(1 for p in ceyrekler if p["net"] > 0)
        yaz(f"  Artıda biten çeyrek: {arti} / {CEYREK_SAYISI}")
        yaz("")
        sonuc_json[bot] = round(float(k["net_beklenti"]), 4)
        ozet.append({"bot": bot, "kod": kod, "islem": k["islem_sayisi"], "net": k["net_tutar"],
                     "arti_ceyrek": arti, "kazanma": k["kazanma_orani"], "basabas": basabas})

        if sinyalle_cikar or c.get("kar_hedefi_yuzde") is None:
            continue   # sabit hedef yoksa (kanal sinyali, iz süren stop) "stop = hedef" anlamsızdır
        alt_kural = stop_hedefe_esit(kural)
        alt_islemler, _ = islemleri_topla(alt_kural, piyasa, yukle, komisyon, baslangic, bitis)
        karsilastirma.append((bot, k, kr.karne(alt_islemler, tutar, bakiye)))

    yaz("ÖZET")
    artida = [o for o in ozet if o["net"] > 0]
    istikrarli = [o for o in ozet if o["net"] > 0 and o["arti_ceyrek"] >= 3]
    yaz(f"  Yıl sonunda artıda: {len(artida)} / {len(ozet)} bot"
        + (f" ({', '.join(o['kod'] for o in artida)})" if artida else ""))
    yaz(f"  Hem artıda hem dört çeyreğin en az üçünde artı: {len(istikrarli)} bot"
        + (f" ({', '.join(o['kod'] for o in istikrarli)})" if istikrarli else ""))
    toplam = sum(o["net"] for o in ozet)
    yaz(f"  {len(ozet)} botun toplamı: {_sayi(toplam, 2, True)} USDT "
        f"(her bot {_sayi(bakiye, 0)} USDT sanal bakiyeyle)")
    sirali = sorted(ozet, key=lambda o: o["net"], reverse=True)
    yaz("  Sıralama (net USDT): " + ", ".join(f"{o['kod']} {_sayi(o['net'], 2, True)}" for o in sirali))
    yaz("")

    yaz("BİLGİ İÇİN (ayar önerisi değildir): aynı sinyaller, stop hedefle aynı genişlikte olsaydı")
    yaz("  Bot          Şimdiki ayar: işlem / kazanma / net USDT     Stop = hedef: işlem / kazanma / net USDT")
    for bot, simdi, alt in karsilastirma:
        yaz(f"  {bot:<12} {simdi['islem_sayisi']:>5} / %{_sayi(simdi['kazanma_orani'], 1):>5} / "
            f"{_sayi(simdi['net_tutar'], 2, True):>8}"
            f"{'':>17}{alt['islem_sayisi']:>5} / %{_sayi(alt['kazanma_orani'], 1):>5} / "
            f"{_sayi(alt['net_tutar'], 2, True):>8}")
    yaz("  Bir yıla bakıp daha iyi görüneni seçmek geçmişe ezberdir. Denenecekse ayrı bir sanal botla,")
    yaz("  kendi 30 gününde denenir.")
    return "\n".join(satirlar) + "\n", sonuc_json, eksik
