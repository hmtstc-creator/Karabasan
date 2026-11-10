"""Likidite ekranının verisi: fonlama, açık faiz, spread, hacim ve kaba bir sıkışma riski etiketi.

Botların hepsi açığa satış (short) yapar. Bu modül, pozisyon açılan coinlerde "açığa satış
sıkışması" (short squeeze: fiyat yükselince açığa satanların zorla kapanıp fiyatı daha da
yükseltmesi) riskini ve piyasanın inceliğini gösterecek ölçüleri toplar. Yalnız okur; hiçbir
ayar, kural ya da bot dosyası yazmaz. Yalnız standart kütüphane (pandas / numpy yok).

Ağ kuralı:
- hesapla(baglam) ASLA ağda beklemez. Özet her 20 saniyede çıkarılır ve Telegram habercisi
  de aynı işlevi çağırır.
- ag_ac() çağrılmadıkça (varsayılan kapalı) hiç ağ isteği yapılmaz. Bayrağı yalnız panel
  süreci açar.
- Bayrak açıksa ve önbellek bayatsa hesapla arka planda TEK bir daemon iş parçacığı başlatır
  ve eldeki (belki boş) görüntüyü hemen döndürür.
- Yalnız GET, anahtarsız, yalnız https://fapi.binance.com ve yalnız IZINLI_YOLLAR.
- Hata sayfayı düşürmez: alan "alınamadı" olur, son başarılı değerin yaşı gösterilir; hiçbir
  istek başarılı olmazsa yeniden deneme aralığı uzar.

Binance yanıt biçimleri ezberden yazıldı; Claude'un çalışma alanından Binance'e erişim yok.
Ayrıştırma bu yüzden savunmacıdır ve gerçek yanıtla ilk kez sunucuda karşılaşacaktır.

Etiketin eşikleri (ESIKLER) bir trader'ın kaba kuralıdır; geçmiş veriyle SINANMADI.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .defter_sayfa import BAYAT_SANIYE as DEFTER_BAYAT_SANIYE
from .stop_sonrasi import sembol as _sembol

TABAN = "https://fapi.binance.com"
IZINLI_YOLLAR = (
    "/fapi/v1/premiumIndex",
    "/fapi/v1/ticker/24hr",
    "/fapi/v1/ticker/bookTicker",
    "/futures/data/openInterestHist",
)
ZAMAN_ASIMI = 8            # saniye (en çok 10)
EN_FAZLA_BAYT = 8_000_000  # toplu yanıtlar büyüktür; bundan uzunu okunmaz
YENILEME_SANIYE = 300      # önbellek bu kadar eskiyince yeniden istenir
EN_UZUN_BEKLEME = 3600     # art arda hatada aralık en çok buna kadar uzar
YENI_COIN_BEKLEME = 60     # listede önbellekte olmayan coin varsa erken yenileme için en az ara
KULLANIM_SINIRI_DAKIKA = 30  # bundan eski değer etikete katılmaz
EN_FAZLA_ISLEM_COINI = 8
ISTEK_ARASI = 0.2          # istekler arası kısa bekleme (Binance'i yormamak için)
AF_ARALIK = "15m"          # açık faiz geçmişinin adımı
AF_ADET = 97               # 24 saat + 1 nokta
AF_PENCERELER = (("1s", 1.0), ("4s", 4.0), ("24s", 24.0))
SEMBOL_KALIBI = re.compile(r"^[A-Z0-9]{2,20}$")

# Kaba uyarı eşikleri. SINANMADI: geçmiş veriyle doğrulanmış değildir.
ESIKLER = {
    "fonlama_eksi_orta": -0.01,    # dönem başına yüzde; bunun altı: short öder (1 puan)
    "fonlama_eksi_yuksek": -0.05,  # bunun altı: kalabalık belirgin biçimde short'ta (2 puan)
    "af_artis_orta": 10.0,         # açık faiz 24 saatte yüzde bu kadar arttıysa 1 puan
    "af_artis_yuksek": 25.0,       # 2 puan
    "fiyat_artis": 8.0,            # fiyat 24 saatte yüzde bu kadar yükseldiyse 1 puan
    "spread_ince": 5.0,            # on binde (bps); bunun üstü ince (1 puan)
    "spread_cok_ince": 15.0,       # 2 puan
    "hacim_ince": 20_000_000.0,    # USDT / 24 saat; bunun altı ince (1 puan)
    "hacim_cok_ince": 5_000_000.0,  # 2 puan
    "orta_puan": 2,                # toplam puan bu ve üstü: orta
    "yuksek_puan": 4,              # bu ve üstü: yüksek
    "en_az_olcu": 2,               # dört ölçü grubundan en az bu kadarı yoksa "veri yok"
}

GRUPLAR = ("fonlama", "acik_faiz", "spread", "hacim")
GRUP_ADI = {"fonlama": "fonlama", "acik_faiz": "açık faiz", "spread": "spread", "hacim": "24 saatlik hacim"}

# Testler ve panel için değiştirilebilir getirici: getir(yol, parametreler) -> JSON'dan çözülmüş nesne.
getir = None

_kilit = threading.Lock()
_durum = {
    "ag_acik": False,
    "is": None,             # çalışan arka plan iş parçacığı
    "coinler": {},          # sembol -> {grup: {"zaman": datetime, ...}}
    "alinamadi": {},        # "grup" ya da "grup:SEMBOL" -> kısa hata metni (son turda)
    "son_deneme": None,     # time.monotonic()
    "son_deneme_zamani": None,
    "son_basari_zamani": None,
    "ardisik_hata": 0,
    "baslatilan": 0,        # kaç kez arka plan işi başlatıldı (test ve teşhis)
}


class VeriHatasi(Exception):
    """Binance yanıtı beklenen biçimde değil ya da hata bildirdi."""


def ag_ac() -> None:
    """Ağ isteklerine izin verir. Yalnız panel süreci çağırır."""
    with _kilit:
        _durum["ag_acik"] = True


def ag_kapat() -> None:
    with _kilit:
        _durum["ag_acik"] = False


def sifirla() -> None:
    """Önbelleği ve bayrağı ilk haline döndürür (testler için)."""
    global getir
    with _kilit:
        _durum.update({"ag_acik": False, "is": None, "coinler": {}, "alinamadi": {}, "son_deneme": None,
                       "son_deneme_zamani": None, "son_basari_zamani": None, "ardisik_hata": 0, "baslatilan": 0})
    getir = None


# --------------------------------------------------------------------------
# Ağ: tek kapı
# --------------------------------------------------------------------------


def varsayilan_getir(yol: str, parametreler: dict | None = None):
    """Binance'in herkese açık vadeli adresinden JSON getirir. Yalnız GET, anahtarsız."""
    if yol not in IZINLI_YOLLAR:
        raise VeriHatasi("izinli olmayan adres")
    adres = TABAN + yol
    if parametreler:
        adres += "?" + urllib.parse.urlencode(parametreler)
    istek = urllib.request.Request(adres, headers={"User-Agent": "karabasan-bot", "Accept": "application/json"})
    with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
        govde = yanit.read(EN_FAZLA_BAYT + 1)
    if len(govde) > EN_FAZLA_BAYT:
        raise VeriHatasi("yanıt beklenenden büyük")
    return json.loads(govde.decode("utf-8"))


