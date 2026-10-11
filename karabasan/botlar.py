"""Sınavdaki sanal botların tanımı ve komisyon ayarları.

Tek doğruluk kaynağı burasıdır: hazır motorun strateji sınıfları, bot
yapılandırmaları ve Docker Compose dosyası bu listeden üretilir.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# (bot adı, strateji sınıfı, kural kodu, piyasa)
#
# 11 Ekim 2026'da değişti: S1-S4'ün "vadeli alım" botları kaldırıldı, yerlerine
# dört yeni strateji botu geldi. Kaldırılanlar spot'taki ikizleriyle aynı
# işlemleri açıyordu (geçmiş testi: aynı sinyaller, yalnız komisyon farklı),
# yani yeni bilgi üretmiyordu. Yeni stratejiler vadelide çalışır: komisyon
# daha düşüktür ve açığa satış yalnız orada mümkündür.
BOTLAR = [
    ("s1-spot", "S1Spot", "S1", "spot"),
    ("s2-spot", "S2Spot", "S2", "spot"),
    ("s3-spot", "S3Spot", "S3", "spot"),
    ("s4-spot", "S4Spot", "S4", "spot"),
    ("s1k-vadeli", "S1KVadeli", "S1K", "vadeli"),
    ("s2k-vadeli", "S2KVadeli", "S2K", "vadeli"),
    ("s5-vadeli", "S5Vadeli", "S5", "vadeli"),
    ("s5k-vadeli", "S5KVadeli", "S5K", "vadeli"),
    ("s6-vadeli", "S6Vadeli", "S6", "vadeli"),
    ("s6k-vadeli", "S6KVadeli", "S6K", "vadeli"),
    # 11 Ekim 2026'da eklendi (Smartmoney): yeni fikir, yeni sanal bot. Sona eklenir ki
    # öncekilerin kapıları ve açılış sırası değişmesin.
    ("sm-vadeli", "SMVadeli", "SM", "vadeli"),
    ("smk-vadeli", "SMKVadeli", "SMK", "vadeli"),
]

ILK_PORT = 8081


def ek_dilimler(piyasa: str) -> list[str]:
    """Bu piyasadaki botların borsadan ayrıca istediği dilimler (örnek: ["1d"]).

    Sunucu betikleri hangi geçmiş veriyi indireceğini buradan öğrenir. Kural
    dosyalarını düz JSON olarak okur; sunucunun kendi Python'unda numpy ve pandas
    olmadığı için kural motorunu içe aktarmaz.
    """
    klasor = Path(__file__).resolve().parent / "stratejiler"
    dilimler: list[str] = []
    for _bot, _sinif, kural_kodu, bot_piyasasi in BOTLAR:
        if bot_piyasasi != piyasa:
            continue
        try:
            kural = json.loads((klasor / f"{kural_kodu}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for dilim in kural.get("borsa_dilimleri", []):
            if dilim not in dilimler:
                dilimler.append(str(dilim))
    return dilimler

# Başlangıç değerleri. Komisyon oranları hesabına göre burada güncellenir.
# Sunucudaki user_data/ayarlar.json dosyasında yazan bir değer buradakini ezer;
# o dosya yalnız sunucuya özel değerler (örneğin panel adresleri) içindir.
VARSAYILAN_AYARLAR = {
    "komisyon_yuzde": {
        # Sınavda tüm emirler piyasa emridir, bu yüzden alıcı (taker) oranı kullanılır.
        "spot": 0.075,
        "vadeli": 0.05,
    },
    "sanal_bakiye": 1000,
    "islem_tutari": 50,
    "en_fazla_pozisyon": 20,
    "parite_sayisi": 60,
    "en_az_hacim_24s": 5_000_000,
    "en_az_listelenme_gun": 30,
    "en_fazla_fark_yuzde": 0.10,
    # Paneli tarayıcıda açtığın adresler (örnek: http://karabasan:8081).
    "panel_adresleri": [],
}

KOMISYON_SINIRI = (0.0, 1.0)  # yüzde; bunun dışı yazım hatasıdır


class AyarHatasi(ValueError):
    pass


def ayar_yolu() -> Path:
    """ayarlar.json'un yeri: önce ortam değişkeni, sonra user_data klasörü."""
    ortam = os.environ.get("KARABASAN_AYAR")
    if ortam:
        return Path(ortam)
    return Path(__file__).resolve().parent.parent / "user_data" / "ayarlar.json"


def ayarlari_yukle(yol: Path | None = None) -> dict:
    """ayarlar.json'u okur; dosya yoksa başlangıç değerlerini döndürür."""
    yol = yol or ayar_yolu()
    ayar = json.loads(json.dumps(VARSAYILAN_AYARLAR))  # derin kopya
    if yol.exists():
        try:
            okunan = json.loads(yol.read_text(encoding="utf-8"))
        except json.JSONDecodeError as hata:
            raise AyarHatasi(f"{yol} okunamadı, JSON biçimi bozuk: {hata}") from hata
        for anahtar, deger in okunan.items():
            if isinstance(deger, dict) and isinstance(ayar.get(anahtar), dict):
                ayar[anahtar].update(deger)
            else:
                ayar[anahtar] = deger
    ayarlari_dogrula(ayar)
    return ayar


def ayarlari_dogrula(ayar: dict) -> None:
    alt, ust = KOMISYON_SINIRI
    for piyasa in ("spot", "vadeli"):
        oran = ayar["komisyon_yuzde"].get(piyasa)
        if isinstance(oran, bool) or not isinstance(oran, (int, float)) or not alt <= oran <= ust:
            raise AyarHatasi(
                f"'{piyasa}' komisyonu yüzde olarak {alt} ile {ust} arasında olmalı "
                f"(örnek: 0.075). Verilen: {oran!r}"
            )
    for alan in ("sanal_bakiye", "islem_tutari", "en_fazla_pozisyon", "parite_sayisi"):
        deger = ayar.get(alan)
        if isinstance(deger, bool) or not isinstance(deger, (int, float)) or deger <= 0:
            raise AyarHatasi(f"'{alan}' sıfırdan büyük bir sayı olmalı. Verilen: {deger!r}")
    if ayar["islem_tutari"] > ayar["sanal_bakiye"]:
        raise AyarHatasi("'islem_tutari' sanal bakiyeden büyük olamaz.")


def net_hedef_orani(kar_hedefi_yuzde: float, komisyon_yuzde: float, aciga_satis: bool = False) -> float:
    """Fiyat hedefini, hazır motorun beklediği 'komisyon sonrası kâr oranına' çevirir.

    Kural dosyasındaki kâr hedefi fiyat hareketidir (%1,2 = fiyat %1,2 lehe gidince kapat).
    Hazır motor ise hedefi komisyon düşülmüş kâr oranı olarak ister. İkisini eşleyen formül:

        alım:         net = (1 + hedef) * (1 - komisyon) / (1 + komisyon) - 1
        açığa satış:  net = 1 - (1 - hedef) * (1 + komisyon) / (1 - komisyon)
    """
    hedef = kar_hedefi_yuzde / 100.0
    komisyon = komisyon_yuzde / 100.0
    if aciga_satis:
        return 1.0 - (1.0 - hedef) * (1.0 + komisyon) / (1.0 - komisyon)
    return (1.0 + hedef) * (1.0 - komisyon) / (1.0 + komisyon) - 1.0
