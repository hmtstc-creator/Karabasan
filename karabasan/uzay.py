"""Karabasan Uzayı: coinlerin girişe uzaklığı (10 Kasım 2026, Ahmet'in isteği).

Her coin için son 24 saatin her 5 dakikalık mumunda, seçilen botun giriş şartlarından
hangilerinin doğru olmadığını hesaplar. Pano bunu üç boyutlu uzayda çizer: merkez = bütün
şartlar doğru (giriş anı), halka = eksik şart sayısı, bölge = coini en çok tutan şart grubu.

Yalnız okur ve hesaplar: emir göndermez, bot ayarı değiştirmez. Denenen ayar (degerler / pasif)
yalnız bu hesapta kullanılır; canlı kural dosyalarına dokunulmaz (3. kural).

Geleceğe bakmaz: yalnız kapanmış mumlar kullanılır (ayar.veri_topla); bir mumun şart durumu
sonradan gelen veriyle değişmez (test: test_uzay.Gelecek).
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import ayar as a
from . import botlar as _botlar
from . import gostergeler as g
from .kural import _kosul, _sutun_adi, sinyal_uret

COINLER = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "ADA", "LINK", "AVAX", "LTC", "BCH", "TRX",
           "DOT", "ATOM", "ETC", "FIL", "NEAR", "UNI", "XLM", "AAVE", "ALGO"]
PENCERE_SAAT = 24
TAZELEME_SN = 150
GRUPLAR = [
    {"ad": "Büyük yön", "aciklama": "günlük ve saatlik yön şartları"},
    {"ad": "Bölge", "aciklama": "15 dakikalık bölge ve güç şartları"},
    {"ad": "Tetik", "aciklama": "5 dakikalık tetik şartları"},
    {"ad": "Hacim", "aciklama": "hacim şartı"},
]


def bot_adlari() -> list[str]:
    return [b[0] for b in _botlar.BOTLAR]


def kural_kur(bot: str, degerler: dict | None = None, pasif=None) -> tuple[dict, dict, dict]:
    """(canlı kural, denenen kural, temiz ayar). Geçersiz değer AyarHatasi verir; bilinmeyen yol yok sayılır."""
    canli = a.kural_hazirla(bot)
    gecerli = {yol: eski for yol, _ad, eski in a.tum_sayilar(canli)}
    degisim: dict[str, float] = {}
    for yol, deger in (degerler or {}).items():
        if yol not in gecerli:
            continue
        yeni = a.sayi_oku(str(deger))
        if abs(yeni - float(gecerli[yol])) > 1e-9:
            degisim[yol] = yeni
    kural = a.uygula(canli, degisim) if degisim else canli
    pasif = sorted({str(p) for p in (pasif or [])} & a.pasif_anahtarlari(canli))
    if pasif:
        kural = a.pasifla(kural, pasif)
    return canli, kural, {"degerler": degisim, "pasif": pasif}


def sart_grubu(kural: dict, kosul: dict) -> int:
    """Şartın uzaydaki bölgesi: hacim → 3; yoksa içindeki göstergelerin en büyük zaman dilimine göre."""
    sutunlar: list = []
    a._kosul_sutunlari(kosul, sutunlar)
    adlar = [_sutun_adi(s) for s in sutunlar]
    if any(s == "hacim" or s.startswith("hacim") for s in adlar):
        return 3
    en_buyuk = g.dilim_dakika(kural["zaman_dilimi"])
    for s in adlar:
        ad, _ek = a._gosterge_bul(kural, s)
        if ad is not None:
            dilim = kural["gostergeler"][ad].get("dilim")
            if dilim:
                en_buyuk = max(en_buyuk, g.dilim_dakika(dilim))
    if en_buyuk >= 60:
        return 0
    return 1 if en_buyuk > g.dilim_dakika(kural["zaman_dilimi"]) else 2


def bot_semasi(bot: str) -> dict:
    """Panonun ayar ekranları için: botun bütün ayarlanabilir sayıları, şartları ve kapatılabilen parçaları."""
    kural = a.kural_hazirla(bot)
    sartlar = []
    for k in a.kriterler(kural):
        bilgi = a.kriter_bilgisi(kural, k["sira"])
        sartlar.append({
            "sira": k["sira"], "yazi": k["yazi"], "anlam": bilgi["anlam"], "sozluk": bilgi["sozluk"],
            "grup": sart_grubu(kural, kural["giris"]["hepsi"][k["sira"]]),
            "sayilar": [_sayi(kural, s) for s in k["sayilar"]],
        })
    cikis = a.cikis_sayilari(kural)
    return {
        "bot": bot, "kod": kural["kod"], "ad": kural["ad"], "yon": kural["yon"],
        "aciklama": kural.get("aciklama", ""), "dilim": kural["zaman_dilimi"],
        "sartlar": sartlar,
        "gostergeler": [_sayi(kural, s) for s in a.gosterge_sayilari(kural)],
        "giris_emri": [_sayi(kural, s) for s in cikis if s[0].startswith("giris_limiti.")],
        "cikis": [_sayi(kural, s) for s in cikis if s[0].startswith("cikis.") or s[0] == "bekleme_dakika"],
        "pozisyon": [_sayi(kural, s) for s in cikis if s[0] == "kaldirac" or s[0].startswith("zararda_ekleme.")],
        "pasif": [{"anahtar": an, "ad": ad} for an, ad in a.pasif_secenekleri(kural)],
        "gruplar": GRUPLAR,
    }


def _sayi(kural: dict, s) -> dict:
    yol, ad, deger = s
    tam = isinstance(deger, int) and not isinstance(deger, bool)
    d = abs(float(deger))
    adim = (1 if d < 50 else 5) if tam else (0.05 if d < 0.5 else 0.1 if d < 5 else 0.5)
    ust = max(d * 3, adim * 20) if d else adim * 40
    alt = adim if tam else 0
    if yol == "kaldirac":   # kural motoru sınavda 1 ile 2 kat arasını kabul eder (6. kural)
        alt, ust = 1, 2
    return {"yol": yol, "ad": ad, "deger": deger, "tam": tam, "adim": adim,
            "alt": alt, "ust": int(round(ust)) if tam else round(ust, 2),
            "aciklama": a.sayi_aciklamasi(kural, yol)}


class MumDeposu:
    """Mumları bellekte tutar ve yalnız eksik kalan son kısmı indirir (her tazelemede coin başına tek küçük istek)."""

    def __init__(self, getir=None, en_fazla: int = 120):
        self._getir = getir or a.binance_getir
        self._kilit = threading.Lock()
        self._veri: dict[tuple, pd.DataFrame] = {}
        self._en_fazla = en_fazla

    def al(self, parite: str, piyasa: str, aralik: str, bas: datetime, son: datetime) -> pd.DataFrame:
        anahtar = (parite, piyasa, aralik)
        dk = g.dilim_dakika(aralik)
        with self._kilit:
            eldeki = self._veri.get(anahtar)
        bas_z, son_z = pd.Timestamp(bas), pd.Timestamp(son)
        if eldeki is not None and len(eldeki) and eldeki["date"].iloc[0] <= bas_z + pd.Timedelta(minutes=dk):
            son_mum = eldeki["date"].iloc[-1]
            if son_mum + pd.Timedelta(minutes=2 * dk) <= son_z:
                yeni = self._getir(parite, piyasa, aralik, son_mum.to_pydatetime(), son)
                eldeki = (pd.concat([eldeki, yeni], ignore_index=True)
                          .drop_duplicates(subset="date", keep="last").sort_values("date").reset_index(drop=True))
        else:
            eldeki = self._getir(parite, piyasa, aralik, bas, son)
        if len(eldeki):
            eldeki = eldeki[eldeki["date"] >= bas_z - pd.Timedelta(minutes=dk)].reset_index(drop=True)
        with self._kilit:
            if anahtar not in self._veri and len(self._veri) >= self._en_fazla:
                self._veri.pop(next(iter(self._veri)))
            self._veri[anahtar] = eldeki
        return eldeki[eldeki["date"] <= son_z].reset_index(drop=True)


def _yuvarla(simdi: datetime) -> datetime:
    simdi = simdi.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return simdi - timedelta(minutes=simdi.minute % 5)


def coin_durumu(kural: dict, df: pd.DataFrame, ek: dict, pencere_bas: pd.Timestamp) -> dict:
    """Bir coinin pencere içindeki her mumu için eksik şartların bit maskesi (bit k = k. şart doğru değil) ve kapanışlar."""
    tablo = sinyal_uret(df, kural, ek)
    maske = (pd.to_datetime(tablo["date"], utc=True) >= pencere_bas).to_numpy()
    eksik = None
    for k, kosul in enumerate(kural["giris"]["hepsi"]):
        yanlis = (~_kosul(tablo, kosul).fillna(False).astype(bool)).to_numpy()[maske].astype("int64") << k
        eksik = yanlis if eksik is None else eksik | yanlis
    return {"eksik": [int(x) for x in eksik], "fiyat": [float(f"{x:.6g}") for x in tablo["close"].to_numpy()[maske]]}


def hesapla(bot: str, degerler: dict | None = None, pasif=None, depo: MumDeposu | None = None,
            simdi: datetime | None = None, coinler: list[str] | None = None) -> dict:
    """Panonun uzay verisi. Bir coin indirilemezse o coin 'hata' ile gelir, ötekiler etkilenmez."""
    depo = depo or MumDeposu()
    canli, kural, temiz = kural_kur(bot, degerler, pasif)
    degisti = bool(temiz["degerler"] or temiz["pasif"])
    bitis = _yuvarla(simdi or datetime.now(timezone.utc))
    pencere_bas = pd.Timestamp(bitis - timedelta(hours=PENCERE_SAAT))
    dk = g.dilim_dakika(kural["zaman_dilimi"])
    adim = PENCERE_SAAT * 60 // dk
    cikti = []
    for coin in (coinler or COINLER):
        kayit = {"ad": coin}
        try:
            df, ek = a.veri_topla(kural, coin, "vadeli", bitis, 1, depo.al, None, diger=canli if degisti else None)
            if df.empty or len(df[df["date"] >= pencere_bas]) < adim // 2:
                raise a.AyarHatasi("mum yok")
            kayit.update(coin_durumu(kural, df, ek, pencere_bas))
            if degisti:
                kayit["canli"] = coin_durumu(canli, df, ek, pencere_bas)["eksik"]
            kayit["eksik"] = kayit["eksik"][-adim:]
            kayit["fiyat"] = kayit["fiyat"][-adim:]
        except Exception as hata:  # noqa: BLE001 - tek coin öbürlerini düşürmesin
            kayit["hata"] = "Bu coinin verisi şu an alınamadı." if not isinstance(hata, a.AyarHatasi) else str(hata)
        cikti.append(kayit)
    uzunluk = min((len(c["eksik"]) for c in cikti if "eksik" in c), default=0)
    for c in cikti:
        if "eksik" in c:
            c["eksik"], c["fiyat"] = c["eksik"][-uzunluk:], c["fiyat"][-uzunluk:]
            if "canli" in c:
                c["canli"] = c["canli"][-uzunluk:]
    ekran = a.uygula(canli, temiz["degerler"]) if temiz["degerler"] else canli   # pasif şartın yazısı da görünsün
    sartlar = [{"yazi": k["yazi"], "grup": sart_grubu(canli, canli["giris"]["hepsi"][k["sira"]]),
                "pasif": f"k{k['sira']}" in temiz["pasif"]} for k in a.kriterler(ekran)]
    return {"bot": bot, "bitis": bitis.strftime("%Y-%m-%dT%H:%M:%SZ"), "adim_dakika": dk, "adim": uzunluk,
            "degisti": degisti, "ayar": temiz, "sartlar": sartlar, "gruplar": GRUPLAR, "coinler": cikti}


class UzayServisi:
    """Canlı ayarın uzay verisini bellekte tutar; istek geldiğinde eskiyse yeniler. Denenen ayar her seferinde hesaplanır."""

    def __init__(self, getir=None, saat=None):
        self.depo = MumDeposu(getir)
        self._saat = saat or (lambda: datetime.now(timezone.utc))
        self._kilit = threading.Lock()
        self._hesap = threading.Semaphore(2)
        self._canli: dict[str, tuple[float, dict]] = {}

    def al(self, bot: str, degerler: dict | None = None, pasif=None) -> dict:
        if bot not in bot_adlari():
            raise a.AyarHatasi("Böyle bir bot yok.")
        _canli, _kural, temiz = kural_kur(bot, degerler, pasif)
        if temiz["degerler"] or temiz["pasif"]:
            with self._hesap:
                return hesapla(bot, temiz["degerler"], temiz["pasif"], self.depo, self._saat())
        with self._kilit:
            eldeki = self._canli.get(bot)
        if eldeki and time.monotonic() - eldeki[0] < TAZELEME_SN:
            return eldeki[1]
        with self._hesap:
            sonuc = hesapla(bot, None, None, self.depo, self._saat())
        with self._kilit:
            self._canli[bot] = (time.monotonic(), sonuc)
        return sonuc

    def isit(self) -> None:
        """Panel açılırken arka planda: ilk istek beklemesin diye canlı botların verisini hazırlar."""
        for bot in bot_adlari():
            try:
                self.al(bot)
            except Exception:  # noqa: BLE001
                pass
