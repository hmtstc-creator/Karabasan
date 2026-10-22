"""Stop sonrası izleme: stop olan işlemde fiyat sonra ne yaptı, stop dar mıydı?

Bir işlem stop olduğunda soru şudur: stop biraz daha geniş olsaydı bu işlem
kurtulur muydu, yoksa zarar yalnız büyür müydü? Bu modül o soruyu tek tek
işlemler için değil, bir botun bütün stopları için yanıtlar; çünkü geniş stop
bazı işlemleri kurtarırken kurtaramadıklarının zararını büyütür ve önemli
olan toplamdır.

Mantık:

1. Stop olan işlem, kendi süresi dolana kadar (giriş anı + stratejinin en uzun
   süresi) izlenir. Daha uzun izlenmez; işlem zaten o süreden sonra açık
   kalamazdı. Süre sınırı olmayan stratejilerde (iz süren stoplu botlar)
   giriş anından en az IZLEME_SURESIZ kadar, stoptan sonra en az
   IZLEME_STOP_SONRASI kadar izlenir; o anda hâlâ açık olan seçenek son
   fiyattan değerlenir ("açık kalırdı").
2. Aynı işlem, stop 1,5 / 2 / 3 kat geniş olsaydı ne olurdu diye yeniden
   oynatılır: geniş stop da olur muydu, kâr hedefine ulaşır mıydı, yoksa süre
   mi dolardı. Aynı mumda hem geniş stop hem hedef görülürse stop sayılır
   (kötümser). İz süren stoplu stratejide stratejinin kendi kuralı uygulanır
   (benzetimdeki gibi): kâr, komisyon düşülünce tetiğe ulaşınca stop en iyi
   fiyatın mesafe kadar gerisine çekilir; bir mumun tepesi stopu ancak sonraki
   mumdan itibaren taşır. Stop olan işlemde iz süren stop o ana kadar hiç devreye
   girmemiştir (girseydi işlem iz süren stopla kapanırdı), yani stoptan önceki
   en iyi fiyat tetiğin altındadır ve hesabı değiştirmez.
3. Bot başına toplanır: gerçek sonuç ile her seçeneğin farkı, dönemin iki
   yarısında ayrı ayrı.
4. Karar çıkarılır: "veri yetersiz", "stop dar görünüyor", "stop yerinde" ya
   da "kararsız". Karar değişince bir ders olarak kaydedilir. "Stop dar"
   demek için kural bilerek zordur: en az 30 stop, farkın şansla
   açıklanamayacak kadar büyük olması ve dönemin iki yarısına da yayılması
   gerekir. Rastgele veride bile bazı seçenekler iyi görünür; kural onları
   elemek içindir.

Bu bir geriye bakıştır ve sınırları vardır:

- Yalnız stop olan işlemlere bakar. Stop geniş olsaydı işlem daha uzun açık
  kalır, o sırada gelen başka sinyaller atlanırdı; bu hesaba girmez.
- Geçmişe bakıp en iyi stopu seçmek kolaydır, geleceği tutması ayrı konudur.
  Bu yüzden karar hiçbir ayarı değiştirmez. "Stop dar" kararı yalnız bir
  öneridir: geniş stoplu hal ayrı bir sanal botla denenir.

Yalnız Python standart kütüphanesini kullanır. Sunucuda kayitci servisi
`bir_tur` işini 10 dakikada bir çağırır; mumlar Binance'in herkese açık,
anahtarsız fiyat verisinden gelir.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

CARPANLAR = (1.5, 2.0, 3.0)
EN_AZ_STOP = 30             # karar vermek için gereken izlenmiş stop sayısı
EN_AZ_FARK_YUZDE = 0.15     # stop başına ortalama iyileşme (işlem tutarının yüzdesi)
EN_AZ_YARI_PAYI = 0.25      # iyileşmenin en az bu kadarı dönemin her iki yarısından gelmeli
EN_AZ_T = 2.0               # ortalama farkın, kendi standart hatasının en az kaç katı olması gerektiği
DERS_ARASI = timedelta(hours=24)   # aynı bot için iki ders arasındaki en kısa süre
DENEME_SINIRI = 3           # mum alınamayan işlem kaç kez yeniden denenir
TUR_SINIRI = 25             # bir turda en fazla kaç işlem izlenir
BEKLEME = timedelta(minutes=3)     # süre dolduktan sonra son mumun kapanması için pay
IZLEME_SURESIZ = timedelta(hours=72)        # süre sınırı olmayan stratejide girişten itibaren izleme
IZLEME_STOP_SONRASI = timedelta(hours=24)   # ... ve stoptan sonra en az bu kadar

SPOT_ADRESI = "https://api.binance.com/api/v3/klines"
VADELI_ADRESI = "https://fapi.binance.com/fapi/v1/klines"

KARAR_ADI = {
    "yetersiz": "Veri yetersiz",
    "dar": "Stop dar görünüyor",
    "yerinde": "Stop yerinde",
    "kararsiz": "Kararsız",
}

gunluk = logging.getLogger("karabasan.stop_sonrasi")


def carpan_metni(carpan: float) -> str:
    """1.5 -> '1,5', 2.0 -> '2'."""
    return f"{carpan:g}".replace(".", ",")


def _sayi(deger: float, basamak: int = 2) -> str:
    metin = f"{abs(deger):.{basamak}f}".replace(".", ",")
    if abs(deger) < 0.5 * 10 ** (-basamak):
        return metin
    return ("+" if deger > 0 else "−") + metin


# --------------------------------------------------------------------------
# Tek işlem
# --------------------------------------------------------------------------


def izle(
    yon: str,
    giris_fiyati: float,
    giris_zamani: datetime,
    stop_zamani: datetime,
    mumlar: list[tuple],
    hedef_yuzde: float | None,
    stop_yuzde: float,
    sure_dakika: float | None,
    komisyon_yuzde: float,
    mum_dakika: int = 1,
    carpanlar: tuple = CARPANLAR,
    iz: dict | None = None,
    bitis: datetime | None = None,
) -> dict | None:
    """Stop olan bir işlemi süresi dolana kadar izler.

    mumlar: (açılış zamanı, açılış, yüksek, düşük, kapanış) demetleri, eskiden yeniye.
    hedef_yuzde None ise sabit kâr hedefi yoktur. iz: {"tetik_yuzde", "mesafe_yuzde"}
    (iz süren stop). sure_dakika None ise süre sınırı yoktur; izleme 'bitis'te biter.
    Dönen sözlük:
        hedefi_gordu   fiyat, pencere içinde kâr hedefine (hedef yoksa iz süren stopun
                       tetiğine) ulaştı mı
        esik           "hedef" ya da "iz": hedefi_gordu neye bakıyor
        en_kotu_yuzde  stop sonrasında girişe göre en kötü nokta (eksi sayı)
        alternatif     {"1.5": {"sonuc": "hedef"|"iz"|"stop"|"sure"|"acik", "net_yuzde": ...}, ...}
    Pencerede hiç mum yoksa ya da veri pencerenin sonuna yetişmiyorsa None döner.
    """
    if not giris_fiyati or giris_fiyati <= 0:
        return None
    alim = yon != "aciga_satis"
    mum = timedelta(minutes=mum_dakika)
    if sure_dakika is not None:
        bitis = giris_zamani + timedelta(minutes=float(sure_dakika))
    if bitis is None:
        raise ValueError("Süre sınırı yoksa izlemenin bitişi verilmeli.")
    pencere = [m for m in mumlar if m[0] + mum > stop_zamani and m[0] < bitis]
    if not pencere:
        return None
    # Veri pencerenin sonuna yetişmeli; yoksa "süre doldu" sonucu yanlış olur.
    if bitis - (pencere[-1][0] + mum) > 2 * mum:
        return None

    stop = stop_yuzde / 100.0
    maliyet = 2.0 * komisyon_yuzde
    hedef_fiyat = None
    if hedef_yuzde is not None:
        hedef_fiyat = giris_fiyati * (1 + hedef_yuzde / 100.0 if alim else 1 - hedef_yuzde / 100.0)
    tetik = float(iz["tetik_yuzde"]) if iz else None
    mesafe = float(iz["mesafe_yuzde"]) / 100.0 if iz else None

    def lehe(fiyat: float) -> float:
        """Girişe göre yüzde sonuç (artı = kâr), komisyon hariç."""
        oran = fiyat / giris_fiyati - 1.0
        return (oran if alim else -oran) * 100.0

    def hedefe_degdi(m: tuple) -> bool:
        if hedef_fiyat is None:
            return False
        return m[2] >= hedef_fiyat if alim else m[3] <= hedef_fiyat

    def tetige_degdi(m: tuple) -> bool:
        return tetik is not None and lehe(m[2] if alim else m[3]) - maliyet >= tetik

    en_kotu = min(lehe(m[3] if alim else m[2]) for m in pencere)
    son_sonuc = "sure" if sure_dakika is not None else "acik"
    alternatif = {}
    for carpan in carpanlar:
        genis = giris_fiyati * (1 - carpan * stop if alim else 1 + carpan * stop)
        sonuc, net = son_sonuc, lehe(pencere[-1][4]) - maliyet
        en_iyi = giris_fiyati
        for m in pencere:
            # Etkin stop: geniş stop ya da (devredeyse) iz süren stop, hangisi yakınsa.
            etkin, iz_devrede = genis, False
            if tetik is not None and lehe(en_iyi) - maliyet >= tetik:
                seviye = en_iyi * (1 - mesafe) if alim else en_iyi * (1 + mesafe)
                if (seviye > etkin) if alim else (seviye < etkin):
                    etkin, iz_devrede = seviye, True
            if (m[3] <= etkin) if alim else (m[2] >= etkin):
                if iz_devrede:
                    # Mum stopun ötesinde açıldıysa açılıştan kapanır.
                    fiyat = min(m[1], etkin) if alim else max(m[1], etkin)
                    sonuc, net = "iz", lehe(fiyat) - maliyet
                else:
                    sonuc, net = "stop", -carpan * stop_yuzde - maliyet
                break
            if hedefe_degdi(m):
                sonuc, net = "hedef", hedef_yuzde - maliyet
                break
            en_iyi = max(en_iyi, m[2]) if alim else min(en_iyi, m[3])
        alternatif[f"{carpan:g}"] = {"sonuc": sonuc, "net_yuzde": round(net, 4)}
    esik = "hedef" if hedef_fiyat is not None else "iz"
    return {
        "hedefi_gordu": any((hedefe_degdi(m) if esik == "hedef" else tetige_degdi(m)) for m in pencere),
        "esik": esik,
        "en_kotu_yuzde": round(en_kotu, 4),
        "alternatif": alternatif,
    }


def esik_metni(esik: str) -> str:
    """Özetteki 'hedefi gördü' sayısının neyi saydığı, cümle içinde."""
    if esik == "iz":
        return "iz süren stopun devreye girdiği kâra ulaştı"
    return "süre dolmadan kâr hedefini gördü"


def secenek_metni(satir: dict) -> str:
    """Bir seçeneğin sonuç dağılımı: '3 tanesi hedefe ulaşır, 5 tanesi yine stop olur, ...'."""
    parcalar = [
        (satir.get("hedef", 0), "hedefe ulaşır"),
        (satir.get("iz", 0), "iz süren stopla kârla kapanır"),
        (satir.get("stop", 0), "yine stop olur"),
        (satir.get("sure", 0), "süre dolunca kapanır"),
        (satir.get("acik", 0), "izleme bitince hâlâ açık olur"),
    ]
    metin = ", ".join(f"{adet} tanesi {ne}" for adet, ne in parcalar if adet)
    return metin or "sonuç yok"


def islem_cumlesi(kayit: dict) -> str:
    """Tek bir stop için kısa söz: en dar hangi stop kurtarırdı?"""
    for carpan in sorted(kayit["alternatif"], key=float):
        if kayit["alternatif"][carpan]["sonuc"] == "hedef":
            return f"stop {carpan_metni(float(carpan))} kat geniş olsaydı hedefe ulaşırdı"
        if kayit["alternatif"][carpan]["sonuc"] == "iz":
            return f"stop {carpan_metni(float(carpan))} kat geniş olsaydı iz süren stopla kârla kapanırdı"
    en_genis = max(kayit["alternatif"], key=float)
    if kayit["alternatif"][en_genis]["sonuc"] == "stop":
        return f"{carpan_metni(float(en_genis))} kat geniş stop da olurdu"
    if kayit.get("esik") == "iz":
        return "geniş stopla da kârla kapanmazdı"
    return "geniş stopla da hedefe ulaşmazdı"


# --------------------------------------------------------------------------
# Bot başına özet ve karar
# --------------------------------------------------------------------------


def t_degeri(farklar: list[float]) -> float | None:
    """Ortalama farkın standart hatasına oranı: fark şansla açıklanabilir mi?

    2'nin altı "bu kadar fark rastgele de çıkabilirdi" demektir. Bütün farklar
    aynıysa oran sonsuzdur; ±99 ile sınırlanır.
    """
    adet = len(farklar)
    if adet < 2:
        return None
    ort = sum(farklar) / adet
    varyans = sum((f - ort) ** 2 for f in farklar) / (adet - 1)
    if varyans <= 1e-12:
        return 0.0 if abs(ort) < 1e-9 else (99.0 if ort > 0 else -99.0)
    return max(-99.0, min(99.0, ort / (varyans / adet) ** 0.5))


def ozetle(kayitlar: list[dict], stop_yuzde: float | None, islem_tutari: float) -> dict:
    """Bir botun izlenmiş stoplarını toplar ve karar çıkarır.

    Her kayıt: gercek_net_yuzde, alternatif, hedefi_gordu, en_kotu_yuzde, cikis_zamani.
    """
    kayitlar = sorted(kayitlar, key=lambda k: k["cikis_zamani"])
    adet = len(kayitlar)
    yari = adet // 2
    satirlar = []
    carpanlar = sorted({c for k in kayitlar for c in k["alternatif"]}, key=float)
    for carpan in carpanlar:
        sayim = {"hedef": 0, "iz": 0, "stop": 0, "sure": 0, "acik": 0}
        farklar = []
        for k in kayitlar:
            secenek = k["alternatif"].get(carpan)
            if secenek is None:
                farklar.append(0.0)
                continue
            sayim[secenek["sonuc"]] += 1
            farklar.append(secenek["net_yuzde"] - k["gercek_net_yuzde"])
        satirlar.append(
            {
                "carpan": float(carpan),
                "stop_yuzde": None if stop_yuzde is None else round(stop_yuzde * float(carpan), 4),
                "hedef": sayim["hedef"],
                "iz": sayim["iz"],
                "stop": sayim["stop"],
                "sure": sayim["sure"],
                "acik": sayim["acik"],
                "fark_yuzde": round(sum(farklar), 4),
                "fark_tutar": round(sum(farklar) / 100.0 * islem_tutari, 4),
                "fark_tutar_ilk_yari": round(sum(farklar[:yari]) / 100.0 * islem_tutari, 4),
                "fark_tutar_son_yari": round(sum(farklar[yari:]) / 100.0 * islem_tutari, 4),
                "fark_t": None if t_degeri(farklar) is None else round(t_degeri(farklar), 2),
            }
        )
    return {
        "stop_sayisi": adet,
        "hedefi_goren": sum(1 for k in kayitlar if k["hedefi_gordu"]),
        # Eski kayıtlarda alan yok: hepsi sabit hedefliydi.
        "esik": next((k.get("esik", "hedef") for k in reversed(kayitlar)), "hedef"),
        "en_kotu_yuzde": min((k["en_kotu_yuzde"] for k in kayitlar), default=None),
        "carpanlar": satirlar,
        "karar": karar_ver(adet, satirlar),
    }


def karar_ver(adet: int, satirlar: list[dict]) -> dict:
    """Stop dar mı? Kural bilerek tutucudur: az veriyle ya da tutarsız sonuçla 'dar' denmez."""
    if adet < EN_AZ_STOP or not satirlar:
        return {
            "kod": "yetersiz",
            "carpan": None,
            "metin": f"Karar için en az {EN_AZ_STOP} izlenmiş stop gerekiyor; şimdilik {adet} var.",
        }
    saglam = [
        s for s in satirlar
        if s["fark_tutar"] > 0
        and min(s["fark_tutar_ilk_yari"], s["fark_tutar_son_yari"]) >= EN_AZ_YARI_PAYI * s["fark_tutar"]
        and s["fark_yuzde"] / adet >= EN_AZ_FARK_YUZDE
        and (s.get("fark_t") is None or s["fark_t"] >= EN_AZ_T)
    ]
    en_iyi = max(satirlar, key=lambda s: s["fark_tutar"])
    if saglam:
        s = max(saglam, key=lambda s: s["fark_tutar"])
        return {
            "kod": "dar",
            "carpan": s["carpan"],
            "metin": (
                f"Stop dar görünüyor. Stop {carpan_metni(s['carpan'])} kat geniş olsaydı bu {adet} "
                f"stopta sonuç {_sayi(s['fark_tutar'])} USDT daha iyi olurdu; fark şansla açıklanamayacak "
                "kadar büyük ve dönemin iki yarısına da yayılıyor. Öneri: geniş stoplu hali ayrı bir sanal "
                "botla dene; mevcut ayar değişmez."
            ),
        }
    if en_iyi["fark_tutar"] <= 0:
        return {
            "kod": "yerinde",
            "carpan": None,
            "metin": (
                f"Stop yerinde görünüyor. Bu {adet} stopta daha geniş stop sonucu kötüleştirirdi "
                f"(en iyi seçenek {carpan_metni(en_iyi['carpan'])} kat: {_sayi(en_iyi['fark_tutar'])} USDT)."
            ),
        }
    return {
        "kod": "kararsiz",
        "carpan": None,
        "metin": (
            f"Net bir sonuç yok; önceki bir sonuç varsa artık geçerli sayılmaz. {carpan_metni(en_iyi['carpan'])} kat geniş stop bu {adet} stopta "
            f"{_sayi(en_iyi['fark_tutar'])} USDT fark ederdi, ama bu kadar fark şansla da çıkabilir ya da "
            "dönemin yalnız bir yarısından geliyor."
        ),
    }


def ders_gerekli_mi(dersler: list[dict], bot: str, karar: dict, simdi: datetime) -> bool:
    """Bu karar yeni bir ders mi?

    'Veri yetersiz' ders değildir. 'Kararsız' tek başına ders değildir; yalnız daha
    önce yazılmış bir sonucu ('dar' ya da 'yerinde') geri alıyorsa yazılır. Aynı karar
    yinelenmez.
    """
    if karar["kod"] == "yetersiz":
        return False
    oncekiler = [d for d in dersler if d.get("bot") == bot]
    if not oncekiler:
        return karar["kod"] != "kararsiz"
    son = oncekiler[-1]
    if (son.get("karar"), son.get("carpan")) == (karar["kod"], karar["carpan"]):
        return False
    try:
        son_zaman = datetime.strptime(son["zaman"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError):
        return True
    return simdi - son_zaman >= DERS_ARASI


# --------------------------------------------------------------------------
# Kayıt dosyası
# --------------------------------------------------------------------------


def dosya_yolu(veri_klasoru: Path) -> Path:
    return Path(veri_klasoru) / "kayit" / "stop_sonrasi.json"


def dosya_oku(yol: Path) -> dict:
    bos = {"surum": 1, "islemler": {}, "basarisiz": {}, "dersler": [], "son_tur": None}
    try:
        veri = json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return bos
    if not isinstance(veri, dict) or not isinstance(veri.get("islemler"), dict):
        return bos
    return {**bos, **veri}


def dosya_yaz(yol: Path, veri: dict) -> None:
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".json.yeni")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(gecici, yol)


def anahtar(bot: str, kimlik) -> str:
    return f"{bot}#{kimlik}"


def _zaman(metin: str) -> datetime:
    return datetime.strptime(metin, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _zaman_metni(zaman: datetime) -> str:
    return zaman.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Stopu sonradan değişen botların eski stopları. Eski stopla kapanmış işlemler yeni ayarın
# dersine katılmaz ve yeni stopla yeniden oynatılmaz (22 Ekim 2026: SMK / SMDK %3 -> %9, stop
# sonrası dersinin ardından). İşlemin stopu kayıttaki sonucundan okunur: stopla kapanan
# işlemin neti yaklaşık -(stop + komisyon).
ESKI_STOPLAR = {"smk-vadeli": (3.0,), "smdk-vadeli": (3.0,)}
STOP_TOLERANSI = 1.0


def eski_stoplu(bot: str, net_yuzde) -> bool:
    """Stopla kapanmış bu işlem botun eski bir stop ayarıyla mı açılmıştı?"""
    if net_yuzde is None:
        return False
    return any(abs(abs(float(net_yuzde)) - eski) <= STOP_TOLERANSI for eski in ESKI_STOPLAR.get(bot, ()))


def donem_kayitlari(veri: dict, bot: str, baslangic: datetime | None, bitis: datetime | None) -> list[dict]:
    """Bir botun, verilen dönemde açılıp kapanmış izlenmiş stopları (eski stop ayarıyla olanlar hariç)."""
    secilen = []
    for k in veri["islemler"].values():
        if k.get("bot") != bot:
            continue
        if eski_stoplu(bot, k.get("gercek_net_yuzde")):
            continue
        try:
            giris, cikis = _zaman(k["giris_zamani"]), _zaman(k["cikis_zamani"])
        except (KeyError, ValueError):
            continue
        if baslangic is not None and giris < baslangic:
            continue
        if bitis is not None and cikis > bitis:
            continue
        secilen.append(k)
    return secilen


# --------------------------------------------------------------------------
# Mum verisi: Binance'in herkese açık fiyat geçmişi (anahtar gerekmez)
# --------------------------------------------------------------------------


def sembol(parite: str) -> str:
    """'SOL/USDT' ve 'SOL/USDT:USDT' -> 'SOLUSDT'."""
    return str(parite).split(":", 1)[0].replace("/", "").upper()


def mum_getir(parite: str, piyasa: str, baslangic: datetime, bitis: datetime, zaman_asimi: int = 20) -> tuple[list, int]:
    """Verilen aralığın mumlarını indirir. Dönen ikili: (mumlar, mum uzunluğu dakika)."""
    dakika = (bitis - baslangic) / timedelta(minutes=1)
    if dakika <= 990:
        aralik, uzunluk = "1m", 1
    elif dakika <= 4950:
        aralik, uzunluk = "5m", 5
    else:
        aralik, uzunluk = "15m", 15
    if piyasa == "vadeli":
        taban = os.environ.get("KARABASAN_BINANCE_VADELI", VADELI_ADRESI)
    else:
        taban = os.environ.get("KARABASAN_BINANCE_SPOT", SPOT_ADRESI)
    sorgu = urllib.parse.urlencode(
        {
            "symbol": sembol(parite),
            "interval": aralik,
            "startTime": int(baslangic.timestamp() * 1000),
            "endTime": int(bitis.timestamp() * 1000),
            "limit": 1000,
        }
    )
    istek = urllib.request.Request(f"{taban}?{sorgu}", headers={"User-Agent": "karabasan-bot"})
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
        satirlar = json.loads(yanit.read().decode("utf-8"))
    mumlar = [
        (
            datetime.fromtimestamp(int(s[0]) / 1000.0, tz=timezone.utc),
            float(s[1]), float(s[2]), float(s[3]), float(s[4]),
        )
        for s in satirlar
    ]
    return mumlar, uzunluk


# --------------------------------------------------------------------------
# Tur: yeni stopları izle, kararları güncelle
# --------------------------------------------------------------------------


def bir_tur(veri_klasoru: Path, simdi: datetime | None = None, getir=mum_getir, ara: float = 0.3) -> dict:
    """Süresi dolmuş, henüz izlenmemiş stopları izler; karar değiştiyse ders yazar.

    Botların kayıt dosyalarını yalnız okur. Dönen sözlük: {"izlenen", "bekleyen",
    "basarisiz", "yeni_ders"}.
    """
    from . import sonuc  # kayitci hafif kalsın diye burada
    from .botlar import BOTLAR, ayarlari_yukle
    from .kural import kural_yukle

    veri_klasoru = Path(veri_klasoru)
    simdi = simdi or datetime.now(timezone.utc)
    yol = dosya_yolu(veri_klasoru)
    veri = dosya_oku(yol)
    ayar = ayarlari_yukle(veri_klasoru / "ayarlar.json")
    donem = sonuc.donem_bilgisi(
        simdi,
        sonuc.zaman_dosyasi_oku(veri_klasoru / "isinma_baslangici.txt"),
        sonuc.zaman_dosyasi_oku(veri_klasoru / "sinav_baslangici.txt"),
    )
    sayim = {"izlenen": 0, "bekleyen": 0, "basarisiz": 0, "yeni_ders": 0}

    for bot, _sinif, kural_kodu, piyasa in BOTLAR:
        kural = kural_yukle(kural_kodu)
        cikis = kural["cikis"]
        if "sinyal" in cikis or cikis.get("stop_atr") or cikis.get("kar_hedefi_r"):
            # Çıkış sinyali yalnız göstergelerle hesaplanır, işlem başına stop da kayıtta yok;
            # ham mumlardan yeniden oynatılamaz. (Bugünkü canlı botların hiçbiri böyle değil.)
            continue
        if kural.get("zararda_ekleme") or kural.get("kaldirac", 1) != 1:
            # Ek girişli / kaldıraçlı bot (SMK2, SMDK2): stopu geniş halin sonucu tek girişli,
            # kaldıraçsız işleme göre kurulu; bu botların stop dersi ikizlerinden (SMK, SMDK) okunur.
            continue
        hedef = cikis.get("kar_hedefi_yuzde")
        hedef = None if hedef is None else float(hedef)
        stop = float(cikis["zarar_durdur_yuzde"])
        sure = cikis.get("sure_asimi_dakika")
        sure = None if sure is None else float(sure)
        iz = cikis.get("iz_suren_stop")
        komisyon = float(ayar["komisyon_yuzde"][piyasa])
        kayit = sonuc.islemleri_oku(veri_klasoru / "db" / f"{bot}.sqlite")
        for i in kayit["kapali"]:
            if i["neden"] != "stop" or i.get("kimlik") is None:
                continue
            if eski_stoplu(bot, i.get("net_yuzde")):
                continue    # eski stop ayarıyla açılmış işlem; şimdiki stopla yeniden oynatılamaz
            a = anahtar(bot, i["kimlik"])
            if a in veri["islemler"] or veri["basarisiz"].get(a, 0) >= DENEME_SINIRI:
                continue
            if sure is not None:
                pencere_sonu = i["giris_zamani"] + timedelta(minutes=sure)
            else:
                pencere_sonu = max(i["giris_zamani"] + IZLEME_SURESIZ, i["cikis_zamani"] + IZLEME_STOP_SONRASI)
            if simdi < pencere_sonu + BEKLEME or sayim["izlenen"] + sayim["basarisiz"] >= TUR_SINIRI:
                sayim["bekleyen"] += 1
                continue
            sonuc_kaydi = None
            try:
                bas = i["cikis_zamani"].replace(second=0, microsecond=0)
                mumlar, uzunluk = getir(i["parite"], piyasa, bas - timedelta(minutes=5), pencere_sonu)
                sonuc_kaydi = izle(
                    i["yon"], float(i["giris_fiyati"] or 0), i["giris_zamani"], i["cikis_zamani"],
                    mumlar, hedef, stop, sure, komisyon, mum_dakika=uzunluk, iz=iz, bitis=pencere_sonu,
                )
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as hata:
                gunluk.warning("%s için mum alınamadı: %s", a, hata)
            if sonuc_kaydi is None:
                veri["basarisiz"][a] = veri["basarisiz"].get(a, 0) + 1
                sayim["basarisiz"] += 1
            else:
                veri["islemler"][a] = {
                    "bot": bot,
                    "kod": kural_kodu,
                    "parite": i["parite"],
                    "yon": i["yon"],
                    "giris_zamani": _zaman_metni(i["giris_zamani"]),
                    "cikis_zamani": _zaman_metni(i["cikis_zamani"]),
                    "gercek_net_yuzde": round(float(i["net_yuzde"]), 4),
                    **sonuc_kaydi,
                }
                sayim["izlenen"] += 1
            if ara:
                time.sleep(ara)

        # Karar: sayfanın gösterdiği dönemin stoplarıyla.
        ozet = ozetle(
            donem_kayitlari(veri, bot, donem["baslangic"], donem["bitis"]), stop, float(ayar["islem_tutari"])
        )
        if ders_gerekli_mi(veri["dersler"], bot, ozet["karar"], simdi):
            veri["dersler"].append(
                {
                    "zaman": _zaman_metni(simdi),
                    "bot": bot,
                    "kod": kural_kodu,
                    "ad": kural["ad"],
                    "karar": ozet["karar"]["kod"],
                    "carpan": ozet["karar"]["carpan"],
                    "stop_sayisi": ozet["stop_sayisi"],
                    "metin": ozet["karar"]["metin"],
                }
            )
            sayim["yeni_ders"] += 1

    veri["son_tur"] = _zaman_metni(simdi)
    dosya_yaz(yol, veri)
    return sayim
