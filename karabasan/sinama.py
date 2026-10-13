"""Panel sınaması: aday botların 4 yıllık veride, önceden yazılmış kurallarla sınanması.

12 Ekim 2026'da beş farklı okuldan uzman rolündeki ajanlar (SMC, kantitatif, trend,
mikro yapı, risk) üç tur tartıştı ve aday botlarla birlikte bir sınama protokolü
üzerinde anlaştı. Bu modül o protokoldür (bkz. CLAUDE.md "Uzman paneli"):

- Veri: ~20 vadeli parite, 4 yıl. İlk 3 yıl geliştirme dönemidir; son yıl AYRILMIŞTIR
  ve AYRILMIS_ACIK True yapılana kadar hiçbir hesapta kullanılmaz. Açılması bütün
  adaylar için birlikte ve bir kez olur; kural dosyalarının özetleri rapora yazılır.
- Giriş piyasa emriyle. Maliyet: taraf başına %0,05 komisyon + kayma (en az kuralın
  'en_az_kayma_yuzde'si, ya da sinyal mumu aralığının %10'u, hangisi büyükse) + açık
  tutulan her fonlama ödemesi. "Maliyet iki katında" sınaması komisyon ve kaymayı ikiye katlar.
- Tutar riske göre: her işlem stopta yaklaşık 1 USDT kaybettirir (tutar = 1 / stop,
  en çok 100 USDT). Bot başına en çok 'en_fazla_pozisyon' açık işlem, giriş sıklığı
  sınırları, günlük fren (24 saatte kapanmış zarar bakiyenin %2'sini aşarsa 24 saat
  yeni giriş yok), coin kilidi (24 saatte aynı coinde 2 stop -> 24 saat) ve seri stop
  kilidi (24 saatte 4 stop -> 12 saat; trend botları muaf).
- Her adayın bir rastgele giriş plasebosu vardır (aynı sayıda işlem, aynı yön, aynı tutma
  süresi, rastgele coin ve an) ve gerekirse kural plasebosu (iddia edilen şartı kaldırılmış
  hali). Asıl kural plaseboyu geçemiyorsa ölür.
- Deneme defteri: önceki 112 deneme (12 strateji + 100 çıkış varyasyonu) ve buradaki her
  deneme sayılır. Kural başına en çok 3 önceden yazılmış deneme; hepsi raporlanır,
  en iyisi seçilmez: canlıya gidecek olan önceden yazılmıştır ('canli').

Bu modül hiçbir ayarı değiştirmez, hiçbir emir göndermez.
"""

from __future__ import annotations

import hashlib
import heapq
import math
from collections import deque
from typing import Callable

import numpy as np
import pandas as pd

from .benzetim import aday_islemler
from .kural import (STRATEJI_KLASORU, bilgi_sinyalleri, cikis_metni, ek_veri_topla, kural_yukle,
                    sinyal_uret)

# Binance vadelide en az 4 yıllık geçmişi olan, hacmi yüksek pariteler (BTC hariç: 50-100
# USDT'lik işlemle BTC vadeli açılamıyor; BTC yalnız referans). Bunlar bugün hâlâ listede
# olan coinlerdir: dönem içinde borsadan çıkarılan coinler veride yok ("hayatta kalanlar
# yanılgısı"); sonuç bu yüzden biraz iyimserdir.
COINLER = ["ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "LINK", "AVAX", "DOT", "LTC",
           "BCH", "TRX", "ATOM", "ETC", "FIL", "NEAR", "UNI", "XLM", "AAVE", "ALGO"]
REFERANS = "BTC"

GELISTIRME_YIL = 3
AYRILMIS_GUN = 365
# Son yıl yalnız bir kez, bütün adaylar için birlikte açılır. Açmak bir karardır:
# kural dosyaları dondurulur ve bu değişiklik ayrı bir işlemle (commit) yapılır.
AYRILMIS_ACIK = False

BAKIYE = 1000.0           # bot başına sanal bakiye (USDT)
ISLEM_RISKI = 1.0         # işlem başına riske giren tutar (USDT)
EN_FAZLA_TUTAR = 100.0
KOMISYON = 0.05           # taraf başına, vadeli alıcı (taker)
KAYMA_ORANI = 0.10        # sinyal mumu aralığının bu payı kadar kayma
GUNLUK_FREN_YUZDE = 2.0
COIN_STOP_SAYISI, COIN_KILIDI = 2, pd.Timedelta(hours=24)
SERI_STOP_SAYISI, SERI_KILIDI = 4, pd.Timedelta(hours=12)
AYNI_YON_ORTAK_SINIR = 10  # bütün botlar birlikte (panel portföyü)
PENCERE = pd.Timedelta(hours=24)

T_ESIGI = 2.5             # gün bazında t-değeri çıtası
PLASEBO_T_ESIGI = 2.0
PLASEBO_TEKRAR = 20
KURAL_PLASEBO_FARKI = 0.10  # asıl kural, şartı kaldırılmış halinden işlem başına en az bu kadar iyi olmalı
ONCEKI_DENEME = 118  # 112 eski + Ahmet Özel 1. sürümün 6 denemesi (13 Ekim 2026)

