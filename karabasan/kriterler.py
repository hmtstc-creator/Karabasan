"""Ahmet Özel stratejisinin kriterleri: tek liste, değerler kural dosyalarından okunur.

Sonuç sayfasının "Kriterler" ekranı ve Ahmet'in değişiklik isteği yazdığı düzenleme
sayfası (claude.ai'deki "Bot Kriterleri") bu listeyi gösterir. Değerler burada
yazılmaz; her seferinde aday kural dosyalarından ve panel sınamasının ayarlarından
okunur, yani sayfa her zaman kodun gerçekte kullandığı değeri gösterir.

Bir değeri değiştirmek kural dosyasını değiştirmek demektir: yeni bir deneme sayılır,
deneme defterine yazılır ve sınama yeniden çalışır (bkz. stratejiler/aday/BENIOKU.md).
Bu modül yalnız okur; hiçbir dosyaya yazmaz.

Yalnız standart kütüphane: panel sınamasının ayarları (pandas isteyen sinama.py)
okunamazsa o grup listeden düşer, kalan kriterler yine gösterilir.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

ADAY_KLASORU = Path(__file__).resolve().parent / "stratejiler" / "aday"
ALIM, SATIS = "AHMETOZEL", "AHMETOZELK"
# Ahmet'in değişiklik isteğini yazdığı sayfa (claude.ai; yalnız Ahmet açabilir).
DUZENLEME_ADRESI = "https://claude.ai/artifact/GnD6sEpXhB3XEQkcL7hCVo"


def _kural(kod: str) -> dict:
    return json.loads((ADAY_KLASORU / f"{kod}.json").read_text(encoding="utf-8"))


def _kosul(kural: dict, sol: str) -> dict:
    return next(k for k in kural["giris"]["hepsi"] if k.get("sol") == sol)


def _dokunus(kural: dict) -> dict:
    """Destek / direnç yaklaşma koşulu (ilk seviyeninki; ikinci seviye aynı değerleri taşır)."""
    grup = next(k for k in kural["giris"]["hepsi"] if "herhangi" in k)
    return grup["herhangi"][0]["hepsi"][0]


def _gun(dakika) -> float:
    return float(dakika) / 1440.0


# (kimlik, grup, ad, birim, açıklama, değer okuyucu). Okuyucu bir kural dosyası alır.
KURAL_KRITERLERI = [
    ("yapi_uzunluk", "Günlük trend", "Salınım uzunluğu", "gün",
     "Bir tepe ya da dibin sayılması için iki yanında kaç gün daha düşük (yüksek) mum olmalı. "
     "Trend yönü (BOS / CHoCH) bu salınımlardan çıkar.",
     lambda k: k["gostergeler"]["yapi"]["periyot"]),
    ("kirilmadi_gun", "Günlük trend", "Trend bozulmamış olmalı", "gün",
     "Son bu kadar günün hiçbirinde trend ters yöne dönmemiş (CHoCH yok) olmalı.",
     lambda k: k["gostergeler"]["yon10"]["periyot"]),
    ("ema_kisa", "Ortalamalar", "Kısa EMA", "gün",
     "Alımda kısa EMA uzun EMA'nın üstünde, açığa satışta altında olmalı.",
     lambda k: k["gostergeler"]["ema20"]["periyot"]),
    ("ema_uzun", "Ortalamalar", "Uzun EMA", "gün", "Kısa EMA ile karşılaştırılan ortalama.",
     lambda k: k["gostergeler"]["ema50"]["periyot"]),
    ("sma", "Ortalamalar", "SMA", "gün",
     "Alımda kapanış bu ortalamanın üstünde, açığa satışta altında olmalı.",
     lambda k: k["gostergeler"]["sma200"]["periyot"]),
    ("haftalik_salinim", "Haftalık destek / direnç", "Haftalık salınım uzunluğu", "hafta",
     "Haftalık dip (destek) ya da tepe (direnç) için iki yanında kaç hafta olmalı.",
     lambda k: k["gostergeler"]["hyapi"]["periyot"]),
    ("fvg_en_az", "Haftalık destek / direnç", "FVG en küçük boyu", "%",
     "Haftalık boşluk (FVG) fiyatın en az bu kadarı genişlikte olmalı.",
     lambda k: k["gostergeler"]["hfvg"]["en_az_yuzde"]),
    ("fvg_omur", "Haftalık destek / direnç", "FVG ömrü", "hafta",
     "Bir boşluk en çok bu kadar hafta geçerli sayılır.",
     lambda k: k["gostergeler"]["hfvg"]["omur"]),
    ("dokunus_atr", "Haftalık destek / direnç", "Desteğe yaklaşma payı", "x ATR",
     "Fiyat desteğe bu kadar günlük oynaklık (ATR) mesafesine kadar inmiş (direnç için çıkmış) olmalı.",
     lambda k: abs(_dokunus(k)["sag"]["ekle"]["carpan"])),
    ("dokunus_gun", "Haftalık destek / direnç", "Yaklaşma kaç gün içinde", "gün",
     "Desteğe yaklaşma son bu kadar günün birinde olmuş olmalı; bugün desteğin doğru yanında kapanış.",
     lambda k: _dokunus(k)["son_n_mumda"]),
    ("macd_hizli", "MACD", "Hızlı ortalama", "gün", "MACD çizgisinin hızlı ortalaması.",
     lambda k: k["gostergeler"]["macd"].get("hizli", 12)),
    ("macd_yavas", "MACD", "Yavaş ortalama", "gün", "MACD çizgisinin yavaş ortalaması.",
     lambda k: k["gostergeler"]["macd"].get("yavas", 26)),
    ("macd_sinyal", "MACD", "Sinyal ortalaması", "gün", "MACD sinyal çizgisi.",
     lambda k: k["gostergeler"]["macd"].get("sinyal", 9)),
    ("macd_gun", "MACD", "Dönüş kaç gün içinde", "gün",
     "MACD histogramı son bu kadar günde sıfırı geçmiş (dönüş vermiş) olmalı.",
     lambda k: _kosul(k, "macd_fark")["son_n_mumda"]),
    ("stop_gun", "Stop ve hedef", "Stop: son kaç günün dibi", "gün",
     "Stop son bu kadar günün dibinin (açığa satışta tepesinin) biraz ötesine konur.",
     lambda k: k["gostergeler"]["dip5" if "dip5" in k["gostergeler"] else "tepe5"]["periyot"]),
    ("stop_pay", "Stop ve hedef", "Stop payı", "x ATR", "Stopun o dibin ne kadar ötesinde olacağı.",
     lambda k: k["cikis"]["stop_atr"]["pay"]),
    ("stop_en_az", "Stop ve hedef", "Stop en az", "%", "Stop bundan daha yakın konmaz.",
     lambda k: k["cikis"]["stop_atr"]["en_az_yuzde"]),
    ("stop_en_cok", "Stop ve hedef", "Stop en çok", "%", "Stop bundan daha uzak konmaz.",
     lambda k: k["cikis"]["zarar_durdur_yuzde"]),
    ("hedef_r", "Stop ve hedef", "Kâr hedefi", "x stop",
     "Hedef, stop uzaklığının bu katı (stop %5 ve 2 ise hedef %10).",
     lambda k: k["cikis"]["kar_hedefi_r"]),
    ("sure", "Stop ve hedef", "En uzun süre", "gün", "İşlem bu kadar gün sonra hâlâ açıksa kapanır.",
     lambda k: _gun(k["cikis"]["sure_asimi_dakika"])),
    ("pozisyon", "Risk", "Aynı anda en çok işlem", "işlem", "Botun aynı anda açık tutabileceği işlem sayısı.",
     lambda k: k["portfoy"]["en_fazla_pozisyon"]),
    ("giris_24s", "Risk", "24 saatte en çok giriş", "giriş", "Bir günde açılabilecek en çok işlem.",
     lambda k: k["portfoy"]["giris_sinirlari"][0]["sayi"]),
]

# Sınamanın ölçütleri (sinama.py). Okuyucu (sinama modülü, aile) alır.
SINAMA_KRITERLERI = [
    ("coin_sayisi", "Sınama", "Coin sayısı", "coin",
     "Kaç coinde sınanır. Bütün adaylar için ortaktır; artırmak yeni coinlerin verisini indirmeyi gerektirir.",
     lambda s, a: len(s.COINLER)),
    ("gelistirme_yil", "Sınama", "Sınama süresi", "yıl",
     "Kaç yıllık geçmişte sınanır (son yıl ayrıca saklıdır). Bütün adaylar için ortak.",
     lambda s, a: s.GELISTIRME_YIL),
    ("en_az_islem", "Sınama", "En az işlem", "işlem", "Bundan az işlem çıkarsa karar verilmez (HÜKÜM YOK).",
     lambda s, a: a["en_az_islem"]),
    ("en_az_gun", "Sınama", "En az farklı gün", "gün", "İşlemler en az bu kadar farklı günde açılmış olmalı.",
     lambda s, a: a["en_az_gun"]),
    ("esik_r", "Sınama", "İşlem başına en az kazanç", "x risk",
     "İşlem başına ortalama kazanç, riske edilen tutarın en az bu katı olmalı (1 USDT risk için 0,15 USDT).",
     lambda s, a: a["esik_net_r"]),
    ("plasebo_r", "Sınama", "Destek şartsız halden fark", "x risk",
     "Asıl kural, destek / direnç şartı kaldırılmış halinden işlem başına en az bu kadar iyi olmalı.",
     lambda s, a: a["kural_plasebo_r"]),
    ("kazanc_kayip", "Sınama", "Ortalama kazanç / kayıp", "kat", "Ortalama kazanç ortalama kaybın en az bu katı.",
     lambda s, a: a["en_az_kazanc_kayip"]),
    ("en_fazla_dusus", "Sınama", "En büyük düşüş", "USDT", "Arka arkaya kayıplarla en çok bu kadar düşebilir.",
     lambda s, a: a["en_fazla_dusus"]),
    ("t_esigi", "Sınama", "Şans eşiği (t)", "",
     "Sonucun şanstan ayrılması için gün bazında t en az bu kadar olmalı. Bütün adaylar için ortak.",
     lambda s, a: s.T_ESIGI),
]


def _sayi(deger):
    deger = float(deger)
    return int(deger) if deger.is_integer() else round(deger, 4)


def liste() -> list[dict]:
    """Kriterler, sırasıyla: kimlik, grup, ad, birim, açıklama, alım ve açığa satış değeri."""
    alim, satis = _kural(ALIM), _kural(SATIS)
    sonuc = []
    for kimlik, grup, ad, birim, aciklama, oku in KURAL_KRITERLERI:
        sonuc.append({"kimlik": kimlik, "grup": grup, "ad": ad, "birim": birim, "aciklama": aciklama,
                      "alim": _sayi(oku(alim)), "satis": _sayi(oku(satis))})
    try:
        sinama = importlib.import_module("karabasan.sinama")
    except ImportError:  # pandas yok: sınama ölçütleri gösterilmez
        return sonuc
    aileler = {a["ad"]: a for a in sinama.ADAYLAR}
    for kimlik, grup, ad, birim, aciklama, oku in SINAMA_KRITERLERI:
        sonuc.append({"kimlik": kimlik, "grup": grup, "ad": ad, "birim": birim, "aciklama": aciklama,
                      "alim": _sayi(oku(sinama, aileler[ALIM])), "satis": _sayi(oku(sinama, aileler[SATIS]))})
    return sonuc


def metin_degeri(deger) -> str:
    return f"{deger:g}".replace(".", ",") if isinstance(deger, float) else str(deger)
