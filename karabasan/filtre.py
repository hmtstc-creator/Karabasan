"""Filtre (Elek): coinleri dört katmandan geçirir.

    1. Uygunluk   Bu coin hiç alınmalı mı?
    2. Likidite   Girip çıkarken fiyatı bozar mıyım?
    3. Hareket    %1'lik hedefe ulaşacak kadar oynuyor mu?
    4. Güç        Yön lehimize mi?

Her coin için hangi katmandan geçtiği, elendiyse nedeni ve bir sıralama
puanı döner. Sınav sırasında yalnız 1. ve 2. katman eler; 3. ve 4. katmanın
sonucu etiket olarak kaydedilir.

Bu modül veri çekmez. Her coin şu alanları taşıyan bir sözlüktür
(eksik alan, o kontrolün geçilemediği anlamına gelir):

    sembol, isleme_acik, izinli, etiketler (liste: sabit, sarili, kaldiracli, izleme),
    listelenme_gun, hacim_24s, alis, satis, derinlik, atr_yuzde_gunluk,
    degisim_24s_yuzde, ema50_4s_ustunde, goreli_guc, son20_net
"""

from __future__ import annotations

VARSAYILAN_AYAR = {
    # 1. Uygunluk
    "haric_etiketler": ["sabit", "sarili", "kaldiracli", "izleme"],
    "en_az_listelenme_gun": 30,
    "kara_liste": [],
    # 2. Likidite
    "en_az_hacim_24s": 5_000_000.0,
    "en_fazla_fark_yuzde": 0.10,
    "derinlik_kati": 20.0,
    # 3. Hareket
    "atr_alt_yuzde": 3.0,
    "atr_ust_yuzde": 12.0,
    "en_fazla_yukselis_24s_yuzde": 25.0,
    "en_fazla_dusus_24s_yuzde": 15.0,
    # 4. Güç
    "ema50_4s_ustunde_sart": True,
    "goreli_guc_pozitif_sart": True,
    "son20_zararda_dinlenme": True,
}

KATMAN_ADI = {1: "Uygunluk", 2: "Likidite", 3: "Hareket", 4: "Güç"}


def _yuzde(deger: float, basamak: int = 2) -> str:
    return f"%{deger:.{basamak}f}".replace(".", ",")


def _tutar(deger: float) -> str:
    if deger >= 1_000_000:
        return f"{deger / 1_000_000:.1f} milyon".replace(".", ",")
    return f"{deger:,.0f}".replace(",", ".")


def fark_yuzde(alis: float, satis: float) -> float:
    """Alıcı-satıcı farkı, orta fiyatın yüzdesi olarak."""
    orta = (alis + satis) / 2.0
    return (satis - alis) / orta * 100.0 if orta > 0 else float("inf")


def _katman1(c: dict, a: dict) -> str | None:
    if not c.get("isleme_acik", False):
        return "Parite işleme kapalı"
    if not c.get("izinli", False):
        return "Parite hesabına izinli değil"
    if c.get("sembol") in a["kara_liste"]:
        return "Kara listende"
    for etiket in c.get("etiketler", []):
        if etiket in a["haric_etiketler"]:
            ad = {
                "sabit": "Sabit coin",
                "sarili": "Sarılı (wrapped) token",
                "kaldiracli": "Kaldıraçlı token",
                "izleme": "Binance izleme etiketi taşıyor",
            }.get(etiket, etiket)
            return ad
    gun = c.get("listelenme_gun")
    if gun is None or gun < a["en_az_listelenme_gun"]:
        return f"Listelenme yaşı {gun if gun is not None else '?'} gün, sınır {a['en_az_listelenme_gun']}"
    return None


def _katman2(c: dict, a: dict, pozisyon_tutari: float) -> str | None:
    hacim = c.get("hacim_24s")
    if hacim is None or hacim < a["en_az_hacim_24s"]:
        return (
            f"24 saatlik hacim {_tutar(hacim or 0)}, sınır {_tutar(a['en_az_hacim_24s'])}"
        )
    alis, satis = c.get("alis"), c.get("satis")
    if not alis or not satis:
        return "Alış ve satış fiyatı okunamadı"
    fark = fark_yuzde(alis, satis)
    if fark > a["en_fazla_fark_yuzde"]:
        return f"Alıcı-satıcı farkı {_yuzde(fark)}, sınır {_yuzde(a['en_fazla_fark_yuzde'])}"
    derinlik = c.get("derinlik")
    gereken = pozisyon_tutari * a["derinlik_kati"]
    if derinlik is None or derinlik < gereken:
        return f"Emir derinliği {_tutar(derinlik or 0)}, gereken {_tutar(gereken)}"
    return None


def _katman3(c: dict, a: dict) -> str | None:
    oynaklik = c.get("atr_yuzde_gunluk")
    if oynaklik is None:
        return "Oynaklık hesaplanamadı"
    if oynaklik < a["atr_alt_yuzde"]:
        return f"Günlük oynaklık {_yuzde(oynaklik, 1)}, alt sınır {_yuzde(a['atr_alt_yuzde'], 1)}"
    if oynaklik > a["atr_ust_yuzde"]:
        return f"Günlük oynaklık {_yuzde(oynaklik, 1)}, üst sınır {_yuzde(a['atr_ust_yuzde'], 1)}"
    degisim = c.get("degisim_24s_yuzde")
    if degisim is None:
        return "24 saatlik değişim okunamadı"
    if degisim > a["en_fazla_yukselis_24s_yuzde"]:
        return f"Son 24 saatte {_yuzde(degisim, 1)} yükselmiş, sınır {_yuzde(a['en_fazla_yukselis_24s_yuzde'], 0)}"
    if degisim < -a["en_fazla_dusus_24s_yuzde"]:
        return f"Son 24 saatte {_yuzde(abs(degisim), 1)} düşmüş, sınır {_yuzde(a['en_fazla_dusus_24s_yuzde'], 0)}"
    return None


