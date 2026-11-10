"""Rejim ekranı: Karabasan piyasa ortamı motoru için elde olan ne varsa.

Bu ekran bilerek "canlı puan kaydı yok" diye başlar: puan, durum ve vetolar canlıda hiçbir yerde
hesaplanıp kaydedilmiyor (karabasan/sonuc_rejim.py başındaki nota bak). Sonra kuralları, küresel
kaydı (dominans, TOTAL2), işlem kaydından yeniden kurulan art arda stop pencerelerini ve geçmiş
ölçüm raporunun durumunu gösterir. Betik yok; yalnız satır içi SVG ve <details>.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from . import sayfa as s

DURUM_SINIFI = {"YESIL": "arti", "SARI": "uyari", "KIRMIZI": "eksi", "SIYAH": "notr"}
DURUM_SIMGESI = {"YESIL": "▲", "SARI": "●", "KIRMIZI": "▼", "SIYAH": "■"}
KAYIT_ETIKETI = {"var": ("arti", "✓ canlı veri var"), "kismen": ("uyari", "◐ yalnız ham girdi kaydı"),
                 "yok": ("eksi", "✕ canlı veri yok")}

STIL = """
.rejim-kutu{margin:0 0 16px;padding:18px 18px;border-radius:var(--r-buyuk,20px);border:1px solid rgba(255,159,67,.35);
border-left:4px solid var(--uyari);background:rgba(255,159,67,.08)}
.rejim-kutu h3{margin:0 0 6px;font-size:1.25rem;color:var(--buz)}
.rejim-kutu p{margin:6px 0 0;color:var(--buz);max-width:68ch;font-size:.9375rem}
.rejim-kutu .alt{margin-top:8px}
.rejim-liste{list-style:none;margin:10px 0 0;padding:0;display:grid;gap:8px}
.rejim-liste li{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;padding:10px 0;
border-top:1px solid var(--cizgi);min-height:44px;align-items:baseline}
.rejim-liste li:first-child{border-top:0}
.rejim-ad{font-weight:600;flex:1 1 12ch}
.rejim-deger{font:650 1rem var(--rakam);text-align:right}
.rejim-liste .alt{flex-basis:100%}
.rejim-rozet{display:inline-block;padding:2px 9px;border-radius:999px;border:1px solid currentColor;font-size:.75rem;
font-weight:600;white-space:nowrap}
.rejim-sayilar{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0 0}
.rejim-sayilar div{padding:10px 12px;border:1px solid var(--cizgi);border-radius:var(--r-orta,12px);background:var(--yuzey)}
.rejim-sayilar dt{color:var(--soluk);font-size:.75rem}
.rejim-sayilar dd{margin:2px 0 0;font:650 1.125rem/1.25 var(--rakam)}
.rejim-sayilar dd .alt{font-family:var(--govde);font-size:.75rem}
.rejim-svg text{font:600 12px var(--govde)}
.rejim-dilim-ad{fill:var(--gece)}
.rejim-dilim-dis{fill:var(--buz)}
.rejim-verisiz{fill-opacity:.55;stroke:var(--buz);stroke-width:1.5;stroke-dasharray:4 3}
.rejim-arti{fill:var(--arti)}.rejim-uyari{fill:var(--altin)}.rejim-eksi{fill:var(--eksi)}.rejim-notr{fill:var(--soluk)}
.rejim-cizgi{fill:none;stroke:var(--holo);stroke-width:2;stroke-linejoin:round;vector-effect:non-scaling-stroke}
.rejim-bosluk{fill:var(--uyari);opacity:.18}
@media (min-width:900px){.rejim-sayilar{grid-template-columns:repeat(4,1fr)}}
"""


def _zaman(deger):
    if isinstance(deger, datetime):
        return deger if deger.tzinfo else deger.replace(tzinfo=timezone.utc)
    if isinstance(deger, str):
        try:
            z = datetime.fromisoformat(deger.replace("Z", "+00:00"))
            return z if z.tzinfo else z.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _durum(kod: str, adlar: dict) -> str:
    return (f'<span class="{DURUM_SINIFI.get(kod, "notr")}">{DURUM_SIMGESI.get(kod, "")} '
            f'{escape(adlar.get(kod, kod))}</span>')


# --------------------------------------------------------------------------
# Kurallar
# --------------------------------------------------------------------------


def _bilesen_grafigi(bilesenler: list) -> str:
    """Puanın beş bileşeni tek bir 100'lük şeritte; dilim genişliği ağırlık."""
    g, h, x = 360.0, 54.0, 0.0
    toplam = sum(b["agirlik_yuzde"] for b in bilesenler) or 1.0
    parca = []
    for k, b in enumerate(bilesenler):
        w = b["agirlik_yuzde"] / toplam * g
        renk = s.SERI_RENKLERI[k % len(s.SERI_RENKLERI)]
        ipucu = f'{b["ad"]}: ağırlık %{s.sayi(b["agirlik_yuzde"], 0)}; {KAYIT_ETIKETI[b["kayit"]][1]}'
        parca.append(f'<rect x="{x + 1:.1f}" y="4" width="{max(w - 2, 1):.1f}" height="{h - 8:g}" rx="6" '
                     f'style="fill:{renk}"><title>{escape(ipucu)}</title></rect>')
        if b["kayit"] != "var":  # canlı verisi olmayan dilim kesik çerçeveli ve soluk (renge ek işaret)
            parca[-1] = parca[-1].replace('rx="6" ', 'rx="6" class="rejim-verisiz" ', 1)
        parca.append(f'<text class="rejim-dilim-ad" x="{x + w / 2:.1f}" y="{h / 2:.1f}" text-anchor="middle" '
                     f'dominant-baseline="middle">{escape(b["kod"])} {s.sayi(b["agirlik_yuzde"], 0)}</text>')
        x += w
    return (f'<svg class="g-svg rejim-svg" viewBox="0 0 {g:g} {h:g}" role="img" '
            f'aria-label="Puanın bileşenleri ve ağırlıkları">{"".join(parca)}</svg>')