def _hata_metni(hata: Exception) -> str:
    if isinstance(hata, urllib.error.HTTPError):
        return f"HTTP {hata.code}"
    if isinstance(hata, VeriHatasi):
        return str(hata)[:80]
    if isinstance(hata, (TimeoutError, urllib.error.URLError, OSError)):
        return "bağlantı kurulamadı"
    if isinstance(hata, ValueError):
        return "yanıt okunamadı"
    return type(hata).__name__


# --------------------------------------------------------------------------
# Savunmacı ayrıştırma
# --------------------------------------------------------------------------


def _sayi(deger) -> float | None:
    """Metin ya da sayı -> sonlu float; olmuyorsa None."""
    if deger is None or isinstance(deger, bool):
        return None
    try:
        s = float(deger)
    except (TypeError, ValueError):
        return None
    return s if math.isfinite(s) else None


def _zaman(ms) -> datetime | None:
    s = _sayi(ms)
    if s is None or s <= 0:
        return None
    try:
        return datetime.fromtimestamp(s / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _liste(yanit) -> list:
    """Yanıtı sözlük listesine çevirir; Binance hata sözlüğünü ({"code","msg"}) hataya çevirir."""
    if isinstance(yanit, dict):
        if "code" in yanit and "symbol" not in yanit:
            raise VeriHatasi(f"Binance hata kodu {str(yanit.get('code'))[:12]}")
        yanit = [yanit]
    if not isinstance(yanit, list):
        raise VeriHatasi("beklenmeyen yanıt biçimi")
    return [s for s in yanit if isinstance(s, dict)]


def _sembole_gore(yanit, istenen) -> dict:
    istenen = set(istenen)
    sonuc = {}
    for satir in _liste(yanit):
        ad = satir.get("symbol")
        if isinstance(ad, str) and ad in istenen:
            sonuc[ad] = satir
    return sonuc


def fonlama_ayristir(yanit, istenen) -> dict:
    """premiumIndex -> {sembol: {"oran_yuzde", "sonraki", "isaret_fiyati"}}; okunamayan sembol atlanır."""
    sonuc = {}
    for ad, s in _sembole_gore(yanit, istenen).items():
        oran = _sayi(s.get("lastFundingRate"))
        if oran is None or abs(oran) > 0.2:   # ±%20'den büyük oran veri hatasıdır
            continue
        sonuc[ad] = {"oran_yuzde": oran * 100.0, "sonraki": _zaman(s.get("nextFundingTime")),
                     "isaret_fiyati": _sayi(s.get("markPrice"))}
    return sonuc


def hacim_ayristir(yanit, istenen) -> dict:
    """ticker/24hr -> {sembol: {"hacim_usdt", "fiyat_degisim_yuzde"}}."""
    sonuc = {}
    for ad, s in _sembole_gore(yanit, istenen).items():
        hacim = _sayi(s.get("quoteVolume"))
        if hacim is None or hacim < 0:
            continue
        sonuc[ad] = {"hacim_usdt": hacim, "fiyat_degisim_yuzde": _sayi(s.get("priceChangePercent"))}
    return sonuc


def spread_ayristir(yanit, istenen) -> dict:
    """bookTicker -> {sembol: {"spread_bps"}}: en iyi alış ile satış arası, orta fiyatın on bindesi."""
    sonuc = {}
    for ad, s in _sembole_gore(yanit, istenen).items():
        alis, satis = _sayi(s.get("bidPrice")), _sayi(s.get("askPrice"))
        if not alis or not satis or alis <= 0 or satis < alis:
            continue
        sonuc[ad] = {"spread_bps": (satis - alis) / ((satis + alis) / 2.0) * 10_000.0}
    return sonuc


def acik_faiz_ayristir(yanit) -> list:
    """openInterestHist -> [(zaman, USDT değeri)], zamana göre sıralı; bozuk satır atlanır."""
    seri = []
    for s in _liste(yanit):
        zaman, deger = _zaman(s.get("timestamp")), _sayi(s.get("sumOpenInterestValue"))
        if zaman is None or deger is None or deger <= 0:
            continue
        seri.append((zaman, deger))
    seri.sort(key=lambda zd: zd[0])
    return seri


def acik_faiz_degisimi(seri: list, simdi: datetime) -> dict | None:
    """Açık faizin son değeri ve 1 / 4 / 24 saatlik yüzde değişimi.

    Geleceğe bakmaz: yalnız zamanı 'simdi' ya da öncesi olan noktalar kullanılır. Her pencere
    için karşılaştırma noktası, son noktadan en az o kadar eski olan EN YENİ noktadır; o nokta
    pencerenin 1,5 katından eskiyse (seride boşluk varsa) değişim None kalır.
    """
    gecmis = [(z, d) for z, d in seri if z <= simdi]
    if not gecmis:
        return None
    son_zaman, son = gecmis[-1]
    degisim = {}
    for ad, saat in AF_PENCERELER:
        hedef = son_zaman - timedelta(hours=saat)
        eski = [(z, d) for z, d in gecmis if z <= hedef]
        if not eski or (son_zaman - eski[-1][0]) > timedelta(hours=saat * 1.5):
            degisim[ad] = None
        else:
            degisim[ad] = (son / eski[-1][1] - 1.0) * 100.0
    return {"zaman": son_zaman, "usdt": son, "degisim": degisim}


# --------------------------------------------------------------------------
# Yenileme (ağa çıkan tek yer)
# --------------------------------------------------------------------------


def yenile(semboller: list, getirici=None, simdi: datetime | None = None, ara: float = ISTEK_ARASI) -> dict:
    """Verilen sembollerin ölçülerini ister ve önbelleğe yazar. Eşzamanlıdır; hesapla bunu çağırmaz.

    Başarılı grup yenisiyle değişir; başarısız grup eski değeriyle (ve eski zamanıyla) kalır.
    Dönen sözlük: {"basarili": istek sayısı, "hatali": istek sayısı}.
    """
    getirici = getirici or getir or varsayilan_getir
    semboller = [s for s in semboller if isinstance(s, str) and SEMBOL_KALIBI.match(s)]
    yeni, alinamadi = {}, {}
    basarili = hatali = 0

    def an() -> datetime:
        return simdi or datetime.now(timezone.utc)

    toplu = (("fonlama", "/fapi/v1/premiumIndex", fonlama_ayristir),
             ("hacim", "/fapi/v1/ticker/24hr", hacim_ayristir),
             ("spread", "/fapi/v1/ticker/bookTicker", spread_ayristir))
    for sira, (grup, yol, ayristir) in enumerate(toplu):
        if sira and ara:
            time.sleep(ara)
        try:
            sonuc = ayristir(getirici(yol, None), semboller)
            basarili += 1
        except Exception as hata:  # noqa: BLE001 - ağ ve biçim hatası sayfayı düşürmemeli
            alinamadi[grup] = _hata_metni(hata)
            hatali += 1
            continue
        zaman = an()
        for ad in semboller:
            if ad in sonuc:
                yeni.setdefault(ad, {})[grup] = {"zaman": zaman, **sonuc[ad]}
            else:
                alinamadi[f"{grup}:{ad}"] = "yanıtta yok"
    for ad in semboller:
        if ara:
            time.sleep(ara)
        try:
            seri = acik_faiz_ayristir(
                getirici("/futures/data/openInterestHist", {"symbol": ad, "period": AF_ARALIK, "limit": AF_ADET}))
            basarili += 1
        except Exception as hata:  # noqa: BLE001
            alinamadi[f"acik_faiz:{ad}"] = _hata_metni(hata)
            hatali += 1
            continue
        olcu = acik_faiz_degisimi(seri, an())
        if olcu is None:
            alinamadi[f"acik_faiz:{ad}"] = "yanıt boş"
        else:
            yeni.setdefault(ad, {})["acik_faiz"] = olcu

    with _kilit:
        for ad, gruplar in yeni.items():
            _durum["coinler"].setdefault(ad, {}).update(gruplar)
        # Artık listede olmayan coinler önbellekte birikmesin.
        for ad in [a for a in _durum["coinler"] if a not in semboller]:
            del _durum["coinler"][ad]
        _durum["alinamadi"] = alinamadi
        _durum["son_deneme_zamani"] = an()
        if basarili:
            _durum["son_basari_zamani"] = an()
            _durum["ardisik_hata"] = 0
        else:
            _durum["ardisik_hata"] += 1
    return {"basarili": basarili, "hatali": hatali}


def bekleme_saniye(ardisik_hata: int) -> float:
    """İki deneme arasındaki en az süre: her başarısız turda iki katına çıkar, en çok bir saat."""
    return float(min(EN_UZUN_BEKLEME, YENILEME_SANIYE * 2 ** min(max(ardisik_hata, 0), 8)))


def _arka_plan(semboller: list) -> None:
    try:
        yenile(semboller)
    except Exception:  # noqa: BLE001 - arka plan işi asla süreci düşürmemeli
        with _kilit:
            _durum["ardisik_hata"] += 1
    finally:
        with _kilit:
            _durum["son_deneme"] = time.monotonic()
            _durum["is"] = None


def _yenileme_baslat(semboller: list) -> bool:
    """Gerekiyorsa TEK bir arka plan işi başlatır; beklemez. Başlattıysa True."""
    with _kilit:
        if not _durum["ag_acik"] or not semboller or _durum["is"] is not None:
            return False
        son = _durum["son_deneme"]
        if son is not None:
            gecen = time.monotonic() - son
            eksik = any(ad not in _durum["coinler"] for ad in semboller) and not _durum["ardisik_hata"]
            if gecen < (YENI_COIN_BEKLEME if eksik else bekleme_saniye(_durum["ardisik_hata"])):
                return False
        is_parcacigi = threading.Thread(target=_arka_plan, args=(list(semboller),), daemon=True,
                                        name="karabasan-likidite")
        _durum["is"] = is_parcacigi
        _durum["son_deneme"] = time.monotonic()
        _durum["baslatilan"] += 1
    is_parcacigi.start()
    return True


# --------------------------------------------------------------------------
# Coin listesi, etiket, defter
# --------------------------------------------------------------------------


def coin_listesi(baglam: dict) -> list:
    """Açık pozisyonların coinleri (önde) + dönemde en çok işlem yapılanlar (en çok 8) + BTC."""
    coinler = {}

    def ekle(parite) -> dict | None:
        ad = _sembol(parite)
        if not SEMBOL_KALIBI.match(ad):
            return None   # kayıttan gelen metin doğrulanmadan adrese konmaz
        return coinler.setdefault(ad, {"sembol": ad, "parite": str(parite).split(":", 1)[0], "acik": False,
                                       "acik_botlar": [], "islem_sayisi": 0})

    for i in baglam.get("acik") or []:
        c = ekle(i.get("parite"))
        if c is not None:
            c["acik"] = True
            bot = str(i.get("kod") or i.get("bot") or "")
            if bot and bot not in c["acik_botlar"]:
                c["acik_botlar"].append(bot)
    sayac = {}
    for i in baglam.get("islemler") or []:
        ad = _sembol(i.get("parite"))
        if SEMBOL_KALIBI.match(ad):
            adet, _ = sayac.get(ad, (0, None))
            sayac[ad] = (adet + 1, i.get("parite"))
    for ad, (adet, parite) in sayac.items():
        if ad in coinler:
            coinler[ad]["islem_sayisi"] = adet
    en_cok = sorted(sayac.items(), key=lambda kv: (-kv[1][0], kv[0]))[:EN_FAZLA_ISLEM_COINI]
    for ad, (adet, parite) in en_cok:
        c = ekle(parite)
        if c is not None:
            c["islem_sayisi"] = adet
    ekle("BTC/USDT:USDT")
    return sorted(coinler.values(), key=lambda c: (not c["acik"], -c["islem_sayisi"], c["sembol"]))


def sikisma_riski(olculer: dict) -> dict:
    """Ölçülerden kaba sıkışma riski etiketi: dusuk / orta / yuksek / veri_yok.

    olculer: {"fonlama": yüzde, "af_24s": yüzde, "fiyat_24s": yüzde, "spread_bps", "hacim_usdt"};
    eksik olan None. Dönen 'nedenler' etiketin hangi ölçüden kaç puan aldığını yazar.
    Eşikler SINANMADI; bu bir tahmin değil, bakılacak yeri gösteren kaba bir uyarıdır.
    """
    e = ESIKLER
    nedenler, eksik, puan = [], [], 0

    def ekle(p: int, olcu: str, metin: str) -> None:
        nonlocal puan
        puan += p
        nedenler.append({"olcu": olcu, "puan": p, "metin": metin})

    fonlama = olculer.get("fonlama")
    if fonlama is None:
        eksik.append("fonlama")
    elif fonlama <= e["fonlama_eksi_yuksek"]:
        ekle(2, "fonlama", "Fonlama belirgin eksi: açığa satan ödüyor, kalabalık açığa satışta.")
    elif fonlama <= e["fonlama_eksi_orta"]:
        ekle(1, "fonlama", "Fonlama eksi: açığa satan ödüyor.")
    else:
        ekle(0, "fonlama", "Fonlama artı ya da sıfıra yakın: açığa satan ödemiyor.")

    af = olculer.get("af_24s")
    if af is None:
        eksik.append("acik_faiz")
    elif af >= e["af_artis_yuksek"]:
        ekle(2, "acik_faiz", "Açık faiz 24 saatte hızla arttı: kaldıraçlı pozisyon birikiyor.")
    elif af >= e["af_artis_orta"]:
        ekle(1, "acik_faiz", "Açık faiz 24 saatte arttı.")
    else:
        ekle(0, "acik_faiz", "Açık faizde belirgin artış yok.")

    fiyat = olculer.get("fiyat_24s")
    if fiyat is not None and fiyat >= e["fiyat_artis"]:
        ekle(1, "fiyat", "Fiyat 24 saatte sert yükseldi: açığa satanlar zaten baskı altında.")

    spread, hacim = olculer.get("spread_bps"), olculer.get("hacim_usdt")
    ince = 0
    if spread is None:
        eksik.append("spread")
    elif spread >= e["spread_cok_ince"]:
        ince = 2
    elif spread >= e["spread_ince"]:
        ince = 1
    if hacim is None:
        eksik.append("hacim")
    elif hacim < e["hacim_cok_ince"]:
        ince = max(ince, 2)
    elif hacim < e["hacim_ince"]:
        ince = max(ince, 1)
    if spread is not None or hacim is not None:
        ekle(ince, "incelik", ("Piyasa çok ince: küçük alım bile fiyatı sıçratabilir." if ince == 2 else
                               "Piyasa ince: spread geniş ya da hacim düşük." if ince == 1 else
                               "Piyasa ince görünmüyor."))

    if len(GRUPLAR) - len(eksik) < e["en_az_olcu"]:
        etiket = "veri_yok"
    elif puan >= e["yuksek_puan"]:
        etiket = "yuksek"
    elif puan >= e["orta_puan"]:
        etiket = "orta"
    else:
        etiket = "dusuk"
    return {"etiket": etiket, "puan": puan, "nedenler": nedenler, "eksik": eksik, "ince": ince >= 1}


def defter_ozeti(veri_klasoru, simdi: datetime) -> dict:
    """Emir defteri kaydının (yalnız BTC) son satırı. Tek küçük sorgu, yalnız okuma; dosya yoksa var=False."""
    yol = Path(veri_klasoru) / "kayit" / "defter.sqlite"
    try:
        if not yol.exists():
            return {"var": False}
        vt = sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=1)
        try:
            satir = vt.execute("SELECT zaman, dengesizlik_20, dengesizlik_tum, makas_bps FROM ornek_v1 "
                               "ORDER BY zaman DESC LIMIT 1").fetchone()
        finally:
            vt.close()
    except (sqlite3.Error, OSError):
        return {"var": False}
    if not satir or _sayi(satir[0]) is None:
        return {"var": False}
    yas = max(0.0, simdi.timestamp() - float(satir[0]))
    return {"var": True, "zaman": datetime.fromtimestamp(float(satir[0]), tz=timezone.utc), "yas_saniye": yas,
            "bayat": yas > DEFTER_BAYAT_SANIYE, "dengesizlik_20": _sayi(satir[1]),
            "dengesizlik_tum": _sayi(satir[2]), "makas_bps": _sayi(satir[3])}