def _katman4(c: dict, a: dict) -> str | None:
    if a["ema50_4s_ustunde_sart"] and not c.get("ema50_4s_ustunde", False):
        return "4 saatlik ortalamanın (EMA50) altında"
    if a["goreli_guc_pozitif_sart"]:
        guc = c.get("goreli_guc")
        if guc is None or guc <= 0:
            return "BTC'ye göre zayıf"
    if a["son20_zararda_dinlenme"]:
        son20 = c.get("son20_net")
        if son20 is not None and son20 < 0:
            return "Son 20 işlemde net zarar ettirdi, dinleniyor"
    return None


def siralama_puani(c: dict, a: dict) -> float:
    """Geçen coinleri sıralamak için 0-100 puan: likidite, oynaklık uyumu ve güç."""
    puan = 0.0
    hacim = c.get("hacim_24s") or 0.0
    # Hacim: sınırın 1 katı -> 0, 20 katı ve üstü -> 35 puan
    kat = hacim / a["en_az_hacim_24s"] if a["en_az_hacim_24s"] > 0 else 0.0
    puan += max(0.0, min(35.0, (kat - 1.0) / 19.0 * 35.0))
    # Fark: sınırda -> 0, sıfırda -> 25 puan
    if c.get("alis") and c.get("satis"):
        fark = fark_yuzde(c["alis"], c["satis"])
        puan += max(0.0, min(25.0, (1.0 - fark / a["en_fazla_fark_yuzde"]) * 25.0))
    # Oynaklık: bandın ortasında 20 puan, kenarlarda 0
    oynaklik = c.get("atr_yuzde_gunluk")
    if oynaklik is not None:
        orta = (a["atr_alt_yuzde"] + a["atr_ust_yuzde"]) / 2.0
        yari = (a["atr_ust_yuzde"] - a["atr_alt_yuzde"]) / 2.0
        puan += max(0.0, 20.0 * (1.0 - abs(oynaklik - orta) / yari)) if yari > 0 else 0.0
    # Güç: göreli güç +%5 ve üstü -> 20 puan
    guc = c.get("goreli_guc")
    if guc is not None:
        puan += max(0.0, min(20.0, guc / 5.0 * 20.0))
    return round(puan, 1)


def filtrele(
    coinler: list[dict],
    pozisyon_tutari: float,
    ayar: dict | None = None,
    eleyen_katmanlar: tuple = (1, 2, 3, 4),
) -> list[dict]:
    """Coinleri katmanlardan geçirir.

    eleyen_katmanlar: hangi katmanların coin eleyeceği. Sınavda (1, 2) verilir;
    3. ve 4. katman yine hesaplanır ve sonuca yazılır ama elemez.

    Her sonuç: sembol, gecti, elendigi_katman, neden, katmanlar {1..4: bool},
    nedenler {katman: metin}, puan
    """
    a = {**VARSAYILAN_AYAR, **(ayar or {})}
    sonuclar = []
    for c in coinler:
        nedenler = {
            1: _katman1(c, a),
            2: _katman2(c, a, pozisyon_tutari),
            3: _katman3(c, a),
            4: _katman4(c, a),
        }
        katmanlar = {k: n is None for k, n in nedenler.items()}
        elendigi = next((k for k in (1, 2, 3, 4) if k in eleyen_katmanlar and not katmanlar[k]), None)
        sonuclar.append(
            {
                "sembol": c.get("sembol"),
                "gecti": elendigi is None,
                "elendigi_katman": elendigi,
                "neden": f"{KATMAN_ADI[elendigi]}: {nedenler[elendigi]}" if elendigi else "",
                "katmanlar": katmanlar,
                "nedenler": {k: n for k, n in nedenler.items() if n is not None},
                "siki_filtreden_gecer": all(katmanlar.values()),
                "puan": siralama_puani(c, a),
            }
        )
    sonuclar.sort(key=lambda s: (not s["gecti"], -s["puan"], str(s["sembol"])))
    return sonuclar


def huni(sonuclar: list[dict], eleyen_katmanlar: tuple = (1, 2, 3, 4)) -> list[dict]:
    """Ekrandaki huni: her katmandan kaç coin geçti."""
    kalan = len(sonuclar)
    satirlar = [{"asama": "Başlangıç", "kalan": kalan}]
    for k in (1, 2, 3, 4):
        if k not in eleyen_katmanlar:
            continue
        kalan -= sum(1 for s in sonuclar if s["elendigi_katman"] == k)
        satirlar.append({"asama": f"{k}. {KATMAN_ADI[k]}", "kalan": kalan})
    return satirlar


def izleme_listesi(sonuclar: list[dict]) -> list[str]:
    """Geçen coinlerin sembolleri, puana göre sıralı."""
    return [s["sembol"] for s in sonuclar if s["gecti"]]