def _esik_grafigi(k: dict) -> str:
    """0–100 cetveli: Kırmızı / Sarı / Yeşil bölgeleri; Siyah puanla değil vetoyla gelir."""
    g, h, sol, sag = 360.0, 64.0, 6.0, 6.0
    ad = k["durum_adi"]

    def x(v):
        return sol + v / 100.0 * (g - sol - sag)

    bolgeler = [(0.0, k["esik_sari"], "KIRMIZI"), (k["esik_sari"], k["esik_yesil"], "SARI"),
                (k["esik_yesil"], 100.0, "YESIL")]
    parca = []
    for a, b, kod in bolgeler:
        parca.append(f'<rect class="rejim-{DURUM_SINIFI[kod]}" x="{x(a):.1f}" y="6" width="{x(b) - x(a):.1f}" '
                     f'height="24" rx="4"><title>{escape(ad.get(kod, kod))}: puan {s.sayi(a, 0)}–{s.sayi(b, 0)}'
                     f'</title></rect><text class="rejim-dilim-ad" x="{(x(a) + x(b)) / 2:.1f}" y="18" '
                     f'text-anchor="middle" dominant-baseline="middle">{DURUM_SIMGESI[kod]} {escape(ad.get(kod, kod))}</text>')
    for v in (0.0, k["esik_sari"], k["esik_yesil"], 100.0):
        parca.append(f'<text class="g-eksen" x="{x(v):.1f}" y="50" text-anchor="middle">{s.sayi(v, 0)}</text>')
    return (f'<svg class="g-svg rejim-svg" viewBox="0 0 {g:g} {h:g}" role="img" '
            f'aria-label="Durum eşikleri: {s.sayi(k["esik_sari"], 0)} ve {s.sayi(k["esik_yesil"], 0)}">'
            f'{"".join(parca)}</svg>')


def _veto_satirlari(k: dict, stop_var: bool) -> list[tuple[str, str, str, str]]:
    """(kural, eşik, veri durumu sınıfı, veri durumu metni)."""
    e = k["veto_esikleri"]

    def sy(ad, b=1):
        return s.sayi(e.get(ad), b) if e.get(ad) is not None else "–"

    yok = ("eksi", "✕ veri yok")
    return [
        ("BTC ani düşüş", f'15 dakikada %{sy("btc_15dk_dusus_yuzde")} ya da 1 saatte %{sy("btc_1s_dusus_yuzde")} '
                          f'düşüş → {sy("btc_veto_dakika", 0)} dakika Siyah', *yok),
        ("Art arda stop", f'{sy("art_arda_stop", 0)} stop üst üste → {sy("art_arda_stop_dakika", 0)} dakika Siyah',
         *(("uyari", "◐ işlem kaydından yeniden kuruldu") if stop_var else yok)),
        ("Bayat fiyat verisi", f'{sy("veri_bayat_saniye", 0)} saniyeden eski veri → düzelene kadar Siyah', *yok),
        ("USDT sabitten sapma", f'%{sy("sabit_coin_sapma_yuzde")} sapma → düzelene kadar Siyah', *yok),
        ("NASDAQ düşüşü", f'Seans içinde %{sy("nasdaq_dusus_yuzde")} düşüş → Siyah', *yok),
        ("Ekonomik veri saati", f'Açıklamadan {sy("takvim_once_dakika", 0)} dakika önce, '
                                f'{sy("takvim_sonra_dakika", 0)} dakika sonrasına kadar Siyah', *yok),
        ("Günlük zarar limiti / acil stop", "Gün sonuna kadar / elle kaldırılana kadar Siyah", *yok),
    ]


