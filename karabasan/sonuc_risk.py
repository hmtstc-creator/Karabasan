"""Risk ekranının verisi (10 Kasım 2026): sermaye koruma gözüyle açık risk, düşüş, yoğunlaşma.

Yalnız okur; hiçbir ayar ya da bot dosyası yazmaz. Yalnız Python standart kütüphanesi:
`karabasan.sonuc`, `kural` ve `detay` numpy'ı (dolaylı olarak) içe aktardığı için burada
içe aktarılmaz. Açık pozisyonların stoptaki kaybı (`stopta_kayip`) bağlamda `sonuc.acik_risk`
tarafından zaten hesaplanmıştır; burada yeniden hesaplanmaz, yalnız toplanır.

Bütçe paydası: her botun kendi sanal bakiyesi vardır (`ayar["sanal_bakiye"]`, yapılandırma
üreteci bunu her botun `dry_run_wallet` değeri yapar). Toplam bütçe = bot sayısı × bakiye.
Ek girişli botlarda motorun cüzdanı 3 kat büyütülür (ek girişler parasızlıktan kalmasın), ama
sayfanın bütün yüzdeleri, sonuç sayfasının geri kalanı gibi, ayardaki bakiyeye göredir.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

STRATEJI_KLASORU = Path(__file__).parent / "stratejiler"
GUNLUK_GUN = 14          # günlük bütçe kullanımında son kaç gün
EK_GIRIS_PAYI = 1.01     # tutar ilk tutarın %1'inden fazla büyükse ek giriş yapılmış sayılır (acik_risk ile aynı)
VERI_AZ_ISLEM = 20       # düşüş ölçüsü bundan az kapanmış işlemle "veri az"


# --------------------------------------------------------------------------
# Saf hesaplar (testli)
# --------------------------------------------------------------------------


def dusus_olcumu(islemler: list, simdi: datetime | None = None, butce: float | None = None) -> dict:
    """Kapanmış işlemlerin birikimli net sonucundan (kayıtlı net_tutar) tepeden düşüş ölçüleri.

    Tam çözünürlükte, her işlem kapanışında bir nokta. Tepe sıfırdan başlar (dönem başı).
    "Su altı" = birikimli sonuç son tepenin altında; tepeye yeniden ulaşınca biter.
    Açık pozisyonların kâğıt üstü sonucu dahil değildir (anlık fiyat verisi yok).
    """
    sirali = sorted(islemler, key=lambda i: i["cikis_zamani"])
    bos = {"islem_sayisi": len(sirali), "simdiki": None, "en_derin": None, "en_derin_zaman": None,
           "simdiki_yuzde": None, "en_derin_yuzde": None, "en_uzun_su_alti_gun": None,
           "su_alti_gun": None, "su_altinda": False, "tepe": None, "noktalar": []}
    if not sirali:
        return bos
    toplam = 0.0
    tepe = 0.0
    tepe_zaman = min(i["giris_zamani"] for i in sirali)
    en_derin, en_derin_zaman = 0.0, None
    en_uzun = timedelta(0)
    noktalar = []
    for i in sirali:
        toplam += float(i["net_tutar"])
        z = i["cikis_zamani"]
        if toplam >= tepe - 1e-9:
            if _su_altindaydi(noktalar):           # su altından çıkış: süreyi kaydet
                en_uzun = max(en_uzun, z - tepe_zaman)
            tepe, tepe_zaman = max(tepe, toplam), z
        dusus = toplam - tepe
        if dusus < en_derin - 1e-12:
            en_derin, en_derin_zaman = dusus, z
        noktalar.append((z.timestamp(), round(toplam, 6), round(dusus, 6)))
    simdiki = toplam - tepe
    su_altinda = simdiki < -1e-9
    son = simdi or sirali[-1]["cikis_zamani"]
    su_alti = (son - tepe_zaman) if su_altinda else timedelta(0)
    en_uzun = max(en_uzun, su_alti)
    pay = (lambda v: v / butce * 100.0) if butce else (lambda v: None)
    return {
        "islem_sayisi": len(sirali),
        "simdiki": simdiki,
        "en_derin": en_derin,
        "en_derin_zaman": en_derin_zaman,
        "simdiki_yuzde": pay(simdiki),
        "en_derin_yuzde": pay(en_derin),
        "en_uzun_su_alti_gun": en_uzun.total_seconds() / 86400.0,
        "su_alti_gun": su_alti.total_seconds() / 86400.0 if su_altinda else 0.0,
        "su_altinda": su_altinda,
        "tepe": tepe,
        "noktalar": noktalar,
    }


def _su_altindaydi(noktalar: list) -> bool:
    return bool(noktalar) and noktalar[-1][2] < -1e-9


def gunluk_teminat(pozisyonlar: list, simdi: datetime, gun_sayisi: int = GUNLUK_GUN) -> list[dict]:
    """Her UTC günü için o günün herhangi bir anında aynı anda açık teminatların en büyük toplamı.

    pozisyonlar: {"giris_zamani", "cikis_zamani" (açıksa None), "tutar"}. Açık olanlar `simdi`'de
    biter sayılır; `simdi`'den sonrası hiç kullanılmaz. `detay.gunluk_kullanim` ile aynı fikir
    (o modül numpy'a bağlı olduğu için burada yeniden kullanılamıyor), ek olarak açık pozisyonlar.
    Son `gun_sayisi` gün; işlem olmayan günler sıfır yazılır.
    """
    olaylar = []
    for p in pozisyonlar:
        g = p["giris_zamani"]
        c = p.get("cikis_zamani") or simdi
        if g > simdi:
            continue
        c = min(c, simdi)
        t = float(p.get("tutar") or 0.0)
        olaylar.append((g, +t))
        olaylar.append((c, -t))
    olaylar.sort(key=lambda o: (o[0], o[1]))   # aynı anda çıkış ve giriş: önce çıkış
    bugun = simdi.astimezone(timezone.utc).date()
    gunler = [bugun - timedelta(days=k) for k in range(gun_sayisi - 1, -1, -1)]
    sonuc = []
    for gun in gunler:
        bas = datetime(gun.year, gun.month, gun.day, tzinfo=timezone.utc)
        bit = min(bas + timedelta(days=1), simdi)
        acik = 0.0
        sira = 0
        while sira < len(olaylar) and olaylar[sira][0] < bas:
            acik += olaylar[sira][1]
            sira += 1
        # tam gün başında kapananlar (çıkış == bas) gün başında açık sayılmaz
        while sira < len(olaylar) and olaylar[sira][0] == bas and olaylar[sira][1] < 0:
            acik += olaylar[sira][1]
            sira += 1
        en_cok = max(acik, 0.0)
        while sira < len(olaylar) and olaylar[sira][0] < bit:
            acik += olaylar[sira][1]
            en_cok = max(en_cok, acik)
            sira += 1
        sonuc.append({"gun": gun.isoformat(), "en_cok": round(en_cok, 6), "tamam": bit >= bas + timedelta(days=1)})
    return sonuc


def ekleme_ayari(kod: str) -> dict | None:
    """Kuralın `zararda_ekleme` ve stop değerleri, JSON'dan doğrudan (kural.py numpy istediği için)."""
    for yol in (STRATEJI_KLASORU / f"{kod}.json", STRATEJI_KLASORU / "emekli" / f"{kod}.json"):
        if yol.exists():
            try:
                kural = json.loads(yol.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            ekleme = kural.get("zararda_ekleme")
            if not ekleme:
                return None
            return {"stopa_kala_yuzde": float(ekleme["stopa_kala_yuzde"]), "kat": float(ekleme["kat"]),
                    "stop_yuzde": float((kural.get("cikis") or {}).get("zarar_durdur_yuzde") or 0.0),
                    "kaldirac": float(kural.get("kaldirac", 1))}
    return None


def ek_giris_yapildi(islem: dict, ilk_tutar: float) -> bool:
    """Ek giriş kaydı (orders tablosu) varsa ya da teminat ilk tutarı aştıysa (acik_risk ile aynı ölçü)."""
    return bool(islem.get("ek_girisler")) or float(islem.get("tutar") or 0.0) > ilk_tutar * EK_GIRIS_PAYI


def _ek_giris_fiyati(islem: dict, ayar_: dict) -> float | None:
    if islem.get("ek_girisler"):
        return float(islem["ek_girisler"][0]["fiyat"])
    ilk = islem.get("ilk_giris_fiyati") or islem.get("giris_fiyati")
    if not ilk:
        return None
    uzaklik = ayar_["stop_yuzde"] - ayar_["stopa_kala_yuzde"]
    yon = 1.0 if islem.get("yon") == "aciga_satis" else -1.0
    return float(ilk) * (1 + yon * uzaklik / 100.0)


# --------------------------------------------------------------------------
# Ana hesap
# --------------------------------------------------------------------------


def hesapla(baglam: dict) -> dict:
    ayar = baglam.get("ayar") or {}
    simdi = baglam.get("simdi") or datetime.now(timezone.utc)
    botlar = baglam.get("botlar") or []
    acik = list(baglam.get("acik") or [])
    islemler = list(baglam.get("islemler") or [])
    bot_islemleri = baglam.get("bot_islemleri") or {}
    bakiye = float(ayar.get("sanal_bakiye") or 0.0) or None
    ilk_tutar = float(ayar.get("islem_tutari") or 0.0)
    bot_sayisi = len(botlar)
    toplam_butce = bakiye * bot_sayisi if bakiye and bot_sayisi else None

    def oran(v, payda):
        return None if v is None or not payda else v / payda * 100.0

    kaldirac = {b["bot"]: float(b.get("kaldirac") or 1.0) for b in botlar}
    eklemeler = {b["kod"]: ekleme_ayari(b["kod"]) for b in botlar}

    # ---- Açık risk ----
    bilinen = [i for i in acik if i.get("stopta_kayip") is not None]
    stopta_toplam = sum(float(i["stopta_kayip"]) for i in bilinen) if bilinen else (0.0 if not acik else None)
    bot_satirlari = []
    for b in botlar:
        kendi = [i for i in acik if i.get("bot") == b["bot"]]
        kayiplar = [float(i["stopta_kayip"]) for i in kendi if i.get("stopta_kayip") is not None]
        teminat = sum(float(i.get("tutar") or 0.0) for i in kendi)
        bot_satirlari.append({
            "bot": b["bot"], "kod": b["kod"], "adet": len(kendi),
            "bilinmeyen": len(kendi) - len(kayiplar),
            "stopta_kayip": sum(kayiplar) if kayiplar else (0.0 if not kendi else None),
            "butce_yuzde": oran(sum(kayiplar), bakiye) if kayiplar else (0.0 if not kendi else None),
            "teminat": teminat,
            "teminat_yuzde": oran(teminat, bakiye),
            "kaldirac": kaldirac.get(b["bot"], 1.0),
            "ekleme": eklemeler.get(b["kod"]) is not None,
        })

    # ---- Düşüş ----
    toplam_dusus = dusus_olcumu(islemler, simdi, toplam_butce)
    toplam_dusus["veri_az"] = len(islemler) < VERI_AZ_ISLEM
    bot_dusus = []
    for b in botlar:
        d = dusus_olcumu(bot_islemleri.get(b["kod"]) or [], simdi, bakiye)
        d.pop("noktalar", None)
        bot_dusus.append({"bot": b["bot"], "kod": b["kod"], **d})

    senaryo = None
    if not acik:
        pass   # açık pozisyon yok: senaryo yok
    elif stopta_toplam is not None and toplam_dusus["simdiki"] is not None:
        # Hepsi stopa giderse: bugünkü düşüşün üstüne stoptaki kayıp (tepe aynı kalır).
        derinlik = toplam_dusus["simdiki"] + stopta_toplam
        senaryo = {"dusus": derinlik, "dusus_yuzde": oran(derinlik, toplam_butce),
                   "en_derinden_derin": derinlik < (toplam_dusus["en_derin"] or 0.0) - 1e-9}
    elif stopta_toplam is not None and not islemler:
        senaryo = {"dusus": stopta_toplam, "dusus_yuzde": oran(stopta_toplam, toplam_butce), "en_derinden_derin": False}

    # ---- Yoğunlaşma (kaldıraçlı büyüklük: teminat × kaldıraç) ----
    nominal_toplam = 0.0
    yonler = {"aciga_satis": 0.0, "alim": 0.0}
    coinler: dict[str, dict] = {}
    for i in acik:
        nominal = float(i.get("tutar") or 0.0) * kaldirac.get(i.get("bot"), 1.0)
        nominal_toplam += nominal
        yonler["aciga_satis" if i.get("yon") == "aciga_satis" else "alim"] += nominal
        parite = str(i.get("parite") or "?").split(":", 1)[0]
        c = coinler.setdefault(parite, {"parite": parite, "nominal": 0.0, "stopta_kayip": 0.0,
                                        "botlar": [], "adet": 0})
        c["nominal"] += nominal
        c["adet"] += 1
        c["stopta_kayip"] += float(i.get("stopta_kayip") or 0.0)
        kod = str(i.get("kod") or i.get("bot"))
        if kod not in c["botlar"]:
            c["botlar"].append(kod)
    coin_listesi = sorted(coinler.values(), key=lambda c: c["nominal"], reverse=True)
    for c in coin_listesi:
        c["pay"] = oran(c["nominal"], nominal_toplam)
    yogunlasma = {
        "nominal_toplam": nominal_toplam,
        "nominal_yuzde": oran(nominal_toplam, toplam_butce),
        "aciga_satis_pay": oran(yonler["aciga_satis"], nominal_toplam),
        "alim_pay": oran(yonler["alim"], nominal_toplam),
        "coinler": coin_listesi,
        "en_buyuk_coin": coin_listesi[0] if coin_listesi else None,
        "ortak_coinler": [c for c in coin_listesi if len(c["botlar"]) > 1],
    }

    # ---- Günlük teminat kullanımı (bütün botlar) ----
    pozisyonlar = ([{"giris_zamani": i["giris_zamani"], "cikis_zamani": i["cikis_zamani"], "tutar": i.get("tutar")}
                    for i in islemler]
                   + [{"giris_zamani": i["giris_zamani"], "cikis_zamani": None, "tutar": i.get("tutar")} for i in acik])
    gunluk = gunluk_teminat(pozisyonlar, simdi)
    for g in gunluk:
        g["yuzde"] = oran(g["en_cok"], toplam_butce)
    teminat_simdi = sum(float(i.get("tutar") or 0.0) for i in acik)

    # ---- Zararda ek girişli botlar ----
    ek_botlar = [b for b in botlar if eklemeler.get(b["kod"])]
    yapilan, bekleyen = [], []
    for i in acik:
        e = eklemeler.get(i.get("kod"))
        if not e:
            continue
        satir = {
            "bot": i.get("bot"), "kod": i.get("kod"), "parite": i.get("parite"), "kimlik": i.get("kimlik"),
            "giris_zamani": i.get("giris_zamani"),
            "ilk_giris_fiyati": i.get("ilk_giris_fiyati") or i.get("giris_fiyati"),
            "ortalama_fiyat": i.get("giris_fiyati"),
            "ek_giris_fiyati": _ek_giris_fiyati(i, e),
            "stop_fiyati": i.get("stop_fiyati"),
            "teminat": float(i.get("tutar") or 0.0),
            "nominal": float(i.get("tutar") or 0.0) * e["kaldirac"],
            "stopta_kayip": i.get("stopta_kayip"),
            "stopta_kayip_yuzde": oran(i.get("stopta_kayip"), bakiye),
        }
        if ek_giris_yapildi(i, ilk_tutar):
            yapilan.append(satir)
        else:
            satir["eklenecek_teminat"] = ilk_tutar * e["kat"]
            bekleyen.append(satir)
    kapanan_ekli = []
    for b in ek_botlar:
        for i in bot_islemleri.get(b["kod"]) or []:
            if ek_giris_yapildi(i, ilk_tutar):
                kapanan_ekli.append(i)
    ekleme = {
        "botlar": [b["kod"] for b in ek_botlar],
        "ayar": {b["kod"]: eklemeler[b["kod"]] for b in ek_botlar},
        "yapilan": yapilan,
        "bekleyen": bekleyen,
        "bekleyen_ek_teminat": sum(s["eklenecek_teminat"] for s in bekleyen),
        "kapanan_ekli_adet": len(kapanan_ekli),
        "kapanan_ekli_net": sum(float(i["net_tutar"]) for i in kapanan_ekli) if kapanan_ekli else None,
        # Karne yüzde × ilk tutar ile hesaplar; ek girişte kayıtlı tutardan farklı çıkabilir.
        "kapanan_ekli_karne": (sum(float(i["net_yuzde"]) / 100.0 * ilk_tutar for i in kapanan_ekli)
                               if kapanan_ekli else None),
        "kapanan_ekli_en_kotu": min((float(i["net_tutar"]) for i in kapanan_ekli), default=None),
    }

    return {
        "butce": {"bot_basi": bakiye, "bot_sayisi": bot_sayisi, "toplam": toplam_butce, "ilk_tutar": ilk_tutar},
        "acik": {
            "adet": len(acik),
            "bilinmeyen": len(acik) - len(bilinen),
            "stopta_kayip": stopta_toplam,
            "butce_yuzde": oran(stopta_toplam, toplam_butce),
            "teminat": teminat_simdi,
            "teminat_yuzde": oran(teminat_simdi, toplam_butce),
            "botlar": bot_satirlari,
        },
        "dusus": {"toplam": toplam_dusus, "botlar": bot_dusus},
        "senaryo": senaryo,
        "yogunlasma": yogunlasma,
        "gunluk": gunluk,
        "ekleme": ekleme,
    }
