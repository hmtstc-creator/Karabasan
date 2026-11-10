"""Likidite ekranı: coin başına fonlama, açık faiz, spread, hacim ve kaba sıkışma riski.

Veri karabasan/sonuc_likidite.py'den gelir (ozet["ek"]["likidite"]). Betik yok; yalnız HTML ve CSS.
"""

from __future__ import annotations

from html import escape

from . import sayfa as s

STIL = """
.likidite-durum{margin:0 0 14px}
.likidite-ust{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px}
.likidite-ust h3{margin:0}
.likidite-rozet{display:inline-block;padding:3px 10px;border-radius:999px;font:600 .8125rem/1.4 var(--govde);
border:1px solid var(--cizgi);white-space:nowrap}
.likidite-rozet.yuksek{color:var(--eksi);border-color:var(--eksi)}
.likidite-rozet.orta{color:var(--uyari);border-color:var(--uyari)}
.likidite-rozet.dusuk{color:var(--arti);border-color:var(--arti)}
.likidite-rozet.veri_yok{color:var(--soluk)}
.likidite-acik{color:var(--altin);font-size:.8125rem;font-weight:600}
.kart.likidite-acik-kart{border-color:var(--altin)}
.likidite-olcu{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0;margin:12px 0 0;
border-top:1px solid var(--cizgi)}
.likidite-olcu div{padding:9px 8px 8px 0;min-width:0;border-bottom:1px solid var(--cizgi)}
.likidite-olcu dt{color:var(--soluk);font-size:.75rem}
.likidite-olcu dd{margin:0;font:700 1.0625rem/1.3 var(--rakam);overflow-wrap:anywhere}
.likidite-olcu dd .alt{font-family:var(--govde);font-size:.75rem;font-weight:400}
.likidite-neden{margin:10px 0 0;padding-left:18px;font-size:.875rem}
.likidite-neden li{margin:2px 0}
.likidite-eylem{margin:10px 0 0;font-size:.875rem}
.likidite-sozluk{margin:0;padding:0;list-style:none;font-size:.875rem}
.likidite-sozluk li{margin:6px 0}
.likidite-baglanti{display:inline-flex;align-items:center;min-height:44px}
"""

ETIKET = {"yuksek": ("▲", "yüksek"), "orta": ("●", "orta"), "dusuk": ("▼", "düşük"), "veri_yok": ("–", "veri yok")}
ETIKET_EYLEMI = {
    "yuksek": "Bu coinde açığa satış pozisyonu varsa yakından izle ve Claude'a sor; ayar değiştirme.",
    "orta": "İzle; durum kötüleşirse (fonlama daha eksi, açık faiz daha hızlı artış) Claude'a sor.",
    "dusuk": "Şu an ek bir şey yapmana gerek yok.",
    "veri_yok": "Etiket için yeterli ölçü yok; karar verirken bu coine güvenme.",
}


def _yas(dakika) -> str:
    if dakika is None:
        return "zamanı bilinmiyor"
    if dakika < 1:
        return "az önce"
    return s._sure(dakika) + " önce"


def _deger(grup_veri, hata, metin_uret, ag_acik: bool) -> str:
    """Bir ölçünün hücresi: değer (yaşıyla), ya da 'alınamadı' / 'veri yok'."""
    if grup_veri is None:
        if not ag_acik:
            return '<span class="notr">canlı sayfada</span>'
        if hata:
            return f'<span class="uyari">alınamadı</span><span class="alt">{escape(str(hata))}</span>'
        return '<span class="notr">veri yok</span>'
    metin = metin_uret(grup_veri)
    ek = ""
    if grup_veri.get("eski"):
        ek = f'<span class="alt uyari">eski: {_yas(grup_veri.get("yas_dakika"))}; etikete katılmadı</span>'
    elif hata:
        ek = f'<span class="alt uyari">son deneme alınamadı; değer {_yas(grup_veri.get("yas_dakika"))}</span>'
    return metin + ek


def _fonlama(v) -> str:
    oran = v.get("oran_yuzde")
    if oran is None:
        return "–"
    if oran < 0:
        anlam = "short öder"
        sinif = "eksi"
    elif oran > 0:
        anlam = "short alır"
        sinif = "arti"
    else:
        anlam, sinif = "sıfır", "notr"
    return (f'<span class="{sinif}">{s.isaretli_yuzde(oran, 4)}</span>'
            f'<span class="alt">{anlam} (dönem başına)</span>')