# Aday aileleri. 'denemeler' önceden yazılmıştır; 'canli' canlıya gidecek olandır (en iyisi değil).
ADAYLAR = [
    {
        "ad": "ZSD", "baslik": "Zorla satış dönüşü (alım, 15 dk)",
        "denemeler": ["ZSD", "ZSDF", "ZSDT"], "canli": "ZSD",
        "kural_plasebolari": {"ZSDP": "BTC şartı kaldırılmış hal (tasfiye iddiası)"},
        "en_az_gun": 30, "en_az_islem": 0, "esik_net_yuzde": 0.20, "esik_brut_yuzde": None,
        "en_iyi_3_gun": True, "btc_iliskisi": True, "trend": False,
    },
    {
        "ad": "TRG", "baslik": "Günlük trend takibi (alım)",
        "denemeler": ["TRG14", "TRG28", "TRG56"], "canli": "TRG28",
        "kural_plasebolari": {},
        "en_az_gun": 0, "en_az_islem": 100, "esik_net_yuzde": 0.0, "esik_brut_yuzde": 0.5,
        "en_iyi_3_gun": False, "btc_iliskisi": True, "trend": True,
    },
    {
        "ad": "TRGK", "baslik": "Günlük trend takibi (açığa satış)",
        "denemeler": ["TRGK14", "TRGK28", "TRGK56"], "canli": "TRGK28",
        "kural_plasebolari": {},
        "en_az_gun": 0, "en_az_islem": 100, "esik_net_yuzde": 0.0, "esik_brut_yuzde": 0.5,
        "en_iyi_3_gun": False, "btc_iliskisi": False, "trend": True,
    },
    # ASYA AVI (SMC uzmanının önerisi; 2. aşama): tek deneme, iki plaseboyla. Panelin üçü kuşkulu.
    {
        "ad": "ASYA", "baslik": "Asya seansı likidite avı (alım, 15 dk)",
        "denemeler": ["ASYA"], "canli": "ASYA",
        "kural_plasebolari": {"ASYAP1": "aynı kural 12:00-18:59 penceresiyle",
                              "ASYAP2": "aynı kural saat şartı olmadan (kayan 7 saatlik aralık)"},
        "en_az_gun": 100, "en_az_islem": 0, "esik_net_yuzde": 0.15, "esik_brut_yuzde": None,
        "en_iyi_3_gun": True, "btc_iliskisi": True, "trend": False,
    },
    {
        "ad": "ASYAK", "baslik": "Asya seansı likidite avı (açığa satış, 15 dk)",
        "denemeler": ["ASYAK"], "canli": "ASYAK",
        "kural_plasebolari": {"ASYAKP1": "aynı kural 12:00-18:59 penceresiyle",
                              "ASYAKP2": "aynı kural saat şartı olmadan (kayan 7 saatlik aralık)"},
        "en_az_gun": 100, "en_az_islem": 0, "esik_net_yuzde": 0.15, "esik_brut_yuzde": None,
        "en_iyi_3_gun": True, "btc_iliskisi": False, "trend": False,
    },
    # Fonlama sıkışması (mikro yapı uzmanı; 3. aşama): sayım 3 yılda 571 olay buldu, panel kararıyla
    # bot olarak sınanır. Tek deneme, fonlama şartı kaldırılmış kural plasebosuyla.
    {
        "ad": "FONK", "baslik": "Fonlama sıkışması (açığa satış, 1 s)",
        "denemeler": ["FONK"], "canli": "FONK",
        "kural_plasebolari": {"FONKP": "aynı kural fonlama şartı olmadan"},
        "en_az_gun": 0, "en_az_islem": 60, "esik_net_yuzde": 0.20, "esik_brut_yuzde": None,
        "en_iyi_3_gun": True, "btc_iliskisi": False, "trend": False,
    },
    {
        "ad": "FON", "baslik": "Fonlama sıkışması (alım, 1 s)",
        "denemeler": ["FON"], "canli": "FON",
        "kural_plasebolari": {"FONP": "aynı kural fonlama şartı olmadan"},
        "en_az_gun": 0, "en_az_islem": 60, "esik_net_yuzde": 0.20, "esik_brut_yuzde": None,
        "en_iyi_3_gun": True, "btc_iliskisi": True, "trend": False,
    },
    # Ahmet'in kendi stratejisi (13 Ekim 2026; komitenin çoğunluk yorumu): günlük yapı ve ortalamalar,
    # haftalık destek / direnç ya da FVG'den dönüş, teyit barı, MACD dönüşü. Üç deneme (2R, 3R, yapı
    # dönünce çıkış), kural plasebosu (destek / direnç şartsız), bilgi için MACD şartsız hal.
    # Ölçüler R cinsinden (risk 1 USDT): işlem başına en az 0,15R ve plasebodan en az 0,15R iyi.
    {
        "ad": "AHMETOZEL", "baslik": "Ahmet Özel (alım, günlük)",
        "denemeler": ["AHMETOZEL", "AHMETOZEL2", "AHMETOZEL3"], "canli": "AHMETOZEL",
        "kural_plasebolari": {"AHMETOZELP1": "aynı kural destek / FVG şartı olmadan"},
        "bilgi_plasebolari": {"AHMETOZELP2": "aynı kural MACD şartı olmadan"},
        "en_az_gun": 40, "en_az_islem": 60, "esik_net_yuzde": 0.0, "esik_brut_yuzde": None,
        "esik_net_r": 0.15, "kural_plasebo_r": 0.15, "en_az_kazanc_kayip": 1.5, "en_fazla_dusus": 15,
        "en_iyi_3_gun": True, "btc_iliskisi": True, "trend": False,
    },
    {
        "ad": "AHMETOZELK", "baslik": "Ahmet Özel (açığa satış, günlük)",
        "denemeler": ["AHMETOZELK", "AHMETOZELK2", "AHMETOZELK3"], "canli": "AHMETOZELK",
        "kural_plasebolari": {"AHMETOZELKP1": "aynı kural direnç / FVG şartı olmadan"},
        "bilgi_plasebolari": {"AHMETOZELKP2": "aynı kural MACD şartı olmadan"},
        "en_az_gun": 40, "en_az_islem": 60, "esik_net_yuzde": 0.0, "esik_brut_yuzde": None,
        "esik_net_r": 0.15, "kural_plasebo_r": 0.15, "en_az_kazanc_kayip": 1.5, "en_fazla_dusus": 15,
        "en_iyi_3_gun": True, "btc_iliskisi": False, "trend": False,
    },
]
# Fonlama aşırılığı sayımı (panelin 4. aday oylaması, oybirliğiyle): bot değil, yalnız sayım.
FONLAMA_ASIRI = 0.05          # 8 saate çevrilmiş tek ödeme, yüzde (olağan %0,01)
FONLAMA_ASIRI_ORTALAMA = 0.03  # son 3 ödemenin ortalaması

MumYukleyici = Callable[[str, str], "pd.DataFrame | None"]
FonlamaYukleyici = Callable[[str], "pd.DataFrame | None"]


# --------------------------------------------------------------------------
# Dönem ve maliyet
# --------------------------------------------------------------------------


