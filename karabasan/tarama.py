"""Çıkış varyasyonu taraması: aynı girişler, 20 farklı çıkış ayarı, son bir yıl.

Ahmet'in isteği (12 Ekim 2026): "farklı 20 varyasyonla bir senelik testler yapıp en
çok kazançlı olanı bul". Her botun giriş sinyalleri bir kez hesaplanır; yalnız çıkış
(kâr hedefi, iz süren stop, stop, süre sınırı) değişir. Hesap bağımsız benzetimdir
(karabasan.benzetim), 12 aylık testle aynı coinler ve aynı dönem.

Geçmişe ezbere karşı: 20 ayar x 5 bot = 100 deneme. Hiçbirinin gerçek bir üstünlüğü
olmasa bile bir kısmı şans eseri artıda görünür. Bu yüzden yıl ikiye bölünür:
- seçim dönemi: ilk 9 ay. "En iyi" ayar yalnız buna bakılarak seçilir.
- doğrulama dönemi: son 3 ay. Seçilen ayarın orada da artıda kalıp kalmadığına bakılır.
Yıl boyunca en çok kazandıran ayar da yazılır (Ahmet'in sorusu), ama "ezbere açık"
diye işaretlenir. Rapor hiçbir ayarı değiştirmez; seçilen ayar yeni bir sanal botla
ya da Ahmet'in kararıyla denenir (3. kural).
"""

from __future__ import annotations

import copy

import pandas as pd

from . import karne as kr
from .benzetim import benzet
from .botlar import BOTLAR, ayarlari_yukle
from .kural import cikis_metni, ek_veri_topla, kural_yukle, sinyal_uret
from .yillik import GUN, Yukleyici, _sayi, _zaman, coinler, veri_donemi

SECIM_ORANI = 0.75   # yılın ilk %75'i (9 ay) seçim, son %25'i (3 ay) doğrulama


def _iz(tetik, mesafe, stop, sure=None):
    c = {"zarar_durdur_yuzde": stop, "iz_suren_stop": {"tetik_yuzde": tetik, "mesafe_yuzde": mesafe}}
    if sure is not None:
        c["sure_asimi_dakika"] = sure
    return c


def _hedef(hedef, stop, sure=None):
    c = {"kar_hedefi_yuzde": hedef, "zarar_durdur_yuzde": stop}
    if sure is not None:
        c["sure_asimi_dakika"] = sure
    return c


# V01 Ahmet'in seçtiği ve canlı botlarda çalışan ayardır.
VARYASYONLAR: list[tuple[str, dict]] = (
    [("V01", _iz(1.2, 0.3, 3.0))]
    + [(f"V{n:02d}", c) for n, c in enumerate(
        [_iz(t, m, s) for t in (0.8, 1.2, 2.0) for m in (0.3, 0.6) for s in (1.5, 3.0)
         if (t, m, s) != (1.2, 0.3, 3.0)], start=2)]
    + [("V13", _iz(1.2, 0.3, 3.0, 240)),
       ("V14", _iz(1.2, 0.3, 3.0, 1440)),
       ("V15", _hedef(0.8, 3.0, 240)),      # eski Smartmoney ayarı
       ("V16", _hedef(1.2, 1.5, 180)),      # eski Sniper ayarı
       ("V17", _hedef(2.0, 3.0)),           # Ahmet: "kâr hedefini 2 yapsak"
       ("V18", _hedef(2.0, 2.0, 1440)),
       ("V19", _hedef(1.0, 1.0, 240)),
       ("V20", _hedef(3.0, 1.5, 1440))]
)


def _girisler(kural: dict, piyasa: str, yukle: Yukleyici) -> tuple[list, list[str]]:
    """Her coin için (mumlar, sinyal tablosu); sinyaller çıkış ayarından bağımsızdır."""
    hazir, eksikler = [], []
    for coin in coinler(piyasa):
        df = yukle(coin, kural["zaman_dilimi"], piyasa)
        if df is None or df.empty:
            eksikler.append(f"{coin} {kural['zaman_dilimi']}")
            continue
        ek_veri, bulunamayan = ek_veri_topla(kural, lambda dilim, c=coin: yukle(c, dilim, piyasa))
        eksikler += [f"{coin} {d}" for d in bulunamayan]
        hazir.append((df, sinyal_uret(df, kural, ek_veri)))
    return hazir, eksikler


