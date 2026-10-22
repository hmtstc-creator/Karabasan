"""Basit mum bazlı işlem benzetimi.

Hazır motorun yerine geçmez. İki işi vardır: stratejilerin mantığını
sunucu olmadan sınamak ve hazır motorun sonuçlarını bağımsız bir
hesapla karşılaştırmak.

Varsayımlar bilerek kötümserdir:
- Sinyal bir mumun kapanışında oluşur, işlem BİR SONRAKİ mumun açılışında açılır.
- Aynı mumda hem stop hem hedef görülürse stop önce gerçekleşmiş sayılır.
- Stop ve süre aşımı çıkışlarına kayma uygulanır; hedef limit emirdir, kaymaz.
- Hedef ya da stopla kapanan mumun sinyali, bir sonraki mumda yeni işlem açabilir.
- Kuralın çıkış sinyali varsa (cikis > sinyal), sinyal mumunun ardından gelen mumun
  açılışında kapanır; o mumun kendi giriş sinyali bir sonraki mumda yeni işlem açabilir.
- Zararda ekleme (zararda_ekleme): fiyat ekleme seviyesine değdiği mumda, seviyeden (mum
  ötesinde açıldıysa açılıştan, kaymalı) bir kez eklenir; aynı mumda stopa da değdiyse
  önce ekleme, sonra stop sayılır (kötümser). Stop fiyatı ilk girişe göre kalır.

Sonuç yüzdeleri ilk girişin teminatı (kaldıraçsız botta işlem tutarı) üzerindendir:
kaldıraç ve ek giriş sonucu o oranda büyütür, komisyon da toplam büyüklük üzerinden alınır.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import gostergeler as g
from .kural import ekleme_fiyati, kaldirac, limit_fiyati, sinyal_uret


class _Yurutucu:
    """Bir sinyal mumundan başlayan tek bir işlemi yürütür (benzet ve aday_islemler ortak kullanır)."""

    def __init__(self, tablo: pd.DataFrame, kural: dict, komisyon_yuzde: float,
                 kayma_yuzde: float, kayma_dizi=None):
        self.kural = kural
        self.alim = kural["yon"] == "alim"
        cikis = kural["cikis"]
        self.komisyon = komisyon_yuzde
        self.hedef = float(cikis["kar_hedefi_yuzde"]) / 100.0 if cikis.get("kar_hedefi_yuzde") is not None else None
        self.stop = float(cikis["zarar_durdur_yuzde"]) / 100.0
        # Hedef stopun katı olarak (kar_hedefi_r): her işlemin hedefi kendi stopundan.
        self.hedef_r = float(cikis["kar_hedefi_r"]) if cikis.get("kar_hedefi_r") is not None else None
        # ATR'ye bağlı stop: işlem başına stop, sinyal mumunda hesaplanmış 'stop_yuzde' sütunundan.
        self.stop_dizi = (tablo["stop_yuzde"].to_numpy(dtype=float) / 100.0
                          if cikis.get("stop_atr") and "stop_yuzde" in tablo else None)
        self.sure = (pd.Timedelta(minutes=int(cikis["sure_asimi_dakika"]))
                     if cikis.get("sure_asimi_dakika") is not None else None)
        iz = cikis.get("iz_suren_stop")
        self.iz = iz
        # İz süren stop: kâr (komisyon düşülmüş) tetiğe ulaşınca, en iyi fiyatın mesafe kadar gerisi.
        self.iz_tetik = float(iz["tetik_yuzde"]) if iz else None
        self.iz_mesafe = float(iz["mesafe_yuzde"]) / 100.0 if iz else None
        self.mum = pd.Timedelta(minutes=g.dilim_dakika(kural["zaman_dilimi"]))
        # Kayma: sabit (kayma_yuzde) ya da mum başına (kayma_dizi, yüzde; panel sınaması).
        n = len(tablo)
        self.kayma = (np.asarray(kayma_dizi, dtype=float) / 100.0 if kayma_dizi is not None
                      else np.full(n, kayma_yuzde / 100.0))
        self.tarih = list(pd.to_datetime(tablo["date"], utc=True))
        self.acilis = tablo["open"].to_numpy(dtype=float)
        self.yuksek = tablo["high"].to_numpy(dtype=float)
        self.dusuk = tablo["low"].to_numpy(dtype=float)
        self.kapanis = tablo["close"].to_numpy(dtype=float)
        self.sinyal = tablo["sinyal"].to_numpy(dtype=bool)
        self.cikis_sinyal = tablo["cikis_sinyal"].to_numpy(dtype=bool)
        self.limit_uzaklik = tablo["giris_limit_yuzde"].to_numpy(dtype=float)
        self.limit = kural.get("giris_limiti")
        # Limit emir kaç mum bekler: konduğu mum dahil, süre dolana kadar.
        self.limit_mum = (int(self.limit["sure_dakika"]) // g.dilim_dakika(kural["zaman_dilimi"])
                          if self.limit else 0)
        self.n = n
        self.kaldirac = kaldirac(kural)
        ekleme = kural.get("zararda_ekleme")
        self.ekleme_kat = float(ekleme["kat"]) if ekleme else None

    def _etkin_stop(self, stop_fiyat: float, en_iyi: float, giris: float) -> tuple[float, bool]:
        """Etkin stop: sabit stop ya da (devredeyse) iz süren stop, hangisi daha yakınsa."""
        if not self.iz:
            return stop_fiyat, False
        alim = self.alim
        kar = ((en_iyi / giris - 1.0) if alim else (1.0 - en_iyi / giris)) * 100.0 - 2.0 * self.komisyon
        if kar >= self.iz_tetik:
            seviye = en_iyi * (1 - self.iz_mesafe) if alim else en_iyi * (1 + self.iz_mesafe)
            if (seviye > stop_fiyat) if alim else (seviye < stop_fiyat):
                return seviye, True
        return stop_fiyat, False

    def _kaymali(self, fiyat: float, k: int, giris: bool) -> float:
        """Piyasa emrinin aleyhe kaymış fiyatı (alımda girişte yukarı, çıkışta aşağı)."""
        kayma = self.kayma[k]
        yukari = self.alim == giris
        return fiyat * (1 + kayma if yukari else 1 - kayma)

    def yurut(self, i: int):
        """i. mumun sinyaliyle açılan işlemi sonuna kadar yürütür.

        Dönen: işlem sözlüğü ('_j' çıkış mumu, '_sonraki_i' bir sonraki sinyalin bakılacağı mum);
        limit emir dolmadıysa {"dolmadi": son mum}; veri işlem kapanmadan bittiyse None.
        """
        alim, n = self.alim, self.n
        acilis, yuksek, dusuk, kapanis, tarih = self.acilis, self.yuksek, self.dusuk, self.kapanis, self.tarih
        if self.limit:
            # Sinyal mumunun ardından gelen mumun açılışında, fiyatın biraz altına (açığa
            # satışta üstüne) limit emir konur; fiyat oraya inerse o fiyattan dolar (kayma
            # yok). Süresinde dolmazsa iptal edilir; son beklenen mumun sinyali yeni emir açabilir.
            giris = limit_fiyati(acilis[i + 1], self.limit_uzaklik[i], alim)
            son = min(i + self.limit_mum, n - 1)
            giris_i = next((k for k in range(i + 1, son + 1)
                            if (dusuk[k] <= giris if alim else yuksek[k] >= giris)), None)
            if giris_i is None:
                return {"dolmadi": son}
        else:
            giris_i = i + 1
            # Girişteki kayma sinyal mumunun hareketinden ölçülür (emir o mumun kapanışında verilir).
            giris = self._kaymali(acilis[giris_i], i, giris=True)
        # İşlemin açılış anı emrin konduğu andır (hazır motor da böyle kaydeder; 14. uyum
        # denemesinde motor açılışı limit emirde dolduğu mumdan 5-10 dk önce yazdı). Süre
        # aşımı da oradan sayılır; çıkışlara ise emrin dolduğu mumdan itibaren bakılır.
        giris_zamani = tarih[i + 1]
        stop = float(self.stop_dizi[i]) if self.stop_dizi is not None else self.stop
        stop_fiyat = giris * (1 - stop) if alim else giris * (1 + stop)
        hedef = self.hedef if self.hedef_r is None else self.hedef_r * stop
        hedef_fiyat = None
        if hedef is not None:
            hedef_fiyat = giris * (1 + hedef) if alim else giris * (1 - hedef)
        en_iyi = giris          # işlem açıkken görülen en iyi fiyat (alımda en yüksek)
        ilk_giris = giris
        # Girişler: (fiyat, ilk teminata göre büyüklük). Ekleme olursa ikinci giriş eklenir;
        # 'giris' o zaman ortalama giriş fiyatıdır (hedef ve iz süren stop ondan hesaplanır).
        girisler = [(giris, 1.0)]
        # Ekleme seviyesi: ilk girişten (stop - stopa_kala) yüzde aleyhe.
        ekleme_fiyat = ekleme_fiyati(self.kural, giris)
        ekleme_zamani = None

        neden = None
        cikis_fiyat = None
        j = giris_i
        while j < n:
            # Çıkış sinyali önceki mumun kapanışında oluştuysa işlem bu mumun açılışında kapanır.
            if j > giris_i and self.cikis_sinyal[j - 1]:
                neden = "cikis_sinyali"
                cikis_fiyat = self._kaymali(acilis[j], j - 1, giris=False)
                break
            # Etkin stop: sabit stop ya da (devredeyse) iz süren stop, hangisi daha yakınsa.
            # Önceki mumlardaki en iyi fiyattan hesaplanır; bu mumun tepesi stopu ancak
            # bir sonraki mumdan itibaren taşır (mum içinde sıra bilinmez: kötümser).
            etkin, iz_devrede = self._etkin_stop(stop_fiyat, en_iyi, giris)
            # Zararda ekleme: iz süren stop devredeyse fiyat ekleme seviyesine ondan önce
            # değmez (iz seviyesi kâr tarafındadır); değilse seviyeye değen mumda eklenir.
            if ekleme_fiyat is not None and ekleme_zamani is None and not iz_devrede and (
                    dusuk[j] <= ekleme_fiyat if alim else yuksek[j] >= ekleme_fiyat):
                ek = min(acilis[j], ekleme_fiyat) if alim else max(acilis[j], ekleme_fiyat)
                ek = self._kaymali(ek, j, giris=True)
                girisler.append((ek, self.ekleme_kat))
                toplam = sum(b for _f, b in girisler)
                giris = toplam / sum(b / f for f, b in girisler)     # ortalama giriş
                ekleme_zamani = tarih[j]
                en_iyi = ek
                if hedef is not None:
                    hedef_fiyat = giris * (1 + hedef) if alim else giris * (1 - hedef)
            if alim:
                stop_oldu = dusuk[j] <= etkin
                hedef_oldu = hedef_fiyat is not None and yuksek[j] >= hedef_fiyat
            else:
                stop_oldu = yuksek[j] >= etkin
                hedef_oldu = hedef_fiyat is not None and dusuk[j] <= hedef_fiyat
            if stop_oldu:
                if iz_devrede:
                    # Mum stopun ötesinde açıldıysa açılıştan kapanır.
                    neden = "iz_suren_stop"
                    cikis_fiyat = min(acilis[j], etkin) if alim else max(acilis[j], etkin)
                else:
                    neden = "zarar_durdur"
                    cikis_fiyat = etkin
                cikis_fiyat = self._kaymali(cikis_fiyat, j, giris=False)
                break
            # Limit emrin dolduğu mumda tepe, fiyat limite inmeden önce görülmüş olabilir:
            # kötümser olmak için o mumda hedef sayılmaz, en iyi fiyat da güncellenmez.
            ilk_limit_mumu = bool(self.limit) and j == giris_i
            # Ek girişin yapıldığı mumda da öyle: o mumun lehe ucu ekten önce görülmüş olabilir.
            ekleme_mumu = ekleme_zamani is not None and ekleme_zamani == tarih[j]
            if ilk_limit_mumu or ekleme_mumu:
                hedef_oldu = False
            if hedef_oldu:
                neden = "kar_hedefi"
                cikis_fiyat = hedef_fiyat
                break
            if not (ilk_limit_mumu or ekleme_mumu):
                en_iyi = max(en_iyi, yuksek[j]) if alim else min(en_iyi, dusuk[j])
            if self.sure is not None and tarih[j] + self.mum - giris_zamani >= self.sure:
                neden = "sure_asimi"
                cikis_fiyat = self._kaymali(kapanis[j], j, giris=False)
                break
            j += 1

        if neden is None:
            # Veri bitti, işlem açık kaldı: sonuca katılmaz.
            return None

        # Sonuç ilk teminat üzerinden: her giriş kendi büyüklüğüyle, kaldıraç çarpanıyla.
        buyukluk = sum(b for _f, b in girisler) * self.kaldirac
        if alim:
            brut = sum(b * (cikis_fiyat / f - 1.0) for f, b in girisler) * self.kaldirac * 100.0
        else:
            brut = sum(b * (f - cikis_fiyat) / f for f, b in girisler) * self.kaldirac * 100.0
        cikis_zamani = tarih[j] if neden == "cikis_sinyali" else tarih[j] + self.mum
        return {
            "kod": self.kural["kod"],
            "yon": self.kural["yon"],
            "giris_zamani": giris_zamani,
            "cikis_zamani": cikis_zamani,
            "giris_fiyati": float(giris),
            "cikis_fiyati": float(cikis_fiyat),
            "neden": neden,
            "brut_yuzde": float(brut),
            "net_yuzde": float(brut - 2.0 * self.komisyon * buyukluk),
            "sure_dakika": float((cikis_zamani - giris_zamani) / pd.Timedelta(minutes=1)),
            "stop_yuzde": float(stop * 100.0),
            "ilk_giris_fiyati": float(ilk_giris),
            "ekleme_zamani": ekleme_zamani,
            # İlk teminatın kaç katı büyüklükte pozisyon (kaldıraç x girişler); kaldıraçsız,
            # eklemesiz işlemde 1.
            "buyukluk": float(buyukluk),
            # Aynı paritede aynı anda tek işlem. Hedef ve stop mumun içinde gerçekleşir;
            # o mumun kapanışındaki sinyal bir sonraki mumda yeni işlem açabilir (hazır motor
            # da böyle yapar: önce girişe, sonra çıkışa bakar). Süre aşımı mumun kapanışında
            # olur; motor onu bir sonraki mumun açılışında kapatır, o mumda yeni giriş olmaz.
            # 12 Ekim 2026'ya kadar burada hep j + 1 vardı: art arda sinyal veren S2'de motor
            # benzetimden 26 işlem fazla saydı (uyum denemesi 7, işlem işlem eşleştirme).
            "_j": j,
            "_sonraki_i": j + 1 if neden == "sure_asimi" else j,
        }


def _disari(islem: dict) -> dict:
    return {k: v for k, v in islem.items() if not k.startswith("_")}


def benzet(
    df: pd.DataFrame,
    kural: dict,
    komisyon_yuzde: float = 0.075,
    kayma_yuzde: float = 0.0,
    ek_veri: dict | None = None,
    hazir_tablo: pd.DataFrame | None = None,
) -> list[dict]:
    """Tek bir parite için kuralı geçmiş veride çalıştırır, işlem listesi döndürür.

    komisyon_yuzde: taraf başına komisyon (alışta bir kez, satışta bir kez).
    kayma_yuzde:    piyasa emriyle giriş ve çıkışta fiyatın aleyhe kaydığı pay.
    ek_veri:        kuralın borsadan ayrıca istediği dilimlerin mumları, örnek {"1d": tablo}
                    (bkz. kural.gosterge_ekle).
    hazir_tablo:    sinyal_uret'in bu mumlar için daha önce ürettiği tablo. Aynı girişleri
                    farklı çıkış ayarlarıyla sınarken (varyasyon taraması) yeniden hesaplanmaz.
                    Çıkış sinyali ve limit uzaklığı da o tablodan okunur.

    Çıkışlar: sabit stop; varsa kâr hedefi, iz süren stop, çıkış sinyali ve süre sınırı.
    Kâr hedefi ve süre sınırı isteğe bağlıdır.
    """
    tablo = hazir_tablo if hazir_tablo is not None else sinyal_uret(df, kural, ek_veri)
    y = _Yurutucu(tablo, kural, komisyon_yuzde, kayma_yuzde)
    bekleme = pd.Timedelta(minutes=int(kural.get("bekleme_dakika", 0)))

    islemler: list[dict] = []
    kilit_bitis = None  # stop sonrası bekleme
    i = 0
    while i < y.n - 1:
        if not y.sinyal[i] or (kilit_bitis is not None and y.tarih[i + 1] < kilit_bitis):
            i += 1
            continue
        sonuc = y.yurut(i)
        if sonuc is None:
            break
        if "dolmadi" in sonuc:
            i = max(sonuc["dolmadi"], i + 1)
            continue
        islemler.append(_disari(sonuc))
        if sonuc["neden"] == "zarar_durdur" and bekleme > pd.Timedelta(0):
            kilit_bitis = sonuc["cikis_zamani"] + bekleme
        i = sonuc["_sonraki_i"]
    return islemler


def aday_islemler(tablo: pd.DataFrame, kural: dict, komisyon_yuzde: float, kayma_dizi=None) -> list[dict]:
    """Her giriş sinyali için, öbür işlemlerden bağımsız olarak açılacak işlem (panel sınaması).

    Aynı paritede üst üste binen adaylar da döner; hangisinin gerçekten açılacağına
    portföy geçişi karar verir (karabasan.sinama). Bunun için her aday kendi sinyal
    mumunu ('sinyal_i') ve kapandıktan sonra yeni sinyale bakılabilecek ilk mumu
    ('sonraki_i') taşır: portföy kısıtı hiç devreye girmezse sonuç benzet ile aynıdır.
    Limitli giriş desteklenmez (panel kararı: piyasa emri).
    """
    if kural.get("giris_limiti"):
        raise ValueError("aday_islemler limitli girişi desteklemez.")
    y = _Yurutucu(tablo, kural, komisyon_yuzde, 0.0, kayma_dizi)
    adaylar = []
    for i in np.flatnonzero(y.sinyal[: y.n - 1]):
        sonuc = y.yurut(int(i))
        if sonuc is None:
            continue
        aday = _disari(sonuc)
        aday["sinyal_i"] = int(i)
        aday["sonraki_i"] = int(sonuc["_sonraki_i"])
        adaylar.append(aday)
    return adaylar
