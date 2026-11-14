"""Sağlama sayfası (/sagla): sanal kârın gerçekten tutarlı olup olmadığını bağımsız yoldan denetler.

Ahmet (14 Kasım 2026): "600 küsür kâr gerçek mi yoksa hikaye mi? Matematikteki sağlama işlemi gibi düşün."

Sonuç sayfası kârı `sonuc.islemleri_oku` ile toplar. Bu modül aynı kayıt dosyalarını (user_data/db/<bot>.sqlite,
salt okunur) AYRI bir yoldan okur ve şunları sınar:

  1. Toplam sağlaması   : kayıttaki kâr sütunlarının SQL toplamı = sayfanın gösterdiği toplam.
  2. Emirden yeniden hesap : her işlemin kârı, emir kayıtlarındaki (orders) gerçekleşen fiyat ve miktarlardan
                          komisyon düşülerek baştan hesaplanır; işlemin kayıtlı kârıyla karşılaştırılır.
  3. Mantık denetimi    : çıkışı girişten önce olan, çift kayıtlı, fiyatsız, sonuçsuz işlem; çıkış nedeniyle
                          işaretin çelişmesi (stop'ta kâr, kâr hedefinde zarar).
  4. Yoğunlaşma         : kâr birkaç şanslı işleme mi bağlı? (en iyi 5 işlem çıkınca ne kalır)
  5. Fiyat gerçekliği   : (isteğe bağlı, ?mum=1) örnek işlemlerin giriş / çıkış fiyatı o dakikanın Binance mumunun
                          dip-tepe aralığında mı? Binance'e ulaşılamazsa "belirsiz" der, "geçti" demez.

Dürüstlük kuralı: bir denetim çalışamadıysa durumu "belirsiz" olur; hiçbir zaman yeşil sayılmaz.
Bu sayfa DEFTERİN içeride tutarlı olduğunu kanıtlar. Sanal işlemin gerçek hesapta aynı kârı getireceğini GARANTİ ETMEZ
(sanal emirler kayma, derinlik ve reddedilme yaşamaz); sayfa bunu her zaman açıkça yazar.

Yalnız Python standart kütüphanesi. Hiçbir şey yazmaz, hiçbir bota dokunmaz.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from . import site_gezinti
from .botlar import BOTLAR
from .sonuc import donem_bilgisi, zaman_coz, zaman_dosyasi_oku

# Eşikler. Kasıtlı olarak sıkı tutuldu; gevşetmek için neden gerekir.
TUTAR_TOLERANS = 0.02          # bir işlemin yeniden hesabı kayıttan bu USDT'den fazla sapmamalı
ORAN_TOLERANS = 0.005          # ... ya da kârın mutlak değerinin %0,5'i (hangisi büyükse)
TOPLAM_TOLERANS = 0.01         # toplam sağlaması: bu USDT'den fazla fark olmamalı
KAPSAMA_ASGARI = 0.95          # işlemlerin en az bu kadarında emir kaydı bulunmalı; yoksa "belirsiz"
FIYAT_TOLERANS = 0.002         # mum aralığının %0,2 dışına kadar kabul (sanal emir defter fiyatından dolar)
MUM_ORNEK = 10                 # fiyat gerçekliği için bot başına örnek işlem sayısı
EN_IYI_N = 5
ISARET_PAYI = 0.5              # "stop'ta kâr" / "hedefte zarar" için komisyon payı (USDT)

DURUM_ADI = {"ok": "TUTTU", "hata": "TUTMADI", "belirsiz": "BELİRSİZ", "uyari": "DİKKAT"}


def _sayi(deger, basamak=2, isaret=False) -> str:
    if deger is None:
        return "-"
    metin = f"{deger:{'+' if isaret else ''},.{basamak}f}"
    return metin.replace(",", "_").replace(".", ",").replace("_", ".")


def _kayit_oku(db_yolu: Path) -> dict:
    """Ham tablo satırları: {"islemler": [...], "emirler": {işlem kimliği: [...]}, "hata": metin ya da None}."""
    if not db_yolu.exists():
        return {"islemler": [], "emirler": {}, "hata": "Kayıt dosyası yok."}
    try:
        vt = sqlite3.connect(f"file:{db_yolu}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as hata:
        return {"islemler": [], "emirler": {}, "hata": f"Kayıt açılamadı: {hata}"}
    try:
        vt.row_factory = sqlite3.Row
        islemler = [dict(s) for s in vt.execute("SELECT * FROM trades ORDER BY id")]
        emirler: dict = {}
        try:
            for s in vt.execute("SELECT * FROM orders ORDER BY id"):
                e = dict(s)
                emirler.setdefault(e.get("ft_trade_id"), []).append(e)
        except sqlite3.Error:
            emirler = {}
        return {"islemler": islemler, "emirler": emirler, "hata": None}
    except sqlite3.Error as hata:
        return {"islemler": [], "emirler": {}, "hata": f"Kayıt okunamadı: {hata}"}
    finally:
        vt.close()


def _sayi_ya_none(deger):
    try:
        return None if deger is None else float(deger)
    except (TypeError, ValueError):
        return None


def kapali_islemler(satirlar: list[dict], baslangic: datetime | None, bitis: datetime | None) -> list[dict]:
    """Sayfanın sayacağı kapalı işlemler (aynı dönem süzgeci), ama kendi okumamızla."""
    sonuc = []
    for s in satirlar:
        if s.get("is_open"):
            continue
        giris, cikis = zaman_coz(s.get("open_date")), zaman_coz(s.get("close_date"))
        if giris is None or cikis is None:
            continue
        if baslangic is not None and giris < baslangic:
            continue
        if bitis is not None and cikis > bitis:
            continue
        sonuc.append(s)
    return sonuc


def emirden_kar(islem: dict, emirler: list[dict]) -> dict:
    """İşlemin kârını emir kayıtlarından baştan hesaplar.

    Dönen: {"hesap": USDT ya da None, "neden": None ya da neden}. Giriş tarafı: açığa satışta "sell", alımda "buy";
    kapanış tarafı tersi. Değer = gerçekleşen miktar × ortalama fiyat. Kâr = (açığa satış için giriş − çıkış, alım
    için çıkış − giriş) − komisyonlar + fonlama. Kaldıraç sonucu değiştirmez (teminat farkı kâr değil).
    """
    kisa = bool(islem.get("is_short"))
    giris_tarafi, cikis_tarafi = ("sell", "buy") if kisa else ("buy", "sell")
    giris_deger = cikis_deger = 0.0
    giris_adet = cikis_adet = 0
    for e in emirler:
        taraf = e.get("ft_order_side")
        if taraf not in (giris_tarafi, cikis_tarafi):
            continue
        miktar = _sayi_ya_none(e.get("filled"))
        fiyat = next((_sayi_ya_none(e.get(a)) for a in ("average", "safe_price", "price") if e.get(a)), None)
        if not miktar or miktar <= 0 or fiyat is None:
            continue
        if e.get("status") in ("canceled", "cancelled", "expired", "rejected") and not miktar:
            continue
        if taraf == giris_tarafi:
            giris_deger += miktar * fiyat
            giris_adet += 1
        else:
            cikis_deger += miktar * fiyat
            cikis_adet += 1
    if not giris_adet or not cikis_adet:
        return {"hesap": None, "neden": "gerçekleşmiş giriş ya da çıkış emri kaydı yok"}
    brut = (giris_deger - cikis_deger) if kisa else (cikis_deger - giris_deger)
    maliyet = _sayi_ya_none(islem.get("fee_open_cost"))
    maliyet_k = _sayi_ya_none(islem.get("fee_close_cost"))
    if maliyet is not None and maliyet_k is not None:
        komisyon = maliyet + maliyet_k
    else:
        fo, fc = _sayi_ya_none(islem.get("fee_open")), _sayi_ya_none(islem.get("fee_close"))
        if fo is None or fc is None:
            return {"hesap": None, "neden": "komisyon bilgisi kayıtta yok"}
        komisyon = fo * giris_deger + fc * cikis_deger
    fonlama = _sayi_ya_none(islem.get("funding_fees")) or 0.0
    return {"hesap": brut - komisyon + fonlama, "neden": None}


def _kayitli_kar(islem: dict):
    return _sayi_ya_none(islem.get("close_profit_abs"))


def emir_sagla(kapali: list[dict], emirler: dict) -> dict:
    """Emirden yeniden hesap sonucu: kapsama, sapmalı işlemler, toplam sapma."""
    kontrol = sapan = 0
    toplam_fark = 0.0
    en_kotu: list[dict] = []
    nedenler: dict[str, int] = {}
    for s in kapali:
        kayitli = _kayitli_kar(s)
        if kayitli is None:
            nedenler["kayıtlı kâr sütunu boş"] = nedenler.get("kayıtlı kâr sütunu boş", 0) + 1
            continue
        h = emirden_kar(s, emirler.get(s.get("id")) or [])
        if h["hesap"] is None:
            nedenler[h["neden"]] = nedenler.get(h["neden"], 0) + 1
            continue
        kontrol += 1
        fark = h["hesap"] - kayitli
        toplam_fark += fark
        if abs(fark) > max(TUTAR_TOLERANS, ORAN_TOLERANS * abs(kayitli)):
            sapan += 1
            en_kotu.append({"kimlik": s.get("id"), "parite": s.get("pair"), "kayitli": kayitli,
                            "hesap": h["hesap"], "fark": fark})
    en_kotu.sort(key=lambda r: abs(r["fark"]), reverse=True)
    return {"toplam_islem": len(kapali), "kontrol_edilen": kontrol, "sapan": sapan,
            "toplam_fark": toplam_fark, "en_kotu": en_kotu[:5], "kontrol_edilemeyen_nedenler": nedenler,
            "kapsama": (kontrol / len(kapali)) if kapali else None}


def mantik_denetimi(kapali: list[dict]) -> dict:
    """Satır başına saçmalık araması: sorun listesi (kimlik, açıklama)."""
    sorunlar: list[tuple] = []
    goruldu: dict[tuple, int] = {}
    for s in kapali:
        kimlik = s.get("id")
        giris, cikis = zaman_coz(s.get("open_date")), zaman_coz(s.get("close_date"))
        kar = _kayitli_kar(s)
        if kar is None or kar != kar:
            sorunlar.append((kimlik, "kâr değeri boş ya da sayı değil"))
            continue
        if giris and cikis and cikis < giris:
            sorunlar.append((kimlik, "çıkış girişten önce"))
        if not _sayi_ya_none(s.get("close_rate")) or not _sayi_ya_none(s.get("open_rate")):
            sorunlar.append((kimlik, "giriş ya da çıkış fiyatı yok"))
        anahtar = (s.get("pair"), str(s.get("open_date")))
        if anahtar in goruldu:
            sorunlar.append((kimlik, f"{goruldu[anahtar]} numaralı işlemle aynı coin ve aynı açılış anı (çift kayıt)"))
        else:
            goruldu[anahtar] = kimlik
        neden = s.get("exit_reason") or ""
        if neden in ("stop_loss", "stoploss_on_exchange") and kar > ISARET_PAYI and not s.get("funding_fees"):
            sorunlar.append((kimlik, f"stop ile çıkmış ama {_sayi(kar, 2, True)} USDT kârlı"))
        if neden == "roi" and kar < -ISARET_PAYI:
            sorunlar.append((kimlik, f"kâr hedefiyle çıkmış ama {_sayi(kar, 2, True)} USDT zararlı"))
    return {"bakilan": len(kapali), "sorunlar": sorunlar[:20], "sorun_sayisi": len(sorunlar)}


def yogunlasma(kapali: list[dict]) -> dict:
    """Kâr birkaç işleme mi dayanıyor? En iyi N işlem çıkarılınca toplam ne olur."""
    karlar = sorted((k for k in (_kayitli_kar(s) for s in kapali) if k is not None), reverse=True)
    toplam = sum(karlar)
    en_iyi = sum(karlar[:EN_IYI_N])
    kazanan = sum(1 for k in karlar if k > 0)
    return {"islem": len(karlar), "kazanan": kazanan, "toplam": toplam, "en_iyi_toplam": en_iyi,
            "en_iyiden_sonra": toplam - en_iyi, "en_iyi_n": EN_IYI_N,
            "ortanca": (karlar[len(karlar) // 2] if karlar else None)}


def fiyat_gercekligi(kapali: list[dict], piyasa: str, mum_fn, ornek: int = MUM_ORNEK) -> dict:
    """Örnek işlemlerin giriş ve çıkış fiyatı o dakikanın mum aralığında mı? mum_fn(parite, piyasa, "1m", bas, bit)."""
    if not kapali:
        return {"ornek": 0, "icinde": 0, "disinda": [], "alinamayan": 0}
    adim = max(1, len(kapali) // ornek)
    secilen = kapali[::adim][:ornek]
    icinde = alinamayan = 0
    disinda: list[dict] = []
    for s in secilen:
        for ad, zaman_alani, fiyat_alani in (("giriş", "open_date", "open_rate"), ("çıkış", "close_date", "close_rate")):
            an, fiyat = zaman_coz(s.get(zaman_alani)), _sayi_ya_none(s.get(fiyat_alani))
            if an is None or not fiyat:
                alinamayan += 1
                continue
            try:
                mumlar = mum_fn(s.get("pair"), piyasa, "1m", an - timedelta(minutes=3), an + timedelta(minutes=3))
            except Exception:  # noqa: BLE001 - ağ hatası "geçti" sayılmaz, "alınamadı" sayılır
                mumlar = []
            if not mumlar:
                alinamayan += 1
                continue
            dip, tepe = min(m[3] for m in mumlar), max(m[2] for m in mumlar)
            if dip * (1 - FIYAT_TOLERANS) <= fiyat <= tepe * (1 + FIYAT_TOLERANS):
                icinde += 1
            else:
                disinda.append({"kimlik": s.get("id"), "parite": s.get("pair"), "taraf": ad, "fiyat": fiyat,
                                "dip": dip, "tepe": tepe})
    return {"ornek": len(secilen), "icinde": icinde, "disinda": disinda[:5], "disinda_sayi": len(disinda),
            "alinamayan": alinamayan}


def _denetim(kimlik: str, ad: str, durum: str, ozet: str, ayrinti: list | None = None) -> dict:
    return {"kimlik": kimlik, "ad": ad, "durum": durum, "ozet": ozet, "ayrinti": ayrinti or []}


def bot_sagla(bot: str, piyasa: str, kayit: dict, baslangic, bitis, sayfa_toplami: float | None,
              mum_fn=None) -> dict:
    """Tek botun bütün denetimleri."""
    if kayit["hata"]:
        return {"bot": bot, "hata": kayit["hata"], "denetimler": [], "kapali": 0, "toplam": 0.0}
    kapali = kapali_islemler(kayit["islemler"], baslangic, bitis)
    kayitli = [_kayitli_kar(s) for s in kapali]
    toplam = sum(k for k in kayitli if k is not None)
    denetimler = []

    # 1. Toplam sağlaması
    if sayfa_toplami is None:
        denetimler.append(_denetim("toplam", "Toplam sağlaması", "belirsiz",
                                   "Sayfanın toplamı alınamadığından karşılaştırılamadı."))
    else:
        fark = sayfa_toplami - toplam
        denetimler.append(_denetim(
            "toplam", "Toplam sağlaması", "ok" if abs(fark) <= TOPLAM_TOLERANS else "hata",
            f"Kayıtların kendi toplamı {_sayi(toplam, 2, True)} USDT; sayfa {_sayi(sayfa_toplami, 2, True)} USDT "
            f"gösteriyor. Fark {_sayi(fark, 4, True)}."))

    # 2. Emirden yeniden hesap
    e = emir_sagla(kapali, kayit["emirler"])
    if not kapali:
        denetimler.append(_denetim("emir", "Emirden yeniden hesap", "belirsiz", "Kapalı işlem yok."))
    else:
        kapsama = e["kapsama"] or 0.0
        if e["sapan"]:
            durum = "hata"
        elif kapsama < KAPSAMA_ASGARI:
            durum = "belirsiz"
        elif abs(e["toplam_fark"]) > max(TOPLAM_TOLERANS, 0.001 * abs(toplam)):
            durum = "hata"
        else:
            durum = "ok"
        ozet = (f"{e['toplam_islem']} işlemin {e['kontrol_edilen']} tanesi (%{_sayi(kapsama * 100, 0)}) emir "
                f"kayıtlarından baştan hesaplandı; {e['sapan']} tanesi kayıtlı kârdan sapıyor. Toplam fark "
                f"{_sayi(e['toplam_fark'], 4, True)} USDT.")
        ayrinti = [f"#{r['kimlik']} {r['parite']}: kayıtlı {_sayi(r['kayitli'], 4, True)}, hesap "
                   f"{_sayi(r['hesap'], 4, True)}" for r in e["en_kotu"]]
        ayrinti += [f"{n}: {c} işlem" for n, c in e["kontrol_edilemeyen_nedenler"].items()]
        denetimler.append(_denetim("emir", "Emirden yeniden hesap", durum, ozet, ayrinti))

    # 3. Mantık
    m = mantik_denetimi(kapali)
    denetimler.append(_denetim(
        "mantik", "Mantık denetimi", "ok" if m["sorun_sayisi"] == 0 and kapali else ("belirsiz" if not kapali else "hata"),
        (f"{m['bakilan']} işlem tarandı; {m['sorun_sayisi']} çelişki bulundu." if kapali else "Kapalı işlem yok."),
        [f"#{k}: {a}" for k, a in m["sorunlar"]]))

    # 4. Yoğunlaşma
    y = yogunlasma(kapali)
    if y["islem"] == 0:
        denetimler.append(_denetim("yogun", "Kâr birkaç işleme mi bağlı?", "belirsiz", "Kapalı işlem yok."))
    else:
        kalan = y["en_iyiden_sonra"]
        if y["islem"] <= EN_IYI_N:
            durum, not_ = "belirsiz", "İşlem sayısı bu denetim için çok az."
        elif y["toplam"] > 0 and kalan <= 0:
            durum, not_ = "uyari", "En iyi işlemler çıkınca kâr sıfırın altına iniyor: sonuç birkaç şansa bağlı."
        elif y["toplam"] <= 0:
            durum, not_ = "ok", "Toplam zaten kârda değil; bu denetimin bulacağı bir şişirme yok."
        else:
            durum, not_ = "ok", "En iyi işlemler çıkınca bile kâr sürüyor."
        denetimler.append(_denetim(
            "yogun", "Kâr birkaç işleme mi bağlı?", durum,
            f"{y['islem']} işlemin {y['kazanan']} tanesi kârda. Toplam {_sayi(y['toplam'], 2, True)}; en iyi "
            f"{y['en_iyi_n']} işlem {_sayi(y['en_iyi_toplam'], 2, True)} getirmiş, onlar çıkınca "
            f"{_sayi(kalan, 2, True)} kalıyor. {not_}"))

    # 5. Fiyat gerçekliği (istek üzerine)
    if mum_fn is not None:
        f = fiyat_gercekligi(kapali, piyasa, mum_fn)
        toplam_olcum = f["icinde"] + f.get("disinda_sayi", 0)
        if toplam_olcum == 0:
            durum = "belirsiz"
        elif f.get("disinda_sayi", 0):
            durum = "hata"
        elif f["alinamayan"]:
            durum = "belirsiz"
        else:
            durum = "ok"
        denetimler.append(_denetim(
            "fiyat", "Fiyatlar piyasada gerçekten vardı", durum,
            f"{f['ornek']} örnek işlemin giriş ve çıkış fiyatı o dakikanın Binance mumuyla karşılaştırıldı: "
            f"{f['icinde']} tanesi mum aralığında, {f.get('disinda_sayi', 0)} tanesi dışında, "
            f"{f['alinamayan']} tanesi için mum alınamadı.",
            [f"#{r['kimlik']} {r['parite']} {r['taraf']} fiyatı {r['fiyat']} mum aralığı {r['dip']}–{r['tepe']}"
             for r in f["disinda"]]))
    return {"bot": bot, "hata": None, "denetimler": denetimler, "kapali": len(kapali), "toplam": toplam,
            "acik": sum(1 for s in kayit["islemler"] if s.get("is_open"))}


def genel(veri_klasoru: Path, sayfa_ozeti: dict | None = None, mum_fn=None, simdi: datetime | None = None) -> dict:
    """Bütün botların sağlaması. `sayfa_ozeti`: sonuc.genel_ozet çıktısı (verilirse toplam sağlaması yapılır)."""
    simdi = simdi or datetime.now(timezone.utc)
    donem = donem_bilgisi(simdi, zaman_dosyasi_oku(veri_klasoru / "isinma_baslangici.txt"),
                          zaman_dosyasi_oku(veri_klasoru / "sinav_baslangici.txt"))
    sayfadaki = {b["bot"]: float(b["net_tutar"]) for b in (sayfa_ozeti or {}).get("botlar", [])}
    botlar = []
    for bot, _sinif, _kod, piyasa in BOTLAR:
        kayit = _kayit_oku(veri_klasoru / "db" / f"{bot}.sqlite")
        botlar.append(bot_sagla(bot, piyasa, kayit, donem["baslangic"], donem["bitis"], sayfadaki.get(bot), mum_fn))
    durumlar = [d["durum"] for b in botlar for d in b["denetimler"] if d["kimlik"] != "yogun"]
    if any(b["hata"] for b in botlar) or "hata" in durumlar:
        hukum = "hata"
    elif "belirsiz" in durumlar or not durumlar:
        hukum = "belirsiz"
    else:
        hukum = "ok"
    return {"uretildi": simdi, "donem": donem, "botlar": botlar, "hukum": hukum,
            "toplam_kar": sum(b["toplam"] for b in botlar), "toplam_islem": sum(b["kapali"] for b in botlar),
            "mum_denendi": mum_fn is not None}


# ---------------------------------------------------------------------------------------------- biçim

BICIM = """
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;background:#04070d;color:#e6edf5;font:15px/1.5 system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:12px 14px 40px}
h1{font-size:22px;margin:.6em 0 .2em}h2{font-size:17px;margin:1.4em 0 .4em}
.soluk{color:#8fa1b3}.kutu{border:1px solid #1c2733;border-radius:12px;padding:12px 14px;margin:10px 0;background:#0a1019}
.hukum{font-size:18px;font-weight:600;border-radius:12px;padding:14px;margin:12px 0;border:2px solid}
.hukum.ok{border-color:#3fb950;background:#0d2214}.hukum.hata{border-color:#f85149;background:#2a0f10}
.hukum.belirsiz{border-color:#f2c94c;background:#2a2410}
.rozet{display:inline-block;min-width:78px;text-align:center;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700;margin-right:8px;color:#04070d}
.rozet.ok{background:#3fb950}.rozet.hata{background:#f85149}.rozet.belirsiz{background:#f2c94c}.rozet.uyari{background:#ff9f43}
ul{margin:.3em 0 .3em 1.1em;padding:0;color:#b7c4d1;font-size:13px}
.denetim{margin:8px 0}a{color:#6cb6ff}
button,a.dugme{display:inline-block;padding:10px 16px;border-radius:10px;border:1px solid #f2c94c;background:#f2c94c;color:#04070d;font:600 14px system-ui;text-decoration:none}
"""

HUKUM_METNI = {
    "ok": "Defter kendi içinde tutarlı: kayıtlı kâr, emirlerden baştan hesaplanan kârla ve sayfadaki toplamla uyuşuyor.",
    "hata": "Tutarsızlık bulundu: aşağıdaki kırmızı satırlara bak. Rakama güvenme, önce nedenini anlayalım.",
    "belirsiz": "Bazı denetimler yapılamadı ya da veri yetmedi. Yeşil denmedi; aşağıda hangisi ve neden yazıyor.",
}


def guvenlik_basligi() -> str:
    return "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"


def sayfa_uret(sonuc: dict) -> str:
    uretildi = sonuc["uretildi"].strftime("%d.%m.%Y %H:%M UTC")
    govde = ['<p><a href="/#sonuc">&larr; Pano</a></p>', "<h1>Sağlama: kâr gerçek mi?</h1>",
             '<p class="soluk">Bu sayfa kâr rakamını sayfanın kendi hesabına güvenmeden, kayıt dosyalarından ayrı bir '
             "yoldan baştan hesaplar; matematikteki sağlama gibi. Hiçbir şey yazmaz, hiçbir bota dokunmaz.</p>",
             f'<div class="hukum {sonuc["hukum"]}">{DURUM_ADI[sonuc["hukum"]]}: {escape(HUKUM_METNI[sonuc["hukum"]])}</div>',
             f'<p>Kayıtlı toplam: <b>{_sayi(sonuc["toplam_kar"], 2, True)} USDT</b>, {sonuc["toplam_islem"]} kapalı '
             f'işlem. <span class="soluk">Hesap anı {uretildi}.</span></p>']
    if not sonuc["mum_denendi"]:
        govde.append('<p><a class="dugme" href="/sagla?mum=1">Fiyatları Binance mumlarıyla da sına</a> '
                     '<span class="soluk">(yarım dakika sürebilir)</span></p>')
    for b in sonuc["botlar"]:
        govde.append(f'<h2>{escape(b["bot"])}</h2>')
        if b["hata"]:
            govde.append(f'<div class="kutu"><span class="rozet hata">TUTMADI</span>{escape(b["hata"])}</div>')
            continue
        govde.append(f'<p class="soluk">{b["kapali"]} kapalı işlem, kayıtlı net {_sayi(b["toplam"], 2, True)} USDT, '
                     f'{b["acik"]} açık pozisyon (açıklar toplama girmez).</p>')
        for d in b["denetimler"]:
            ayr = ("<ul>" + "".join(f"<li>{escape(str(a))}</li>" for a in d["ayrinti"]) + "</ul>") if d["ayrinti"] else ""
            govde.append(f'<div class="kutu denetim"><span class="rozet {d["durum"]}">{DURUM_ADI[d["durum"]]}</span>'
                         f'<b>{escape(d["ad"])}</b><div>{escape(d["ozet"])}</div>{ayr}</div>')
    govde.append(
        '<h2>Bu sayfa neyi kanıtlar, neyi kanıtlamaz?</h2><div class="kutu"><p><b>Kanıtlar:</b> sayfadaki kâr rakamı '
        "kayıt dosyalarıyla ve işlemlerin kendi emir kayıtlarıyla çelişmiyor; saçma ya da çift kayıt yok; "
        "(fiyat sınaması açıksa) örnek fiyatlar piyasada gerçekten görülmüş.</p><p><b>Kanıtlamaz:</b> bu işlemlerin "
        "gerçek parayla aynı kârı getireceğini. Sanal emirler (dry-run) gerçek bir borsa kuyruğuna girmez; kayma, "
        "derinlik, reddedilme ve gecikme yaşamaz. Gerçek hesapta sonuç genelde daha kötüdür. Bu yüzden sayfa "
        '"defter doğru" der, "kâr garanti" demez.</p></div>')
    bas = ('<!doctype html><html lang="tr"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width, initial-scale=1">'
           '<meta name="robots" content="noindex"><title>Sağlama</title>'
           f'<style>{BICIM}</style></head><body>' + site_gezinti.serit("sagla") + "<main>")
    return bas + "".join(govde) + "</main></body></html>"


_ONBELLEK: dict = {}


def mum_sonucu_onbellekli(uret, sure: float = 3600.0):
    """Mumlu sağlama pahalıdır (ağ); sonucu bir saat saklar."""
    simdi = time.time()
    if _ONBELLEK.get("an", 0) + sure > simdi and "deger" in _ONBELLEK:
        return _ONBELLEK["deger"]
    deger = uret()
    _ONBELLEK.update({"an": simdi, "deger": deger})
    return deger