def donemler(yukle: MumYukleyici) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """(geliştirme başı, ayrılmış yıl başı, veri sonu). Veri sonu: referansın son tam günü."""
    ref = yukle(REFERANS, "1h")
    if ref is None or ref.empty:
        ref = next((t for t in (yukle(c, "1h") for c in COINLER) if t is not None and not t.empty), None)
    if ref is None:
        raise ValueError("Panel sınaması için veri bulunamadı.")
    son = pd.to_datetime(ref["date"], utc=True).max().floor("D")
    ayrilmis = son - pd.Timedelta(days=AYRILMIS_GUN)
    return ayrilmis - pd.Timedelta(days=365 * GELISTIRME_YIL), ayrilmis, son


def kayma_dizisi(tablo: pd.DataFrame, en_az_yuzde: float, oran: float = KAYMA_ORANI) -> np.ndarray:
    """Mum başına kayma (yüzde): en az 'en_az_yuzde', ya da mum aralığının 'oran' kadarı.

    Aralık payı kısa mumlar içindir (şok anında makas açılır). Günlük mumun 24 saatlik
    aralığı açılıştaki makası anlatmaz; günlük kurallar oranı 0 yapar ('kayma_aralik_orani').
    """
    aralik = ((tablo["high"] - tablo["low"]) / tablo["close"] * 100.0).to_numpy(dtype=float)
    return np.maximum(en_az_yuzde, np.nan_to_num(aralik) * oran)


def fonlama_maliyeti(fonlama: pd.DataFrame | None, giris, cikis, alim: bool) -> float:
    """İşlem açıkken gerçekleşen fonlama ödemelerinin toplamı (yüzde; maliyet artı)."""
    if fonlama is None or len(fonlama) == 0:
        return 0.0
    zaman = fonlama["date"]
    secim = (zaman > giris) & (zaman <= cikis)
    toplam = float(fonlama.loc[secim, "oran_yuzde"].sum())
    return toplam if alim else -toplam


def _ozet(yol) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()[:12]


def kural_dosyasi(kod: str):
    for alt in ("", "aday", "emekli"):
        yol = (STRATEJI_KLASORU / alt / f"{kod}.json") if alt else STRATEJI_KLASORU / f"{kod}.json"
        if yol.exists():
            return yol
    raise FileNotFoundError(kod)


# --------------------------------------------------------------------------
# Adaylar ve portföy geçişi
# --------------------------------------------------------------------------


class Kaynak:
    """Mum ve fonlama yükleyicilerini sarar; referans parite tablolarını bellekte tutar."""

    def __init__(self, yukle: MumYukleyici, fonlama: FonlamaYukleyici):
        self._yukle, self._fonlama = yukle, fonlama
        self._ref: dict = {}
        self._fon: dict = {}

    def mum(self, coin: str, dilim: str):
        if coin == REFERANS:
            if (coin, dilim) not in self._ref:
                self._ref[(coin, dilim)] = self._yukle(coin, dilim)
            return self._ref[(coin, dilim)]
        return self._yukle(coin, dilim)

    def fonlama(self, coin: str):
        if coin not in self._fon:
            self._fon[coin] = self._fonlama(coin)
        return self._fon[coin]


def bot_adaylari(kural: dict, kaynak: Kaynak, bas: pd.Timestamp, son: pd.Timestamp,
                 plasebo_icin: bool = False) -> dict:
    """Her coinde aday işlemleri (maliyet 1x ve 2x) ve plasebo için gereken fiyatları üretir."""
    alim = kural["yon"] == "alim"
    taban = kural["zaman_dilimi"]
    en_az_kayma = float(kural.get("portfoy", {}).get("en_az_kayma_yuzde", 0.05))
    kayma_orani = float(kural.get("portfoy", {}).get("kayma_aralik_orani", KAYMA_ORANI))
    adaylar = {1: [], 2: []}
    fiyatlar = {}
    eksik: list[str] = []
    for coin in COINLER:
        df = kaynak.mum(coin, taban)
        if df is None or df.empty:
            eksik.append(f"{coin} {taban}")
            continue
        ek, bulunamayan = ek_veri_topla(kural, lambda d, c=coin: kaynak.mum(c, d),
                                        lambda p, d: kaynak.mum(p, d), lambda c=coin: kaynak.fonlama(c))
        eksik += [f"{coin} {b}" for b in bulunamayan]
        tablo = sinyal_uret(df, kural, ek)
        kayma = kayma_dizisi(tablo, en_az_kayma, kayma_orani)
        bilgi = {ad: seri.to_numpy() for ad, seri in bilgi_sinyalleri(tablo, kural).items()}
        fon = kaynak.fonlama(coin)
        for kat in (1, 2):
            for a in aday_islemler(tablo, kural, KOMISYON * kat, kayma * kat):
                # Geliştirme döneminde açılıp ayrılmış yıla taşan işlem alınmaz: o yılın verisine bakardı.
                if not (bas <= a["giris_zamani"] and a["cikis_zamani"] < son):
                    continue
                a["coin"] = coin
                a["bilgi"] = {ad: bool(dizi[a["sinyal_i"]]) for ad, dizi in bilgi.items()}
                a["fonlama_yuzde"] = fonlama_maliyeti(fon, a["giris_zamani"], a["cikis_zamani"], alim)
                a["net_yuzde"] -= a["fonlama_yuzde"]
                adaylar[kat].append(a)
        if plasebo_icin:
            fiyatlar[coin] = {
                "tarih": pd.to_datetime(tablo["date"], utc=True).dt.tz_convert(None).to_numpy(),
                "acilis": tablo["open"].to_numpy(dtype=float),
                "kapanis": tablo["close"].to_numpy(dtype=float),
                "kayma": kayma,
                "fonlama": fon,
            }
        del tablo
    return {"adaylar": adaylar, "fiyatlar": fiyatlar, "eksik": eksik}


