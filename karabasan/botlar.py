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
# Geçmiş: 10-11 Ekim 2026'da on bot (S1-S6 ve ters yönlüleri), sonra Smartmoney
# (SM, SMK) eklendi. 12 Ekim 2026'da hepsi 1 kat vadeliye taşındı ve hedef %0,8,
# stop %3 oldu. Aynı gün 12 aylık geçmiş testi on iki botun hepsini ekside
# gösterdi; Ahmet'in isteğiyle yalnız Smartmoney kaldı (öbür kural dosyaları
# karabasan/stratejiler/emekli/ altında). Yeni bot listenin sonuna eklenir ki
# öncekilerin kapısı ve açılış sırası değişmesin.
BOTLAR = [
    ("sm-vadeli", "SMVadeli", "SM", "vadeli"),
    ("smk-vadeli", "SMKVadeli", "SMK", "vadeli"),
    # 12 Ekim 2026 (Ahmet'in isteği): Smartmoney + uyumsuzluk + girişte emir defteri onayı.
    ("smd-vadeli", "SMDVadeli", "SMD", "vadeli"),
    ("smdk-vadeli", "SMDKVadeli", "SMDK", "vadeli"),
    # 12 Ekim 2026 (Ahmet'in isteği, adı "sniper"): günlük Donchian topluluğuyla trend takibi.
    ("sniper-vadeli", "SniperVadeli", "SNIPER", "vadeli"),
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
        # Taban dilimi 5m / 15m dışında olan kural (Sniper: 1d) da o dilimin verisini ister.
        istenen = list(kural.get("borsa_dilimleri", []))
        if kural.get("zaman_dilimi") not in (None, "5m", "15m"):
            istenen.append(kural["zaman_dilimi"])
        for dilim in istenen:
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
