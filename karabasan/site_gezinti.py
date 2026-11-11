"""Sitenin ortak gezinti şeridi.

Ahmet (11 Kasım 2026): "Panoya geçince site başka yere geçiyor; sayfalar ve erişimler çok karışık."
Alt sayfalar (/ayar, /detay, /islem, /coinler, /defter) eskiden "Ana sayfa" diye eski /klasik sayfasına dönüyordu.
Artık hepsi aynı şeridi taşır ve her yol panoya (/) çıkar. Yalnız standart kütüphane; yalnız bağlantı üretir.
"""
from __future__ import annotations

from html import escape

# (ad, adres, tanıtıcı). Hepsi panoya ya da pano dışındaki alt sayfalara gider.
BAGLANTILAR = (
    ("Sonuçlar", "/#sonuc", "sonuc"),
    ("Uzay", "/#uzay", "uzay"),
    ("Ayar ve geçmiş test", "/#lab", "lab"),
    ("Ajan", "/#ajan", "ajan"),
    ("Kriter ayarı", "/ayar", "ayar"),
    ("Coin listesi", "/coinler", "coinler"),
    ("Emir defteri", "/defter", "defter"),
)

STIL = (
    ".site-gez{display:flex;gap:6px;overflow-x:auto;padding:8px 12px;margin:0;background:#04070d;"
    "border-bottom:1px solid #1c2733;-webkit-overflow-scrolling:touch}"
    ".site-gez a{flex:none;display:inline-flex;align-items:center;min-height:36px;padding:0 12px;border-radius:999px;"
    "border:1px solid #1c2733;color:#e6edf5;text-decoration:none;font:13px system-ui,sans-serif;white-space:nowrap}"
    ".site-gez a[aria-current=page]{background:#f2c94c;color:#04070d;border-color:#f2c94c}"
)


def serit(aktif: str = "") -> str:
    """Şerit HTML'i (stil dahil). `aktif`: o sayfanın tanıtıcısı ("ayar", "coinler", "defter"...)."""
    bag = "".join(
        f'<a href="{escape(adres)}"{" aria-current=page" if kimlik == aktif else ""}>{escape(ad)}</a>'
        for ad, adres, kimlik in BAGLANTILAR
    )
    return f'<style>{STIL}</style><nav class="site-gez" aria-label="Site">{bag}</nav>'