def _kurallar(r: dict) -> str:
    k = r.get("kurallar")
    if not k:
        return ('<div class="kose kart"><h3>Kurallar</h3><p class="bos">Veri yok: kural dosyası (puan.py) '
                "okunamadı. Claude'a sor.</p></div>")
    bilesen = "".join(
        f'<li><span class="rejim-ad"><i class="rejim-rozet" style="color:{s.SERI_RENKLERI[i % len(s.SERI_RENKLERI)]};'
        f'border-color:currentColor">{escape(b["kod"])}</i> {escape(b["ad"])}</span>'
        f'<span class="rejim-deger">%{s.sayi(b["agirlik_yuzde"], 0)}</span>'
        f'<span class="alt"><span class="{KAYIT_ETIKETI[b["kayit"]][0]}">{KAYIT_ETIKETI[b["kayit"]][1]}</span> · '
        f'{escape(b["aciklama"])}</span></li>'
        for i, b in enumerate(k["bilesenler"]))
    stop_var = r.get("art_arda_stop") is not None
    veto = "".join(
        f'<li><span class="rejim-ad">{escape(ad)}</span><span class="rejim-deger {sinif}">{escape(durum)}</span>'
        f'<span class="alt">{escape(esik)}</span></li>' for ad, esik, sinif, durum in _veto_satirlari(k, stop_var))
    adlar = k["durum_adi"]
    botlar = r.get("botlar") or []
    if botlar:
        bot_satir = "".join(
            f'<li><span class="rejim-ad">{escape(str(b.get("ad") or b.get("kod") or "?"))}</span>'
            f'<span class="rejim-deger">'
            + (", ".join(_durum(d, adlar) for d in b["izinli_durumlar"]) or '<span class="notr">belirtilmemiş</span>')
            + "</span></li>" for b in botlar)
    else:
        bot_satir = '<li><span class="alt">Bot yok.</span></li>'
    return f"""<div class="kose kart"><h3>Puanın bileşenleri</h3>
<p class="alt">Puan (0–100) beş alt puanın ağırlıklı toplamıdır. Kesik çerçeveli dilimin canlı verisi yok.</p>
{_bilesen_grafigi(k["bilesenler"])}
<ul class="rejim-liste">{bilesen}</ul>
<p class="g-not">Bir bileşenin verisi yoksa motor onun ağırlığını öbürlerine dağıtır; BTC trendi yoksa puan hiç çıkmaz.
Şu an beşinin de canlı puanı yok.</p></div>
<div class="kose kart"><h3>Durumlar</h3>
<p class="alt">Puan durumu belirler; bir veto tetiklenirse puan ne olursa olsun durum Siyah olur.</p>
{_esik_grafigi(k)}
<p class="g-not">Kötüleşme anında uygulanır; iyileşme için puan {k["yukselis_icin_olcum"]} ölçüm üst üste eşiğin üstünde
kalmalı ve her seferinde bir basamak çıkılır. {_durum("SIYAH", adlar)}: yeni işlem yok.</p>
<h3 style="margin-top:14px">Botların tasarlandığı durum</h3>
<ul class="rejim-liste">{bot_satir}</ul>
<p class="g-not uyari">▲ Canlıda uygulanmıyor: botlar bu alana bakmadan, durum ne olursa olsun işlem açar.
Alan yalnız kural dosyası okunurken denetlenir ve geçmiş ölçümünde "bu durumlarda çalışsaydı ne olurdu" sorusu için
kullanılır. Ne yapmalı: sınav sonu kararında, botun sonucunun Karabasan süzgeci olmadan alındığını dikkate al.</p></div>
<div class="kose kart"><h3>Veto kuralları</h3>
<p class="alt">Veto: tek başına botu durduran acil durum kuralı. Hangisinin kaydı var, aşağıda.</p>
<ul class="rejim-liste">{veto}</ul></div>"""


