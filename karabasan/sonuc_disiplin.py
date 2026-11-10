"""Disiplin ekranının verisi: işlemlerin kalitesi ve kural denetimi (10 Kasım 2026).

Yürütme ve disiplin gözüyle kapanmış sanal işlemlere bakar:

- Stopa giden işlemler hangi saatte (Bükreş saati, 4 saatlik dilimler), hangi gün, hangi coinde,
  hangi botta genel orandan belirgin fazla? Yeterli işlem yoksa "Veri az".
- Komisyon ne kadar yiyor (yaklaşık), sınavın ek kayma payı ne kadar.
- Kazanan / kaybeden işlemlerin süresi; çıkış nedenine göre süre.
- Stop sonrası izleme kararı (Dersler ekranı) bot başına.
- Kural denetimi yalnız kayıttaki veriden: her denetim "temiz", "ihlal" ya da "denetlenemedi" der.
- "Bugün dikkat edilecek 3 şey": yukarıdakilerden kural tabanlı seçim (dikkat_sec, saf işlev).

Yalnız okur; hiçbir ayar, kural ya da bot dosyası yazılmaz. Yalnız standart kütüphane:
karabasan.kural, karabasan.detay ve karabasan.sonuc (karne üzerinden) pandas istediği için içe
aktarılmaz; aynı değerdeki sabitler aşağıdadır ve testle eşitliği denetlenir; kural dosyası
(JSON) doğrudan okunur, günlük bütçe kullanımı burada aynı yöntemle (olay taraması) hesaplanır.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import stop_sonrasi as ss

STRATEJI_KLASORU = Path(__file__).parent / "stratejiler"

STOP_NEDENLERI = ("stop", "tasfiye")     # zararla kesilen çıkışlar (iz süren stop kârla kapanır, sayılmaz)
SAAT_DILIMI_SAAT = 4                     # saatler 4'erli dilimlerde toplanır (00-04, 04-08 ...)
EN_AZ_DILIM_ISLEM = 10                   # bir dilimin yorumlanması için gereken işlem
EN_AZ_STOP_TOPLAM = 10                   # stop dilimlerine bakmak için gereken toplam stop
DILIM_FARK_PUAN = 15.0                   # dilimin stop oranı genelden en az bu kadar puan yüksek ...
DILIM_KAT = 1.5                          # ... ve genel oranın en az bu katı olmalı
EN_AZ_SURE_ISLEM = 5                     # kazanan / kaybeden süre karşılaştırması için her yanda
BEKLEME_TOLERANS_DK = 5                  # motor kilidi mum sınırında biter: bir mum pay
STOP_TASMA_PUAN = 1.5                    # beklenen en büyük stop kaybının üstünde bu kadar puan = taşma
ACIK_RISK_ESIK = 25.0                    # açık pozisyonlar stopta toplam bu kadar USDT'den fazla kaybettirirse
SERI_ESIK = 3                            # şu anki art arda kayıp serisi bu kadar ya da uzunsa
MALIYET_EN_AZ_ISLEM = 20
MALIYET_PAY_ESIK = 50.0                  # komisyon brüt kârın en az bu yüzdesini yiyorsa
DIKKAT_SAYISI = 3

# sonuc.SAAT_DILIMI, sonuc.SESSIZLIK_DAKIKA, karne.SINAV_ESIKLERI["ek_kayma_yuzde"] ile aynı (testli).
SAAT_DILIMI = "Europe/Bucharest"
SESSIZLIK_DAKIKA = 15
EK_KAYMA_YUZDE = 0.05

ONCELIK = {"ihlal": 1, "sessiz": 2, "acik_risk": 3, "seri": 4, "maliyet": 5, "stop_dilimi": 6}


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------


def _kural_oku(kod: str) -> dict | None:
    """Kural dosyasını (JSON) okur; yoksa ya da bozuksa None."""
    for yol in (STRATEJI_KLASORU / f"{kod}.json", STRATEJI_KLASORU / "emekli" / f"{kod}.json"):
        try:
            return json.loads(yol.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def _yerel(zaman: datetime) -> datetime:
    """sonuc._yerel ile aynı: Bükreş saati, saat dilimi verisi yoksa UTC."""
    try:
        from zoneinfo import ZoneInfo

        return zaman.astimezone(ZoneInfo(SAAT_DILIMI))
    except Exception:  # noqa: BLE001
        return zaman.astimezone(timezone.utc)


def _zaman_coz(metin) -> datetime | None:
    if isinstance(metin, datetime):
        return metin if metin.tzinfo else metin.replace(tzinfo=timezone.utc)
    try:
        z = datetime.fromisoformat(str(metin).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return z if z.tzinfo else z.replace(tzinfo=timezone.utc)


def _stop_mu(i: dict) -> bool:
    return str(i.get("neden") or "") in STOP_NEDENLERI


def _bot_bilgisi(botlar: list) -> dict:
    return {b["bot"]: b for b in botlar}


def _ornek(i: dict, ayrinti: str) -> dict:
    return {"bot": i.get("bot"), "kod": i.get("kod"), "kimlik": i.get("kimlik"), "parite": i.get("parite"),
            "zaman": i.get("cikis_zamani") or i.get("giris_zamani"), "ayrinti": ayrinti}


def _denetim(ad: str, aciklama: str, ornekler: list | None = None, neden: str | None = None) -> dict:
    """neden verilirse denetlenemedi; yoksa ornekler boşsa temiz, doluysa ihlal."""
    if neden is not None:
        return {"ad": ad, "aciklama": aciklama, "durum": "denetlenemedi", "adet": 0, "ornekler": [], "neden": neden}
    ornekler = ornekler or []
    return {"ad": ad, "aciklama": aciklama, "durum": "ihlal" if ornekler else "temiz",
            "adet": len(ornekler), "ornekler": ornekler[:5], "neden": None}


# --------------------------------------------------------------------------
# Stop dilimleri
# --------------------------------------------------------------------------


def stop_dilimleri(islemler: list) -> dict:
    """Stop oranı saat dilimine, güne, coine ve bota göre; belirgin yüksek dilimler işaretli."""
    n = len(islemler)
    stop = sum(1 for i in islemler if _stop_mu(i))
    genel = stop / n * 100.0 if n else None
    gruplar: dict[str, dict] = {"saat": {}, "gun": {}, "coin": {}, "bot": {}}
    for i in islemler:
        yerel = _yerel(i["giris_zamani"])
        bas = yerel.hour // SAAT_DILIMI_SAAT * SAAT_DILIMI_SAAT
        anahtarlar = {"saat": bas, "gun": yerel.weekday(),
                      "coin": str(i.get("parite") or "?").split(":", 1)[0], "bot": str(i.get("kod") or i.get("bot"))}
        for tur, a in anahtarlar.items():
            k = gruplar[tur].setdefault(a, {"islem": 0, "stop": 0})
            k["islem"] += 1
            k["stop"] += 1 if _stop_mu(i) else 0
    yeterli = stop >= EN_AZ_STOP_TOPLAM
    cikti = {"islem": n, "stop": stop, "genel_oran": genel, "yeterli": yeterli, "turler": {}, "yuksek": []}
    for tur, d in gruplar.items():
        satirlar = []
        for a, k in sorted(d.items(), key=lambda kv: kv[0]):
            oran = k["stop"] / k["islem"] * 100.0
            yuksek = (yeterli and k["islem"] >= EN_AZ_DILIM_ISLEM and genel is not None
                      and oran - genel >= DILIM_FARK_PUAN and oran >= genel * DILIM_KAT)
            satir = {"tur": tur, "anahtar": a, "islem": k["islem"], "stop": k["stop"], "oran": oran,
                     "az": k["islem"] < EN_AZ_DILIM_ISLEM, "yuksek": yuksek}
            satirlar.append(satir)
            if yuksek:
                cikti["yuksek"].append(satir)
        cikti["turler"][tur] = satirlar
    cikti["yuksek"].sort(key=lambda s: (-(s["oran"] - (genel or 0)), -s["islem"]))
    return cikti


# --------------------------------------------------------------------------
# Maliyet: komisyon ve ek kayma payı
# --------------------------------------------------------------------------


def maliyet(islemler: list, botlar: list, komisyon_yuzde: dict, ek_kayma_yuzde: float) -> dict:
    """Yaklaşık toplam komisyon (USDT), brüt sonuç ve komisyonun brüt kâra oranı.

    Varsayım: komisyon iki taraflıdır (giriş + çıkış), her taraf pozisyon büyüklüğünün (teminat ×
    kaldıraç) 'komisyon_yuzde' kadarı; çıkış fiyatındaki fark yok sayılır. Kayıttaki net_tutar
    komisyon sonrasıdır, brüt = net + komisyon.
    """
    bilgi = _bot_bilgisi(botlar)
    komisyon = net = kayma = 0.0
    bot_satir: dict[str, dict] = {}
    for i in islemler:
        b = bilgi.get(i.get("bot")) or {}
        kat = float(b.get("kaldirac") or 1.0)
        oran = float(komisyon_yuzde.get(b.get("piyasa") or "vadeli", komisyon_yuzde.get("vadeli", 0.0)))
        tutar = float(i.get("tutar") or 0.0)
        k = tutar * kat * oran / 100.0 * 2.0
        komisyon += k
        net += float(i["net_tutar"])
        kayma += tutar * ek_kayma_yuzde / 100.0
        s = bot_satir.setdefault(i.get("bot"), {"bot": i.get("bot"), "kod": i.get("kod"), "islem": 0,
                                                "komisyon": 0.0, "net": 0.0, "gidis_donus_yuzde": 2 * oran * kat})
        s["islem"] += 1
        s["komisyon"] += k
        s["net"] += float(i["net_tutar"])
    brut = net + komisyon
    pay = komisyon / brut * 100.0 if brut > 0 else None
    satirlar = []
    for b in botlar:
        s = bot_satir.get(b["bot"])
        if not s:
            continue
        s["brut"] = s["net"] + s["komisyon"]
        s["ek_kaymali_net"] = b.get("net_tutar_ek_kaymali")
        satirlar.append(s)
    return {"islem": len(islemler), "komisyon": komisyon, "net": net, "brut": brut, "pay_yuzde": pay,
            "ek_kayma_yuzde": ek_kayma_yuzde, "ek_kayma_tutar": kayma, "botlar": satirlar}


# --------------------------------------------------------------------------
# Süreler
# --------------------------------------------------------------------------


def _ort(liste: list) -> float | None:
    return sum(liste) / len(liste) if liste else None


def sureler(islemler: list) -> dict:
    kazanan = [float(i["sure_dakika"]) for i in islemler if i.get("sure_dakika") is not None and float(i["net_tutar"]) > 0]
    kaybeden = [float(i["sure_dakika"]) for i in islemler if i.get("sure_dakika") is not None and float(i["net_tutar"]) <= 0]
    nedenler: dict[str, list] = {}
    for i in islemler:
        if i.get("sure_dakika") is not None:
            nedenler.setdefault(str(i.get("neden") or "bilinmiyor"), []).append(float(i["sure_dakika"]))
    yeterli = len(kazanan) >= EN_AZ_SURE_ISLEM and len(kaybeden) >= EN_AZ_SURE_ISLEM
    ok, oy = _ort(kazanan), _ort(kaybeden)
    return {
        "kazanan_adet": len(kazanan), "kaybeden_adet": len(kaybeden),
        "kazanan_ort": ok, "kaybeden_ort": oy, "yeterli": yeterli,
        "kat": (oy / ok) if yeterli and ok else None,
        "nedenler": sorted(({"neden": n, "adet": len(v), "ort": _ort(v)} for n, v in nedenler.items()),
                           key=lambda r: -r["adet"]),
    }


# --------------------------------------------------------------------------
# Kural denetimleri (saf işlevler)
# --------------------------------------------------------------------------


def butce_tepesi(islemler: list, simdi: datetime | None = None) -> list[dict]:
    """Her UTC günü için aynı anda açık teminatların en büyük toplamı (detay.gunluk_kullanim ile aynı
    yöntem; açık işlemler 'simdi'ye kadar açık sayılır)."""
    if not islemler:
        return []
    araliklar = [(i["giris_zamani"], i.get("cikis_zamani") or simdi, float(i.get("tutar") or 0.0))
                 for i in islemler
                 if i.get("giris_zamani") is not None and (i.get("cikis_zamani") or simdi) is not None]
    olaylar = sorted([(a, +t) for a, _b, t in araliklar] + [(b, -t) for _a, b, t in araliklar],
                     key=lambda o: (o[0], o[1]))
    gunler = sorted({a.date() for a, _b, _t in araliklar} | {b.date() for _a, b, _t in araliklar})
    sonuc = []
    for gun in gunler:
        bas = datetime(gun.year, gun.month, gun.day, tzinfo=timezone.utc)
        bit = bas + timedelta(days=1)
        acik = sum(t for a, b, t in araliklar if a < bas <= b)
        en_cok = acik
        for z, t in olaylar:
            if bas <= z < bit:
                acik += t
                en_cok = max(en_cok, acik)
        sonuc.append({"gun": gun.isoformat(), "en_cok": en_cok})
    return sonuc


def ust_uste_pozisyonlar(islemler: list, simdi: datetime) -> list[dict]:
    """Aynı botta aynı coinde zamanı çakışan iki pozisyon (motor buna izin vermez)."""
    gruplar: dict[tuple, list] = {}
    for i in islemler:
        if i.get("giris_zamani") is not None:
            gruplar.setdefault((i.get("bot"), i.get("parite")), []).append(i)
    cikti = []
    for liste in gruplar.values():
        liste = sorted(liste, key=lambda i: i["giris_zamani"])
        son_bitis, onceki = None, None
        for i in liste:
            if son_bitis is not None and i["giris_zamani"] < son_bitis:
                cikti.append(_ornek(i, f"önceki pozisyon (no {onceki.get('kimlik')}) kapanmadan açılmış"))
            bitis = i.get("cikis_zamani") or simdi
            if son_bitis is None or bitis > son_bitis:
                son_bitis, onceki = bitis, i
    return cikti


def bekleme_ihlalleri(islemler: list, bekleme_dk: dict) -> list[dict]:
    """Stoptan sonra aynı botta aynı coinde 'bekleme_dakika' dolmadan açılan işlemler.

    Canlıda bekleme motorun StoplossGuard korumasıyla uygulanır: stopla kapanan işlemden sonra o coin,
    o botta bekleme süresi kadar kilitlenir (karabasan_stratejileri.protections). Kilit mum sınırında
    biter; bu yüzden BEKLEME_TOLERANS_DK pay bırakılır. Yalnız 'stop' / 'tasfiye' çıkışları sayılır.
    """
    cikti = []
    gruplar: dict[tuple, list] = {}
    for i in islemler:
        gruplar.setdefault((i.get("bot"), i.get("parite")), []).append(i)
    for (bot, _p), liste in gruplar.items():
        dk = bekleme_dk.get(bot) or 0
        if dk <= 0:
            continue
        sinir = timedelta(minutes=dk - BEKLEME_TOLERANS_DK)
        stoplar = [i["cikis_zamani"] for i in liste if _stop_mu(i) and i.get("cikis_zamani")]
        for i in liste:
            for z in stoplar:
                if z <= i["giris_zamani"] < z + sinir:
                    gecen = (i["giris_zamani"] - z).total_seconds() / 60.0
                    cikti.append(_ornek(i, f"stoptan {gecen:.0f} dakika sonra açılmış (bekleme {dk} dakika)"))
                    break
    return sorted(cikti, key=lambda o: o["zaman"])


def stop_tasmalari(islemler: list, botlar: list, komisyon_yuzde: dict) -> list[dict]:
    """Stopun beklenen en büyük kaybından belirgin büyük kayıpla kapanan işlemler.

    Beklenen en büyük kayıp (teminatın yüzdesi) = stop × kaldıraç + iki taraf komisyon × kaldıraç.
    Ek girişli işlemde ek kısım stopa daha yakından girdiği için gerçek kayıp bunun altında kalır.
    """
    bilgi = _bot_bilgisi(botlar)
    cikti = []
    for i in islemler:
        b = bilgi.get(i.get("bot")) or {}
        stop = b.get("stop_yuzde")
        if not stop or i.get("net_yuzde") is None:
            continue
        kat = float(b.get("kaldirac") or 1.0)
        oran = float(komisyon_yuzde.get(b.get("piyasa") or "vadeli", 0.0))
        beklenen = float(stop) * kat + 2 * oran * kat
        kayip = -float(i["net_yuzde"])
        if kayip > beklenen + STOP_TASMA_PUAN:
            cikti.append(_ornek(i, f"teminatın %{kayip:.1f} kaybı; stopta en çok yaklaşık %{beklenen:.1f} beklenirdi"))
    return cikti


def guncel_seri(islemler: list) -> dict:
    """En son kapanan işlemlerden geriye art arda kayıp sayısı ve toplamı."""
    adet, toplam = 0, 0.0
    for i in sorted(islemler, key=lambda i: i["cikis_zamani"], reverse=True):
        if float(i["net_tutar"]) > 0:
            break
        adet += 1
        toplam += float(i["net_tutar"])
    return {"adet": adet, "toplam": toplam}


def denetimler(baglam: dict) -> list[dict]:
    botlar = baglam.get("botlar") or []
    islemler = baglam.get("islemler") or []
    acik = baglam.get("acik") or []
    simdi = baglam["simdi"]
    ayar = baglam.get("ayar") or {}
    komisyon = dict(ayar.get("komisyon_yuzde") or {})
    sonuc = []

    # 1. Günlük bütçe aşımı (bot başına sanal bakiye)
    bakiye = float(ayar.get("sanal_bakiye") or 0.0)
    if bakiye <= 0:
        sonuc.append(_denetim("Günlük bütçe", "Bir botun aynı anda kullandığı teminat sanal bakiyesini aşmamalı.",
                              neden="sanal bakiye ayarı okunamadı"))
    else:
        ornek = []
        for b in botlar:
            hepsi = [i for i in islemler if i.get("bot") == b["bot"]] + [i for i in acik if i.get("bot") == b["bot"]]
            for g in butce_tepesi(hepsi, simdi):
                if g["en_cok"] > bakiye + 0.01:
                    ornek.append({"bot": b["bot"], "kod": b.get("kod"), "kimlik": None, "parite": None, "zaman": None,
                                  "ayrinti": f"{g['gun']}: aynı anda {g['en_cok']:.0f} USDT teminat (bütçe {bakiye:.0f})"})
        sonuc.append(_denetim("Günlük bütçe", f"Bir botun aynı anda kullandığı teminat {bakiye:.0f} USDT'yi aşmamalı.", ornek))

    # 2. Aynı coinde üst üste açık pozisyon
    sonuc.append(_denetim("Aynı coinde iki pozisyon", "Bir bot aynı coinde ikinci pozisyonu, birincisi kapanmadan açmamalı.",
                          ust_uste_pozisyonlar(list(islemler) + list(acik), simdi)))

    # 3-4. Ek giriş kuralları
    izinli = {b["bot"]: "ek giriş" in str(b.get("ekleme_metni") or "") for b in botlar}
    tum = list(islemler) + list(acik)
    if not any("ek_girisler" in i for i in tum):
        neden = "kayıtta ek giriş bilgisi yok" if tum else "henüz işlem yok"
        sonuc.append(_denetim("1 kat botta ek giriş", "Zararda ekleme yalnız SMK2 / SMDK2'de var.", neden=neden))
        sonuc.append(_denetim("Tek ek giriş hakkı", "Ek girişli botta bir işleme en çok bir ek giriş.", neden=neden))
    else:
        yasak = [_ornek(i, f"{len(i['ek_girisler'])} ek giriş görünüyor") for i in tum
                 if i.get("ek_girisler") and not izinli.get(i.get("bot"), False)]
        fazla = [_ornek(i, f"{len(i['ek_girisler'])} ek giriş (hak bir)") for i in tum
                 if izinli.get(i.get("bot"), False) and len(i.get("ek_girisler") or []) > 1]
        sonuc.append(_denetim("1 kat botta ek giriş", "Zararda ekleme yalnız SMK2 / SMDK2'de var; öbür botlarda görülmemeli.", yasak))
        sonuc.append(_denetim("Tek ek giriş hakkı", "Ek girişli botta bir işleme en çok bir ek giriş.", fazla))

    # 5. Stop sonrası bekleme
    bekleme, okunamayan = {}, []
    for b in botlar:
        kural = _kural_oku(str(b.get("kod")))
        if kural is None:
            okunamayan.append(str(b.get("kod")))
        else:
            bekleme[b["bot"]] = int(kural.get("bekleme_dakika") or 0)
    if botlar and len(okunamayan) == len(botlar):
        sonuc.append(_denetim("Stoptan sonra bekleme", "Stoptan sonra aynı coine bekleme süresi dolmadan girilmemeli.",
                              neden="kural dosyaları okunamadı"))
    else:
        sureler_ = sorted({v for v in bekleme.values() if v})
        metin = (f"Stoptan sonra aynı botta aynı coine {', '.join(str(s) for s in sureler_)} dakika dolmadan girilmemeli."
                 if sureler_ else "Kural dosyalarında bekleme süresi yok.")
        sonuc.append(_denetim("Stoptan sonra bekleme", metin, bekleme_ihlalleri(islemler, bekleme)))

    # 6. Stopun tutmadığı işaret
    tasma = stop_tasmalari(islemler, botlar, komisyon)
    eski = sum(1 for i in islemler if _stop_mu(i) and ss.eski_stoplu(str(i.get("bot")), i.get("net_yuzde")))
    aciklama = "Bir işlem stopun izin verdiğinden belirgin büyük kayıpla kapanmamalı (fiyat stopun üstünden atlamış olabilir)."
    if eski:
        aciklama += (f" {eski} stop eski %3 stop dönemine ait; hepsi bugünkü stopa göre denetlendi, o dönemdeki küçük "
                     "taşmalar bu yüzden görünmez.")
    sonuc.append(_denetim("Stopun üstünde kayıp", aciklama, tasma))

    # 7. Sessiz bot
    sessiz = [{"bot": b["bot"], "kod": b.get("kod"), "kimlik": None, "parite": None, "zaman": None,
               "ayrinti": ("kayıt dosyası yok" if b.get("gunluk_yasi_dakika") is None
                           else f"son {b['gunluk_yasi_dakika']:.0f} dakikadır yazmıyor")}
              for b in botlar if not b.get("calisiyor")]
    if not botlar:
        sonuc.append(_denetim("Sessiz bot", "Her bot dakikada bir kayıt yazmalı.", neden="bot listesi boş"))
    else:
        sonuc.append(_denetim("Sessiz bot", f"Her bot en çok {SESSIZLIK_DAKIKA} dakikada bir kayıt yazmalı.", sessiz))
    return sonuc


# --------------------------------------------------------------------------
# Bugün dikkat edilecek 3 şey (saf işlev)
# --------------------------------------------------------------------------


def dikkat_sec(adaylar: list[dict], adet: int = DIKKAT_SAYISI) -> list[dict]:
    """Adayları önceliğe (ONCELIK; küçük = önemli), sonra büyüklüğe (agirlik; büyük önce),
    sonra geliş sırasına göre dizer ve ilk 'adet' tanesini döndürür."""
    sirali = sorted(enumerate(adaylar),
                    key=lambda ka: (ONCELIK.get(ka[1]["tur"], 99), -float(ka[1].get("agirlik") or 0.0), ka[0]))
    return [a for _k, a in sirali[:adet]]


def dikkat_adaylari(denetim: list, botlar: list, acik: list, seriler: dict, mal: dict, dilim: dict) -> list[dict]:
    adaylar = []
    for d in denetim:
        if d["durum"] == "ihlal" and d["ad"] != "Sessiz bot":
            adaylar.append({"tur": "ihlal", "agirlik": d["adet"],
                            "ne": f"Kural denetimi: {d['ad']}", "sayi": f"{d['adet']} ihlal",
                            "yapmali": "Bu ekrandaki kural denetiminde örnek işlemlere bak ve Claude'a sor; ayar değiştirme."})
    sessiz = [b for b in botlar if not b.get("calisiyor")]
    if sessiz:
        yaslar = [b.get("gunluk_yasi_dakika") for b in sessiz]
        bilinen = [y for y in yaslar if y is not None]
        sayi = ("kayıt dosyası yok" if not bilinen else f"en uzun {max(bilinen):.0f} dakikadır kayıt yok")
        adaylar.append({"tur": "sessiz", "agirlik": len(sessiz),
                        "ne": f"Sessiz bot: {', '.join(str(b.get('kod')) for b in sessiz)}", "sayi": sayi,
                        "yapmali": "Telegram'da /durum yaz; bir saatten uzun sürerse Claude'a sor."})
    toplam = sum(float(i.get("stopta_kayip") or 0.0) for i in acik)
    if acik and -toplam >= ACIK_RISK_ESIK:
        adaylar.append({"tur": "acik_risk", "agirlik": -toplam,
                        "ne": f"{len(acik)} açık pozisyon", "sayi": f"hepsi stopa giderse yaklaşık {toplam:.2f} USDT",
                        "yapmali": "İzle; botlar stopu kendisi uygular, elle kapatma."})
    for b in botlar:
        s = seriler.get(b["bot"]) or {}
        if s.get("adet", 0) >= SERI_ESIK:
            adaylar.append({"tur": "seri", "agirlik": s["adet"],
                            "ne": f"{b.get('kod')} art arda kayıpta", "sayi": f"son {s['adet']} işlem eksi, toplam {s['toplam']:.2f} USDT",
                            "yapmali": "İzle; seri tek başına sonuç değildir, sınav sonu kararında dikkate al."})
    if mal["islem"] >= MALIYET_EN_AZ_ISLEM and mal["komisyon"] > 0:
        if mal["brut"] <= 0:
            adaylar.append({"tur": "maliyet", "agirlik": mal["komisyon"],
                            "ne": "Komisyon zararı büyütüyor", "sayi": f"yaklaşık {mal['komisyon']:.2f} USDT komisyon, brüt sonuç da eksi",
                            "yapmali": "Sınav sonu kararında dikkate al: gerçek parada kayma da eklenir."})
        elif (mal["pay_yuzde"] or 0) >= MALIYET_PAY_ESIK:
            adaylar.append({"tur": "maliyet", "agirlik": mal["pay_yuzde"],
                            "ne": "Komisyon kârın büyük kısmını yiyor", "sayi": f"brüt kârın yaklaşık %{mal['pay_yuzde']:.0f}'i",
                            "yapmali": "Sınav sonu kararında dikkate al: kenar ince, gerçek kayma bunu silebilir."})
    for s in dilim.get("yuksek", [])[:2]:
        adaylar.append({"tur": "stop_dilimi", "agirlik": s["oran"] - (dilim.get("genel_oran") or 0),
                        "ne": f"Stop yoğun dilim: {dilim_adi(s)}",
                        "sayi": f"%{s['oran']:.0f} stop ({s['stop']}/{s['islem']}), genel %{dilim['genel_oran']:.0f}",
                        "yapmali": "İzle; tek dönemin sonucu olabilir, ayar değiştirme. Claude'a sor."})
    return adaylar


GUN_ADLARI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def dilim_adi(s: dict) -> str:
    if s["tur"] == "saat":
        return f"{s['anahtar']:02d}:00–{s['anahtar'] + SAAT_DILIMI_SAAT:02d}:00"
    if s["tur"] == "gun":
        return GUN_ADLARI[s["anahtar"]]
    return str(s["anahtar"])


# --------------------------------------------------------------------------
# Giriş noktası
# --------------------------------------------------------------------------


def stop_dersleri(botlar: list, izleme: dict | None) -> list[dict]:
    dersler = [d for d in (izleme or {}).get("dersler") or [] if isinstance(d, dict)]
    cikti = []
    for b in botlar:
        st = b.get("stop_sonrasi") or {}
        karar = st.get("karar") or {}
        son = next((d for d in reversed(dersler) if d.get("bot") == b["bot"]), None)
        cikti.append({
            "bot": b["bot"], "kod": b.get("kod"), "stop_yuzde": b.get("stop_yuzde"),
            "karar_kod": karar.get("kod"), "karar_adi": ss.KARAR_ADI.get(karar.get("kod"), "Veri yok"),
            "metin": karar.get("metin"), "stop_sayisi": st.get("stop_sayisi", 0),
            "son_ders": None if son is None else {"zaman": _zaman_coz(son.get("zaman")),
                                                  "ad": son.get("ad"), "metin": son.get("metin")},
        })
    return cikti


def hesapla(baglam: dict) -> dict:
    botlar = baglam.get("botlar") or []
    islemler = baglam.get("islemler") or []
    acik = baglam.get("acik") or []
    ayar = baglam.get("ayar") or {}
    ek_kayma = EK_KAYMA_YUZDE
    dilim = stop_dilimleri(islemler)
    mal = maliyet(islemler, botlar, dict(ayar.get("komisyon_yuzde") or {}), ek_kayma)
    denetim = denetimler(baglam)
    seriler = {b["bot"]: guncel_seri([i for i in islemler if i.get("bot") == b["bot"]]) for b in botlar}
    adaylar = dikkat_adaylari(denetim, botlar, acik, seriler, mal, dilim)
    for s in dilim["yuksek"]:
        s["ad"] = dilim_adi(s)
    return {
        "islem_sayisi": len(islemler),
        "durum_verisi": None,   # Karabasan piyasa durumu işlem kaydında yok (canlı durum kaydı tutulmuyor)
        "stop_dilimleri": dilim,
        "maliyet": mal,
        "sureler": sureler(islemler),
        "stop_dersleri": stop_dersleri(botlar, baglam.get("izleme")),
        "denetimler": denetim,
        "seriler": seriler,
        "dikkat": dikkat_sec(adaylar),
        "dikkat_aday_sayisi": len(adaylar),
    }