def _acik_faiz(v) -> str:
    d = (v.get("degisim") or {})
    d24 = d.get("24s")
    usdt = v.get("usdt")
    ana = (f'<span class="{s._isaret_sinifi(d24)}">{s.isaretli_yuzde(d24, 1)}</span>' if d24 is not None
           else '<span class="notr">–</span>')
    parca = [f"1 sa {s.isaretli_yuzde(d.get('1s'), 1)}", f"4 sa {s.isaretli_yuzde(d.get('4s'), 1)}"]
    if usdt is not None:
        parca.append(f"toplam {s.sayi(usdt / 1e6, 1)} milyon USDT")
    return ana + f'<span class="alt">24 saatte · {" · ".join(parca)}</span>'


def _spread(v) -> str:
    bps = v.get("spread_bps")
    return f'{s.sayi(bps, 1)} bps<span class="alt">on binde; büyükse piyasa ince</span>' if bps is not None else "–"


def _hacim(v) -> str:
    h, f = v.get("hacim_usdt"), v.get("fiyat_degisim_yuzde")
    fiyat = f" · fiyat {s.isaretli_yuzde(f, 1)}" if f is not None else ""
    return f'{s.sayi(h / 1e6, 1)} milyon USDT<span class="alt">son 24 saat{fiyat}</span>' if h is not None else "–"


def _coin_karti(c: dict, ag_acik: bool) -> str:
    risk = c.get("risk") or {"etiket": "veri_yok", "nedenler": [], "eksik": []}
    etiket = risk.get("etiket") if risk.get("etiket") in ETIKET else "veri_yok"
    simge, ad = ETIKET[etiket] if ag_acik else ("–", "veri yok")
    acik = ""
    if c.get("acik"):
        botlar = ", ".join(escape(str(b)) for b in c.get("acik_botlar") or [])
        acik = f'<span class="likidite-acik">● açık pozisyon{": " + botlar if botlar else ""}</span>'
    islem = c.get("islem_sayisi") or 0
    alt = f"Dönemde {islem} kapanmış işlem" if islem else "Dönemde kapanmış işlem yok"
    hucreler = "".join(
        f"<div><dt>{baslik}</dt><dd>{_deger(c.get(g), c.get(g + '_hata'), uret, ag_acik)}</dd></div>"
        for baslik, g, uret in (("Fonlama", "fonlama", _fonlama), ("Açık faiz değişimi", "acik_faiz", _acik_faiz),
                                ("Spread", "spread", _spread), ("Hacim", "hacim", _hacim)))
    if ag_acik:
        nedenler = "".join(
            f'<li>{escape(n["metin"])} <span class="alt" style="display:inline">({n["puan"]} puan)</span></li>'
            for n in risk.get("nedenler") or [])
        eksik = risk.get("eksik") or []
        if eksik:
            from .sonuc_likidite import GRUP_ADI  # yalnız ad tablosu; ağa çıkmaz
            nedenler += f'<li class="notr">Eksik ölçü: {escape(", ".join(GRUP_ADI.get(e, e) for e in eksik))}</li>'
        govde = (f'<ul class="likidite-neden">{nedenler}</ul>' if nedenler else "")
        govde += f'<p class="likidite-eylem"><strong>Ne yapmalı:</strong> {ETIKET_EYLEMI[etiket]}</p>'
    else:
        govde = ""
    sinif = "kose kart likidite-acik-kart" if c.get("acik") else "kose kart"
    return f"""<div class="{sinif}">
<div class="likidite-ust"><h3>{escape(str(c.get("parite") or c.get("sembol")))}</h3>
<span class="likidite-rozet {etiket if ag_acik else 'veri_yok'}">{simge} sıkışma riski: {ad}</span></div>
<p class="alt">{acik + " · " if acik else ""}{alt}</p>
<dl class="likidite-olcu">{hucreler}</dl>
{govde}</div>"""