# --------------------------------------------------------------------------
# Küresel kayıt
# --------------------------------------------------------------------------


def _seri_grafigi(seri: list, etiket: str, bicim, bosluklar: list) -> str:
    if len(seri) < 2:
        return '<p class="bos">Grafik için veri az.</p>'
    ys = [v for _, v in seri]
    adimlar = s._guzel_adimlar(min(ys), max(ys))
    c = s._Cerceve(seri[0][0], seri[-1][0], adimlar[0], adimlar[-1], yukseklik=170.0, sol=52.0)
    parca = [c.y_ekseni(adimlar, bicim), s._zaman_etiketleri(c)]
    for b in bosluklar:
        bas, bit = _zaman(b.get("baslangic")), _zaman(b.get("bitis"))
        if bas and bit:
            x0, x1 = max(c.x(bas.timestamp()), c.sol), min(c.x(bit.timestamp()), c.g - c.sag)
            if x1 > x0:
                parca.append(f'<rect class="rejim-bosluk" x="{x0:.1f}" y="{c.ust:g}" width="{max(x1 - x0, 2):.1f}" '
                             f'height="{c.h - c.ust - c.alt:g}"><title>Kayıt boşluğu: {s._sure(b["dakika"])}</title></rect>')
    nokta = " ".join(f"{c.x(t):.1f},{c.y(v):.1f}" for t, v in seri)
    son_t, son_v = seri[-1]
    parca.append(f'<polyline class="rejim-cizgi" points="{nokta}"><title>{escape(etiket)}</title></polyline>'
                 f'<circle class="g-uc" style="fill:var(--holo)" cx="{c.x(son_t):.1f}" cy="{c.y(son_v):.1f}" r="4">'
                 f'<title>Son: {bicim(son_v)}</title></circle>')
    return c.svg("".join(parca), etiket)


def _kuresel(r: dict, saat_dilimi: str) -> str:
    k = r.get("kuresel") or {}
    gun = r.get("pencere_gun", 30)
    if not k.get("var"):
        return ('<div class="kose kart"><h3>Altcoin akışı: ham kayıt</h3><p class="bos">Veri yok: küresel kayıt dosyası '
                "(kuresel.csv) bulunamadı. Kaydedici servisi hiç çalışmamış olabilir. Ne yapmalı: Claude'a sor.</p></div>")
    if not k.get("olcum"):
        return (f'<div class="kose kart"><h3>Altcoin akışı: ham kayıt</h3><p class="bos">Son {gun} günde hiç ölçüm yok: '
                "kaydedici durmuş görünüyor. Ne yapmalı: Claude'a sor.</p></div>")
    yas = k["yas_dakika"]
    if k["bayat"]:
        canli = (f'<p class="uyari-serit">▲ Son ölçüm {s._sure(yas)} önce ({s._tarih_saat(_zaman(k["son_zaman"]), saat_dilimi)}). '
                 "Kaydedici 10 dakikada bir yazmalı; durmuş olabilir. Ne yapmalı: Claude'a sor.</p>")
    else:
        canli = f'<p class="g-not arti">● Kaydedici çalışıyor: son ölçüm {s._sure(yas)} önce.</p>'

    def dom(v):
        return s.sayi(v, 1)

    def milyar(v):
        return s.sayi(v / 1e9, 0)

    def puan_degisim(v):
        if v is None:
            return '<span class="notr">veri yok</span>'
        return f'<span class="{"arti" if v > 0 else "eksi" if v < 0 else "notr"}">{"▲" if v > 0 else "▼" if v < 0 else "●"} {s.isaretli(v, 2)} puan</span>'

    def yuzde_degisim(v):
        if v is None:
            return '<span class="notr">veri yok</span>'
        return f'<span class="{"arti" if v > 0 else "eksi" if v < 0 else "notr"}">{"▲" if v > 0 else "▼" if v < 0 else "●"} {s.isaretli_yuzde(v, 1)}</span>'

    az = k["kapsanan_gun"] < 7
    bosluk_metni = ("Boşluk yok." if not k["bosluk_sayisi"] else
                    f'{k["bosluk_sayisi"]} boşluk, toplam {s._sure(k["bosluk_toplam_dakika"])}; en uzunu '
                    f'{s._sure(k["en_uzun_bosluk_dakika"])}. Turuncu şerit boşluktur.')
    bosluklar = k.get("son_bosluklar") or []
    return f"""<div class="kose kart"><h3>Altcoin akışı: ham kayıt (son {gun} gün)</h3>
<p class="alt">BTC dominansı: bütün kripto piyasasının yüzde kaçının BTC olduğu. TOTAL2: BTC hariç kripto piyasasının toplam değeri.
Altcoin akışı bileşeninin ham girdisi budur; bileşenin puanı hesaplanmıyor.</p>
{canli}
<dl class="rejim-sayilar">
<div><dt>Dominans şimdi</dt><dd>%{dom(k["dominans"])}</dd></div>
<div><dt>Dominans 24 saat / 7 gün</dt><dd>{puan_degisim(k["dominans_24s"])}<span class="alt">{puan_degisim(k["dominans_7g"])}</span></dd></div>
<div><dt>TOTAL2 şimdi</dt><dd>{milyar(k["total2"])} milyar $</dd></div>
<div><dt>TOTAL2 24 saat / 7 gün</dt><dd>{yuzde_degisim(k["total2_24s"])}<span class="alt">{yuzde_degisim(k["total2_7g"])}</span></dd></div>
</dl>
<p class="g-not">Dominans yükselip TOTAL2 düşüyorsa para altcoinlerden BTC'ye kaçıyor demektir; açığa satış (fiyat düşünce kazanan)
botlar için bu ortam lehtedir, tersi aleyhtedir. Ne yapmalı: izle; tek başına karar verdirmez.</p>
<h3 style="margin-top:14px">Dominans (%)</h3>
{_seri_grafigi(k["dominans_seri"], "BTC dominansı, son " + str(gun) + " gün", dom, bosluklar)}
<h3 style="margin-top:14px">TOTAL2 (milyar $)</h3>
{_seri_grafigi(k["total2_seri"], "TOTAL2, son " + str(gun) + " gün", milyar, bosluklar)}
<p class="g-not">Grafikte her {k["kova_saat"]} saatin son ölçümü var. {k["olcum"]} ölçüm, {s.sayi(k["kapsanan_gun"], 1)} gün;
beklenenin {s.yuzde(k["kapsama_yuzde"], 0)}'i kaydedilmiş. {bosluk_metni}{" Veri az: kayıt 7 günden kısa." if az else ""}</p></div>"""


