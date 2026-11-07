"""Bot kriter ayar laboratuvarı: bir botun kriterlerini geçmişe sarıp denemek (7 Kasım 2026, Ahmet'in isteği).

Ahmet bir bot, bir coin ve bir geçmiş dönem seçer; her kriterin sayısını değiştirir; geçmiş veride
giriş ve çıkışların nereye düştüğünü, hangi kriterin hangi girişi engellediğini görür.

**Hiçbir şeyi değiştirmez.** Canlı botların kural dosyaları ve ayarları olduğu gibi kalır; burada
yapılan değişiklik yalnız bu isteğin bellekteki bir kopyasındadır (3. kural: sınav sürerken strateji
ayarı değişmez). Bulunan güzel bir ayar bir öneridir, kendiliğinden uygulanmaz; uygulamak yeni bir
sanal bot ve kendi 30 günü demektir. Çok sayıda ayar denendikçe birinin geçmişte şans eseri iyi
görünmesi kolaylaşır; sayfa bunu açıkça söyler.

Mumlar Binance'in herkese açık, anahtarsız adresinden gelir; emir yok. Hesap, bağımsız benzetimle
(`benzetim.benzet`) yapılır: hazır motor değildir, Karabasan durum süzgeci ve (SMDK'da) emir defteri
onayı uygulanmaz.
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import botlar as _botlar
from . import gostergeler as g
from .benzetim import benzet
from .kural import KuralHatasi, _kosul, _sutun_adi, gereken_ek_mum, gereken_mum, kural_dogrula, kural_yukle, sinyal_uret
from .stop_sonrasi import SPOT_ADRESI, VADELI_ADRESI, sembol

COINLER = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "ADA", "LINK", "AVAX", "LTC", "BCH", "TRX"]
EN_FAZLA_GUN = 45
EN_FAZLA_GERI = 365
ONBELLEK_SN = 900
TARAMA_ADET = 5
KOMISYON_YUZDE = 0.05   # vadeli, taraf başına (botlar.VARSAYILAN_AYARLAR)

_UST_DILIM = {"1d": "günlük", "1h": "1 saatlik", "15m": "15 dakikalık", "4h": "4 saatlik"}
_SAYISAL_ALANLAR = ("periyot", "hizli", "yavas", "sinyal", "omur", "en_az_yuzde")


class AyarHatasi(ValueError):
    """Kullanıcıya olduğu gibi gösterilebilen hata."""


# --------------------------------------------------------------------------
# Kural içinde yol: "giris.hepsi.3.sag" gibi
# --------------------------------------------------------------------------


def _al(kok, yol: str):
    for parca in yol.split("."):
        kok = kok[int(parca)] if isinstance(kok, list) else kok[parca]
    return kok


def _koy(kok, yol: str, deger) -> None:
    parcalar = yol.split(".")
    ust = _al(kok, ".".join(parcalar[:-1])) if len(parcalar) > 1 else kok
    son = parcalar[-1]
    if isinstance(ust, list):
        ust[int(son)] = deger
    else:
        ust[son] = deger


def _say(deger) -> bool:
    return isinstance(deger, (int, float)) and not isinstance(deger, bool)


# --------------------------------------------------------------------------
# Düz Türkçe adlar
# --------------------------------------------------------------------------

_TABAN = {"yuksek": "Mum tepesi", "dusuk": "Mum dibi", "kapanis": "Kapanış", "acilis": "Açılış", "hacim": "Hacim"}
_SONEK = {"_yon": "yönü", "_denge": "denge çizgisi", "_kirilim": "kırılımı", "_sblok_alt": "satış bloğunun alt sınırı",
          "_sblok_ust": "satış bloğunun üst sınırı", "_ablok_alt": "alış bloğunun alt sınırı",
          "_ablok_ust": "alış bloğunun üst sınırı", "_boga": "boğa uyumsuzluğu sayısı",
          "_ayi": "ayı uyumsuzluğu sayısı", "_hist": "histogramı", "_fark": "histogramı",
          "_blok_alt": "alış bloğunun alt sınırı", "_blok_ust": "alış bloğunun üst sınırı", "_tepe": "son tepesi",
          "_dip": "son dibi", "_boga_ust": "boğa boşluğunun üst sınırı", "_boga_alt": "boğa boşluğunun alt sınırı",
          "_ayi_ust": "ayı boşluğunun üst sınırı", "_ayi_alt": "ayı boşluğunun alt sınırı"}


def _gosterge_adi(ad: str, tanim: dict) -> str:
    tur, per = tanim.get("tur"), tanim.get("periyot")
    if tur == "sma" and per == 1:
        etiket = "Kapanış"
    elif tur in ("sma", "ema", "rsi", "atr"):
        etiket = f"{tur.upper()} {per}"
    elif tur == "hacim_ort":
        etiket = f"Hacim ortalaması {per}"
    elif tur == "yapi":
        etiket = "Piyasa yapısı"
    elif tur == "macd":
        etiket = "MACD"
    else:
        etiket = str(tur).capitalize() + (f" {per}" if per else "")
    dilim = tanim.get("dilim")
    if dilim in _UST_DILIM:
        etiket += f" ({_UST_DILIM[dilim]})"
    return etiket


def sutun_etiketi(kural: dict, sutun: str) -> str:
    """Bir tablo sütununun düz adı ("rsi14_1s" -> "RSI 14 (1 saatlik)")."""
    if sutun in _TABAN:
        return _TABAN[sutun]
    en_uyan = None
    for ad in kural["gostergeler"]:
        if (sutun == ad or sutun.startswith(ad + "_")) and (en_uyan is None or len(ad) > len(en_uyan)):
            en_uyan = ad
    if en_uyan is None:
        return sutun
    etiket = _gosterge_adi(en_uyan, kural["gostergeler"][en_uyan])
    ek = sutun[len(en_uyan):]
    if ek in _SONEK:
        etiket = f"{etiket} {_SONEK[ek]}" if "(" not in etiket else \
            etiket.replace(" (", f" {_SONEK[ek]} (", 1)
    elif ek:
        etiket += f" {ek.strip('_')}"
    return etiket


def _sayi_yazi(x) -> str:
    return f"{x:g}".replace(".", ",") if _say(x) else str(x)


def _islenen_yazi(kural: dict, islenen) -> str:
    if _say(islenen):
        return _sayi_yazi(islenen)
    if isinstance(islenen, str):
        return sutun_etiketi(kural, islenen)
    yazi = sutun_etiketi(kural, islenen["ad"])
    if islenen.get("kaydir"):
        yazi += f" ({int(islenen['kaydir'])} mum öncesi)"
    if islenen.get("carpan", 1.0) != 1.0:
        yazi += f" × {_sayi_yazi(islenen['carpan'])}"
    return yazi


_ISLEM = {">": "üstünde", "<": "altında", ">=": "en az", "<=": "en çok",
          "yukari_keser": "yukarı keser", "asagi_keser": "aşağı keser"}


def kosul_yazisi(kural: dict, kosul: dict) -> str:
    if "herhangi" in kosul:
        parca = " ya da ".join(kosul_yazisi(kural, k) for k in kosul["herhangi"])
        return parca + (f" (son {kosul['son_n_mumda']} mumdan birinde)" if kosul.get("son_n_mumda", 1) > 1 else "")
    if "hepsi" in kosul:
        return " ve ".join(kosul_yazisi(kural, k) for k in kosul["hepsi"])
    yazi = f"{_islenen_yazi(kural, kosul['sol'])} {_ISLEM[kosul['islem']]}: {_islenen_yazi(kural, kosul['sag'])}"
    if kosul.get("son_n_mumda", 1) > 1:
        yazi += f" (son {kosul['son_n_mumda']} mumdan birinde)"
    return yazi


# --------------------------------------------------------------------------
# Ayarlanabilir sayılar
# --------------------------------------------------------------------------


def _kosul_sayilari(kural: dict, kosul: dict, yol: str, cikti: list) -> None:
    """Bir koşulun (ve içindekilerin) ayarlanabilir sayıları: (yol, ad, değer)."""
    for alt in ("hepsi", "herhangi"):
        if alt in kosul:
            for i, parca in enumerate(kosul[alt]):
                _kosul_sayilari(kural, parca, f"{yol}.{alt}.{i}", cikti)
            if kosul.get("son_n_mumda") is not None:
                cikti.append((f"{yol}.son_n_mumda", "Hangi mumlarda aranır (son kaç mum)", kosul["son_n_mumda"]))
            return
    etiket = _islenen_yazi(kural, kosul["sol"])
    if _say(kosul["sag"]):
        cikti.append((f"{yol}.sag", f"Eşik · {etiket}", kosul["sag"]))
    elif isinstance(kosul["sag"], dict):
        sag = kosul["sag"]
        if sag.get("carpan") is not None:
            cikti.append((f"{yol}.sag.carpan", f"Çarpan · {sutun_etiketi(kural, sag['ad'])}", sag["carpan"]))
        if sag.get("kaydir"):
            cikti.append((f"{yol}.sag.kaydir", f"Kaç mum öncesiyle · {sutun_etiketi(kural, sag['ad'])}", sag["kaydir"]))
    if kosul.get("son_n_mumda") is not None:
        karsi = f" · {_islenen_yazi(kural, kosul['sag'])}" if isinstance(kosul["sag"], (str, dict)) else ""
        cikti.append((f"{yol}.son_n_mumda", f"Son kaç mumda aranır · {etiket}{karsi}", kosul["son_n_mumda"]))


def kriterler(kural: dict) -> list[dict]:
    """Girişin her şartı: düz yazı ve içindeki ayarlanabilir sayılar. Sıra = giriş şartlarının sırası."""
    sonuc = []
    for i, kosul in enumerate(kural["giris"]["hepsi"]):
        sayilar: list = []
        _kosul_sayilari(kural, kosul, f"giris.hepsi.{i}", sayilar)
        sonuc.append({"sira": i, "yazi": kosul_yazisi(kural, kosul), "sayilar": sayilar})
    return sonuc


def gosterge_sayilari(kural: dict) -> list[tuple[str, str, float]]:
    """Göstergelerin periyotları vb. Bir gösterge birkaç şartta kullanılabilir; değişiklik hepsini etkiler."""
    cikti = []
    for ad, tanim in kural["gostergeler"].items():
        for alan in _SAYISAL_ALANLAR:
            if _say(tanim.get(alan)) and not (tanim.get("tur") == "sma" and tanim.get("periyot") == 1 and alan == "periyot"):
                cikti.append((f"gostergeler.{ad}.{alan}", f"{_gosterge_adi(ad, tanim)} · {alan}", tanim[alan]))
    return cikti


def cikis_sayilari(kural: dict) -> list[tuple[str, str, float]]:
    cikti = []
    limit = kural.get("giris_limiti")
    if limit:
        cikti += [("giris_limiti.atr_kat", "Giriş emri: oynaklık katı (ATR)", limit["atr_kat"]),
                  ("giris_limiti.en_az_yuzde", "Giriş emri: en az uzaklık %", limit["en_az_yuzde"]),
                  ("giris_limiti.en_fazla_yuzde", "Giriş emri: en çok uzaklık %", limit["en_fazla_yuzde"]),
                  ("giris_limiti.sure_dakika", "Giriş emri: bekleme (dakika)", limit["sure_dakika"])]
    cikis = kural["cikis"]
    if _say(cikis.get("zarar_durdur_yuzde")):
        cikti.append(("cikis.zarar_durdur_yuzde", "Stop %", cikis["zarar_durdur_yuzde"]))
    if _say(cikis.get("kar_hedefi_yuzde")):
        cikti.append(("cikis.kar_hedefi_yuzde", "Kâr hedefi %", cikis["kar_hedefi_yuzde"]))
    if cikis.get("iz_suren_stop"):
        cikti += [("cikis.iz_suren_stop.tetik_yuzde", "İz süren stop: devreye girme kârı %",
                   cikis["iz_suren_stop"]["tetik_yuzde"]),
                  ("cikis.iz_suren_stop.mesafe_yuzde", "İz süren stop: en iyi fiyatın gerisi %",
                   cikis["iz_suren_stop"]["mesafe_yuzde"])]
    if _say(cikis.get("sure_asimi_dakika")):
        cikti.append(("cikis.sure_asimi_dakika", "En uzun süre (dakika)", cikis["sure_asimi_dakika"]))
    if _say(kural.get("bekleme_dakika")):
        cikti.append(("bekleme_dakika", "Stoptan sonra bekleme (dakika)", kural["bekleme_dakika"]))
    return cikti


def tum_sayilar(kural: dict) -> list[tuple[str, str, float]]:
    """Ekrandaki sırayla bütün ayarlanabilir sayılar (indeksleri form alanı adıdır: p0, p1, ...)."""
    sirali = [s for k in kriterler(kural) for s in k["sayilar"]]
    return sirali + gosterge_sayilari(kural) + cikis_sayilari(kural)


def kural_hazirla(bot: str) -> dict:
    for ad, _sinif, kod, _piyasa in _botlar.BOTLAR:
        if ad == bot:
            return kural_yukle(kod)
    raise AyarHatasi("Böyle bir bot yok.")


def uygula(kural: dict, degerler: dict[str, float]) -> dict:
    """Kuralın kopyasını verilen sayılarla değiştirir ve doğrular; asıl kural dokunulmaz kalır."""
    kopya = copy.deepcopy(kural)
    for yol, yeni in degerler.items():
        eski = _al(kopya, yol)
        if isinstance(eski, int) and not isinstance(eski, bool):
            if float(yeni) != int(yeni):
                raise AyarHatasi("Bu alan tam sayı olmalı.")
            yeni = int(yeni)
        _koy(kopya, yol, yeni)
    try:
        kural_dogrula(kopya)
    except KuralHatasi as hata:
        raise AyarHatasi(f"Bu değerler kabul edilmedi: {hata}") from hata
    return kopya


def sayi_oku(metin: str) -> float:
    try:
        deger = float(str(metin).strip().replace(",", "."))
    except ValueError as hata:
        raise AyarHatasi(f"“{metin}” bir sayı değil.") from hata
    if deger != deger or abs(deger) > 1e9:
        raise AyarHatasi(f"“{metin}” geçerli bir sayı değil.")
    return deger


# --------------------------------------------------------------------------
# Veri
# --------------------------------------------------------------------------


def binance_getir(parite: str, piyasa: str, aralik: str, bas: datetime, son: datetime) -> pd.DataFrame:
    """[bas, son] arasındaki mumlar; sayfa sayfa indirir. Sütunlar: date, open, high, low, close, volume."""
    taban = (os.environ.get("KARABASAN_BINANCE_VADELI", VADELI_ADRESI) if piyasa == "vadeli"
             else os.environ.get("KARABASAN_BINANCE_SPOT", SPOT_ADRESI))
    dk = g.dilim_dakika(aralik)
    satirlar: list = []
    imlec = int(bas.timestamp() * 1000)
    bitis = int(son.timestamp() * 1000)
    for _ in range(60):
        sorgu = urllib.parse.urlencode({"symbol": sembol(parite), "interval": aralik,
                                        "startTime": imlec, "endTime": bitis, "limit": 1000})
        istek = urllib.request.Request(f"{taban}?{sorgu}", headers={"User-Agent": "karabasan-bot"})
        with urllib.request.urlopen(istek, timeout=12) as yanit:
            parca = json.loads(yanit.read().decode("utf-8"))
        satirlar += parca
        if len(parca) < 1000:
            break
        imlec = int(parca[-1][0]) + dk * 60_000
    return cerceve(satirlar)


def cerceve(satirlar) -> pd.DataFrame:
    tablo = pd.DataFrame({
        "date": pd.to_datetime([int(s[0]) for s in satirlar], unit="ms", utc=True),
        "open": [float(s[1]) for s in satirlar], "high": [float(s[2]) for s in satirlar],
        "low": [float(s[3]) for s in satirlar], "close": [float(s[4]) for s in satirlar],
        "volume": [float(s[5]) for s in satirlar],
    })
    return tablo.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


class VeriOnbellegi:
    """Aynı coin ve dönem için indirilen mumlar 15 dakika saklanır; her tıklamada yeniden indirilmez."""

    def __init__(self, en_fazla: int = 24):
        self._kilit = threading.Lock()
        self._veri: dict = {}
        self.en_fazla = en_fazla

    def al(self, anahtar, uret):
        with self._kilit:
            kayit = self._veri.get(anahtar)
            if kayit and time.monotonic() - kayit[0] < ONBELLEK_SN:
                return kayit[1]
        deger = uret()
        with self._kilit:
            if len(self._veri) >= self.en_fazla:
                self._veri.pop(next(iter(self._veri)))
            self._veri[anahtar] = (time.monotonic(), deger)
        return deger


def _kapanmis(tablo: pd.DataFrame, dilim: str, bitis: datetime) -> pd.DataFrame:
    """Yalnız kapanışı `bitis`ten önce olan mumlar: pencerenin ötesi (gelecek) hiç görülmez."""
    kapanis = tablo["date"] + pd.Timedelta(minutes=g.dilim_dakika(dilim))
    return tablo[kapanis <= pd.Timestamp(bitis)].reset_index(drop=True)


def veri_topla(kural: dict, coin: str, piyasa: str, bitis: datetime, gun: int, getir=binance_getir,
               onbellek: VeriOnbellegi | None = None, diger: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """(taban mumlar, ek_veri). Taban mumlar pencere + göstergelerin oturması için gereken başlangıç mumlarını içerir.

    diger: aynı veriyle çalıştırılacak ikinci kural (canlı ayar ile denenen ayar); ikisinin de ihtiyacına yetecek kadar mum alınır.
    """
    kurallar = [kural] + ([diger] if diger else [])
    taban = kural["zaman_dilimi"]
    dk = g.dilim_dakika(taban)
    bas = bitis - timedelta(days=gun) - timedelta(minutes=(max(gereken_mum(k) for k in kurallar) + 5) * dk)
    saat = lambda z: int(z.timestamp() // 3600)  # noqa: E731 - önbellek anahtarı için saate yuvarla

    def indir(dilim: str, baslangic: datetime) -> pd.DataFrame:
        anahtar = (coin, piyasa, dilim, saat(baslangic), saat(bitis))
        uret = lambda: getir(f"{coin}/USDT", piyasa, dilim, baslangic, bitis)  # noqa: E731
        tablo = onbellek.al(anahtar, uret) if onbellek else uret()
        return _kapanmis(tablo, dilim, bitis)

    df = indir(taban, bas)
    ek: dict = {}
    ek_ihtiyac: dict = {}
    for k in kurallar:
        for dilim, adet in gereken_ek_mum(k).items():
            ek_ihtiyac[dilim] = max(adet, ek_ihtiyac.get(dilim, 0))
    for dilim, adet in ek_ihtiyac.items():
        ek_bas = bitis - timedelta(days=gun) - timedelta(minutes=(adet + 5) * g.dilim_dakika(dilim))
        tablo = indir(dilim, ek_bas)
        if len(tablo):
            ek[dilim] = tablo
    return df, ek


# --------------------------------------------------------------------------
# Deneme
# --------------------------------------------------------------------------


def _ozet(islemler: list[dict]) -> dict:
    net = [float(i["net_yuzde"]) for i in islemler]
    return {"islem": len(islemler), "kazanan": sum(1 for x in net if x > 0), "net_toplam": sum(net),
            "en_kotu": min(net) if net else None}


def _gosterge_bul(kural: dict, sutun: str):
    """Bir sütunun hangi göstergeden geldiği: (gösterge adı, sonek) ya da (None, "")."""
    en_uyan = None
    for ad in kural["gostergeler"]:
        if (sutun == ad or sutun.startswith(ad + "_")) and (en_uyan is None or len(ad) > len(en_uyan)):
            en_uyan = ad
    return (en_uyan, sutun[len(en_uyan):]) if en_uyan else (None, "")


def _kosul_sutunlari(kosul: dict, cikti: list) -> None:
    for alt in ("hepsi", "herhangi"):
        if alt in kosul:
            for parca in kosul[alt]:
                _kosul_sutunlari(parca, cikti)
            return
    for taraf in (kosul["sol"], kosul["sag"]):
        if isinstance(taraf, str):
            cikti.append(taraf)
        elif isinstance(taraf, dict):
            cikti.append(taraf["ad"])
            if taraf.get("ekle"):
                cikti.append(taraf["ekle"]["ad"])


_CIZGI_SONEKLERI = ("_denge", "_tepe", "_dip")
_BANT_SONEKLERI = {"_sblok_alt": "_sblok_ust", "_blok_alt": "_blok_ust", "_boga_alt": "_boga_ust", "_ayi_alt": "_ayi_ust"}


def fiyat_katmanlari(kural: dict, tablo: pd.DataFrame) -> list[dict]:
    """Fiyat grafiğinin üstüne çizilebilecek göstergeler: kriter sırası, çizgi ya da bant, düz ad, sütunlar.

    Yalnız fiyatla aynı ölçekte olanlar (ortalamalar, denge çizgisi, son tepe / dip, emir bloğu, boşluk) çizilir;
    RSI ve hacim gibi başka ölçekli şartlar grafiğin altındaki şeritlerde görünür.
    """
    katmanlar, gorulen = [], set()
    for sira, kosul in enumerate(kural["giris"]["hepsi"]):
        sutunlar: list = []
        _kosul_sutunlari(kosul, sutunlar)
        for ham in sutunlar:
            sutun = _sutun_adi(ham)
            ad, ek = _gosterge_bul(kural, sutun)
            if ad is None or sutun not in tablo or (sira, sutun) in gorulen:
                continue
            tanim = kural["gostergeler"][ad]
            gorulen.add((sira, sutun))
            if tanim.get("tur") in ("ema", "sma") and ek == "" and tanim.get("periyot", 0) > 1:
                katmanlar.append({"sira": sira, "tur": "cizgi", "ad": sutun_etiketi(kural, sutun), "sutun": sutun})
            elif tanim.get("tur") == "yapi" and ek in _CIZGI_SONEKLERI:
                katmanlar.append({"sira": sira, "tur": "cizgi", "ad": sutun_etiketi(kural, sutun), "sutun": sutun})
            elif ek in _BANT_SONEKLERI and ad + _BANT_SONEKLERI[ek] in tablo:
                ust = ad + _BANT_SONEKLERI[ek]
                if (sira, ust) not in gorulen:
                    gorulen.add((sira, ust))
                    katmanlar.append({"sira": sira, "tur": "bant",
                                      "ad": sutun_etiketi(kural, sutun).replace("alt sınırı", "bölgesi"),
                                      "sutun": sutun, "ust": ust})
    return katmanlar


def katman_verisi(tablo: pd.DataFrame, kural: dict, maske, seriler: list) -> dict:
    """Grafiğin altındaki şeritler (her şart + kesişim) ve fiyat üstü çizgi / bantlar; hepsi pencere içi."""
    tarih = pd.to_datetime(tablo["date"], utc=True)[maske]
    cizgiler = []
    for k in fiyat_katmanlari(kural, tablo):
        kayit = {"sira": k["sira"], "tur": k["tur"], "ad": k["ad"],
                 "deger": tablo[k["sutun"]].astype(float).to_numpy()[maske]}
        if k["tur"] == "bant":
            kayit["ust"] = tablo[k["ust"]].astype(float).to_numpy()[maske]
        cizgiler.append(kayit)
    return {"tarih": list(tarih), "kosullar": [s[maske] for s in seriler],
            "hepsi": tablo["sinyal"].to_numpy(dtype=bool)[maske], "cizgiler": cizgiler}


def calistir(kural: dict, df: pd.DataFrame, ek_veri: dict, pencere_bas: pd.Timestamp,
             kriter_olc: bool = False) -> dict:
    """Kuralı verilen mumlarda çalıştırır; pencere içinde açılan işlemleri döndürür.

    kriter_olc: her giriş şartı için pencerede kaç mumda doğru olduğu, "yalnız bu şart yüzünden
    giriş olmadı" mumları (şartı gevşetirsen sinyale dönecek yerler) ve grafiğin katman verisi
    (şartların kesişimi, fiyat üstü çizgi ve bantlar).
    """
    tablo = sinyal_uret(df, kural, ek_veri)
    islemler = benzet(df, kural, komisyon_yuzde=KOMISYON_YUZDE, ek_veri=ek_veri, hazir_tablo=tablo)
    islemler = [i for i in islemler if pd.Timestamp(i["giris_zamani"]) >= pencere_bas]
    maske = (pd.to_datetime(tablo["date"], utc=True) >= pencere_bas).to_numpy()
    sonuc = {"islemler": islemler, "ozet": _ozet(islemler), "sinyal_sayisi": int(tablo["sinyal"].to_numpy()[maske].sum())}
    if kriter_olc:
        seriler = [_kosul(tablo, k).fillna(False).astype(bool).to_numpy() for k in kural["giris"]["hepsi"]]
        sonuc["kriterler"] = kriter_olcumu(tablo, seriler, maske)
        sonuc["katman"] = katman_verisi(tablo, kural, maske, seriler)
    return sonuc


def kriter_olcumu(tablo: pd.DataFrame, seriler: list, maske) -> list[dict]:
    """Her giriş şartı için: doğru mum oranı, tek başına engellediği mum sayısı ve o mumların zamanı."""
    tarih = pd.to_datetime(tablo["date"], utc=True)
    sonuc = []
    for i, seri in enumerate(seriler):
        digerleri = pd.Series(True, index=tablo.index).to_numpy()
        for j, baska in enumerate(seriler):
            if j != i:
                digerleri = digerleri & baska
        engel = digerleri & ~seri & maske
        sonuc.append({"sira": i, "dogru_oran": float(seri[maske].mean()) if maske.any() else 0.0,
                      "engel_sayisi": int(engel.sum()),
                      "engel_zamanlari": [t.to_pydatetime() for t in tarih[engel]][:400]})
    return sonuc


def tarama_degerleri(deger) -> list:
    """Bir sayının çevresinde denenecek değerler (yarısı … bir buçuk katı)."""
    if isinstance(deger, int) and not isinstance(deger, bool):
        adaylar = {max(1, round(deger * k)) for k in (0.5, 0.75, 1.0, 1.25, 1.5)} | {deger}
        return sorted(adaylar)[:TARAMA_ADET + 2]
    adaylar = {round(float(deger) * k, 4) for k in (0.5, 0.75, 1.0, 1.25, 1.5)} | {float(deger)}
    return sorted(adaylar)[:TARAMA_ADET + 2]


def parca_secimi(gun: int) -> int:
    """Grafikte tek çubuğun kapsadığı dakika: pencere uzadıkça çubuk büyür (en çok ~400 çubuk)."""
    for dk in (5, 15, 60, 240, 1440):
        if gun * 1440 / dk <= 400:
            return dk
    return 1440