def portfoy_gecisi(botlar: list[tuple[str, dict, list[dict]]], ortak: bool = False) -> dict[str, list[dict]]:
    """Adaylardan gerçekten açılacak işlemleri seçer: zaman sırasıyla, risk kurallarıyla.

    botlar: [(bot adı, kural, adaylar)]. ortak=True ise bütün botlar tek portföydür:
    aynı yönde toplam en çok AYNI_YON_ORTAK_SINIR pozisyon ve toplam günlük fren eklenir.
    Dönen: {bot adı: kabul edilen işlemler (tutar ve net_usdt eklenmiş)}.
    """
    sira = []
    for b_sira, (bot, kural, adaylar) in enumerate(botlar):
        for a in adaylar:
            sira.append((a["giris_zamani"], b_sira, COINLER.index(a["coin"]) if a["coin"] in COINLER else 99,
                         a["sinyal_i"], bot, a))
    sira.sort(key=lambda x: x[:4])
    ayar = {bot: kural.get("portfoy", {}) for bot, kural, _ in botlar}
    kurallar = {bot: kural for bot, kural, _ in botlar}
    kabul: dict[str, list[dict]] = {bot: [] for bot, _, _ in botlar}

    acik: list = []                      # yığın: (çıkış zamanı, sayaç, bot, işlem)
    acik_sayisi = {bot: 0 for bot in kabul}
    yon_sayisi = {"alim": 0, "aciga_satis": 0}
    sonraki_i: dict = {}                 # (bot, coin) -> bakılabilecek ilk sinyal mumu
    bekleme_bitis: dict = {}             # (bot, coin) -> kuralın stop sonrası beklemesi
    girisler = {bot: deque() for bot in kabul}
    kapananlar = {bot: deque() for bot in kabul}   # (çıkış, net_usdt, stop mu, coin)
    tum_kapanan: deque = deque()
    fren = {bot: pd.Timestamp.min.tz_localize("UTC") for bot in kabul}
    seri_kilit = dict(fren)
    coin_kilit: dict = {}
    ortak_fren = pd.Timestamp.min.tz_localize("UTC")
    gunluk: dict = {}                    # (bot, coin, gün) -> giriş sayısı
    sayac = 0

    def kapat(cikis, bot, islem):
        nonlocal ortak_fren
        acik_sayisi[bot] -= 1
        yon_sayisi[islem["yon"]] -= 1
        stop_mu = islem["neden"] == "zarar_durdur"
        k = kapananlar[bot]
        k.append((cikis, islem["net_usdt"], stop_mu, islem["coin"]))
        while k and k[0][0] <= cikis - PENCERE:
            k.popleft()
        if sum(x[1] for x in k) < -BAKIYE * GUNLUK_FREN_YUZDE / 100.0:
            fren[bot] = max(fren[bot], cikis + PENCERE)
        if stop_mu:
            if sum(1 for x in k if x[2] and x[3] == islem["coin"]) >= COIN_STOP_SAYISI:
                coin_kilit[(bot, islem["coin"])] = cikis + COIN_KILIDI
            if not ayar[bot].get("seri_stop_muaf", False) and sum(1 for x in k if x[2]) >= SERI_STOP_SAYISI:
                seri_kilit[bot] = max(seri_kilit[bot], cikis + SERI_KILIDI)
        if ortak:
            tum_kapanan.append((cikis, islem["net_usdt"]))
            while tum_kapanan and tum_kapanan[0][0] <= cikis - PENCERE:
                tum_kapanan.popleft()
            if sum(x[1] for x in tum_kapanan) < -BAKIYE * len(kabul) * GUNLUK_FREN_YUZDE / 100.0:
                ortak_fren = max(ortak_fren, cikis + PENCERE)

    for t, _b, _c, _i, bot, a in sira:
        while acik and acik[0][0] <= t:
            cikis, _s, kbot, kislem = heapq.heappop(acik)
            kapat(cikis, kbot, kislem)
        anahtar = (bot, a["coin"])
        if a["sinyal_i"] < sonraki_i.get(anahtar, 0) or t < bekleme_bitis.get(anahtar, t):
            continue
        p = ayar[bot]
        if acik_sayisi[bot] >= int(p.get("en_fazla_pozisyon", 5)):
            continue
        if t < fren[bot] or t < seri_kilit[bot] or t < coin_kilit.get(anahtar, t):
            continue
        if ortak and (t < ortak_fren or yon_sayisi[a["yon"]] >= AYNI_YON_ORTAK_SINIR):
            continue
        gecmis = girisler[bot]
        if any(sum(1 for z in gecmis if z > t - pd.Timedelta(hours=s["saat"])) >= s["sayi"]
               for s in p.get("giris_sinirlari", [])):
            continue
        gun_anahtari = (bot, a["coin"], t.floor("D"))
        if gunluk.get(gun_anahtari, 0) >= int(p.get("coin_gunde_en_fazla", 100)):
            continue
        gunluk[gun_anahtari] = gunluk.get(gun_anahtari, 0) + 1
        tutar = min(ISLEM_RISKI / (a["stop_yuzde"] / 100.0), EN_FAZLA_TUTAR)
        islem = {**a, "bot": bot, "tutar": tutar, "net_usdt": tutar * a["net_yuzde"] / 100.0}
        kabul[bot].append(islem)
        gecmis.append(t)
        while gecmis and gecmis[0] <= t - pd.Timedelta(hours=168):
            gecmis.popleft()
        acik_sayisi[bot] += 1
        yon_sayisi[a["yon"]] += 1
        sayac += 1
        heapq.heappush(acik, (a["cikis_zamani"], sayac, bot, islem))
        sonraki_i[anahtar] = a["sonraki_i"]
        bekleme = int(kurallar[bot].get("bekleme_dakika", 0))
        if bekleme and a["neden"] == "zarar_durdur":
            bekleme_bitis[anahtar] = a["cikis_zamani"] + pd.Timedelta(minutes=bekleme)
    return kabul


# --------------------------------------------------------------------------
# Ölçümler
# --------------------------------------------------------------------------


def gunluk_seri(islemler: list[dict], bas: pd.Timestamp, son: pd.Timestamp) -> pd.Series:
    """Dönemin her günü için kapanan işlemlerin net USDT toplamı (işlem olmayan gün 0)."""
    gunler = pd.date_range(bas.floor("D"), (son - pd.Timedelta(seconds=1)).floor("D"), freq="D", tz="UTC")
    seri = pd.Series(0.0, index=gunler)
    for i in islemler:
        gun = pd.Timestamp(i["cikis_zamani"]).floor("D")
        if gun in seri.index:
            seri[gun] += i["net_usdt"]
    return seri


def t_degeri(seri) -> float:
    dizi = np.asarray(seri, dtype=float)
    if len(dizi) < 2 or dizi.std(ddof=1) == 0:
        return 0.0
    return float(dizi.mean() / (dizi.std(ddof=1) / math.sqrt(len(dizi))))


