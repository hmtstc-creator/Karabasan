"""Emir defteri denemesinin sürekli çalışan servisi (BTC/USDT vadeli, sanal).

Her saniye:
1. Binance'in herkese açık emir defterini okur (en iyi 100 alış / satış kademesi).
2. Özellikleri hesaplar (karabasan.defter), 5 ve 15 dakika sonrası için tahmin üretir.
3. Hepsini kaydeder; 5 / 15 dakika dolunca gerçekleşen fiyatı aynı satıra yazar.
4. Tahmin komisyonu karşılıyorsa sanal pozisyon açar, açık pozisyonu denetler.

Dakikada bir 1 dakikalık mumları (RSI, hacim, destek / direnç için), beş dakikada
bir modeli yeniden eğitir. Yalnız herkese açık, anahtarsız adresleri okur
(GET /fapi/v1/depth, /fapi/v1/klines); borsaya hiçbir emir göndermez.

    python3 -m karabasan.defter_servisi

Kayıt: user_data/kayit/defter.sqlite (sonuç sayfası /defter ve Telegram /defter okur).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import defter as d

DERINLIK_ADRESI = f"https://fapi.binance.com/fapi/v1/depth?symbol={d.SEMBOL}&limit=100"
MUM_ADRESI = f"https://fapi.binance.com/fapi/v1/klines?symbol={d.SEMBOL}&interval=1m&limit=120"
EGITIM_ARALIGI_SANIYE = 300
# Saniyelik kayıtlar bu kadar gün saklanır (günde ~86 bin satır).
SAKLAMA_GUN = 8

gunluk = logging.getLogger("karabasan.defter")

ORNEK_TABLOSU = "ornek_v1"
ISLEM_TABLOSU = "islem_v1"
DURUM_TABLOSU = "durum_v1"
ISLEM_ALANLARI = ["ufuk", "yon", "giris_zamani", "bitis_zamani", "giris", "tahmin_yuzde", "hedef", "stop",
                  "tasfiye", "en_kotu_yuzde", "en_iyi_yuzde", "cikis_zamani", "cikis", "neden",
                  "brut_yuzde", "net_yuzde", "net_usdt", "basarili"]


def kayit_yolu() -> Path:
    ortam = os.environ.get("KARABASAN_DEFTER")
    if ortam:
        return Path(ortam)
    return Path(__file__).resolve().parent.parent / "user_data" / "kayit" / "defter.sqlite"


def tablolari_kur(vt: sqlite3.Connection) -> None:
    ozellik_sutunlari = ", ".join(f"{k} REAL" for k in d.OZELLIKLER)
    tahmin_sutunlari = ", ".join(f"tahmin_{u} REAL, gercek_{u} REAL" for u in d.UFUKLAR)
    vt.execute(f"CREATE TABLE IF NOT EXISTS {ORNEK_TABLOSU} (zaman INTEGER PRIMARY KEY, orta REAL, "
               f"alis REAL, satis REAL, {ozellik_sutunlari}, {tahmin_sutunlari})")
    vt.execute(f"CREATE TABLE IF NOT EXISTS {ISLEM_TABLOSU} (id INTEGER PRIMARY KEY AUTOINCREMENT, "
               "ufuk TEXT, yon TEXT, giris_zamani INTEGER, bitis_zamani INTEGER, giris REAL, tahmin_yuzde REAL, "
               "hedef REAL, stop REAL, tasfiye REAL, en_kotu_yuzde REAL, en_iyi_yuzde REAL, "
               "cikis_zamani INTEGER, cikis REAL, neden TEXT, brut_yuzde REAL, net_yuzde REAL, "
               "net_usdt REAL, basarili INTEGER)")
    vt.execute(f"CREATE TABLE IF NOT EXISTS {DURUM_TABLOSU} (anahtar TEXT PRIMARY KEY, deger TEXT)")
    vt.commit()


def _getir(adres: str, zaman_asimi: int = 5):
    istek = urllib.request.Request(adres, headers={"User-Agent": "karabasan-bot", "Accept": "application/json"})
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
        return json.loads(yanit.read().decode("utf-8"))


def derinlik_getir() -> tuple[list, list]:
    veri = _getir(DERINLIK_ADRESI)
    return ([(float(f), float(m)) for f, m in veri["bids"]],
            [(float(f), float(m)) for f, m in veri["asks"]])


def mum_getir() -> list[dict]:
    return [
        {"acilis_zamani": int(m[0]) // 1000, "acilis": float(m[1]), "yuksek": float(m[2]),
         "dusuk": float(m[3]), "kapanis": float(m[4]), "hacim": float(m[5]),
         # Binance kapanış zamanını mumun son milisaniyesi olarak verir.
         "kapanis_zamani": (int(m[6]) + 1) // 1000}
        for m in _getir(MUM_ADRESI, zaman_asimi=10)
    ]


class Servis:
    """Durumu taşıyan servis. 'adim' her saniye bir kez çağrılır; dışarıya bağımlılıkları değiştirilebilir."""

    def __init__(self, yol: Path, getir_defter=derinlik_getir, getir_mumlar=mum_getir,
                 en_az_ogrenme: int = d.EN_AZ_OGRENME_SANIYE, egitim_araligi: int = EGITIM_ARALIGI_SANIYE):
        yol.parent.mkdir(parents=True, exist_ok=True)
        self.vt = sqlite3.connect(str(yol))
        self.vt.execute("PRAGMA journal_mode=WAL")
        tablolari_kur(self.vt)
        self.getir_defter, self.getir_mumlar = getir_defter, getir_mumlar
        self.en_az_ogrenme, self.egitim_araligi = en_az_ogrenme, egitim_araligi
        self.gecmis = d.FiyatGecmisi()
        self.mumlar: list[dict] = []
        self.son_mum = 0
        self.son_egitim = 0
        self.son_budama = 0
        self.adim_sayisi = 0
        # Sonucu henüz belli olmayan anlar: zaman -> {"orta", "x", "olgun": set(ufuk)}
        self.bekleyen: dict[int, dict] = {}
        # Öğrenme kayıtları: ufuk -> [(zaman, özellikler, gerçekleşen değişim %)]
        self.kayitlar: dict[str, list] = {u: [] for u in d.UFUKLAR}
        self.modeller = {u: d.Model() for u in d.UFUKLAR}
        self.acik: dict[str, dict | None] = {u: None for u in d.UFUKLAR}
        self._yukle()

    # ---------------------------------------------------------------- kayıt
    def _yukle(self) -> None:
        """Yeniden başlayınca öğrendiklerini ve açık pozisyonları kayıttan geri alır."""
        simdi = int(time.time())
        sutunlar = ", ".join(d.OZELLIKLER)
        for u in d.UFUKLAR:
            satirlar = self.vt.execute(
                f"SELECT zaman, {sutunlar}, gercek_{u} FROM {ORNEK_TABLOSU} "
                f"WHERE zaman >= ? AND gercek_{u} IS NOT NULL ORDER BY zaman",
                (simdi - d.OGRENME_PENCERESI_SANIYE,)).fetchall()
            self.kayitlar[u] = [(s[0], list(s[1:-1]), s[-1]) for s in satirlar]
        for satir in self.vt.execute(
                f"SELECT id, {', '.join(ISLEM_ALANLARI)} FROM {ISLEM_TABLOSU} WHERE cikis_zamani IS NULL"):
            islem = dict(zip(["id"] + ISLEM_ALANLARI, satir))
            self.acik[islem["ufuk"]] = islem

    def _durum_yaz(self, anahtar: str, deger) -> None:
        self.vt.execute(f"INSERT OR REPLACE INTO {DURUM_TABLOSU} VALUES (?, ?)",
                        (anahtar, json.dumps(deger, ensure_ascii=False)))

    # ---------------------------------------------------------------- iş
    def egit(self, zaman: int) -> None:
        for u, saniye in d.UFUKLAR.items():
            kayit = self.kayitlar[u] = [k for k in self.kayitlar[u]
                                        if k[0] >= zaman - d.OGRENME_PENCERESI_SANIYE]
            if len(kayit) < self.en_az_ogrenme:
                continue
            X, y = d.egitim_verisi(kayit, saniye, zaman)
            self.modeller[u].egit(X, y)
        self._durum_yaz("model", {
            u: {"hazir": m.hazir, "ornek": m.ornek_sayisi, "kayit_saniye": len(self.kayitlar[u]),
                "gereken_saniye": self.en_az_ogrenme} for u, m in self.modeller.items()})
        self._durum_yaz("son_egitim", zaman)
        self.son_egitim = zaman

    def _olgunlastir(self, zaman: int) -> None:
        for t0 in sorted(self.bekleyen):
            kayit = self.bekleyen[t0]
            for u, saniye in d.UFUKLAR.items():
                if u in kayit["olgun"] or t0 + saniye > zaman:
                    continue
                kayit["olgun"].add(u)
                sonra = self.gecmis.bul(t0 + saniye)
                if sonra is None:
                    continue  # o an kayıt yok (bağlantı koptu): bu örnek kullanılmaz
                gercek = (sonra / kayit["orta"] - 1.0) * 100.0
                self.vt.execute(f"UPDATE {ORNEK_TABLOSU} SET gercek_{u} = ? WHERE zaman = ?", (gercek, t0))
                self.kayitlar[u].append((t0, kayit["x"], gercek))
            if len(kayit["olgun"]) == len(d.UFUKLAR):
                del self.bekleyen[t0]

    def _islem_yaz(self, islem: dict) -> None:
        degerler = [islem.get(k) for k in ISLEM_ALANLARI]
        if islem.get("id") is None:
            imlec = self.vt.execute(
                f"INSERT INTO {ISLEM_TABLOSU} ({', '.join(ISLEM_ALANLARI)}) "
                f"VALUES ({', '.join('?' for _ in ISLEM_ALANLARI)})", degerler)
            islem["id"] = imlec.lastrowid
        else:
            self.vt.execute(
                f"UPDATE {ISLEM_TABLOSU} SET {', '.join(f'{k} = ?' for k in ISLEM_ALANLARI)} WHERE id = ?",
                degerler + [islem["id"]])

    def adim(self, zaman: int) -> dict:
        alislar, satislar = self.getir_defter()
        ozet = d.defter_ozeti(alislar, satislar)
        if not self.mumlar or zaman - self.son_mum >= 60:
            try:
                self.mumlar = self.getir_mumlar()
                self.son_mum = zaman
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError) as hata:
                gunluk.warning("Mumlar alınamadı: %s", hata)
        self.gecmis.ekle(zaman, ozet["orta"])
        x = d.ozellik_vektoru(ozet, self.gecmis, zaman, self.mumlar)

        self._olgunlastir(zaman)
        if zaman - self.son_egitim >= self.egitim_araligi:
            self.egit(zaman)
        tahminler = {u: self.modeller[u].tahmin(x) for u in d.UFUKLAR}

        sutunlar = ["zaman", "orta", "alis", "satis", *d.OZELLIKLER, *(f"tahmin_{u}" for u in d.UFUKLAR)]
        self.vt.execute(
            f"INSERT OR REPLACE INTO {ORNEK_TABLOSU} ({', '.join(sutunlar)}) "
            f"VALUES ({', '.join('?' for _ in sutunlar)})",
            [zaman, ozet["orta"], ozet["alis"], ozet["satis"], *x, *tahminler.values()])
        self.bekleyen[zaman] = {"orta": ozet["orta"], "x": x, "olgun": set()}

        for u in d.UFUKLAR:
            islem = self.acik[u]
            if islem is not None:
                sonuc = d.islem_denetle(islem, ozet["alis"], ozet["satis"], zaman)
                if sonuc is not None:
                    self._islem_yaz(sonuc)
                    self.acik[u] = None
                    gunluk.info("İşlem kapandı (%s %s): %s, net %%%.3f", u, sonuc["yon"], sonuc["neden"],
                                sonuc["net_yuzde"])
            if self.acik[u] is None:
                yeni = d.islem_ac(u, tahminler[u], ozet["alis"], ozet["satis"], zaman)
                if yeni is not None:
                    self._islem_yaz(yeni)
                    self.acik[u] = yeni
                    gunluk.info("İşlem açıldı (%s %s) %.1f, tahmin %%%.3f", u, yeni["yon"], yeni["giris"],
                                yeni["tahmin_yuzde"])

        self.adim_sayisi += 1
        if self.adim_sayisi % 10 == 0:
            # Açık işlemlerin "en kötü / en iyi an" bilgisi sayfada güncel görünsün.
            for islem in self.acik.values():
                if islem is not None:
                    self._islem_yaz(islem)
        if zaman - self.son_budama >= 3600:
            self.vt.execute(f"DELETE FROM {ORNEK_TABLOSU} WHERE zaman < ?", (zaman - SAKLAMA_GUN * 86400,))
            self.son_budama = zaman
        self._durum_yaz("son_adim", zaman)
        if self.adim_sayisi % 5 == 0:
            self.vt.commit()
        return {"ozet": ozet, "tahminler": tahminler}

    def kapat(self) -> None:
        self.vt.commit()
        self.vt.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    yol = kayit_yolu()
    servis = Servis(yol)
    gunluk.info("Emir defteri denemesi başladı (%s, sanal). Kayıt: %s", d.SEMBOL, yol)
    ard_arda_hata = 0
    while True:
        zaman = int(time.time())
        try:
            servis.adim(zaman)
            ard_arda_hata = 0
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as hata:
            ard_arda_hata += 1
            if ard_arda_hata in (1, 10) or ard_arda_hata % 300 == 0:
                gunluk.warning("Emir defteri okunamadı (%s. kez): %s", ard_arda_hata, hata)
            # Borsa "çok sık" derse (429 / 418) bir dakika bekle.
            if isinstance(hata, urllib.error.HTTPError) and hata.code in (418, 429):
                time.sleep(60)
        except sqlite3.Error:
            gunluk.exception("Kayıt yazılamadı")
            time.sleep(5)
        # Bir sonraki tam saniyeye kadar bekle.
        time.sleep(max(0.05, 1.0 - (time.time() % 1.0)))


if __name__ == "__main__":
    main()
