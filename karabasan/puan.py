"""Karabasan: piyasa ortamı puanı, durumlar ve veto kuralları.

Formül (tasarım raporundaki başlangıç değerleri):

    K = 0,30*T + 0,20*S + 0,25*A + 0,15*G + 0,10*M

    T  BTC trendi          S  BTC sakinliği      A  Altcoin akışı
    G  Piyasa genişliği    M  Makro risk

Her bileşen 0 ile 100 arasında bir alt puandır. Bir bileşenin verisi yoksa
(örneğin NASDAQ kapalıyken makro), ağırlığı diğer bileşenlere dağıtılır.

Bu modül veri çekmez; yalnız hesap yapar. Bu yüzden sunucu olmadan sınanır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from . import gostergeler as g

AGIRLIKLAR = {"T": 0.30, "S": 0.20, "A": 0.25, "G": 0.15, "M": 0.10}

BILESEN_ADLARI = {
    "T": "BTC trendi",
    "S": "BTC sakinliği",
    "A": "Altcoin akışı",
    "G": "Piyasa genişliği",
    "M": "Makro risk",
}

ESIK_YESIL = 65.0
ESIK_SARI = 45.0
YUKSELIS_ICIN_OLCUM = 3  # daha iyi duruma geçmek için üst üste gereken ölçüm

# Durumların sırası: büyük sayı daha iyi.
DURUM_SIRASI = {"SIYAH": 0, "KIRMIZI": 1, "SARI": 2, "YESIL": 3}

DURUM_ADI = {"YESIL": "Yeşil", "SARI": "Sarı", "KIRMIZI": "Kırmızı", "SIYAH": "Siyah"}

# Altcoin akışı matrisi: (BTC yönü, dominans yönü) -> alt puan
AKIS_MATRISI = {
    ("yukseliyor", "dusuyor"): (100.0, "Para altcoinlere akıyor"),
    ("yatay", "dusuyor"): (85.0, "Altcoinler BTC'den bağımsız güçleniyor"),
    ("yukseliyor", "yukseliyor"): (55.0, "Yükselişi BTC götürüyor, altcoinler geride"),
    ("yatay", "yukseliyor"): (30.0, "Altcoinlerden BTC'ye kaçış"),
    ("dusuyor", "dusuyor"): (15.0, "Her şey düşüyor"),
    ("dusuyor", "yukseliyor"): (0.0, "Altcoinler BTC'den sert düşüyor"),
}

VETO_ESIKLERI = {
    "btc_15dk_dusus_yuzde": 1.5,
    "btc_1s_dusus_yuzde": 3.0,
    "btc_veto_dakika": 120,
    "art_arda_stop": 4,
    "art_arda_stop_dakika": 60,
    "veri_bayat_saniye": 30,
    "sabit_coin_sapma_yuzde": 0.5,
    "nasdaq_dusus_yuzde": 2.0,
    "takvim_once_dakika": 30,
    "takvim_sonra_dakika": 60,
}


def _sinirla(deger: float, alt: float = 0.0, ust: float = 100.0) -> float:
    return max(alt, min(ust, float(deger)))


def _dogrusal(deger: float, x0: float, x1: float, y0: float, y1: float) -> float:
    """deger x0'da y0, x1'de y1 olacak biçimde doğrusal eşleme; uçlarda sabit kalır."""
    if x1 == x0:
        return y0
    oran = (deger - x0) / (x1 - x0)
    oran = max(0.0, min(1.0, oran))
    return y0 + oran * (y1 - y0)


# --------------------------------------------------------------------------
# Bileşenler
# --------------------------------------------------------------------------


def btc_trend_puani(kapanis_4s: pd.Series, kapanis_1s: pd.Series) -> float | None:
    """T: BTC'nin 4 saatlik ortalamalara göre yeri ve 1 saatlik eğimi.

    40 puan: fiyat 4 saatlik EMA50'nin üstünde
    30 puan: 4 saatlik EMA50, EMA200'ün üstünde
    30 puan: 1 saatlik EMA20'nin son 6 saatteki eğimi (-%1 -> 0, +%1 -> 30)
    """
    if len(kapanis_4s) < 200 or len(kapanis_1s) < 30:
        return None
    ema50 = g.ema(kapanis_4s, 50).iloc[-1]
    ema200 = g.ema(kapanis_4s, 200).iloc[-1]
    ema20_1s = g.ema(kapanis_1s, 20)
    egim = (ema20_1s.iloc[-1] / ema20_1s.iloc[-7] - 1.0) * 100.0
    if pd.isna(ema50) or pd.isna(ema200) or pd.isna(egim):
        return None
    puan = 0.0
    if kapanis_4s.iloc[-1] > ema50:
        puan += 40.0
    if ema50 > ema200:
        puan += 30.0
    puan += _dogrusal(egim, -1.0, 1.0, 0.0, 30.0)
    return _sinirla(puan)


def btc_sakinlik_puani(mumlar_1s: pd.DataFrame) -> float | None:
    """S: 1 saatlik oynaklığın son 30 günün ortancasına oranı.

    Oran 0,8 ve altı -> 100 (sakin); 2,0 ve üstü -> 0 (fırtınalı).
    """
    if len(mumlar_1s) < 24 * 30 + 15:
        return None
    oynaklik = g.atr_yuzde(mumlar_1s, 14)
    ortanca = oynaklik.iloc[-24 * 30:].median()
    simdi = oynaklik.iloc[-1]
    if pd.isna(ortanca) or pd.isna(simdi) or ortanca <= 0:
        return None
    return _sinirla(_dogrusal(simdi / ortanca, 0.8, 2.0, 100.0, 0.0))


def yon(degisim_yuzde: float, esik: float) -> str:
    """Yüzde değişimi 'yukseliyor', 'dusuyor' ya da 'yatay' olarak adlandırır."""
    if degisim_yuzde > esik:
        return "yukseliyor"
    if degisim_yuzde < -esik:
        return "dusuyor"
    return "yatay"


def altcoin_akisi_puani(
    btc_degisim_24s_yuzde: float | None,
    dominans_degisim_24s_puan: float | None,
    total2_ema_ustunde: bool | None,
) -> tuple[float | None, str]:
    """A: BTC'nin yönü ile dominansın yönü birlikte okunur.

    TOTAL2 kendi 4 saatlik EMA50'sinin altındaysa alt puandan 20 düşülür.
    Dönen ikili: (alt puan, düz Türkçe açıklama).
    """
    if btc_degisim_24s_yuzde is None or dominans_degisim_24s_puan is None:
        return None, "Dominans verisi yok"
    btc_yon = yon(btc_degisim_24s_yuzde, 1.0)
    dominans_yon = "yukseliyor" if dominans_degisim_24s_puan >= 0 else "dusuyor"
    puan, aciklama = AKIS_MATRISI[(btc_yon, dominans_yon)]
    if total2_ema_ustunde is False:
        puan -= 20.0
        aciklama += "; TOTAL2 ortalamasının altında"
    return _sinirla(puan), aciklama


def genislik_puani(ema_ustundeki_coin: int, toplam_coin: int) -> float | None:
    """G: izlenen coinlerin yüzde kaçı 1 saatlik EMA50'sinin üstünde."""
    if toplam_coin <= 0:
        return None
    return _sinirla(ema_ustundeki_coin / toplam_coin * 100.0)