def en_buyuk_dusus(islemler: list[dict]) -> float:
    toplam, tepe, dusus = 0.0, 0.0, 0.0
    for i in sorted(islemler, key=lambda i: i["cikis_zamani"]):
        toplam += i["net_usdt"]
        tepe = max(tepe, toplam)
        dusus = max(dusus, tepe - toplam)
    return dusus


def olcumler(islemler: list[dict], bas: pd.Timestamp, son: pd.Timestamp,
             btc_gunluk: pd.Series | None = None) -> dict:
    n = len(islemler)
    net = sum(i["net_usdt"] for i in islemler)
    gun = gunluk_seri(islemler, bas, son)
    yillar = []
    parca_sayisi = max(1, round((son - bas).days / 365))
    uzunluk = (son - bas) / parca_sayisi
    for k in range(parca_sayisi):
        p_bas, p_son = bas + uzunluk * k, bas + uzunluk * (k + 1)
        yillar.append(sum(i["net_usdt"] for i in islemler if p_bas <= i["cikis_zamani"] < p_son))
    kazanc = sorted(gun[gun != 0].tolist(), reverse=True)
    en_iyi_3_pay = (sum(kazanc[:3]) / net) if net > 0 else None
    coin_net: dict[str, float] = {}
    for i in islemler:
        coin_net[i["coin"]] = coin_net.get(i["coin"], 0.0) + i["net_usdt"]
    en_iyi_3_islem = sorted((i["net_usdt"] for i in islemler), reverse=True)[:3]
    btc_iliski = None
    if btc_gunluk is not None and n:
        ortak = pd.concat([gun, btc_gunluk], axis=1, join="inner").dropna()
        if len(ortak) > 10 and ortak.iloc[:, 0].std() > 0 and ortak.iloc[:, 1].std() > 0:
            btc_iliski = float(ortak.iloc[:, 0].corr(ortak.iloc[:, 1]))
    nedenler: dict[str, int] = {}
    for i in islemler:
        nedenler[i["neden"]] = nedenler.get(i["neden"], 0) + 1
    return {
        "islem": n,
        "kazanma": (100.0 * sum(1 for i in islemler if i["net_usdt"] > 0) / n) if n else 0.0,
        "net": net,
        "net_yuzde": float(np.mean([i["net_yuzde"] for i in islemler])) if n else 0.0,
        "brut_yuzde": float(np.mean([i["brut_yuzde"] for i in islemler])) if n else 0.0,
        "fonlama_yuzde": float(np.mean([i["fonlama_yuzde"] for i in islemler])) if n else 0.0,
        "t": t_degeri(gun),
        "yillar": yillar,
        "artida_yil": sum(1 for y in yillar if y > 0),
        "en_iyi_3_gun_payi": en_iyi_3_pay,
        "artida_coin": sum(1 for v in coin_net.values() if v > 0),
        "en_iyi_3_islem_haric": net - sum(en_iyi_3_islem),
        "dusus": en_buyuk_dusus(islemler),
        "gun_sayisi": len({pd.Timestamp(i["giris_zamani"]).floor("D") for i in islemler}),
        "btc_iliski": btc_iliski,
        "nedenler": nedenler,
        "ort_sure_saat": float(np.mean([i["sure_dakika"] for i in islemler]) / 60.0) if n else 0.0,
        # İşlem başına risk 1 USDT olduğundan net USDT ortalaması R cinsindendir.
        "ort_r": (net / n / ISLEM_RISKI) if n else 0.0,
        "kazanc_kayip": _kazanc_kayip(islemler),
    }


def _kazanc_kayip(islemler: list[dict]) -> float | None:
    """Ortalama kazanç / ortalama kayıp (USDT)."""
    kazanc = [i["net_usdt"] for i in islemler if i["net_usdt"] > 0]
    kayip = [-i["net_usdt"] for i in islemler if i["net_usdt"] < 0]
    if not kazanc or not kayip:
        return None
    return float(np.mean(kazanc) / np.mean(kayip))


def rastgele_plasebo(islemler: list[dict], fiyatlar: dict, bas, son, tohum: int = 7) -> float | None:
    """Aynı işlemleri rastgele coin ve rastgele anda, aynı süre ve yönde açmanın işlem başına net yüzdesi."""
    coinler = [c for c, f in fiyatlar.items() if len(f["tarih"])]
    if not islemler or not coinler:
        return None
    rng = np.random.default_rng(tohum)
    sonuclar = []
    bas64, son64 = np.datetime64(bas.tz_convert(None)), np.datetime64(son.tz_convert(None))
    for _ in range(PLASEBO_TEKRAR):
        for islem in islemler:
            f = fiyatlar[coinler[rng.integers(len(coinler))]]
            tarih = f["tarih"].astype("datetime64[ns]")
            mum = (tarih[1] - tarih[0]) if len(tarih) > 1 else np.timedelta64(1, "h")
            adim = max(1, int(math.ceil(np.timedelta64(int(islem["sure_dakika"] * 60), "s") / mum)))
            k_bas = int(np.searchsorted(tarih, bas64))
            k_son = int(np.searchsorted(tarih, son64)) - adim - 1
            if k_son <= k_bas + 1:
                continue
            k = int(rng.integers(k_bas + 1, k_son))
            alim = islem["yon"] == "alim"
            giris = f["acilis"][k] * (1 + f["kayma"][k - 1] / 100.0 if alim else 1 - f["kayma"][k - 1] / 100.0)
            c = k + adim - 1
            cikis = f["kapanis"][c] * (1 - f["kayma"][c] / 100.0 if alim else 1 + f["kayma"][c] / 100.0)
            brut = (cikis / giris - 1.0) * 100.0 if alim else (giris - cikis) / giris * 100.0
            fon = fonlama_maliyeti(f["fonlama"], pd.Timestamp(tarih[k], tz="UTC"),
                                   pd.Timestamp(tarih[c], tz="UTC") + pd.Timedelta(mum), alim)
            sonuclar.append(brut - 2.0 * KOMISYON - fon)
    return float(np.mean(sonuclar)) if sonuclar else None


