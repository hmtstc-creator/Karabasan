"""Emir defteri denemesi: BTC/USDT vadeli, ileriye dönük, sanal.

Ahmet'in fikri (12 Ekim 2026): her saniye Binance'in açık emir defterine
(alış ve satış emirlerinin listesi) bakıp, hacim, RSI, destek ve direnç ile
birlikte fiyatın 5 ve 15 dakika sonra nerede olacağını kestirmek; kestirilen
hareket komisyonu karşılıyorsa sanal bir pozisyon açıp hedefe ulaşıp
ulaşmadığını görmek. Geçmiş emir defteri verisi elde olmadığı için bu deneme
yalnız ileriye dönük yapılır: bugünden sonra ne olduğunu kaydeder.

Bu modül hesap kısmıdır (karabasan.defter_servisi her saniye çağırır):

- defter_ozeti: emir defterinden dengesizlik, mikro fiyat, alış / satış duvarları.
- ozellik_vektoru: defter + son fiyatlar + 1 dakikalık mumlar (RSI, hacim,
  destek / direnç) -> sayı listesi.
- Model: sayılardan "5 / 15 dakika sonra fiyat yüzde kaç değişir" tahmini.
  Önceden hazırlanmış bir formül yoktur; model yalnız kendi kaydettiği
  geçmişten öğrenir (kaydedilen her an için, 5 / 15 dakika sonra gerçekte ne
  olduğu belli olunca). Hiç bilmediği bir şeyi bilmiş gibi yapmasın diye
  öğrenme için en az birkaç saatlik kayıt bekler.
- islem_ac / islem_denetle: sanal pozisyon. Borsaya hiçbir emir gitmez.

Geleceğe bakmak yasak (5. kural): bir anın özellikleri yalnız o ana kadar
kapanmış mumlardan ve o anki defterden hesaplanır; model yalnız sonucu
gerçekleşmiş (olgunlaşmış) örneklerle eğitilir.
"""

from __future__ import annotations

import math

import numpy as np

SEMBOL = "BTCUSDT"
# Tahmin ufukları: ad -> saniye
UFUKLAR = {"5dk": 300, "15dk": 900}
# Vadeli, piyasa emri (alıcı / taker) komisyonu: taraf başına yüzde.
KOMISYON_YUZDE = 0.05
GIDIS_DONUS_YUZDE = 2 * KOMISYON_YUZDE
# Beklenen hareket bundan küçükse işlem açılmaz: gidiş-dönüş komisyon %0,10,
# üstüne en az %0,05 pay.
EN_AZ_TAHMIN_YUZDE = 0.15
# Binance BTC vadelide en küçük emir 100 USDT; sanal işlem tutarı buna göre.
ISLEM_TUTARI_USDT = 100.0
KALDIRAC = 1.0
# Tasfiye (likidasyon) fiyatı hesabında bakım teminatı oranı (BTC, küçük pozisyon).
BAKIM_TEMINATI = 0.004
# Model, en az bu kadar olgunlaşmış kayıt birikmeden tahmin vermez.
EN_AZ_OGRENME_SANIYE = 3 * 3600
# Model en fazla bu kadar geriye bakarak öğrenir (piyasa değişir; eski kayıt eskir).
OGRENME_PENCERESI_SANIYE = 48 * 3600
# Ardışık saniyeler birbirine çok benzer; öğrenmede her 5 saniyeden biri alınır.
ORNEK_ADIMI_SANIYE = 5
# Modelin aşırı uç tahmin vermemesi için sınır (yüzde).
EN_FAZLA_TAHMIN_YUZDE = 1.0