def makro_puani(
    nasdaq_degisim_yuzde: float | None,
    altin_degisim_yuzde: float | None = None,
) -> float | None:
    """M: NASDAQ'ın günlük yönü; altın yükselirken NASDAQ düşüyorsa riskten kaçış.

    NASDAQ verisi yoksa (piyasa kapalı) None döner ve ağırlığı dağıtılır.
    """
    if nasdaq_degisim_yuzde is None:
        return None
    puan = 50.0 + _dogrusal(nasdaq_degisim_yuzde, -1.0, 1.0, -25.0, 25.0)
    if (
        altin_degisim_yuzde is not None
        and altin_degisim_yuzde > 1.0
        and nasdaq_degisim_yuzde < -0.5
    ):
        puan -= 25.0
    return _sinirla(puan)


def karabasan_puani(bilesenler: dict, agirliklar: dict | None = None) -> tuple[float | None, dict]:
    """Bileşenlerden toplam puanı hesaplar.

    bilesenler: {"T": 80, "S": 60, "A": None, ...}. None olanların ağırlığı
    diğerlerine oranlı dağıtılır. Dönen ikili: (puan, kullanılan ağırlıklar).
    T (BTC trendi) yoksa puan üretilmez.
    """
    agirliklar = agirliklar or AGIRLIKLAR
    if bilesenler.get("T") is None:
        return None, {}
    mevcut = {k: a for k, a in agirliklar.items() if bilesenler.get(k) is not None}
    toplam = sum(mevcut.values())
    if toplam <= 0:
        return None, {}
    kullanilan = {k: a / toplam for k, a in mevcut.items()}
    puan = sum(float(bilesenler[k]) * a for k, a in kullanilan.items())
    return round(_sinirla(puan), 1), kullanilan