def plasebo_t(islemler: list[dict], plasebo_ort: float | None) -> float | None:
    """(Gerçek işlem başına net - plasebo) / gerçek ortalamanın standart hatası."""
    if plasebo_ort is None or len(islemler) < 2:
        return None
    dizi = np.array([i["net_yuzde"] for i in islemler])
    se = dizi.std(ddof=1) / math.sqrt(len(dizi))
    return float((dizi.mean() - plasebo_ort) / se) if se > 0 else None


# --------------------------------------------------------------------------
# Karar ve rapor
# --------------------------------------------------------------------------


def karar(aile: dict, canli: dict, maliyet2: dict, plasebo_t_degeri, kural_plasebo_farklari: dict,
          deneme_netleri: dict) -> tuple[str, list[str]]:
    """Önceden yazılmış ölçütlere göre: ('GEÇTİ' | 'KALDI' | 'HÜKÜM YOK', nedenler)."""
    nedenler = []
    if canli["islem"] < max(aile["en_az_islem"], 1) or canli["gun_sayisi"] < aile["en_az_gun"]:
        gerek = " ve ".join(p for p in (f"{aile['en_az_islem']} işlem" if aile["en_az_islem"] else "",
                                         f"{aile['en_az_gun']} ayrı gün" if aile["en_az_gun"] else "") if p)
        return "HÜKÜM YOK", [f"yetersiz örnek: {canli['islem']} işlem, {canli['gun_sayisi']} ayrı gün "
                             f"(en az {gerek or '1 işlem'} gerekir)"]
    if canli["net"] <= 0:
        nedenler.append("maliyetler dahil toplam ekside")
    if canli["net_yuzde"] < aile["esik_net_yuzde"]:
        nedenler.append(f"işlem başına net %{_s(canli['net_yuzde'], 3)} < %{_s(aile['esik_net_yuzde'], 2, False)}")
    if aile["esik_brut_yuzde"] is not None and canli["brut_yuzde"] < aile["esik_brut_yuzde"]:
        nedenler.append(f"komisyon öncesi işlem başına %{_s(canli['brut_yuzde'], 3)} < "
                        f"%{_s(aile['esik_brut_yuzde'], 2, False)}")
    if maliyet2["net"] < 0:
        nedenler.append("maliyet iki katında ekside")
    if canli["t"] < T_ESIGI:
        nedenler.append(f"gün bazında t {_s(canli['t'], 2, False)} < {_s(T_ESIGI, 1, False)}")
    yil_sayisi = len(canli["yillar"])
    if canli["artida_yil"] < yil_sayisi - 1:
        nedenler.append(f"artıda yıl {canli['artida_yil']} / {yil_sayisi}")
    if plasebo_t_degeri is None or plasebo_t_degeri < PLASEBO_T_ESIGI:
        nedenler.append("rastgele giriş plasebosunu geçemedi"
                        + (f" (t {_s(plasebo_t_degeri, 2, False)})" if plasebo_t_degeri is not None else ""))
    esik_r = aile.get("kural_plasebo_r")
    for ad, fark in kural_plasebo_farklari.items():
        if esik_r is not None:
            if fark is None or fark < esik_r:
                nedenler.append(f"{ad} plasebosundan işlem başına en az {_s(esik_r, 2, False)}R iyi değil")
        elif fark is None or fark < KURAL_PLASEBO_FARKI:
            nedenler.append(f"{ad} plasebosundan işlem başına en az %{_s(KURAL_PLASEBO_FARKI, 2, False)} iyi değil")
    if aile.get("esik_net_r") is not None and canli["ort_r"] < aile["esik_net_r"]:
        nedenler.append(f"işlem başına ortalama {_s(canli['ort_r'], 2)}R < {_s(aile['esik_net_r'], 2, False)}R")
    if aile.get("en_az_kazanc_kayip") is not None and (
            canli["kazanc_kayip"] is None or canli["kazanc_kayip"] < aile["en_az_kazanc_kayip"]):
        nedenler.append(f"ortalama kazanç / kayıp {_s(canli['kazanc_kayip'], 2, False)} < "
                        f"{_s(aile['en_az_kazanc_kayip'], 1, False)}")
    if aile.get("en_fazla_dusus") is not None and canli["dusus"] > aile["en_fazla_dusus"]:
        nedenler.append(f"en büyük düşüş {_s(canli['dusus'], 1, False)} USDT > {_s(aile['en_fazla_dusus'], 0, False)}")
    if aile["en_iyi_3_gun"] and canli["en_iyi_3_gun_payi"] is not None and canli["en_iyi_3_gun_payi"] > 0.5:
        nedenler.append("kârın yarısından fazlası en iyi 3 günden")
    if aile["trend"]:
        artida = sum(1 for v in deneme_netleri.values() if v > 0)
        if artida < 2:
            nedenler.append(f"kanal uzunluklarının yalnız {artida} / {len(deneme_netleri)} tanesi artıda")
        if canli["artida_coin"] < 3:
            nedenler.append("3'ten az coinde artıda")
        if canli["en_iyi_3_islem_haric"] < -BAKIYE * 0.02:
            nedenler.append("en iyi 3 işlem çıkınca kayıp bakiyenin %2'sini aşıyor")
    if aile["btc_iliskisi"] and canli["btc_iliski"] is not None and canli["btc_iliski"] > 0.5:
        nedenler.append(f"BTC ile ilişki {_s(canli['btc_iliski'], 2, False)} > 0,5 (kâr piyasa yönünden)")
    return ("KALDI" if nedenler else "GEÇTİ"), nedenler


def _s(deger, basamak=2, isaret=True) -> str:
    if deger is None:
        return "-"
    return (f"{deger:+.{basamak}f}" if isaret else f"{deger:.{basamak}f}").replace(".", ",")