# --------------------------------------------------------------------------
# Art arda stop ve geçmiş rapor
# --------------------------------------------------------------------------


def _art_arda(r: dict, saat_dilimi: str) -> str:
    a = r.get("art_arda_stop")
    if a is None:
        return ('<div class="kose kart"><h3>Art arda stop vetosu</h3><p class="bos">Veri yok: veto eşiği kural '
                "dosyasından okunamadı.</p></div>")
    on = (f'<p class="alt">Canlı motor kaydı değildir: bütün botların kapanan işlemleri kapanış sırasıyla dizildi; araya '
          f'stop olmayan bir kapanış girmeden {a["esik"]} stop üst üste gelince veto tetiklenmiş sayıldı ve '
          f'{s.sayi(a["sure_dakika"], 0)} dakika sürdü. "Üst üste"nin bu tanımı kural dosyasında yazılı değildir; en yalın okuma budur.</p>')
    if not a["kapanan_islem"]:
        return f'<div class="kose kart"><h3>Art arda stop vetosu</h3>{on}<p class="bos">Henüz kapanmış işlem yok.</p></div>'
    gun = r.get("pencere_gun", 30)
    if not a["pencere_sayisi"]:
        govde = (f'<p class="bos">Son {gun} günde veto hiç tetiklenmezdi. En uzun stop serisi: {a["en_uzun_seri"]} '
                 f'(eşik {a["esik"]}).</p>')
    else:
        satir = "".join(
            f'<li><span class="rejim-ad">{s._tarih_saat(_zaman(p["baslangic"]), saat_dilimi)}'
            f'{" · sürüyor" if p["suruyor"] else ""}</span><span class="rejim-deger">{s._sure(p["dakika"])}</span>'
            f'<span class="alt">{p["art_arda"]} stop üst üste · bu sürede '
            + (f'<strong class="uyari">▲ {p["acilan_islem"]} işlem açıldı</strong> ({escape(", ".join(p["acan_botlar"]))})'
               if p["acilan_islem"] else '<span class="arti">● işlem açılmadı</span>')
            + "</span></li>" for p in a["pencereler"])
        net = a["acilan_net"]
        govde = f"""<dl class="rejim-sayilar">
<div><dt>Veto penceresi</dt><dd>{a["pencere_sayisi"]}<span class="alt">toplam {s._sure(a["toplam_dakika"])}</span></dd></div>
<div><dt>Bu sürede açılan işlem</dt><dd class="{"uyari" if a["acilan_islem"] else "arti"}">{a["acilan_islem"]}</dd></div>
<div><dt>Onların net sonucu</dt><dd class="{s._isaret_sinifi(net)}">{s.isaretli(net)} USDT<span class="alt">{a["acilan_kapanan"]} tanesi kapandı</span></dd></div>
<div><dt>En uzun stop serisi</dt><dd>{a["en_uzun_seri"]}<span class="alt">şimdi {a["simdiki_seri"]}</span></dd></div>
</dl>
<ul class="rejim-liste">{satir}</ul>
<p class="g-not">Karabasan canlı olsaydı bu pencerelerde yeni işlem açılmazdı. Açılanların net sonucu eksiyse süzgeç para
kurtarırdı, artıysa kaçırtırdı. Ne yapmalı: sınav sonu kararında dikkate al; {a["pencere_sayisi"]} pencere
{"az bir örnektir, sonuç çıkarma" if a["pencere_sayisi"] < 10 else "ancak kaba bir işarettir"}.</p>"""
    return f'<div class="kose kart"><h3>Art arda stop vetosu (kayıttan yeniden kuruldu)</h3>{on}{govde}</div>'