OZELLIKLER = [
    "dengesizlik_5",      # en iyi 5 kademedeki (alış - satış) / toplam miktar
    "dengesizlik_20",
    "dengesizlik_tum",    # defterin tamamında (100 kademe)
    "mikro_bps",          # mikro fiyatın orta fiyattan farkı (on binde)
    "makas_bps",          # en iyi alış ile satış arası (on binde)
    "duvar_alis_bps",     # en büyük alış emrinin orta fiyattan uzaklığı (on binde)
    "duvar_satis_bps",    # en büyük satış emrinin uzaklığı
    "getiri_60s",         # son 1 / 5 / 15 dakikanın fiyat değişimi (yüzde)
    "getiri_300s",
    "getiri_900s",
    "oynaklik_300s",      # son 5 dakikada saniyelik değişimlerin yayılımı (on binde)
    "rsi_1dk",            # 14 mumluk RSI, 1 dakikalık, (RSI - 50) / 50
    "hacim_orani",        # son 5 dakikanın hacmi / son 60 dakikanın ortalaması (log)
    "destek_uzaklik",     # son 60 dakikanın dibine uzaklık (yüzde)
    "direnc_uzaklik",     # son 60 dakikanın tepesine uzaklık (yüzde)
]


# --------------------------------------------------------------------------
# Emir defteri ve mumlar
# --------------------------------------------------------------------------


def _dengesizlik(alis: float, satis: float) -> float:
    toplam = alis + satis
    return 0.0 if toplam <= 0 else (alis - satis) / toplam


def defter_ozeti(alislar: list, satislar: list) -> dict:
    """Emir defterinden özet. alislar / satislar: [(fiyat, miktar), ...], en iyiden başlayarak."""
    alislar = [(float(f), float(m)) for f, m in alislar]
    satislar = [(float(f), float(m)) for f, m in satislar]
    if not alislar or not satislar:
        raise ValueError("Emir defteri boş.")
    en_iyi_alis, alis_miktar = alislar[0]
    en_iyi_satis, satis_miktar = satislar[0]
    if en_iyi_alis >= en_iyi_satis:
        raise ValueError(f"Defter ters: alış {en_iyi_alis} >= satış {en_iyi_satis}")
    orta = (en_iyi_alis + en_iyi_satis) / 2.0
    mikro = (en_iyi_satis * alis_miktar + en_iyi_alis * satis_miktar) / (alis_miktar + satis_miktar)

    def toplam(kademeler, n=None):
        return sum(m for _f, m in (kademeler if n is None else kademeler[:n]))

    duvar_alis = max(alislar, key=lambda k: k[1])[0]
    duvar_satis = max(satislar, key=lambda k: k[1])[0]
    return {
        "alis": en_iyi_alis,
        "satis": en_iyi_satis,
        "orta": orta,
        "dengesizlik_5": _dengesizlik(toplam(alislar, 5), toplam(satislar, 5)),
        "dengesizlik_20": _dengesizlik(toplam(alislar, 20), toplam(satislar, 20)),
        "dengesizlik_tum": _dengesizlik(toplam(alislar), toplam(satislar)),
        "mikro_bps": (mikro - orta) / orta * 1e4,
        "makas_bps": (en_iyi_satis - en_iyi_alis) / orta * 1e4,
        "duvar_alis_bps": (orta - duvar_alis) / orta * 1e4,
        "duvar_satis_bps": (duvar_satis - orta) / orta * 1e4,
    }


def rsi(kapanislar: list, periyot: int = 14) -> float | None:
    """Wilder RSI'ın son değeri; yeterli veri yoksa None."""
    if len(kapanislar) < periyot + 1:
        return None
    farklar = [b - a for a, b in zip(kapanislar[:-1], kapanislar[1:])]
    artis = sum(max(f, 0.0) for f in farklar[:periyot]) / periyot
    dusus = sum(max(-f, 0.0) for f in farklar[:periyot]) / periyot
    for f in farklar[periyot:]:
        artis = (artis * (periyot - 1) + max(f, 0.0)) / periyot
        dusus = (dusus * (periyot - 1) + max(-f, 0.0)) / periyot
    if dusus == 0:
        return 100.0 if artis > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + artis / dusus)


def kapanmis_mumlar(mumlar: list, simdi: float) -> list:
    """Yalnız 'simdi' anında kapanmış mumlar (kapanis_zamani <= simdi). Açık mum geleceği taşır."""
    return [m for m in mumlar if m["kapanis_zamani"] <= simdi]