def _sonuc(islemler: list[dict], baslangic, ayrim, bitis, tutar, bakiye) -> dict:
    def net(bas, son):
        return sum(float(i["net_yuzde"]) for i in islemler if bas <= _zaman(i["giris_zamani"]) < son) * tutar / 100.0

    k = kr.karne(islemler, tutar, bakiye)
    return {"islem": k["islem_sayisi"], "kazanma": k["kazanma_orani"], "net": k["net_tutar"],
            "secim": net(baslangic, ayrim), "dogrulama": net(ayrim, bitis),
            "dusus": k["en_buyuk_dusus_yuzde"], "beklenti": k["net_beklenti"]}


def tara(yukle: Yukleyici, gun: int = GUN, ayar: dict | None = None) -> tuple[str, list[dict], int]:
    """Taramayı yapar. Dönen üçlü: (rapor metni, satırlar, eksik veri sayısı)."""
    ayar = ayar or ayarlari_yukle()
    tutar, bakiye = float(ayar["islem_tutari"]), float(ayar["sanal_bakiye"])
    baslangic, bitis, uyarilar = veri_donemi(yukle, gun)
    ayrim = baslangic + (bitis - baslangic) * SECIM_ORANI

    satirlar: list[dict] = []
    eksik = 0
    for bot, _sinif, kod, piyasa in BOTLAR:
        kural = kural_yukle(kod)
        if kural.get("zararda_ekleme") or kural.get("kaldirac", 1) != 1:
            continue   # ek giriş seviyesi stopa bağlı; çıkış varyasyonları ikizinde (SMK, SMDK) sınanır
        komisyon = float(ayar["komisyon_yuzde"][piyasa])
        hazir, eksikler = _girisler(kural, piyasa, yukle)
        eksik += len(eksikler)
        for vad, cikis in VARYASYONLAR:
            deneme = copy.deepcopy(kural)
            deneme["cikis"] = copy.deepcopy(cikis)
            islemler = []
            for df, tablo in hazir:
                islemler += [i for i in benzet(df, deneme, komisyon_yuzde=komisyon, hazir_tablo=tablo)
                             if baslangic <= _zaman(i["giris_zamani"]) < bitis]
            satirlar.append({"bot": bot, "kod": kod, "varyasyon": vad, "cikis": cikis,
                             **_sonuc(islemler, baslangic, ayrim, bitis, tutar, bakiye)})

    return _rapor(satirlar, baslangic, ayrim, bitis, gun, uyarilar, tutar), satirlar, eksik


def _satir(s: dict) -> str:
    return (f"  {s['varyasyon']}  {s['islem']:>5}  %{_sayi(s['kazanma'], 1):>5}  "
            f"{_sayi(s['net'], 2, True):>8}  {_sayi(s['secim'], 2, True):>8}  "
            f"{_sayi(s['dogrulama'], 2, True):>8}  %{_sayi(s['dusus'], 1):>4}")


def _yorum(s: dict) -> str:
    if s["secim"] <= 0:
        return "(en iyisi bile ilk 9 ayda ekside: bu bot için kâr eden çıkış ayarı yok)."
    if s["dogrulama"] > 0:
        return "(doğrulamada da artıda)."
    return "(doğrulamada ekside: büyük olasılıkla ezber)."