def fonlama_olaylari(fonlama: pd.DataFrame | None, bas, son) -> dict:
    """Aşırı fonlama olayları: ard arda ödemeler tek olay sayılır.

    Oran 8 saate çevrilir (bazı coinler 4 ya da 1 saatte bir öder). 'alim_kalabalik':
    tek ödeme >= FONLAMA_ASIRI ve son 3 ödeme ortalaması >= FONLAMA_ASIRI_ORTALAMA
    (kalabalık alımda, açığa satış adayı); 'satis_kalabalik' aynası.
    """
    sonuc = {"alim_kalabalik": 0, "satis_kalabalik": 0}
    if fonlama is None or len(fonlama) < 4:
        return sonuc
    tablo = fonlama[(fonlama["date"] >= bas) & (fonlama["date"] < son)].sort_values("date")
    if len(tablo) < 4:
        return sonuc
    aralik_saat = tablo["date"].diff().dt.total_seconds().div(3600).clip(lower=1, upper=8).fillna(8)
    oran = tablo["oran_yuzde"].to_numpy() * (8.0 / aralik_saat.to_numpy())
    ortalama = pd.Series(oran).rolling(3).mean().to_numpy()
    for ad, isaret in (("alim_kalabalik", 1), ("satis_kalabalik", -1)):
        olay = (isaret * oran >= FONLAMA_ASIRI) & (isaret * ortalama >= FONLAMA_ASIRI_ORTALAMA)
        sonuc[ad] = int(np.sum(olay[1:] & ~olay[:-1]) + (1 if len(olay) and olay[0] else 0))
    return sonuc


def fonlama_sayimi(kaynak: Kaynak, bas, son) -> str:
    satirlar = [f"FONLAMA AŞIRILIĞI SAYIMI (bot değil; tek ödeme >= %{_s(FONLAMA_ASIRI, 2, False)} ve son 3 "
                f"ortalaması >= %{_s(FONLAMA_ASIRI_ORTALAMA, 2, False)}, 8 saate çevrilmiş; ard arda ödemeler tek olay)"]
    toplam = {"alim_kalabalik": 0, "satis_kalabalik": 0}
    parcalar = []
    for coin in COINLER:
        o = fonlama_olaylari(kaynak.fonlama(coin), bas, son)
        toplam = {k: toplam[k] + o[k] for k in toplam}
        if o["alim_kalabalik"] or o["satis_kalabalik"]:
            parcalar.append(f"{coin} {o['alim_kalabalik']}/{o['satis_kalabalik']}")
    satirlar.append(f"  Kalabalık alımda: {toplam['alim_kalabalik']} olay; kalabalık açığa satışta: "
                    f"{toplam['satis_kalabalik']} olay (dönem boyunca, {len(COINLER)} coin).")
    satirlar.append("  Coin başına (alım / satış): " + (", ".join(parcalar) if parcalar else "yok"))
    satirlar.append("  Panelin kararı: 3 yılda 100'den az olay varsa bu fikir bot olmaz, en çok süzgeç olur.")
    return "\n".join(satirlar)


def btc_gunluk_getiri(kaynak: Kaynak) -> pd.Series | None:
    tablo = kaynak.mum(REFERANS, "1d")
    if tablo is None or tablo.empty:
        return None
    kapanis = pd.Series(tablo["close"].astype(float).to_numpy(), index=pd.to_datetime(tablo["date"], utc=True))
    return kapanis.pct_change() * 100.0