class FiyatGecmisi:
    """Saniyelik orta fiyatlar: {saniye: fiyat}. Eskiler atılır."""

    def __init__(self, saklama_saniye: int = 1200):
        self.saklama = saklama_saniye
        self.fiyatlar: dict[int, float] = {}

    def ekle(self, zaman: int, fiyat: float) -> None:
        self.fiyatlar[zaman] = fiyat
        if len(self.fiyatlar) > self.saklama + 120:
            sinir = zaman - self.saklama
            for z in [z for z in self.fiyatlar if z < sinir]:
                del self.fiyatlar[z]

    def bul(self, zaman: int, tolerans: int = 3) -> float | None:
        """O saniyenin fiyatı; o saniye eksikse en yakın (en fazla 'tolerans' saniye) değer."""
        for fark in range(tolerans + 1):
            for z in (zaman - fark, zaman + fark):
                if z in self.fiyatlar:
                    return self.fiyatlar[z]
        return None


def ozellik_vektoru(ozet: dict, gecmis: FiyatGecmisi, zaman: int, mumlar: list) -> list[float]:
    """OZELLIKLER sırasıyla sayı listesi. Yalnız 'zaman' anına kadar bilinenleri kullanır."""
    orta = ozet["orta"]

    def getiri(saniye):
        once = gecmis.bul(zaman - saniye)
        return 0.0 if not once else (orta / once - 1.0) * 100.0

    degisimler = []
    onceki = None
    for z in range(zaman - 300, zaman + 1):
        f = gecmis.fiyatlar.get(z)
        if f is not None and onceki is not None:
            degisimler.append(math.log(f / onceki) * 1e4)
        if f is not None:
            onceki = f
    oynaklik = float(np.std(degisimler)) if len(degisimler) >= 30 else 0.0

    kapali = kapanmis_mumlar(mumlar, zaman)
    kapanislar = [m["kapanis"] for m in kapali]
    r = rsi(kapanislar[-120:])
    son60 = kapali[-60:]
    if len(son60) >= 10:
        hacimler = [m["hacim"] for m in son60]
        ort = sum(hacimler) / len(hacimler)
        son5 = sum(hacimler[-5:]) / len(hacimler[-5:])
        hacim_orani = math.log((son5 + 1e-9) / (ort + 1e-9))
        dip = min(m["dusuk"] for m in son60)
        tepe = max(m["yuksek"] for m in son60)
        destek = (orta - dip) / orta * 100.0
        direnc = (tepe - orta) / orta * 100.0
    else:
        hacim_orani = destek = direnc = 0.0

    degerler = {
        **{k: ozet[k] for k in ("dengesizlik_5", "dengesizlik_20", "dengesizlik_tum", "mikro_bps",
                                "makas_bps", "duvar_alis_bps", "duvar_satis_bps")},
        "getiri_60s": getiri(60),
        "getiri_300s": getiri(300),
        "getiri_900s": getiri(900),
        "oynaklik_300s": oynaklik,
        "rsi_1dk": 0.0 if r is None else (r - 50.0) / 50.0,
        "hacim_orani": hacim_orani,
        "destek_uzaklik": destek,
        "direnc_uzaklik": direnc,
    }
    return [float(degerler[k]) for k in OZELLIKLER]


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


def egitim_verisi(kayitlar: list, ufuk_saniye: int, simdi: int,
                  pencere: int = OGRENME_PENCERESI_SANIYE,
                  adim: int = ORNEK_ADIMI_SANIYE) -> tuple[np.ndarray, np.ndarray]:
    """Öğrenme örnekleri: (zaman, özellikler, gerçekleşen değişim yüzdesi) kayıtlarından.

    Yalnız sonucu 'simdi' anında belli olanlar alınır (zaman + ufuk <= simdi);
    geleceği bilen bir örnek modele hiç girmez.
    """
    X, y = [], []
    for zaman, ozellik, gercek in kayitlar:
        if gercek is None or zaman + ufuk_saniye > simdi or zaman < simdi - pencere:
            continue
        if zaman % adim:
            continue
        X.append(ozellik)
        y.append(gercek)
    return np.asarray(X, dtype=float).reshape(-1, len(OZELLIKLER)), np.asarray(y, dtype=float)


