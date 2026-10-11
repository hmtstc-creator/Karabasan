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
"""

from __future__ import annotations

import pandas as pd

from . import gostergeler as g
from .kural import limit_fiyati, sinyal_uret


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
    alim = kural["yon"] == "alim"
    cikis = kural["cikis"]
    hedef = float(cikis["kar_hedefi_yuzde"]) / 100.0 if cikis.get("kar_hedefi_yuzde") is not None else None
    stop = float(cikis["zarar_durdur_yuzde"]) / 100.0
    sure = (pd.Timedelta(minutes=int(cikis["sure_asimi_dakika"]))
            if cikis.get("sure_asimi_dakika") is not None else None)
    iz = cikis.get("iz_suren_stop")
    # İz süren stop: kâr (komisyon düşülmüş) tetiğe ulaşınca, en iyi fiyatın mesafe kadar gerisi.
    iz_tetik = float(iz["tetik_yuzde"]) if iz else None
    iz_mesafe = float(iz["mesafe_yuzde"]) / 100.0 if iz else None
    bekleme = pd.Timedelta(minutes=int(kural.get("bekleme_dakika", 0)))
    mum = pd.Timedelta(minutes=g.dilim_dakika(kural["zaman_dilimi"]))
    kayma = kayma_yuzde / 100.0

    tarih = list(pd.to_datetime(tablo["date"], utc=True))
    acilis = tablo["open"].to_numpy(dtype=float)
    yuksek = tablo["high"].to_numpy(dtype=float)
    dusuk = tablo["low"].to_numpy(dtype=float)
    kapanis = tablo["close"].to_numpy(dtype=float)
    sinyal = tablo["sinyal"].to_numpy(dtype=bool)
    cikis_sinyal = tablo["cikis_sinyal"].to_numpy(dtype=bool)
    limit_uzaklik = tablo["giris_limit_yuzde"].to_numpy(dtype=float)
    limit = kural.get("giris_limiti")
    # Limit emir kaç mum bekler: konduğu mum dahil, süre dolana kadar.
    limit_mum = int(limit["sure_dakika"]) // g.dilim_dakika(kural["zaman_dilimi"]) if limit else 0

    islemler: list[dict] = []
    kilit_bitis = None  # stop sonrası bekleme
    i = 0
    n = len(tablo)
    while i < n - 1:
        if not sinyal[i] or (kilit_bitis is not None and tarih[i + 1] < kilit_bitis):
            i += 1
            continue

        if limit:
            # Sinyal mumunun ardından gelen mumun açılışında, fiyatın biraz altına (açığa
            # satışta üstüne) limit emir konur; fiyat oraya inerse o fiyattan dolar (kayma
            # yok). Süresinde dolmazsa iptal edilir; son beklenen mumun sinyali yeni emir açabilir.
            giris = limit_fiyati(acilis[i + 1], limit_uzaklik[i], alim)
            son = min(i + limit_mum, n - 1)
            giris_i = next((k for k in range(i + 1, son + 1)
                            if (dusuk[k] <= giris if alim else yuksek[k] >= giris)), None)
            if giris_i is None:
                i = max(son, i + 1)
                continue
        else:
            giris_i = i + 1
            giris = acilis[giris_i] * (1 + kayma if alim else 1 - kayma)
        # İşlemin açılış anı emrin konduğu andır (hazır motor da böyle kaydeder; 14. uyum
        # denemesinde motor açılışı limit emirde dolduğu mumdan 5-10 dk önce yazdı). Süre
        # aşımı da oradan sayılır; çıkışlara ise emrin dolduğu mumdan itibaren bakılır.
        giris_zamani = tarih[i + 1]
        stop_fiyat = giris * (1 - stop) if alim else giris * (1 + stop)
        hedef_fiyat = None
        if hedef is not None:
            hedef_fiyat = giris * (1 + hedef) if alim else giris * (1 - hedef)
        en_iyi = giris          # işlem açıkken görülen en iyi fiyat (alımda en yüksek)

        neden = None
        cikis_fiyat = None
        j = giris_i
        while j < n:
            # Çıkış sinyali önceki mumun kapanışında oluştuysa işlem bu mumun açılışında kapanır.
            if j > giris_i and cikis_sinyal[j - 1]:
                neden = "cikis_sinyali"
                cikis_fiyat = acilis[j] * (1 - kayma if alim else 1 + kayma)
                break
            # Etkin stop: sabit stop ya da (devredeyse) iz süren stop, hangisi daha yakınsa.
            # Önceki mumlardaki en iyi fiyattan hesaplanır; bu mumun tepesi stopu ancak
            # bir sonraki mumdan itibaren taşır (mum içinde sıra bilinmez: kötümser).
            etkin, iz_devrede = stop_fiyat, False
            if iz:
                kar = ((en_iyi / giris - 1.0) if alim else (1.0 - en_iyi / giris)) * 100.0 - 2.0 * komisyon_yuzde
                if kar >= iz_tetik:
                    seviye = en_iyi * (1 - iz_mesafe) if alim else en_iyi * (1 + iz_mesafe)
                    if (seviye > etkin) if alim else (seviye < etkin):
                        etkin, iz_devrede = seviye, True
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
                cikis_fiyat *= (1 - kayma if alim else 1 + kayma)
                break
            # Limit emrin dolduğu mumda tepe, fiyat limite inmeden önce görülmüş olabilir:
            # kötümser olmak için o mumda hedef sayılmaz, en iyi fiyat da güncellenmez.
            ilk_limit_mumu = bool(limit) and j == giris_i
            if ilk_limit_mumu:
                hedef_oldu = False
            if hedef_oldu:
                neden = "kar_hedefi"
                cikis_fiyat = hedef_fiyat
                break
            if not ilk_limit_mumu:
                en_iyi = max(en_iyi, yuksek[j]) if alim else min(en_iyi, dusuk[j])
            if sure is not None and tarih[j] + mum - giris_zamani >= sure:
                neden = "sure_asimi"
                cikis_fiyat = kapanis[j] * (1 - kayma if alim else 1 + kayma)
                break
            j += 1

        if neden is None:
            # Veri bitti, işlem açık kaldı: sonuca katılmaz.
            break

        if alim:
            brut = (cikis_fiyat / giris - 1.0) * 100.0
        else:
            brut = (giris - cikis_fiyat) / giris * 100.0
        cikis_zamani = tarih[j] if neden == "cikis_sinyali" else tarih[j] + mum
        islemler.append(
            {
                "kod": kural["kod"],
                "yon": kural["yon"],
                "giris_zamani": giris_zamani,
                "cikis_zamani": cikis_zamani,
                "giris_fiyati": float(giris),
                "cikis_fiyati": float(cikis_fiyat),
                "neden": neden,
                "brut_yuzde": float(brut),
                "net_yuzde": float(brut - 2.0 * komisyon_yuzde),
                "sure_dakika": float((cikis_zamani - giris_zamani) / pd.Timedelta(minutes=1)),
            }
        )
        if neden == "zarar_durdur" and bekleme > pd.Timedelta(0):
            kilit_bitis = cikis_zamani + bekleme
        # Aynı paritede aynı anda tek işlem. Hedef ve stop mumun içinde gerçekleşir;
        # o mumun kapanışındaki sinyal bir sonraki mumda yeni işlem açabilir (hazır motor
        # da böyle yapar: önce girişe, sonra çıkışa bakar). Süre aşımı mumun kapanışında
        # olur; motor onu bir sonraki mumun açılışında kapatır, o mumda yeni giriş olmaz.
        # 12 Ekim 2026'ya kadar burada hep j + 1 vardı: art arda sinyal veren S2'de motor
        # benzetimden 26 işlem fazla saydı (uyum denemesi 7, işlem işlem eşleştirme).
        i = j + 1 if neden == "sure_asimi" else j
    return islemler