def puandan_durum(puan: float) -> str:
    """Puanın tek başına karşılık geldiği durum (histerezis ve veto hariç)."""
    if puan >= ESIK_YESIL:
        return "YESIL"
    if puan >= ESIK_SARI:
        return "SARI"
    return "KIRMIZI"


# --------------------------------------------------------------------------
# Vetolar
# --------------------------------------------------------------------------


@dataclass
class Veto:
    kod: str
    gerekce: str
    bitis: datetime | None  # None: koşul düzelene kadar


def veto_kontrol(simdi: datetime, girdi: dict, esikler: dict | None = None) -> list[Veto]:
    """Şu anda tetiklenen vetoları döndürür.

    girdi alanları (hepsi isteğe bağlı; verilmeyen kontrol edilmez):
      btc_15dk_degisim_yuzde, btc_1s_degisim_yuzde, gunluk_zarar_doldu (bool),
      art_arda_stop (int), veri_yasi_saniye, sabit_coin_fiyati,
      nasdaq_seans_degisim_yuzde, takvim_olaylari (datetime listesi),
      acil_stop (bool)
    """
    e = {**VETO_ESIKLERI, **(esikler or {})}
    vetolar: list[Veto] = []

    d15 = girdi.get("btc_15dk_degisim_yuzde")
    if d15 is not None and d15 <= -e["btc_15dk_dusus_yuzde"]:
        vetolar.append(Veto(
            "btc_ani_dusus",
            f"BTC 15 dakikada %{abs(d15):.1f} düştü".replace(".", ","),
            simdi + timedelta(minutes=e["btc_veto_dakika"]),
        ))
    d1s = girdi.get("btc_1s_degisim_yuzde")
    if d1s is not None and d1s <= -e["btc_1s_dusus_yuzde"]:
        vetolar.append(Veto(
            "btc_ani_dusus",
            f"BTC 1 saatte %{abs(d1s):.1f} düştü".replace(".", ","),
            simdi + timedelta(minutes=e["btc_veto_dakika"]),
        ))
    if girdi.get("gunluk_zarar_doldu"):
        gun_sonu = (simdi + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        vetolar.append(Veto("gunluk_zarar", "Günlük zarar limiti doldu", gun_sonu))
    stoplar = girdi.get("art_arda_stop")
    if stoplar is not None and stoplar >= e["art_arda_stop"]:
        vetolar.append(Veto(
            "art_arda_stop",
            f"Art arda {stoplar} stop",
            simdi + timedelta(minutes=e["art_arda_stop_dakika"]),
        ))
    yas = girdi.get("veri_yasi_saniye")
    if yas is not None and yas > e["veri_bayat_saniye"]:
        vetolar.append(Veto("veri_bayat", f"Fiyat verisi {int(yas)} saniyedir güncellenmiyor", None))
    sabit = girdi.get("sabit_coin_fiyati")
    if sabit is not None and abs(sabit - 1.0) * 100.0 > e["sabit_coin_sapma_yuzde"]:
        sapma = abs(sabit - 1.0) * 100.0
        vetolar.append(Veto(
            "sabit_coin_sapma",
            f"USDT sabitinden %{sapma:.2f} saptı".replace(".", ","),
            None,
        ))
    nasdaq = girdi.get("nasdaq_seans_degisim_yuzde")
    if nasdaq is not None and nasdaq <= -e["nasdaq_dusus_yuzde"]:
        vetolar.append(Veto(
            "nasdaq_dusus",
            f"NASDAQ seans içinde %{abs(nasdaq):.1f} düştü".replace(".", ","),
            None,
        ))
    for olay in girdi.get("takvim_olaylari", []):
        basla = olay - timedelta(minutes=e["takvim_once_dakika"])
        bitis = olay + timedelta(minutes=e["takvim_sonra_dakika"])
        if basla <= simdi <= bitis:
            vetolar.append(Veto("takvim", "Önemli ekonomik veri açıklaması penceresi", bitis))
    if girdi.get("acil_stop"):
        vetolar.append(Veto("acil_stop", "Acil stop elle verildi", None))
    return vetolar


# --------------------------------------------------------------------------
# Durum makinesi: açılması yavaş, kapanması hızlı
# --------------------------------------------------------------------------


@dataclass
class DurumMakinesi:
    """Karabasan'ın durumunu ölçümden ölçüme taşır.

    - Daha kötü duruma geçiş anında uygulanır.
    - Daha iyi duruma geçmek için puan üst üste YUKSELIS_ICIN_OLCUM ölçümde
      o durumun eşiğinin üstünde kalmalıdır; geçiş bir basamak yapılır.
    - Süreli bir veto, süresi dolana kadar botu Siyah'ta tutar.
    """

    durum: str = "KIRMIZI"
    aday: str | None = None
    aday_sayaci: int = 0
    veto_bitis: datetime | None = None
    veto_gerekce: str = ""
    gecmis: list = field(default_factory=list)

    def guncelle(self, simdi: datetime, puan: float | None, vetolar: list[Veto]) -> dict:
        onceki = self.durum

        # 1) Vetolar
        if vetolar:
            bitisler = [v.bitis for v in vetolar if v.bitis is not None]
            if bitisler:
                en_gec = max(bitisler)
                if self.veto_bitis is None or en_gec > self.veto_bitis:
                    self.veto_bitis = en_gec
            self.veto_gerekce = "; ".join(v.gerekce for v in vetolar)
        veto_surer = bool(vetolar) or (self.veto_bitis is not None and simdi < self.veto_bitis)
        if not veto_surer:
            self.veto_bitis = None

        if veto_surer or puan is None:
            self.durum = "SIYAH"
            self.aday, self.aday_sayaci = None, 0
            if puan is None and not veto_surer:
                self.veto_gerekce = "Puan hesaplanamadı (veri eksik)"
        else:
            hedef = puandan_durum(puan)
            # Vetodan çıkışta en kötü işlem durumundan başlanır.
            mevcut = "KIRMIZI" if self.durum == "SIYAH" else self.durum
            if DURUM_SIRASI[hedef] < DURUM_SIRASI[mevcut]:
                # Kötüleşme: anında.
                mevcut = hedef
                self.aday, self.aday_sayaci = None, 0
            elif DURUM_SIRASI[hedef] > DURUM_SIRASI[mevcut]:
                # İyileşme: bir üst basamak için üst üste ölçüm gerekir.
                bir_ust = {"KIRMIZI": "SARI", "SARI": "YESIL"}[mevcut]
                if self.aday == bir_ust:
                    self.aday_sayaci += 1
                else:
                    self.aday, self.aday_sayaci = bir_ust, 1
                if self.aday_sayaci >= YUKSELIS_ICIN_OLCUM:
                    mevcut = bir_ust
                    self.aday, self.aday_sayaci = None, 0
            else:
                self.aday, self.aday_sayaci = None, 0
            self.durum = mevcut
            self.veto_gerekce = ""

        kayit = {
            "zaman": simdi,
            "puan": puan,
            "durum": self.durum,
            "onceki_durum": onceki,
            "degisti": self.durum != onceki,
            "veto": self.veto_gerekce if self.durum == "SIYAH" else "",
            "veto_bitis": self.veto_bitis if self.durum == "SIYAH" else None,
        }
        self.gecmis.append(kayit)
        return kayit


def gerekce_metni(puan: float | None, durum: str, bilesenler: dict, veto: str = "") -> str:
    """Kararın düz Türkçe gerekçesi (panel, Telegram ve kayıt defteri için)."""
    if durum == "SIYAH":
        return f"Siyah: {veto or 'veto'}. Yeni alım yok."
    parcalar = []
    for kod in ("T", "S", "A", "G", "M"):
        deger = bilesenler.get(kod)
        if deger is None:
            continue
        parcalar.append(f"{BILESEN_ADLARI[kod]} {float(deger):.0f}")
    puan_metni = f"{puan:.1f}".replace(".", ",") if puan is not None else "yok"
    return f"{DURUM_ADI[durum]}: puan {puan_metni} ({', '.join(parcalar)})."


def durum_ayarlari(durum: str) -> dict:
    """Bir durumda botun nasıl davranacağı (gerçek para aşamasında kullanılır)."""
    return {
        "YESIL": {"yeni_alim": True, "pozisyon_carpani": 1.0},
        "SARI": {"yeni_alim": True, "pozisyon_carpani": 0.5},
        "KIRMIZI": {"yeni_alim": False, "pozisyon_carpani": 0.0},
        "SIYAH": {"yeni_alim": False, "pozisyon_carpani": 0.0},
    }[durum]