def sina(yukle: MumYukleyici, fonlama_yukle: FonlamaYukleyici, adaylar: list[dict] | None = None) -> tuple[str, dict]:
    """Bütün aday aileleri sınar. Dönen: (rapor metni, sonuçlar)."""
    adaylar = adaylar if adaylar is not None else ADAYLAR
    kaynak = Kaynak(yukle, fonlama_yukle)
    gel_bas, ayr_bas, son = donemler(kaynak.mum)
    bas, bitis = (gel_bas, son) if AYRILMIS_ACIK else (gel_bas, ayr_bas)
    btc = btc_gunluk_getiri(kaynak)
    deneme_sayisi = sum(len(a["denemeler"]) for a in adaylar)

    y: list[str] = []
    yaz = y.append
    yaz("PANEL SINAMASI: aday botlar")
    yaz(f"Hazırlandı: {pd.Timestamp.now(tz='UTC'):%d.%m.%Y %H:%M} UTC.")
    yaz(f"Dönem: {bas:%d.%m.%Y} - {bitis:%d.%m.%Y}. "
        + ("Son yıl AÇIK (ayrılmış yıl dahil)." if AYRILMIS_ACIK else
           f"Son yıl ({ayr_bas:%d.%m.%Y} - {son:%d.%m.%Y}) ayrılmış, KAPALI: hiçbir hesapta yok."))
    yaz(f"Coinler ({len(COINLER)}): {', '.join(COINLER)}. BTC yalnız referans.")
    yaz(f"Maliyet: taraf başına %{_s(KOMISYON, 2, False)} komisyon + kayma (sinyal mumu aralığının "
        f"%{KAYMA_ORANI * 100:g}'u, en az kuralınki) + fonlama. Tutar riske göre: stopta ~1 USDT, en çok 100 USDT.")
    yaz(f"Deneme defteri: önceki {ONCEKI_DENEME} + bu sınamada {deneme_sayisi} = {ONCEKI_DENEME + deneme_sayisi}."
        f" Çıta: gün bazında t >= {_s(T_ESIGI, 1, False)}; plasebo farkında t >= {_s(PLASEBO_T_ESIGI, 1, False)}.")
    yaz("Uyarı: coin listesi bugün borsada olanlardır (çıkarılanlar yok); sonuç biraz iyimserdir.")
    yaz("")

    sonuclar: dict = {"denemeler": {}, "aileler": {}}
    canli_adaylar = []
    tum_eksik: set = set()
    for aile in adaylar:
        yaz(f"=== {aile['ad']}: {aile['baslik']} ===")
        deneme_netleri = {}
        canli = canli2 = plasebo_t_degeri = None
        canli_kural = None
        kural_plasebo_farklari = {}
        for kod in aile["denemeler"] + list(aile["kural_plasebolari"]) + list(aile.get("bilgi_plasebolari", {})):
            kural = kural_yukle(kod)
            canli_mi = kod == aile["canli"]
            uretim = bot_adaylari(kural, kaynak, bas, bitis, plasebo_icin=canli_mi)
            tum_eksik.update(uretim["eksik"])
            kabul = portfoy_gecisi([(kod, kural, uretim["adaylar"][1])])[kod]
            o = olcumler(kabul, bas, bitis, btc)
            sonuclar["denemeler"][kod] = o
            if kod in aile["kural_plasebolari"] or kod in aile.get("bilgi_plasebolari", {}):
                continue
            deneme_netleri[kod] = o["net"]
            ozet = _ozet(kural_dosyasi(kod))
            yaz(f"  {kod}{' (canlıya gidecek)' if canli_mi else ''}  [dosya özeti {ozet}]")
            yaz(f"    {cikis_metni(kural['cikis'])}")
            yaz(f"    İşlem {o['islem']}, kazanma %{_s(o['kazanma'], 1, False)}, net {_s(o['net'])} USDT, "
                f"işlem başına net %{_s(o['net_yuzde'], 3)} (komisyon öncesi %{_s(o['brut_yuzde'], 3)}, "
                f"fonlama %{_s(o['fonlama_yuzde'], 3)})")
            yaz(f"    Gün bazında t {_s(o['t'], 2, False)}, en büyük düşüş {_s(o['dusus'], 2, False)} USDT, "
                f"ayrı gün {o['gun_sayisi']}, ort. süre {_s(o['ort_sure_saat'], 1, False)} saat, "
                f"işlem başına {_s(o['ort_r'], 2)}R, ort. kazanç / kayıp {_s(o['kazanc_kayip'], 2, False)}")
            yaz("    Yıllar (net USDT): " + " | ".join(_s(v) for v in o["yillar"])
                + f"; artıda coin {o['artida_coin']}")
            yaz("    Çıkışlar: " + ", ".join(f"{k} {v}" for k, v in sorted(o["nedenler"].items())))
            if canli_mi:
                canli, canli_kural = o, kural
                canli_adaylar.append((kod, kural, uretim["adaylar"][1]))
                canli2 = olcumler(portfoy_gecisi([(kod, kural, uretim["adaylar"][2])])[kod], bas, bitis, btc)
                plasebo_ort = rastgele_plasebo(kabul, uretim["fiyatlar"], bas, bitis)
                plasebo_t_degeri = plasebo_t(kabul, plasebo_ort)
                yaz(f"    Maliyet iki katında: net {_s(canli2['net'])} USDT")
                yaz(f"    Rastgele giriş plasebosu: işlem başına %{_s(plasebo_ort, 3)}; fark t "
                    f"{_s(plasebo_t_degeri, 2, False)}")
                if o["btc_iliski"] is not None:
                    yaz(f"    Günlük sonucun BTC ile ilişkisi {_s(o['btc_iliski'], 2, False)}")
                for ad in canli_kural.get("bilgi", {}):
                    for deger in (True, False):
                        alt = [i for i in kabul if i["bilgi"].get(ad) == deger]
                        ort = np.mean([i["net_yuzde"] for i in alt]) if alt else None
                        yaz(f"    Bilgi ({ad} = {'evet' if deger else 'hayır'}): {len(alt)} işlem, "
                            f"işlem başına %{_s(ort, 3)}")
                del uretim
        r_ile = aile.get("kural_plasebo_r") is not None
        for kod, aciklama in list(aile["kural_plasebolari"].items()) + list(aile.get("bilgi_plasebolari", {}).items()):
            p = sonuclar["denemeler"][kod]
            bilgi = kod not in aile["kural_plasebolari"]
            if r_ile:
                fark = (canli["ort_r"] - p["ort_r"]) if p["islem"] else None
                yaz(f"  {'Bilgi için plasebo' if bilgi else 'Kural plasebosu'} {kod} ({aciklama}): {p['islem']} işlem, "
                    f"işlem başına {_s(p['ort_r'], 2)}R, net {_s(p['net'])} USDT; asıl kural farkı {_s(fark, 2)}R")
            else:
                fark = (canli["net_yuzde"] - p["net_yuzde"]) if p["islem"] else None
                yaz(f"  {'Bilgi için plasebo' if bilgi else 'Kural plasebosu'} {kod} ({aciklama}): {p['islem']} işlem, "
                    f"işlem başına %{_s(p['net_yuzde'], 3)}; asıl kural farkı %{_s(fark, 3)}")
            if not bilgi:
                kural_plasebo_farklari[kod] = fark
        hukum, nedenler = karar(aile, canli, canli2, plasebo_t_degeri, kural_plasebo_farklari, deneme_netleri)
        yaz(f"  KARAR ({aile['canli']}): {hukum}")
        for n in nedenler:
            yaz(f"    - {n}")
        yaz("")
        sonuclar["aileler"][aile["ad"]] = {"karar": hukum, "nedenler": nedenler}

    # Bilgi için: canlıya gidecek denemeler tek portföyde, ortak frenlerle.
    ortak = portfoy_gecisi(canli_adaylar, ortak=True)
    hepsi = [i for liste in ortak.values() for i in liste]
    o = olcumler(hepsi, bas, bitis, btc)
    yaz("PANEL PORTFÖYÜ (bilgi için; canlıya gidecek denemeler birlikte, aynı yönde en çok "
        f"{AYNI_YON_ORTAK_SINIR} pozisyon, ortak günlük fren)")
    yaz(f"  İşlem {o['islem']}, net {_s(o['net'])} USDT, gün bazında t {_s(o['t'], 2, False)}, "
        f"en büyük düşüş {_s(o['dusus'], 2, False)} USDT; yıllar: " + " | ".join(_s(v) for v in o["yillar"]))
    yaz("")
    yaz(fonlama_sayimi(kaynak, bas, bitis))
    yaz("")
    if tum_eksik:
        yaz(f"Eksik veri ({len(tum_eksik)}): " + ", ".join(sorted(tum_eksik)[:30]))
        yaz("")
    yaz("ÖZET")
    for aile in adaylar:
        s = sonuclar["aileler"][aile["ad"]]
        yaz(f"  {aile['ad']} ({aile['canli']}): {s['karar']}")
    yaz("")
    yaz("NASIL OKUNMALI")
    yaz("  'GEÇTİ' kazandıracağı anlamına gelmez: yalnız önceden yazılmış ölçütleri ilk 3 yılda geçti")
    yaz("  demektir. Geçenler ayrılmış son yılda bir kez sınanır; orada da artıda kalırsa sanal bot")
    yaz("  olarak 30 günlük canlı sınava girer. 'KALDI' ise bot kurulmaz. Bu rapor hiçbir ayarı değiştirmez.")
    return "\n".join(y) + "\n", sonuclar
