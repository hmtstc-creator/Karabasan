"""Panodaki geçmiş test: denenen bot ayarını sunucudaki indirilmiş mumlarda çalıştırır (10 Kasım 2026, Ahmet'in isteği).

Veri: 12 aylık test ve panel sınaması için sunucuya indirilen dosyalar
(user_data/data/binance/futures/<COIN>_USDT_USDT-<dilim>-futures.feather). Dosyası olmayan coin, dönem 90 günü
geçmiyorsa Binance'in herkese açık mum adresinden indirilir; geçiyorsa atlanır ve bu sonuçta yazılır.

Hesap bağımsız benzetimdir (karabasan.benzetim), 12 aylık testle aynı motor. Karabasan süzgeci uygulanmaz.
Sonuç yalnız gösterilir: canlı kural dosyaları ve botlar değişmez (3. kural). Dönem ikiye ayrılır
(ilk %70 "seçim", son %30 "doğrulama"): ayar seçime bakılarak beğenildiyse, doğrulama onun görmediği dönemdir.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from . import ayar as a
from . import gostergeler as g
from . import karne as kr
from . import uzay as _uzay
from .benzetim import benzet
from .botlar import ayarlari_yukle
from .kural import ek_veri_topla, gereken_ek_mum, gereken_mum

GUNLER = (30, 90, 180, 365)
INDIRME_SINIRI_GUN = 90
EN_FAZLA_COIN = 21
SECIM_PAYI = 0.7
SUTUNLAR = ["date", "open", "high", "low", "close", "volume"]
NEDEN_ADI = {"kar_hedefi": "Kâr hedefi", "zarar_durdur": "Stop", "sure_asimi": "Süre doldu",
             "cikis_sinyali": "Çıkış sinyali", "iz_suren_stop": "İz süren stop"}


class TestHatasi(ValueError):
    """Kullanıcıya olduğu gibi gösterilebilen düz Türkçe hata."""


def _utc(z) -> pd.Timestamp:
    z = pd.Timestamp(z)
    return z.tz_localize("UTC") if z.tzinfo is None else z.tz_convert("UTC")


class YerelVeri:
    """Sunucuya indirilmiş mum dosyalarını okur; son okunanları bellekte tutar (dosya değişince yeniden okur)."""

    def __init__(self, klasor: Path, en_fazla: int = 48, oku=None):
        self._oku = oku or pd.read_feather   # testlerde başka okuyucu verilir (buradaki ortamda pyarrow yok)
        self.kok = Path(klasor) / "data" / "binance" / "futures"
        self._kilit = threading.Lock()
        self._bellek: OrderedDict[tuple, tuple[float, pd.DataFrame]] = OrderedDict()
        self._en_fazla = en_fazla

    def _yol(self, coin: str, dilim: str) -> Path:
        return self.kok / f"{coin}_USDT_USDT-{dilim}-futures.feather"

    def coinler(self, dilim: str = "5m") -> list[str]:
        try:
            adlar = [p.name.split("_USDT_USDT-")[0] for p in self.kok.glob(f"*_USDT_USDT-{dilim}-futures.feather")]
        except OSError:
            return []
        return sorted(ad for ad in adlar if ad.isalnum() and len(ad) <= 12)

    def yukle(self, coin: str, dilim: str) -> pd.DataFrame | None:
        yol = self._yol(coin, dilim)
        try:
            damga = yol.stat().st_mtime
        except OSError:
            return None
        with self._kilit:
            eldeki = self._bellek.get((coin, dilim))
            if eldeki and eldeki[0] == damga:
                self._bellek.move_to_end((coin, dilim))
                return eldeki[1]
        try:
            tablo = self._oku(yol)[SUTUNLAR]
        except Exception:  # noqa: BLE001 - bozuk ya da yarım dosya "veri yok" sayılır
            return None
        tablo["date"] = pd.to_datetime(tablo["date"], utc=True)
        tablo = tablo.sort_values("date").reset_index(drop=True)
        with self._kilit:
            self._bellek[(coin, dilim)] = (damga, tablo)
            while len(self._bellek) > self._en_fazla:
                self._bellek.popitem(last=False)
        return tablo


def _ozet(islemler: list[dict], tutar: float, bakiye: float) -> dict:
    k = kr.karne(islemler, tutar, bakiye)
    netler = [float(i["net_yuzde"]) for i in sorted(islemler, key=lambda i: i["cikis_zamani"])]
    seri = en_uzun = 0
    for x in netler:
        seri = seri + 1 if x <= 0 else 0
        en_uzun = max(en_uzun, seri)
    nedenler: dict[str, int] = {}
    for i in islemler:
        ad = NEDEN_ADI.get(i["neden"], i["neden"])
        nedenler[ad] = nedenler.get(ad, 0) + 1
    sonlu = lambda x: None if x is None or x != x or x in (float("inf"), float("-inf")) else float(x)  # noqa: E731
    return {
        "islem": len(islemler), "kazanan": sum(1 for x in netler if x > 0),
        "kazanma_orani": sonlu(k["kazanma_orani"]), "basabas_orani": sonlu(k["basabas_orani"]),
        "net_yuzde": float(sum(netler)), "net_usdt": float(sum(netler) * tutar / 100.0),
        "islem_basina_yuzde": sonlu(k["net_beklenti"]), "ort_kazanc": sonlu(k["ort_kazanc"]), "ort_kayip": sonlu(k["ort_kayip"]),
        "kar_faktoru": sonlu(k["kar_faktoru"]), "en_kotu_yuzde": min(netler) if netler else None,
        "en_uzun_kayip_serisi": en_uzun, "dusus_yuzde": sonlu(k["en_buyuk_dusus_yuzde"]), "nedenler": nedenler,
    }


def _egri(islemler: list[dict], tutar: float, en_fazla: int = 240) -> list[list]:
    sirali = sorted(islemler, key=lambda i: i["cikis_zamani"])
    toplam, nokta = 0.0, []
    for i in sirali:
        toplam += float(i["net_yuzde"]) * tutar / 100.0
        nokta.append([_utc(i["cikis_zamani"]).strftime("%Y-%m-%dT%H:%MZ"), round(toplam, 3)])
    if len(nokta) > en_fazla:
        adim = len(nokta) / en_fazla
        nokta = [nokta[min(len(nokta) - 1, int(k * adim))] for k in range(en_fazla)] + [nokta[-1]]
    return nokta


def _rapor(islemler: list[dict], baslangic: pd.Timestamp, bitis: pd.Timestamp, tutar: float, bakiye: float) -> dict:
    sinir = baslangic + (bitis - baslangic) * SECIM_PAYI
    parca = (bitis - baslangic) / 4
    return {
        "ozet": _ozet(islemler, tutar, bakiye),
        "secim": _ozet([i for i in islemler if _utc(i["giris_zamani"]) < sinir], tutar, bakiye),
        "dogrulama": _ozet([i for i in islemler if _utc(i["giris_zamani"]) >= sinir], tutar, bakiye),
        "dogrulama_baslangic": sinir.strftime("%Y-%m-%d"),
        "ceyrekler": [{"baslangic": (baslangic + parca * k).strftime("%Y-%m-%d"),
                       **{alan: _ozet([i for i in islemler
                                       if baslangic + parca * k <= _utc(i["giris_zamani"]) < baslangic + parca * (k + 1)],
                                      tutar, bakiye)[alan] for alan in ("islem", "net_usdt")}} for k in range(4)],
        "egri": _egri(islemler, tutar),
    }


def _kimlik(kural: dict) -> str:
    return hashlib.sha1(json.dumps(kural, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def calistir(kural: dict, canli: dict | None, coinler: list[str], gun: int, veri: YerelVeri, getir=None,
             ayar: dict | None = None, ilerleme=None, simdi: datetime | None = None, canli_bellek: dict | None = None) -> dict:
    """Kuralı (ve verilirse karşılaştırma için canlı kuralı) seçilen coinlerde son `gun` günde çalıştırır."""
    ayar = ayar or ayarlari_yukle()
    tutar, bakiye = float(ayar["islem_tutari"]), float(ayar["sanal_bakiye"])
    komisyon = float(ayar["komisyon_yuzde"]["vadeli"])
    getir = getir or a.binance_getir
    taban = kural["zaman_dilimi"]
    dk = g.dilim_dakika(taban)
    kurallar = [kural] + ([canli] if canli is not None else [])
    ek_ihtiyac: dict[str, int] = {}
    for k in kurallar:
        for dilim, adet in gereken_ek_mum(k).items():
            ek_ihtiyac[dilim] = max(adet, ek_ihtiyac.get(dilim, 0))
    isinma = timedelta(minutes=(max(gereken_mum(k) for k in kurallar) + 5) * dk)
    ek_isinma = max([timedelta(minutes=(adet + 5) * g.dilim_dakika(d)) for d, adet in ek_ihtiyac.items()],
                    default=timedelta(0))

    # 1) Veriyi topla: önce sunucudaki dosya; yoksa ve dönem kısaysa indir.
    tablolar: dict[str, tuple[pd.DataFrame, str]] = {}
    notlar: list[str] = []
    an = _utc(simdi or datetime.now(timezone.utc)).floor("5min")
    for coin in coinler:
        df = veri.yukle(coin, taban)
        if df is not None and len(df):
            tablolar[coin] = (df, "sunucu")
        elif gun <= INDIRME_SINIRI_GUN:
            try:
                bas = (an - timedelta(days=gun) - max(isinma, ek_isinma)).to_pydatetime()
                df = getir(f"{coin}/USDT", "vadeli", taban, bas, an.to_pydatetime())
                if len(df):
                    tablolar[coin] = (df, "indirildi")
            except Exception:  # noqa: BLE001
                df = None
            if coin not in tablolar:
                notlar.append(f"{coin}: veri alınamadı, atlandı.")
        else:
            notlar.append(f"{coin}: sunucuda indirilmiş verisi yok; {INDIRME_SINIRI_GUN} günden uzun dönemde atlandı.")
    if not tablolar:
        raise TestHatasi("Seçilen coinlerin hiçbiri için veri bulunamadı.")
    bitis = min(_utc(df["date"].max()) for df, _k in tablolar.values())
    baslangic = bitis - pd.Timedelta(days=gun)
    kisa = [c for c, (df, _k) in tablolar.items() if _utc(df["date"].min()) > baslangic]
    if kisa:
        notlar.append("Verisi dönemin tamamını kapsamayan coinler: " + ", ".join(kisa) + " (ilk günleri eksik).")

    # 2) Her coinde benzetim.
    hepsi: list[dict] = []
    canli_hepsi: list[dict] = []
    coin_ozeti = []
    canli_anahtar = None
    if canli is not None:
        canli_anahtar = (_kimlik(canli), tuple(sorted(tablolar)), gun, str(bitis))
        if canli_bellek is not None and canli_anahtar in canli_bellek:
            canli_hepsi = canli_bellek[canli_anahtar]
            canli = None
    for sira, (coin, (df, kaynak)) in enumerate(tablolar.items()):
        if ilerleme:
            ilerleme(sira, len(tablolar), coin)
        eksik_dilim: list[str] = []

        def ek_yukle(dilim: str, coin=coin, kaynak=kaynak):
            tablo = veri.yukle(coin, dilim) if kaynak == "sunucu" else None
            if tablo is None and kaynak == "indirildi":
                try:
                    tablo = getir(f"{coin}/USDT", "vadeli", dilim,
                                  (baslangic - timedelta(minutes=(ek_ihtiyac.get(dilim, 30) + 5) * g.dilim_dakika(dilim))).to_pydatetime(),
                                  bitis.to_pydatetime())
                except Exception:  # noqa: BLE001
                    tablo = None
            if tablo is None or not len(tablo):
                return None
            alt = baslangic - pd.Timedelta(minutes=(ek_ihtiyac.get(dilim, 30) + 5) * g.dilim_dakika(dilim))
            return tablo[(tablo["date"] >= alt) & (tablo["date"] <= bitis)].reset_index(drop=True)

        ek, bulunamayan = ek_veri_topla(kural, ek_yukle)
        eksik_dilim += bulunamayan
        geri = max(isinma, ek_isinma) if bulunamayan else isinma
        dilim_df = df[(df["date"] >= baslangic - geri) & (df["date"] <= bitis)].reset_index(drop=True)
        kendi = [{**i, "coin": coin} for i in benzet(dilim_df, kural, komisyon_yuzde=komisyon, ek_veri=ek)
                 if baslangic <= _utc(i["giris_zamani"]) < bitis]
        hepsi += kendi
        if canli is not None:
            canli_hepsi += [{**i, "coin": coin} for i in benzet(dilim_df, canli, komisyon_yuzde=komisyon, ek_veri=ek)
                            if baslangic <= _utc(i["giris_zamani"]) < bitis]
        net = sum(float(i["net_yuzde"]) for i in kendi)
        coin_ozeti.append({"coin": coin, "kaynak": kaynak, "islem": len(kendi),
                           "kazanan": sum(1 for i in kendi if float(i["net_yuzde"]) > 0),
                           "net_usdt": net * tutar / 100.0})
        if eksik_dilim:
            notlar.append(f"{coin}: {', '.join(eksik_dilim)} mumları yok; 5 dakikalık mumlardan toplandı (canlı botla birebir tutmayabilir).")
    if ilerleme:
        ilerleme(len(tablolar), len(tablolar), "")
    if canli_anahtar and canli_bellek is not None and canli is not None:
        canli_bellek[canli_anahtar] = canli_hepsi
        while len(canli_bellek) > 12:
            canli_bellek.pop(next(iter(canli_bellek)))

    sonuc = _rapor(hepsi, baslangic, bitis, tutar, bakiye)
    sonuc.update(
        baslangic=baslangic.strftime("%Y-%m-%d"), bitis=bitis.strftime("%Y-%m-%d %H:%M"), gun=gun,
        islem_tutari=tutar, coinler=coin_ozeti, notlar=notlar,
        islemler=[{"coin": i["coin"], "giris": _utc(i["giris_zamani"]).strftime("%Y-%m-%d %H:%M"),
                   "cikis": _utc(i["cikis_zamani"]).strftime("%Y-%m-%d %H:%M"),
                   "neden": NEDEN_ADI.get(i["neden"], i["neden"]), "net_yuzde": round(float(i["net_yuzde"]), 3)}
                  for i in sorted(hepsi, key=lambda i: i["cikis_zamani"])[-80:]],
    )
    if canli_anahtar:
        sonuc["canli"] = _rapor(canli_hepsi, baslangic, bitis, tutar, bakiye)
    uyari = []
    if sonuc["ozet"]["islem"] < 30:
        uyari.append("30'dan az işlem: bu sonuç şans olabilir, karar için yetmez.")
    if sonuc["dogrulama"]["islem"] < 10:
        uyari.append("Doğrulama döneminde 10'dan az işlem var; seçim dönemindeki sonucu doğrulamaya yetmez.")
    elif sonuc["secim"]["net_usdt"] > 0 >= sonuc["dogrulama"]["net_usdt"]:
        uyari.append("Seçim dönemi artıda ama doğrulama dönemi değil: ayar geçmişe ezber olabilir.")
    sonuc["uyarilar"] = uyari
    return sonuc


def ajan_ozeti(sonuc: dict) -> dict:
    """Ajanın okuyacağı kısa hali: eğri ve işlem listesi olmadan."""
    kisa = {k: sonuc[k] for k in ("baslangic", "bitis", "gun", "ozet", "secim", "dogrulama", "dogrulama_baslangic",
                                  "ceyrekler", "coinler", "notlar", "uyarilar") if k in sonuc}
    if "canli" in sonuc:
        kisa["canli_ayar"] = {k: sonuc["canli"][k] for k in ("ozet", "secim", "dogrulama")}
    return json.loads(json.dumps(kisa, default=lambda x: round(float(x), 4)))


class TestYoneticisi:
    """Testleri arka planda sırayla çalıştırır; pano ilerlemeyi ve sonucu kimlikle sorar."""

    def __init__(self, klasor: Path, getir=None, oku=None):
        self.klasor = Path(klasor)
        self.veri = YerelVeri(klasor, oku=oku)
        self._getir = getir
        self._kilit = threading.Lock()
        self._sira = threading.Semaphore(1)
        self._isler: OrderedDict[str, dict] = OrderedDict()
        self._canli_bellek: dict = {}

    def hazir_coinler(self) -> list[str]:
        return self.veri.coinler("5m")

    def _hazirla(self, bot: str, degerler, pasif, coinler, gun) -> tuple[dict, dict | None, list[str], int, dict]:
        try:
            canli, kural, temiz = _uzay.kural_kur(bot, degerler, pasif)
        except a.AyarHatasi as hata:
            raise TestHatasi(str(hata)) from hata
        try:
            gun = int(gun)
        except (TypeError, ValueError):
            gun = 0
        if gun not in GUNLER:
            raise TestHatasi("Dönem 30, 90, 180 ya da 365 gün olabilir.")
        temiz_coin = []
        for c in coinler or []:
            c = str(c).upper()[:12]
            if c.isalnum() and c not in temiz_coin:
                temiz_coin.append(c)
        if not temiz_coin:
            raise TestHatasi("En az bir coin seç.")
        degisti = bool(temiz["degerler"] or temiz["pasif"])
        return kural, (canli if degisti else None), temiz_coin[:EN_FAZLA_COIN], gun, temiz

    def simdi_calistir(self, bot: str, degerler, pasif, coinler, gun, ilerleme=None) -> dict:
        kural, canli, coinler, gun, temiz = self._hazirla(bot, degerler, pasif, coinler, gun)
        with self._sira:
            sonuc = calistir(kural, canli, coinler, gun, self.veri, self._getir, ilerleme=ilerleme,
                             canli_bellek=self._canli_bellek)
        sonuc.update(bot=bot, ayar=temiz)
        return sonuc

    def baslat(self, bot: str, degerler, pasif, coinler, gun) -> str:
        self._hazirla(bot, degerler, pasif, coinler, gun)   # geçersiz istek hemen reddedilsin
        kimlik = secrets.token_hex(6)
        is_ = {"durum": "sirada", "biten": 0, "toplam": 0, "coin": "", "basladi": time.time()}
        with self._kilit:
            self._isler[kimlik] = is_
            while len(self._isler) > 24:
                self._isler.popitem(last=False)

        def ilerleme(biten, toplam, coin):
            is_.update(durum="calisiyor", biten=biten, toplam=toplam, coin=coin)

        def calis():
            try:
                is_["sonuc"] = self.simdi_calistir(bot, degerler, pasif, coinler, gun, ilerleme)
                is_["durum"] = "bitti"
            except TestHatasi as hata:
                is_.update(durum="hata", hata=str(hata))
            except Exception as hata:  # noqa: BLE001
                is_.update(durum="hata", hata=f"Test çalıştırılamadı ({type(hata).__name__}).")
            is_["sure"] = round(time.time() - is_["basladi"], 1)

        threading.Thread(target=calis, daemon=True, name="gecmis-test").start()
        return kimlik

    def durum(self, kimlik: str) -> dict | None:
        with self._kilit:
            is_ = self._isler.get(str(kimlik))
        return None if is_ is None else {k: v for k, v in is_.items() if k != "basladi"}