class Model:
    """Sırt regresyonu (ridge): özelliklerin ağırlıklı toplamı, aşırı uyuma karşı küçültülmüş.

    Basit ve açıklanabilir olsun diye seçildi. Ağırlıklar her yeniden eğitimde
    son kayıtlardan hesaplanır. Sabit bir eğilim terimi yoktur: son saatlerde
    fiyat ortalama olarak yükseldiyse bu, "yükselmeye devam eder" diye geleceğe
    taşınmaz; tahmin yalnız o anki özelliklerden gelir.
    """

    def __init__(self, ceza: float = 50.0):
        self.ceza = ceza
        self.agirlik = None
        self.ort = self.sapma = None
        self.ornek_sayisi = 0

    @property
    def hazir(self) -> bool:
        return self.agirlik is not None

    def egit(self, X: np.ndarray, y: np.ndarray) -> None:
        if len(y) < 10:
            return
        self.ort = X.mean(axis=0)
        self.sapma = X.std(axis=0)
        self.sapma[self.sapma == 0] = 1.0
        Z = (X - self.ort) / self.sapma
        A = Z.T @ Z + self.ceza * np.eye(Z.shape[1])
        self.agirlik = np.linalg.solve(A, Z.T @ y)
        self.ornek_sayisi = len(y)

    def tahmin(self, ozellik: list[float]) -> float | None:
        if not self.hazir:
            return None
        z = (np.asarray(ozellik, dtype=float) - self.ort) / self.sapma
        deger = float(z @ self.agirlik)
        return max(-EN_FAZLA_TAHMIN_YUZDE, min(EN_FAZLA_TAHMIN_YUZDE, deger))


# --------------------------------------------------------------------------
# Sanal pozisyon
# --------------------------------------------------------------------------


def tasfiye_fiyati(yon: str, giris: float, kaldirac: float = KALDIRAC) -> float:
    """Yalıtılmış teminatta yaklaşık tasfiye (likidasyon) fiyatı.

    1 kat kaldıraçta alımda fiyatın neredeyse sıfıra, açığa satışta iki katına
    çıkması gerekir; 5-15 dakikada pratikte olmaz. Yine de her işlemde denetlenir.
    """
    if yon == "alim":
        return giris * (1.0 - 1.0 / kaldirac + BAKIM_TEMINATI)
    return giris * (1.0 + 1.0 / kaldirac - BAKIM_TEMINATI)


def islem_ac(ufuk: str, tahmin_yuzde: float | None, alis: float, satis: float, zaman: int,
             en_az: float = EN_AZ_TAHMIN_YUZDE) -> dict | None:
    """Tahmin komisyonu karşılayacak kadar büyükse sanal pozisyon açar, değilse None.

    Giriş piyasa emriyle: alımda en iyi satış, açığa satışta en iyi alış fiyatından.
    Hedef: tahmin edilen hareket kadar lehe. Stop: aynı mesafe kadar aleyhe (1'e 1).
    Süre: tahmin ufku (5 ya da 15 dakika); dolunca o anki fiyattan kapanır.
    """
    if tahmin_yuzde is None or abs(tahmin_yuzde) < en_az:
        return None
    yon = "alim" if tahmin_yuzde > 0 else "satis"
    giris = satis if yon == "alim" else alis
    mesafe = abs(tahmin_yuzde) / 100.0
    isaret = 1.0 if yon == "alim" else -1.0
    return {
        "ufuk": ufuk,
        "yon": yon,
        "giris_zamani": zaman,
        "bitis_zamani": zaman + UFUKLAR[ufuk],
        "giris": giris,
        "tahmin_yuzde": tahmin_yuzde,
        "hedef": giris * (1.0 + isaret * mesafe),
        "stop": giris * (1.0 - isaret * mesafe),
        "tasfiye": tasfiye_fiyati(yon, giris),
        "en_kotu_yuzde": 0.0,
        "en_iyi_yuzde": 0.0,
    }


