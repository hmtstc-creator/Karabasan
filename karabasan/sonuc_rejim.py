"""Rejim ekranının verisi: Karabasan puanı, durumlar ve vetolar için ELDE NE VARSA o.

Dürüst başlangıç noktası (10 Kasım 2026 kod incelemesi): Karabasan puanı canlıda hiçbir yerde
hesaplanıp kaydedilmiyor. `karabasan/puan.py` yalnız tek seferlik geçmiş ölçümünde
(`gecmis_olcum.py`, çıktısı `user_data/logs/karabasan_gecmis.txt`) kullanılır; kural dosyalarındaki
`izinli_durumlar` alanı yalnız doğrulanır, canlı botlar ona bakmaz. Bu yüzden bu modül puan
HESAPLAMAZ, durum UYDURMAZ. Gösterdikleri:

  a) Kuralların kendisi: ağırlıklar, durum eşikleri, veto eşikleri. `puan.py` pandas istediği için
     içe aktarılmaz; dosya metin olarak ayrıştırılır (ast), böylece sayfa ile kod aynı şeyi söyler.
  b) `user_data/kayit/kuresel.csv` (kayitci.py, 10 dakikada bir): BTC dominansı ve TOTAL2'nin
     son 30 günü, son değer, 24 saat / 7 gün değişim, kayıt boşlukları.
  c) Son geçmiş ölçüm raporu var mı, ne zaman yazıldı (içeriği ayrıştırılmaz).
  d) İşlem kayıtlarından YENİDEN KURULAN "art arda stop" pencereleri. Bu, canlı motorun kaydı
     değildir; eşikler puan.py'den okunur, "art arda"nın nasıl sayıldığı aşağıda yazılıdır.

Yalnız okur; yalnız standart kütüphane.
"""

from __future__ import annotations

import ast
import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path



def zaman_coz(metin) -> datetime | None:
    """kuresel.csv zamanı ('2026-10-10T12:00:00Z') -> UTC. sonuc.zaman_coz ile aynı davranış; sonuc.py
    karne.py üzerinden pandas'ı içe aktardığı için buradan çağrılamaz (sunucunun Python'unda pandas yok)."""
    if metin is None:
        return None
    metin = str(metin).strip()
    if metin.endswith("Z"):
        metin = metin[:-1] + "+00:00"
    try:
        zaman = datetime.fromisoformat(metin)
    except ValueError:
        return None
    if zaman.tzinfo is None:
        zaman = zaman.replace(tzinfo=timezone.utc)
    return zaman.astimezone(timezone.utc)

PUAN_DOSYASI = Path(__file__).resolve().parent / "puan.py"
PUAN_SABITLERI = ("AGIRLIKLAR", "BILESEN_ADLARI", "ESIK_YESIL", "ESIK_SARI", "YUKSELIS_ICIN_OLCUM",
                  "DURUM_ADI", "VETO_ESIKLERI")

PENCERE_GUN = 30
ARALIK_DAKIKA = 10            # kayitci.ARALIK_SANIYE ile aynı (test bunu denetler)
BOSLUK_DAKIKA = 30            # üç ölçüm üst üste kaçtıysa "boşluk"
BAYAT_DAKIKA = 30             # son satır bundan eskiyse kaydedici durmuş sayılır
KOVA_SAAT = 6                 # grafik için seyrek örnekleme: her 6 saatin son ölçümü
REFERANS_TOLERANS_DAKIKA = 60  # "24 saat önce" için en fazla bu kadar eski satır kabul edilir
ILK_OKUMA_BAYT = 600_000      # 30 gün x 144 satır x ~90 bayt ~ 400 KB
PENCERE_LISTESI = 12
BOSLUK_LISTESI = 5

