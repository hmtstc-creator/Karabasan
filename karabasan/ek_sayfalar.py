"""Ek ekranlar: Risk, Rejim, Likidite, Güven, Disiplin (10 Kasım 2026).

Her ekranın iki modülü vardır:

    karabasan/sonuc_<ad>.py   hesapla(baglam) -> sözlük      (veri; yalnız okur)
    karabasan/sayfa_<ad>.py   ekran(ozet, saat_dilimi) -> HTML, STIL (biçim kuralları)

Bu modül onları sonuç sayfasına bağlar ve birbirinden yalıtır: bir ekranın hesabı ya da
çizimi hata verirse yalnız o ekran "hazırlanamadı" der; sayfanın geri kalanı ve öbür
ekranlar etkilenmez. Hiçbir ekran bot ayarı yazmaz.

Yalnız Python standart kütüphanesi. Ekran modülleri burada bilerek tembel (işlev içinde)
içe aktarılır: sayfa.py bu modülü, ekran modülleri de sayfa.py'yi kullanır.
"""

from __future__ import annotations

import importlib
import logging

# (kimlik, menüdeki ad). Kimlik aynı zamanda modül adının sonudur ve <section id="..."> değeridir.
EK_EKRANLAR = [
    ("risk", "Risk"),
    ("rejim", "Rejim"),
    ("likidite", "Likidite"),
    ("guven", "Güven"),
    ("disiplin", "Disiplin"),
]
EK_MENU_ACIKLAMA = {
    "risk": "Açık risk, düşüş, yoğunlaşma",
    "rejim": "Piyasa ortamı ve vetolar",
    "likidite": "Fonlama, açık faiz, spread",
    "guven": "Sonuca güvenilir mi",
    "disiplin": "İşlem kalitesi, bugün dikkat",
}

gunluk = logging.getLogger("karabasan.ek_sayfalar")


def veri_topla(baglam: dict) -> dict:
    """Her ek ekranın verisi: {"risk": {...}, ...}. Hata veren ekranın değeri {"hata": True} olur."""
    sonuc = {}
    for kimlik, _ad in EK_EKRANLAR:
        try:
            modul = importlib.import_module(f"karabasan.sonuc_{kimlik}")
            sonuc[kimlik] = modul.hesapla(baglam)
        except Exception:  # noqa: BLE001 - bir ekranın hatası özeti düşürmemeli
            gunluk.exception("Ek ekran verisi çıkarılamadı: %s", kimlik)
            sonuc[kimlik] = {"hata": True}
    return sonuc


def _yedek(kimlik: str, ad: str) -> str:
    return (f'<section id="{kimlik}" class="ekran"><h2 class="ekran-baslik">{ad}</h2>'
            '<p class="bos">Bu ekran şu an hazırlanamadı. Botlar ve öbür ekranlar bundan etkilenmez; '
            "ayrıntı sunucunun kaydındadır.</p></section>")


def ekranlar(ozet: dict, saat_dilimi: str) -> str:
    """Bütün ek ekranların HTML'i, EK_EKRANLAR sırasıyla; her biri tam bir <section>."""
    parca = []
    for kimlik, ad in EK_EKRANLAR:
        try:
            if ((ozet.get("ek") or {}).get(kimlik) or {"hata": True}).get("hata"):
                raise ValueError("veri yok")
            modul = importlib.import_module(f"karabasan.sayfa_{kimlik}")
            govde = modul.ekran(ozet, saat_dilimi)
            if govde.count(f'<section id="{kimlik}"') != 1:
                raise ValueError("ekran kendi bölümünü tam bir kez üretmeli")
            parca.append(govde)
        except Exception:  # noqa: BLE001
            gunluk.exception("Ek ekran çizilemedi: %s", kimlik)
            parca.append(_yedek(kimlik, ad))
    return "\n".join(parca)


def stil() -> str:
    """Ek ekranların biçim kuralları (her modülün STIL metni)."""
    parca = []
    for kimlik, _ad in EK_EKRANLAR:
        try:
            parca.append(str(importlib.import_module(f"karabasan.sayfa_{kimlik}").STIL))
        except Exception:  # noqa: BLE001
            gunluk.exception("Ek ekran biçimi yüklenemedi: %s", kimlik)
    return "\n".join(parca)