def _gecmis(r: dict, saat_dilimi: str) -> str:
    g = r.get("gecmis_raporu") or {}
    if not g.get("var"):
        govde = ('<p class="bos">Bu sunucuda geçmiş ölçüm raporu (karabasan_gecmis.txt) yok. Ne yapmalı: Claude\'a sor; '
                 "rapor sunucuda kurulumla üretilir.</p>")
    else:
        govde = (f'<p class="g-not">Rapor var: {s._tarih_saat(_zaman(g["yazildi"]), saat_dilimi)} tarihinde yazıldı '
                 f'({s._sure(g["yas_gun"] * 1440)} önce). Puanı geçmiş mumlardan bir kez hesaplar; canlı değildir. '
                 "Ne yapmalı: içeriğini Claude'a okut (Telegram'da /olcum yaz ya da sunucu oturumuna sor).</p>")
    return (f'<div class="kose kart"><h3>Geçmiş ölçüm raporu</h3><p class="alt">Karabasan puanının gerçekte hesaplandığı '
            f'tek yer: geçmiş verinin üstünde tek seferlik ölçüm.</p>{govde}</div>')


def ekran(ozet: dict, saat_dilimi: str) -> str:
    r = (ozet.get("ek") or {}).get("rejim") or {}
    return f"""<section id="rejim" class="ekran">
<h2 class="ekran-baslik">Rejim</h2>
<p class="ekran-ozet">Piyasa ortamı motoru (Karabasan): kurallar ve elde olan kayıt</p>
<div class="rejim-kutu"><h3>▲ Canlı Karabasan puanı kaydı yok</h3>
<p>Puan (0–100), durum (Yeşil, Sarı, Kırmızı, Siyah) ve vetolar şu an canlıda hiçbir yerde hesaplanıp kaydedilmiyor. Bu yüzden
"şimdi hangi durumdayız", "son {r.get("pencere_gun", 30)} günde durum geçişleri" ve "hangi veto ne kadar sürdü" sorularının
dürüst cevabı: <strong>veri yok</strong>. Bu ekranda tahmin uydurulmaz.</p>
<p>Botlar Karabasan'a bakmadan işlem açıyor; yani sınav sonucu süzgeçsiz bir sonuçtur.</p>
<p class="alt">Ne yapmalı: canlı puan kaydının eklenip eklenmeyeceği senin kararın; istersen Claude'a sor.</p></div>
<details class="aciklama-kutu"><summary>Bu ekran ne gösteriyor?</summary>
<p>Kuralların kendisi kod dosyasından okunur; sayfa ile kod aynı sayıyı söyler. Dominans ve TOTAL2 10 dakikada bir kaydedilen gerçek
ölçümlerdir. Art arda stop pencereleri işlem kaydından sonradan kurulmuştur, canlı motorun kararı değildir.</p></details>
<div class="g-kartlar">
{_kurallar(r)}
{_kuresel(r, saat_dilimi)}
{_art_arda(r, saat_dilimi)}
{_gecmis(r, saat_dilimi)}
</div>
</section>"""