def _rapor(satirlar, baslangic, ayrim, bitis, gun, uyarilar, tutar) -> str:
    cizgi = []
    yaz = cizgi.append
    yaz(f"Çıkış varyasyonu taraması: {baslangic:%d.%m.%Y} - {bitis:%d.%m.%Y} ({gun} gün)")
    yaz(f"Hazırlandı: {pd.Timestamp.now(tz='UTC'):%d.%m.%Y %H:%M} UTC.")
    yaz(f"Seçim dönemi: {baslangic:%d.%m.%Y} - {ayrim:%d.%m.%Y} (ilk 9 ay). "
        f"Doğrulama dönemi: {ayrim:%d.%m.%Y} - {bitis:%d.%m.%Y} (son 3 ay).")
    yaz(f"Her bot kendi giriş sinyalleriyle; yalnız çıkış değişir. Coinler ETH, SOL, XRP, DOGE; "
        f"işlem başına {tutar:g} USDT, komisyon dahil, bağımsız benzetim.")
    yaz("Limitli girişler ve emir defteri onayı: limit emir benzetimde var, defter onayı yok.")
    for u in uyarilar:
        yaz(u)
    yaz("")
    yaz("VARYASYONLAR")
    for vad, cikis in VARYASYONLAR:
        yaz(f"  {vad}  {cikis_metni(cikis)}" + ("   <- şimdiki ayar" if vad == "V01" else ""))
    yaz("")
    baslik = "  Var.   İşlem  Kazanma  Yıl USDT  Seçim    Doğrulama  Düşüş"
    botlar = list(dict.fromkeys(s["bot"] for s in satirlar))
    secilenler = []
    for bot in botlar:
        grup = [s for s in satirlar if s["bot"] == bot]
        yaz(f"{bot} ({grup[0]['kod']})")
        yaz(baslik)
        for s in sorted(grup, key=lambda s: s["secim"], reverse=True):
            yaz(_satir(s))
        en_iyi = max(grup, key=lambda s: s["secim"])
        secilenler.append(en_iyi)
        yaz(f"  Seçim dönemine göre en iyisi {en_iyi['varyasyon']}: ilk 9 ayda {_sayi(en_iyi['secim'], 2, True)} USDT, "
            f"son 3 ayda {_sayi(en_iyi['dogrulama'], 2, True)} USDT "
            + _yorum(en_iyi))
        yaz("")

    yaz("ÖZET")
    artida = [s for s in satirlar if s["net"] > 0]
    yaz(f"  {len(satirlar)} denemenin {len(artida)} tanesi yıl sonunda artıda.")
    iki_donem = [s for s in satirlar if s["secim"] > 0 and s["dogrulama"] > 0]
    yaz(f"  Hem ilk 9 ayda hem son 3 ayda artıda olan: {len(iki_donem)}"
        + (" (" + ", ".join(f"{s['kod']} {s['varyasyon']}" for s in
                            sorted(iki_donem, key=lambda s: s["net"], reverse=True)[:8]) + ")" if iki_donem else ""))
    yil_en_iyi = max(satirlar, key=lambda s: s["net"])
    yaz(f"  Yıl boyunca en çok kazandıran (ezbere açık): {yil_en_iyi['kod']} {yil_en_iyi['varyasyon']} "
        f"({cikis_metni(yil_en_iyi['cikis'])}): {_sayi(yil_en_iyi['net'], 2, True)} USDT, "
        f"{yil_en_iyi['islem']} işlem, kazanma %{_sayi(yil_en_iyi['kazanma'], 1)}.")
    secim_en_iyi = max(secilenler, key=lambda s: s["secim"])
    yaz(f"  Dürüst seçim (ilk 9 aya göre seçilip son 3 ayda sınanan): {secim_en_iyi['kod']} "
        f"{secim_en_iyi['varyasyon']}: ilk 9 ay {_sayi(secim_en_iyi['secim'], 2, True)}, "
        f"son 3 ay {_sayi(secim_en_iyi['dogrulama'], 2, True)} USDT {_yorum(secim_en_iyi)}")
    simdiki = [s for s in satirlar if s["varyasyon"] == "V01"]
    yaz("  Şimdiki ayar (V01) yıl sonunda: " + ", ".join(f"{s['kod']} {_sayi(s['net'], 2, True)}" for s in simdiki))
    yaz("")
    yaz("NASIL OKUNMALI")
    yaz("  100 deneme yapıldı. Hiçbir ayarın gerçek üstünlüğü olmasa bile birkaçı şans eseri artıda")
    yaz("  görünür. Güvenilir sayılabilecek olan: ilk 9 ayda seçilip son 3 ayda da artıda kalan ve")
    yaz("  işlem sayısı yüksek olandır. Yalnız yıl toplamına bakıp seçmek geçmişe ezberdir.")
    yaz("  Bu rapor hiçbir ayarı değiştirmez.")
    return "\n".join(cizgi) + "\n"
