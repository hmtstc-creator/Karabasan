"""Karne: bir işlem listesinin ölçümleri ve 30 günlük sınavın karar ölçütleri.

İşlem listesi hazır motordan da, benzetimden de gelebilir. Her işlemde en az
şu alanlar bulunmalıdır: giris_zamani, cikis_zamani, net_yuzde.
net_yuzde, komisyon düşülmüş sonuçtur (işlem tutarının yüzdesi).
"""

from __future__ import annotations

import math

import pandas as pd

# 30. gün karar ölçütlerinin eşikleri (tasarım raporundaki değerler).
SINAV_ESIKLERI = {
    "en_az_islem": 100,
    "en_az_kar_faktoru": 1.3,
    "en_fazla_dusus_yuzde": 5.0,
    "en_az_pozitif_hafta": 3,
    "basabas_ustu_puan": 5.0,
    "ek_kayma_yuzde": 0.05,
}


def ek_kayma_uygula(islemler: list[dict], ek_kayma_yuzde: float) -> list[dict]:
    """Her işlemin sonucundan ek kayma payını düşer (yeni liste döndürür)."""
    return [{**i, "net_yuzde": i["net_yuzde"] - ek_kayma_yuzde} for i in islemler]


def karne(islemler: list[dict], islem_tutari: float = 50.0, bakiye: float = 1000.0) -> dict:
    """İşlem listesinin ölçümlerini hesaplar.

    Yüzdeler işlem tutarına göredir; 'net_tutar' ve 'en_buyuk_dusus_yuzde'
    sanal bakiyeye göredir.
    """
    n = len(islemler)
    bos = {
        "islem_sayisi": 0,
        "kazanma_orani": None,
        "basabas_orani": None,
        "ort_kazanc": None,
        "ort_kayip": None,
        "net_beklenti": None,
        "kar_faktoru": None,
        "net_tutar": 0.0,
        "net_bakiye_yuzde": 0.0,
        "en_buyuk_dusus_yuzde": 0.0,
        "ort_sure_dakika": None,
    }
    if n == 0:
        return bos

    sirali = sorted(islemler, key=lambda i: i["cikis_zamani"])
    netler = [float(i["net_yuzde"]) for i in sirali]
    kazanclar = [x for x in netler if x > 0]
    kayiplar = [x for x in netler if x <= 0]

    ort_kazanc = sum(kazanclar) / len(kazanclar) if kazanclar else 0.0
    ort_kayip = sum(kayiplar) / len(kayiplar) if kayiplar else 0.0
    toplam_kazanc = sum(kazanclar)
    toplam_kayip = -sum(kayiplar)
    if toplam_kayip > 0:
        kar_faktoru = toplam_kazanc / toplam_kayip
    else:
        kar_faktoru = math.inf if toplam_kazanc > 0 else 0.0

    # Başabaş oranı, gerçekleşen ortalama kazanç ve kayıptan hesaplanır.
    payda = ort_kazanc + abs(ort_kayip)
    basabas = abs(ort_kayip) / payda * 100.0 if payda > 0 else None

    # Sanal bakiye eğrisi ve tepe noktasından en büyük düşüş.
    tutarlar = [x / 100.0 * islem_tutari for x in netler]
    bakiye_egrisi = bakiye
    tepe = bakiye
    en_buyuk_dusus = 0.0
    for t in tutarlar:
        bakiye_egrisi += t
        tepe = max(tepe, bakiye_egrisi)
        en_buyuk_dusus = max(en_buyuk_dusus, (tepe - bakiye_egrisi) / bakiye * 100.0)

    sureler = [float(i["sure_dakika"]) for i in sirali if i.get("sure_dakika") is not None]
    return {
        "islem_sayisi": n,
        "kazanma_orani": len(kazanclar) / n * 100.0,
        "basabas_orani": basabas,
        "ort_kazanc": ort_kazanc,
        "ort_kayip": ort_kayip,
        "net_beklenti": sum(netler) / n,
        "kar_faktoru": kar_faktoru,
        "net_tutar": sum(tutarlar),
        "net_bakiye_yuzde": sum(tutarlar) / bakiye * 100.0,
        "en_buyuk_dusus_yuzde": en_buyuk_dusus,
        "ort_sure_dakika": sum(sureler) / len(sureler) if sureler else None,
    }