# Bileşenlerin canlı verisi sayfanın okuyabildiği bir kayıtta var mı? (10 Kasım 2026 kod incelemesi)
# "kismen": ham girdinin bir bölümü kaydediliyor, bileşenin kendisi hesaplanmıyor.
BILESEN_KAYDI = {
    "T": ("yok", "BTC mumlarından hesaplanır; canlı hesap ve kayıt yok."),
    "S": ("yok", "BTC'nin saatlik oynaklığından hesaplanır; canlı hesap ve kayıt yok."),
    "A": ("kismen", "Dominans ve TOTAL2 10 dakikada bir kaydediliyor; BTC'nin 24 saatlik değişimi kayıtta yok, "
                    "puan hesaplanmıyor."),
    "G": ("yok", "İzlenen coinlerin ortalamalarına göre yeri gerekir; canlı hesap ve kayıt yok."),
    "M": ("yok", "NASDAQ ve altın verisi hiç toplanmıyor."),
}


# --------------------------------------------------------------------------
# a) Kurallar: puan.py'yi içe aktarmadan oku
# --------------------------------------------------------------------------


def kurallari_oku(yol: Path = PUAN_DOSYASI) -> dict | None:
    """puan.py'nin en üst düzey sabitlerini metinden okur. Okunamazsa None ("veri yok")."""
    try:
        agac = ast.parse(Path(yol).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None
    bulunan = {}
    for dugum in agac.body:
        if isinstance(dugum, ast.Assign) and len(dugum.targets) == 1 and isinstance(dugum.targets[0], ast.Name):
            ad, deger = dugum.targets[0].id, dugum.value
        elif isinstance(dugum, ast.AnnAssign) and isinstance(dugum.target, ast.Name) and dugum.value is not None:
            ad, deger = dugum.target.id, dugum.value
        else:
            continue
        if ad in PUAN_SABITLERI:
            try:
                bulunan[ad] = ast.literal_eval(deger)
            except (ValueError, SyntaxError):
                return None
    if any(ad not in bulunan for ad in PUAN_SABITLERI):
        return None
    try:
        agirlik = {str(k): float(v) for k, v in bulunan["AGIRLIKLAR"].items()}
        adlar = {str(k): str(v) for k, v in bulunan["BILESEN_ADLARI"].items()}
        veto = {str(k): float(v) for k, v in bulunan["VETO_ESIKLERI"].items()}
        durum_adi = {str(k): str(v) for k, v in bulunan["DURUM_ADI"].items()}
        yesil, sari = float(bulunan["ESIK_YESIL"]), float(bulunan["ESIK_SARI"])
        olcum = int(bulunan["YUKSELIS_ICIN_OLCUM"])
    except (TypeError, ValueError, AttributeError):
        return None
    if not agirlik or sum(agirlik.values()) <= 0 or not 0 < sari < yesil < 100:
        return None
    bilesenler = []
    for kod, a in agirlik.items():
        kayit, aciklama = BILESEN_KAYDI.get(kod, ("yok", "Canlı hesap ve kayıt yok."))
        bilesenler.append({"kod": kod, "ad": adlar.get(kod, kod), "agirlik_yuzde": a * 100.0,
                           "kayit": kayit, "aciklama": aciklama})
    return {
        "bilesenler": bilesenler,
        "esik_yesil": yesil,
        "esik_sari": sari,
        "yukselis_icin_olcum": olcum,
        "durum_adi": durum_adi,
        "veto_esikleri": veto,
    }


# --------------------------------------------------------------------------
# b) Küresel kayıt
# --------------------------------------------------------------------------

_onbellek: dict = {}  # yol -> (mtime_ns, boyut, kapsanan en eski an ya da None (dosyanın tamamı), satırlar)


def _satirlari_coz(metin: str, baslik: list[str] | None) -> list[tuple]:
    satirlar = []
    okuyucu = csv.reader(io.StringIO(metin))
    for parca in okuyucu:
        if not parca or parca[0] == "zaman":
            continue
        try:
            sozluk = dict(zip(baslik, parca)) if baslik else {}
            zaman = zaman_coz(parca[0])
            dominans = float(sozluk.get("btc_dominans_yuzde", parca[2]))
            total2 = float(sozluk.get("total2_usd", parca[3]))
        except (ValueError, IndexError, TypeError):
            continue  # yarım ya da bozuk satır
        if zaman is None or not 0 < dominans < 100 or total2 <= 0:
            continue
        satirlar.append((zaman, dominans, total2))
    satirlar.sort(key=lambda s: s[0])
    return satirlar


def kuresel_oku(yol: Path, en_eski: datetime) -> list[tuple] | None:
    """kuresel.csv'nin `en_eski` anından sonraki satırları: [(zaman, dominans %, TOTAL2 USD)].

    Dosya aylarca büyür; bu yüzden sondan okunur ve değişmediği sürece önbellekten verilir.
    Dosya yoksa None.
    """
    yol = Path(yol)
    try:
        durum = yol.stat()
    except OSError:
        return None
    kayitli = _onbellek.get(str(yol))
    if kayitli and kayitli[0] == durum.st_mtime_ns and kayitli[1] == durum.st_size \
            and (kayitli[2] is None or kayitli[2] <= en_eski):
        return [s for s in kayitli[3] if s[0] >= en_eski]
    try:
        with yol.open("rb") as dosya:
            baslik = dosya.readline().decode("utf-8", "replace").strip().split(",")
            if not baslik or baslik[0] != "zaman":
                baslik = None
            okunacak = ILK_OKUMA_BAYT
            while True:
                bas = max(0, durum.st_size - okunacak)
                dosya.seek(bas)
                ham = dosya.read()
                if bas > 0:
                    ham = ham.split(b"\n", 1)[1] if b"\n" in ham else b""  # yarım ilk satırı at
                satirlar = _satirlari_coz(ham.decode("utf-8", "replace"), baslik)
                if bas == 0 or (satirlar and satirlar[0][0] <= en_eski):
                    break
                okunacak *= 2
    except OSError:
        return None
    _onbellek[str(yol)] = (durum.st_mtime_ns, durum.st_size, None if bas == 0 else en_eski, satirlar)
    return [s for s in satirlar if s[0] >= en_eski]


def _onceki_deger(satirlar: list[tuple], an: datetime, sutun: int):
    """`an` anındaki ya da ondan hemen önceki ölçüm; en fazla REFERANS_TOLERANS_DAKIKA eski olabilir."""
    aday = None
    for s in satirlar:
        if s[0] > an:
            break
        aday = s
    if aday is None or (an - aday[0]) > timedelta(minutes=REFERANS_TOLERANS_DAKIKA):
        return None
    return aday[sutun]


def bosluklar(satirlar: list[tuple], esik_dakika: int = BOSLUK_DAKIKA) -> list[dict]:
    """Art arda iki ölçüm arasında eşikten uzun kalan aralar."""
    cikti = []
    for once, sonra in zip(satirlar, satirlar[1:]):
        dakika = (sonra[0] - once[0]).total_seconds() / 60.0
        if dakika > esik_dakika:
            cikti.append({"baslangic": once[0], "bitis": sonra[0], "dakika": dakika})
    return cikti


def seyrek_seri(satirlar: list[tuple], sutun: int, kova_saat: int = KOVA_SAAT) -> list[list]:
    """Grafik için: her `kova_saat` saatlik dilimin son ölçümü, [saniye, değer].

    Dilimler takvime sabitlenir (çağdan itibaren); bu yüzden sonradan gelen veri, bitmiş bir
    dilimin noktasını değiştirmez.
    """
    kova_sn = kova_saat * 3600
    son: dict[int, tuple] = {}
    for s in satirlar:
        son[int(s[0].timestamp()) // kova_sn] = s
    return [[son[k][0].timestamp(), son[k][sutun]] for k in sorted(son)]


def kuresel_ozet(satirlar: list[tuple] | None, simdi: datetime) -> dict:
    """Son 30 günün özeti. `satirlar` None ise dosya yok; boşsa pencerede ölçüm yok."""
    if satirlar is None:
        return {"var": False, "olcum": 0}
    bas = simdi - timedelta(days=PENCERE_GUN)
    satirlar = [s for s in satirlar if bas <= s[0] <= simdi]
    if not satirlar:
        return {"var": True, "olcum": 0}
    son = satirlar[-1]
    yas = (simdi - son[0]).total_seconds() / 60.0

    def degisim(sutun: int, saat: int, oran: bool):
        once = _onceki_deger(satirlar, son[0] - timedelta(hours=saat), sutun)
        if once is None:
            return None
        return (son[sutun] / once - 1.0) * 100.0 if oran else son[sutun] - once

    araliklar = bosluklar(satirlar)
    kapsanan_dakika = (son[0] - satirlar[0][0]).total_seconds() / 60.0
    beklenen = int(kapsanan_dakika // ARALIK_DAKIKA) + 1
    return {
        "var": True,
        "olcum": len(satirlar),
        "ilk_zaman": satirlar[0][0],
        "son_zaman": son[0],
        "yas_dakika": yas,
        "bayat": yas > BAYAT_DAKIKA,
        "dominans": son[1],
        "total2": son[2],
        # Dominans yüzde puanı olarak (puan.py'deki "dominans_degisim_24s_puan" ile aynı birim), TOTAL2 yüzde olarak.
        "dominans_24s": degisim(1, 24, False),
        "dominans_7g": degisim(1, 24 * 7, False),
        "total2_24s": degisim(2, 24, True),
        "total2_7g": degisim(2, 24 * 7, True),
        "dominans_seri": seyrek_seri(satirlar, 1),
        "total2_seri": seyrek_seri(satirlar, 2),
        "kova_saat": KOVA_SAAT,
        "bosluk_sayisi": len(araliklar),
        "bosluk_toplam_dakika": sum(a["dakika"] for a in araliklar),
        "en_uzun_bosluk_dakika": max((a["dakika"] for a in araliklar), default=0.0),
        "son_bosluklar": araliklar[-BOSLUK_LISTESI:][::-1],
        "kapsama_yuzde": min(100.0, len(satirlar) / beklenen * 100.0) if beklenen > 0 else None,
        "kapsanan_gun": kapsanan_dakika / 1440.0,
    }


# --------------------------------------------------------------------------
# d) Art arda stop: kayıttan yeniden kurulur (canlı motor kaydı DEĞİLDİR)
# --------------------------------------------------------------------------


def art_arda_stop(islemler: list, acik: list, esik: int, sure_dakika: float,
                  simdi: datetime, pencere_gun: int = PENCERE_GUN) -> dict:
    """Bütün botların kapanan işlemleri kapanış sırasıyla dizilir; araya stop olmayan bir kapanış
    girmeden üst üste gelen stoplar sayılır. Sayı `esik`e vardığında (ve sonraki her stopta)
    puan.py'deki veto tetiklenmiş olurdu ve `sure_dakika` sürerdi. Üst üste binen süreler tek
    pencere sayılır.

    "Art arda"nın bu tanımı puan.py'de yazılı değildir (orada yalnız sayı ve süre vardır); en yalın
    okuma olarak seçildi ve sayfada açıkça söylenir. Her tetik yalnız kendinden önceki kapanışlara
    bakar: sonradan gelen işlem geçmiş bir tetiği değiştirmez.
    """
    sirali = sorted((i for i in islemler if i.get("cikis_zamani") is not None and i["cikis_zamani"] <= simdi),
                    key=lambda i: i["cikis_zamani"])
    sure = timedelta(minutes=sure_dakika)
    tetikler, sayac, en_uzun = [], 0, 0
    for i in sirali:
        if i.get("neden") == "stop":
            sayac += 1
            en_uzun = max(en_uzun, sayac)
            if sayac >= esik:
                tetikler.append({"zaman": i["cikis_zamani"], "art_arda": sayac})
        else:
            sayac = 0
    pencereler: list[dict] = []
    for t in tetikler:
        if pencereler and t["zaman"] <= pencereler[-1]["bitis"]:
            pencereler[-1]["bitis"] = t["zaman"] + sure
            pencereler[-1]["art_arda"] = max(pencereler[-1]["art_arda"], t["art_arda"])
        else:
            pencereler.append({"baslangic": t["zaman"], "bitis": t["zaman"] + sure, "art_arda": t["art_arda"]})
    bas = simdi - timedelta(days=pencere_gun)
    pencereler = [p for p in pencereler if p["bitis"] >= bas]
    girisler = [(i["giris_zamani"], i.get("kod") or i.get("bot") or "?", i.get("net_tutar"))
                for i in list(islemler) + list(acik) if i.get("giris_zamani") is not None]
    for p in pencereler:
        icinde = [g for g in girisler if p["baslangic"] < g[0] <= p["bitis"]]
        kapanan = [g for g in icinde if g[2] is not None]
        p["dakika"] = (min(p["bitis"], simdi) - p["baslangic"]).total_seconds() / 60.0
        p["suruyor"] = p["bitis"] > simdi
        p["acilan_islem"] = len(icinde)
        p["acan_botlar"] = sorted({g[1] for g in icinde})
        p["acilan_kapanan"] = len(kapanan)
        p["acilan_net"] = sum(g[2] for g in kapanan)
    return {
        "esik": esik,
        "sure_dakika": sure_dakika,
        "kapanan_islem": len(sirali),
        "stop_sayisi": sum(1 for i in sirali if i.get("neden") == "stop"),
        "en_uzun_seri": en_uzun,
        "simdiki_seri": sayac,
        "pencere_sayisi": len(pencereler),
        "toplam_dakika": sum(p["dakika"] for p in pencereler),
        "acilan_islem": sum(p["acilan_islem"] for p in pencereler),
        "acilan_kapanan": sum(p["acilan_kapanan"] for p in pencereler),
        "acilan_net": sum(p["acilan_net"] for p in pencereler),
        "suruyor": any(p["suruyor"] for p in pencereler),
        "pencereler": pencereler[-PENCERE_LISTESI:][::-1],
    }


# --------------------------------------------------------------------------
# c) Geçmiş ölçüm raporu ve toplama
# --------------------------------------------------------------------------


def gecmis_raporu(veri_klasoru: Path, simdi: datetime) -> dict:
    yol = Path(veri_klasoru) / "logs" / "karabasan_gecmis.txt"
    try:
        durum = yol.stat()
    except OSError:
        return {"var": False}
    yazildi = datetime.fromtimestamp(durum.st_mtime, tz=timezone.utc)
    return {"var": True, "yazildi": yazildi, "boyut": durum.st_size,
            "yas_gun": max(0.0, (simdi - yazildi).total_seconds() / 86400.0)}


def hesapla(baglam: dict) -> dict:
    simdi = baglam["simdi"]
    veri_klasoru = Path(baglam["veri_klasoru"])
    kurallar = kurallari_oku()
    satirlar = kuresel_oku(veri_klasoru / "kayit" / "kuresel.csv",
                           simdi - timedelta(days=PENCERE_GUN))
    stoplar = None
    if kurallar is not None:
        veto = kurallar["veto_esikleri"]
        if veto.get("art_arda_stop", 0) >= 1 and veto.get("art_arda_stop_dakika", 0) > 0:
            stoplar = art_arda_stop(baglam.get("islemler") or [], baglam.get("acik") or [],
                                    int(veto["art_arda_stop"]), veto["art_arda_stop_dakika"], simdi)
    return {
        # Canlı Karabasan puanı / durumu / veto kaydı: yok. Bu alanlar bilerek None; uydurulmaz.
        "canli_kayit": False,
        "puan": None,
        "durum": None,
        "kurallar": kurallar,
        "botlar": [{"kod": b.get("kod"), "ad": b.get("ad"), "izinli_durumlar": list(b.get("izinli_durumlar") or [])}
                   for b in baglam.get("botlar") or []],
        "izinli_uygulaniyor": False,
        "kuresel": kuresel_ozet(satirlar, simdi),
        "art_arda_stop": stoplar,
        "gecmis_raporu": gecmis_raporu(veri_klasoru, simdi),
        "pencere_gun": PENCERE_GUN,
    }