def _defter_karti(d: dict, saat_dilimi: str) -> str:
    bag = '<a class="likidite-baglanti" href="/defter">Emir defteri sayfasını aç</a>'
    if not d.get("var"):
        return (f'<div class="kose kart"><h3>BTC emir defteri dengesi</h3>'
                f'<p class="bos">Kayıt yok. Bu ölçü yalnız defter servisi çalışırken dolar.</p>{bag}</div>')
    den = d.get("dengesizlik_20")
    bayat = (f'<p class="g-not uyari">Kayıt {_yas((d.get("yas_saniye") or 0) / 60)} durmuş; defter servisi '
             "çalışmıyor olabilir.</p>") if d.get("bayat") else ""
    if den is None:
        yorum = "Değer okunamadı."
    elif den <= -0.2:
        yorum = "Satış tarafı ağır: açığa satan için kısa vadede rüzgâr arkada."
    elif den >= 0.2:
        yorum = "Alış tarafı ağır: fiyatı yukarı itebilir; açığa satan için kötü yön."
    else:
        yorum = "Belirgin bir ağırlık yok."
    return f"""<div class="kose kart"><h3>BTC emir defteri dengesi</h3>
<p class="alt">Emir defteri: bekleyen alış ve satış emirlerinin listesi. Denge −1 (hepsi satış) ile +1 (hepsi alış) arasıdır.</p>
<dl class="likidite-olcu">
<div><dt>İlk 20 kademe</dt><dd class="{s._isaret_sinifi(den)}">{s.isaretli(den, 2)}</dd></div>
<div><dt>Spread</dt><dd>{s.sayi(d.get("makas_bps"), 2)} bps<span class="alt">{s._tarih_saat(d.get("zaman"), saat_dilimi)}</span></dd></div>
</dl>
<p class="likidite-eylem">{yorum} Saniyelik bir ölçüdür; tek başına karar verdirmez, yalnız izle.</p>{bayat}{bag}</div>"""