# --------------------------------------------------------------------------
# Ekranın verisi
# --------------------------------------------------------------------------


def _yas_dakika(zaman, simdi: datetime) -> float | None:
    return None if zaman is None else max(0.0, (simdi - zaman).total_seconds() / 60.0)


def hesapla(baglam: dict) -> dict:
    """Likidite ekranının verisi. Ağda beklemez; gerekirse arka planda yenileme başlatır."""
    simdi = baglam.get("simdi") or datetime.now(timezone.utc)
    liste = coin_listesi(baglam)
    _yenileme_baslat([c["sembol"] for c in liste])
    with _kilit:
        ag_acik = _durum["ag_acik"]
        onbellek = {ad: {g: dict(v) for g, v in gruplar.items()} for ad, gruplar in _durum["coinler"].items()}
        alinamadi = dict(_durum["alinamadi"])
        son_basari, son_deneme = _durum["son_basari_zamani"], _durum["son_deneme_zamani"]
        ardisik_hata = _durum["ardisik_hata"]

    coinler = []
    for c in liste:
        gruplar = onbellek.get(c["sembol"], {})
        satir = dict(c)
        kullan = {}
        for grup in GRUPLAR:
            veri = gruplar.get(grup)
            hata = alinamadi.get(f"{grup}:{c['sembol']}") or alinamadi.get(grup)
            if veri is None:
                satir[grup] = None
            else:
                yas = _yas_dakika(veri.get("zaman"), simdi)
                veri["yas_dakika"] = yas
                veri["eski"] = yas is None or yas > KULLANIM_SINIRI_DAKIKA
                satir[grup] = veri
                if not veri["eski"]:
                    kullan[grup] = veri
            satir[f"{grup}_hata"] = hata if ag_acik else None
        satir["risk"] = sikisma_riski({
            "fonlama": (kullan.get("fonlama") or {}).get("oran_yuzde"),
            "af_24s": ((kullan.get("acik_faiz") or {}).get("degisim") or {}).get("24s"),
            "fiyat_24s": (kullan.get("hacim") or {}).get("fiyat_degisim_yuzde"),
            "spread_bps": (kullan.get("spread") or {}).get("spread_bps"),
            "hacim_usdt": (kullan.get("hacim") or {}).get("hacim_usdt"),
        })
        coinler.append(satir)

    veri_var = any(c[g] is not None for c in coinler for g in GRUPLAR)
    if not ag_acik:
        durum = "kapali"
    elif veri_var:
        durum = "hazir"
    elif son_deneme is None:
        durum = "bekliyor"
    else:
        durum = "hata"
    return {
        "ag_acik": ag_acik,
        "durum": durum,
        "guncelleme": son_basari,
        "yas_dakika": _yas_dakika(son_basari, simdi),
        "ardisik_hata": ardisik_hata,
        "sonraki_deneme_dakika": bekleme_saniye(ardisik_hata) / 60.0,
        "genel_hatalar": {g: alinamadi[g] for g in GRUPLAR if g in alinamadi} if ag_acik else {},
        "coinler": coinler,
        "defter": defter_ozeti(baglam.get("veri_klasoru") or ".", simdi),
        "tasfiye": {"var": False},
        "esikler": dict(ESIKLER),
        "kullanim_siniri_dakika": KULLANIM_SINIRI_DAKIKA,
    }