def islem_denetle(islem: dict, alis: float, satis: float, zaman: int) -> dict | None:
    """Açık işlemi o anki fiyatla denetler. Kapanırsa sonuç sözlüğünü döndürür, değilse None.

    Çıkış piyasa emriyle: alımı kapatırken en iyi alış, açığa satışı kapatırken en
    iyi satış fiyatı. 'islem' içindeki en kötü / en iyi an bilgisi yerinde güncellenir.
    """
    alim = islem["yon"] == "alim"
    fiyat = alis if alim else satis
    isaret = 1.0 if alim else -1.0
    anlik = (fiyat / islem["giris"] - 1.0) * 100.0 * isaret
    islem["en_kotu_yuzde"] = min(islem["en_kotu_yuzde"], anlik)
    islem["en_iyi_yuzde"] = max(islem["en_iyi_yuzde"], anlik)

    neden = cikis = None
    if (alim and fiyat <= islem["tasfiye"]) or (not alim and fiyat >= islem["tasfiye"]):
        neden, cikis = "tasfiye", fiyat
    elif (alim and fiyat <= islem["stop"]) or (not alim and fiyat >= islem["stop"]):
        neden, cikis = "stop", fiyat
    elif (alim and fiyat >= islem["hedef"]) or (not alim and fiyat <= islem["hedef"]):
        neden, cikis = "hedef", islem["hedef"]
    elif zaman >= islem["bitis_zamani"]:
        neden, cikis = "sure", fiyat
    if neden is None:
        return None
    brut = (cikis / islem["giris"] - 1.0) * 100.0 * isaret
    net = -100.0 if neden == "tasfiye" else brut - GIDIS_DONUS_YUZDE
    return {
        **islem,
        "cikis_zamani": zaman,
        "cikis": cikis,
        "neden": neden,
        "brut_yuzde": brut,
        "net_yuzde": net,
        "net_usdt": net / 100.0 * ISLEM_TUTARI_USDT,
        "basarili": net > 0,
    }


# --------------------------------------------------------------------------
# Giriş anında defter onayı (SMD / SMDK botları)
# --------------------------------------------------------------------------


def defter_onayi(yon: str, alislar: list, satislar: list, en_az_dengesizlik: float = 0.1) -> tuple[bool, str]:
    """Sinyal gelen anda emir defteri işlemin yönünü destekliyor mu?

    Alımda: en iyi 20 kademede alış tarafı en az 'en_az_dengesizlik' kadar ağır
    (örnek 0,1: alışlar satışlardan ~%22 fazla), defterin tamamında da alış tarafı
    satıştan hafif değil ve mikro fiyat orta fiyatın üstünde (yakın alıcılar daha
    kalabalık). Yani fiyatı yukarı itmek aşağı itmekten kolay görünüyor. Açığa satış tersi.
    Dönen ikili: (onay, kayda yazılacak kısa açıklama).
    """
    o = defter_ozeti(alislar, satislar)
    if yon == "alim":
        onay = o["dengesizlik_20"] >= en_az_dengesizlik and o["dengesizlik_tum"] >= 0 and o["mikro_bps"] >= 0
    else:
        onay = o["dengesizlik_20"] <= -en_az_dengesizlik and o["dengesizlik_tum"] <= 0 and o["mikro_bps"] <= 0
    aciklama = (f"defter {'onayladı' if onay else 'onaylamadı'}: dengesizlik ilk 20 kademe "
                f"{o['dengesizlik_20']:+.2f}, tümü {o['dengesizlik_tum']:+.2f}, mikro fiyat {o['mikro_bps']:+.2f} bps")
    return onay, aciklama