def haftalik_net(islemler: list[dict], sinav_baslangici, hafta_sayisi: int = 4) -> list[float]:
    """Sınav başlangıcından itibaren 7 günlük dilimlerin net sonucu (yüzde toplamı).

    30 günlük sınavın son iki günü dördüncü haftaya eklenir.
    """
    baslangic = pd.Timestamp(sinav_baslangici)
    if baslangic.tzinfo is None:
        baslangic = baslangic.tz_localize("UTC")
    toplamlar = [0.0] * hafta_sayisi
    for i in islemler:
        cikis = pd.Timestamp(i["cikis_zamani"])
        if cikis.tzinfo is None:
            cikis = cikis.tz_localize("UTC")
        gun = (cikis - baslangic) / pd.Timedelta(days=1)
        if gun < 0:
            continue
        hafta = min(int(gun // 7), hafta_sayisi - 1)
        toplamlar[hafta] += float(i["net_yuzde"])
    return toplamlar


def duruma_gore(islemler: list[dict], etiket: str = "karabasan_durumu") -> dict:
    """İşlemleri bir etikete göre (örneğin açıldığı andaki Karabasan durumu) ayırıp karneler."""
    gruplar: dict[str, list[dict]] = {}
    for i in islemler:
        gruplar.setdefault(str(i.get(etiket, "BILINMIYOR")), []).append(i)
    return {ad: karne(liste) for ad, liste in gruplar.items()}


def sinav_karari(
    islemler: list[dict],
    sinav_baslangici,
    gecmis_test_net_beklenti: float | None = None,
    islem_tutari: float = 50.0,
    bakiye: float = 1000.0,
    esikler: dict | None = None,
) -> dict:
    """30. gün kararı: yedi ölçütün her birini denetler.

    islemler: komisyonu düşülmüş sanal işlemler. Ek kayma burada uygulanır.
    gecmis_test_net_beklenti: aynı stratejinin 12 aylık geçmiş testindeki
        işlem başına net sonucu; verilmezse 7. ölçüt geçilmemiş sayılır.

    Dönen sözlükte 'gecti' yalnız yedi ölçütün hepsi sağlanırsa True olur.
    """
    e = {**SINAV_ESIKLERI, **(esikler or {})}
    ham = karne(islemler, islem_tutari, bakiye)
    kaymali = ek_kayma_uygula(islemler, e["ek_kayma_yuzde"])
    k = karne(kaymali, islem_tutari, bakiye)
    haftalar = haftalik_net(kaymali, sinav_baslangici)
    pozitif_hafta = sum(1 for h in haftalar if h > 0)

    olcutler = []

    def ekle(ad, gecti, deger, esik):
        olcutler.append({"olcut": ad, "gecti": bool(gecti), "deger": deger, "esik": esik})

    ekle("En az 100 sanal işlem", k["islem_sayisi"] >= e["en_az_islem"],
         k["islem_sayisi"], e["en_az_islem"])
    ekle("Komisyon ve ek kayma dahil net sonuç pozitif",
         k["islem_sayisi"] > 0 and k["net_tutar"] > 0, k["net_tutar"], 0.0)
    ekle("Kâr faktörü en az 1,3",
         k["kar_faktoru"] is not None and k["kar_faktoru"] >= e["en_az_kar_faktoru"],
         k["kar_faktoru"], e["en_az_kar_faktoru"])
    ekle("En büyük düşüş sanal bakiyenin %5'ini aşmamış",
         k["en_buyuk_dusus_yuzde"] <= e["en_fazla_dusus_yuzde"],
         k["en_buyuk_dusus_yuzde"], e["en_fazla_dusus_yuzde"])
    ekle("Dört haftanın en az üçü pozitif",
         pozitif_hafta >= e["en_az_pozitif_hafta"], pozitif_hafta, e["en_az_pozitif_hafta"])
    if k["kazanma_orani"] is not None and k["basabas_orani"] is not None:
        fark = k["kazanma_orani"] - k["basabas_orani"]
        ekle("Kazanma oranı başabaşın en az 5 puan üstünde",
             fark >= e["basabas_ustu_puan"], fark, e["basabas_ustu_puan"])
    else:
        ekle("Kazanma oranı başabaşın en az 5 puan üstünde", False, None, e["basabas_ustu_puan"])
    ekle("12 aylık geçmiş testiyle aynı yönde",
         gecmis_test_net_beklenti is not None and gecmis_test_net_beklenti > 0
         and k["net_beklenti"] is not None and k["net_beklenti"] > 0,
         gecmis_test_net_beklenti, 0.0)

    return {
        "gecti": all(o["gecti"] for o in olcutler),
        "olcutler": olcutler,
        "karne_ham": ham,
        "karne_ek_kaymali": k,
        "haftalik_net": haftalar,
    }