def ekran(ozet: dict, saat_dilimi: str) -> str:
    v = (ozet.get("ek") or {}).get("likidite") or {}
    ag_acik = bool(v.get("ag_acik"))
    durum = v.get("durum")
    coinler = v.get("coinler") or []
    if durum == "kapali":
        serit = ('<p class="bos likidite-durum">Bu bölüm yalnız canlı sayfada dolar (fonlama, açık faiz, spread ve hacim '
                 "Binance'ten canlı alınır). Aşağıda coin listesi ve yerel defter kaydı var.</p>")
    elif durum == "bekliyor":
        serit = '<p class="bos likidite-durum">Veri ilk kez isteniyor; bir dakika içinde sayfayı yenile.</p>'
    elif durum == "hata":
        serit = (f'<p class="uyari-serit likidite-durum">Binance\'ten veri alınamadı. Yeniden deneme '
                 f'{s._sure(v.get("sonraki_deneme_dakika") or 5)} sonra. Botlar bundan etkilenmez.</p>')
    else:
        hatalar = v.get("genel_hatalar") or {}
        ek = (f' <span class="uyari">Son turda alınamayan: {escape(", ".join(sorted(hatalar)))}.</span>'
              if hatalar else "")
        serit = (f'<p class="g-not likidite-durum">Son başarılı güncelleme {_yas(v.get("yas_dakika"))}; '
                 f"5 dakikada bir yenilenir.{ek}</p>")
    sayilar = {k: sum(1 for c in coinler if (c.get("risk") or {}).get("etiket") == k) for k in ETIKET}
    if ag_acik and durum == "hazir":
        ozet_metni = (f"{len(coinler)} coin · ▲ yüksek {sayilar['yuksek']} · ● orta {sayilar['orta']} · "
                      f"▼ düşük {sayilar['dusuk']}")
    else:
        ozet_metni = f"{len(coinler)} coin izleniyor; açık pozisyonu olanlar önde"
    if ag_acik:
        kartlar = "\n".join(_coin_karti(c, ag_acik) for c in coinler) or '<p class="bos">Henüz izlenecek coin yok.</p>'
    else:
        satirlar = "".join(
            f'<li><strong>{escape(str(c.get("parite") or c.get("sembol")))}</strong>'
            + (f' <span class="likidite-acik">● açık pozisyon: {escape(", ".join(map(str, c.get("acik_botlar") or [])))}</span>'
               if c.get("acik") else "")
            + f' <span class="alt" style="display:inline">· dönemde {c.get("islem_sayisi") or 0} işlem</span></li>'
            for c in coinler)
        kartlar = (f'<div class="kose kart"><h3>İzlenen coinler</h3><p class="alt">Ölçüler canlı sayfada dolar.</p>'
                   f'<ul class="likidite-sozluk">{satirlar}</ul></div>')
    e = v.get("esikler") or {}
    esik = ""
    if e:
        esik = (f"Fonlama ≤ {s.isaretli_yuzde(e.get('fonlama_eksi_orta'), 2)} (1 puan), ≤ "
                f"{s.isaretli_yuzde(e.get('fonlama_eksi_yuksek'), 2)} (2 puan); açık faiz 24 saatte ≥ "
                f"{s.isaretli_yuzde(e.get('af_artis_orta'), 0)} (1), ≥ {s.isaretli_yuzde(e.get('af_artis_yuksek'), 0)} (2); "
                f"fiyat 24 saatte ≥ {s.isaretli_yuzde(e.get('fiyat_artis'), 0)} (1); incelik: spread ≥ "
                f"{s.sayi(e.get('spread_ince'), 0)} bps ya da hacim &lt; {s.sayi((e.get('hacim_ince') or 0) / 1e6, 0)} milyon "
                f"USDT (1), spread ≥ {s.sayi(e.get('spread_cok_ince'), 0)} bps ya da hacim &lt; "
                f"{s.sayi((e.get('hacim_cok_ince') or 0) / 1e6, 0)} milyon (2). Toplam ≥ {e.get('orta_puan')}: orta, ≥ "
                f"{e.get('yuksek_puan')}: yüksek. {v.get('kullanim_siniri_dakika', 30)} dakikadan eski değer katılmaz.")
    return f"""<section id="likidite" class="ekran">
<h2 class="ekran-baslik">Likidite</h2>
<p class="ekran-ozet">{escape(ozet_metni)}</p>
<p class="g-not">Botlar açığa satış (short) yapar. Asıl tehlike <strong>açığa satış sıkışması</strong>dır: fiyat yükselince
açığa satanların zorla kapanması fiyatı daha da yükseltir. Bu ekran hangi coinde bu riskin arttığını ve hangi coinin
ince (az alıcı-satıcılı) olduğunu kaba biçimde gösterir.</p>
{serit}
<div class="g-kartlar">
{kartlar}
{_defter_karti(v.get("defter") or {}, saat_dilimi)}
<div class="kose kart"><h3>Tasfiye kümeleri</h3>
<p class="alt">Tasfiye: borsanın teminatı yetmeyen pozisyonu zorla kapatması. Kümeler, çok pozisyonun aynı fiyatta kapanacağı yerlerdir.</p>
<p class="bos">Veri yok. Binance bunu anahtarsız, herkese açık bir adreste toplu vermiyor; tahmin uydurulmadı.</p></div>
</div>
<details class="kose kart" style="margin-top:16px"><summary class="likidite-baglanti">Ölçüler ne demek, etiket nasıl çıkıyor</summary>
<ul class="likidite-sozluk">
<li><strong>Fonlama</strong>: vadeli fiyatı spota bağlamak için iki taraf arasında (çoğunlukla 8 saatte bir) ödenen ücret.
Artıysa açığa satan alır; eksiyse açığa satan öder ve kalabalık açığa satıştadır (sıkışmaya yakıt).</li>
<li><strong>Açık faiz</strong>: kapanmamış bütün vadeli pozisyonların toplamı. Hızla artıyorsa kaldıraçlı pozisyon birikiyor.</li>
<li><strong>Spread</strong>: en iyi alış ile en iyi satış arasındaki fark, on binde (bps). Genişse piyasa incedir.</li>
<li><strong>Hacim</strong>: son 24 saatte el değiştiren tutar. Düşükse küçük bir alım bile fiyatı sıçratabilir.</li>
<li><strong>Eşikler</strong>: {esik or "–"}</li>
<li class="uyari"><strong>Bu eşikler sınanmadı, kaba bir uyarıdır.</strong> Geçmiş veriyle doğrulanmadı; etiket bir tahmin değil,
bakılacak yeri gösterir. Ayar değiştirmek için kullanma; sınav sonu kararında dikkate al.</li>
</ul></details>
</section>"""
