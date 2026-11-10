"""Disiplin ekranı: işlem kalitesi, kural denetimi, bugün dikkat edilecekler (10 Kasım 2026).

Veri: karabasan/sonuc_disiplin.py (ozet["ek"]["disiplin"]). Betik yok; seçimler <details> ile.
"""

from __future__ import annotations

from html import escape

from . import sayfa as s

STIL = """
.disiplin-liste{list-style:none;margin:10px 0 0;padding:0}
.disiplin-liste>li{padding:12px 0;border-bottom:1px solid var(--cizgi)}
.disiplin-satir{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.disiplin-ad{font-weight:650}
.disiplin-rozet{font-weight:700;font-size:.875rem;white-space:nowrap}
.disiplin-ornek{list-style:none;margin:6px 0 0;padding:0;font-size:.8125rem}
.disiplin-ornek a,.disiplin-ornek span.disiplin-ornek-ic{display:flex;align-items:center;min-height:44px;gap:8px;
color:var(--buz);text-decoration:none;border-top:1px dashed var(--cizgi)}
.disiplin-ornek a::after{content:"›";margin-left:auto;color:var(--holo);font-weight:700;font-size:1.125rem}
.disiplin-dilim{margin:6px 0 0}
.disiplin-dilim summary{display:flex;align-items:center;min-height:44px;cursor:pointer;font-weight:650;color:var(--holo);list-style:none}
.disiplin-dilim summary::-webkit-details-marker{display:none}
.disiplin-dilim summary::before{content:"+";width:1.2em;font-weight:700}
.disiplin-dilim[open] summary::before{content:"−"}
.disiplin-dikkat{border-color:rgba(255,159,67,.45)}
.disiplin-dikkat ol{margin:10px 0 0;padding-left:1.4em}
.disiplin-dikkat li{margin:0 0 12px}
.disiplin-dikkat li strong{display:block}
.disiplin-yap{color:var(--altin);font-size:.875rem}
@media (min-width:900px){.disiplin-genis{grid-column:1/-1}}
"""

NEDEN_SIRA = ("kâr hedefi", "iz süren stop", "stop", "süre aşımı")


def _durum_rozeti(d: dict) -> str:
    if d["durum"] == "temiz":
        return '<span class="disiplin-rozet arti">✓ temiz</span>'
    if d["durum"] == "ihlal":
        return f'<span class="disiplin-rozet eksi">▲ ihlal var ({d["adet"]})</span>'
    return '<span class="disiplin-rozet uyari">? denetlenemedi</span>'


def _ornek_satiri(o: dict, saat_dilimi: str) -> str:
    bas = escape(str(o.get("kod") or o.get("bot") or ""))
    if o.get("parite"):
        bas += " · " + s._parite(o["parite"])
    if o.get("zaman") is not None:
        bas += " · " + s._tarih_saat(o["zaman"], saat_dilimi)
    ic = f'<span><strong>{bas}</strong><span class="alt">{escape(str(o.get("ayrinti") or ""))}</span></span>'
    if o.get("kimlik") is not None and o.get("bot"):
        return f'<li><a href="/islem?bot={escape(str(o["bot"]))}&amp;id={int(o["kimlik"])}">{ic}</a></li>'
    return f'<li><span class="disiplin-ornek-ic">{ic}</span></li>'


def _denetim_karti(veri: dict, saat_dilimi: str) -> str:
    satirlar = []
    for d in veri["denetimler"]:
        ek = ""
        if d["durum"] == "ihlal":
            ek = '<ul class="disiplin-ornek">' + "".join(_ornek_satiri(o, saat_dilimi) for o in d["ornekler"]) + "</ul>"
            if d["adet"] > len(d["ornekler"]):
                ek += f'<p class="alt">İlk {len(d["ornekler"])} örnek gösteriliyor.</p>'
        elif d["durum"] == "denetlenemedi":
            ek = f'<span class="alt">Neden: {escape(str(d.get("neden") or ""))}</span>'
        satirlar.append(f'<li><div class="disiplin-satir"><span class="disiplin-ad">{escape(d["ad"])}</span>{_durum_rozeti(d)}</div>'
                        f'<span class="alt">{escape(d["aciklama"])}</span>{ek}</li>')
    ihlal = sum(1 for d in veri["denetimler"] if d["durum"] == "ihlal")
    eylem = ("İhlal görünürse örnek işleme dokunup bak ve Claude'a sor; ayar değiştirme."
             if ihlal else "Hepsi temizse yapılacak bir şey yok; ihlal çıkarsa Claude'a sor.")
    return (f'<div class="kose kart disiplin-genis"><h3>Kural denetimi</h3>'
            f'<p class="alt">Yalnız kayıttaki veriden. Emin olunamayan kural ihlal sayılmaz. {eylem}</p>'
            f'<ul class="disiplin-liste">{"".join(satirlar)}</ul></div>')


def _dilim_listesi(satirlar: list, genel: float | None, ad) -> str:
    cikti = []
    for r in satirlar:
        if r["yuksek"]:
            sinif, etiket = "eksi", " ▲ yüksek"
        elif r["az"]:
            sinif, etiket = "notr", " · veri az"
        else:
            sinif, etiket = "notr", ""
        cikti.append((ad(r), r["oran"], sinif,
                      f'%{s.sayi(r["oran"], 0)}<span class="alt"> {r["stop"]}/{r["islem"]}{etiket}</span>'))
    return s._yatay_cubuklar(cikti, 100.0, tek_yon=True)


def _stop_karti(veri: dict) -> str:
    d = veri["stop_dilimleri"]
    if not d["islem"]:
        return '<div class="kose kart"><h3>Stopa giden işlemler</h3><p class="bos">Henüz kapanmış işlem yok.</p></div>'
    genel = d["genel_oran"]
    bas = (f'<p>{d["islem"]} işlemin {d["stop"]} tanesi stopla kapandı: '
           f'<strong>%{s.sayi(genel, 0)}</strong>.</p>')
    if not d["yeterli"]:
        yorum = f'<p class="g-not">Veri az: dilimleri karşılaştırmak için en az 10 stop gerekir.</p>'
    elif d["yuksek"]:
        adlar = ", ".join(f'{escape(r["ad"])} (%{s.sayi(r["oran"], 0)})' for r in d["yuksek"][:4])
        yorum = (f'<p class="g-not"><strong class="eksi">▲ Stop oranı belirgin yüksek:</strong> {adlar}. '
                 "Tek dönemin sonucu olabilir; izle, sınav sonu kararında dikkate al.</p>")
    else:
        yorum = '<p class="g-not">Hiçbir dilim genel orandan belirgin yüksek değil (en az 10 işlem ve 15 puan fark aranır).</p>'
    adlar = {"saat": ("Saate göre (Bükreş saati, 4 saatlik)", lambda r: f'{r["anahtar"]:02d}–{r["anahtar"] + 4:02d}'),
             "gun": ("Haftanın gününe göre", lambda r: s.GUN_ADLARI[r["anahtar"]]),
             "coin": ("Coine göre", lambda r: str(r["anahtar"])),
             "bot": ("Bota göre", lambda r: str(r["anahtar"]))}
    acilir = "".join(
        f'<details class="disiplin-dilim"><summary>{baslik}</summary>{_dilim_listesi(d["turler"][tur], genel, f)}</details>'
        for tur, (baslik, f) in adlar.items() if d["turler"].get(tur))
    return (f'<div class="kose kart"><h3>Stopa giden işlemler</h3>{bas}{yorum}{acilir}'
            '<p class="alt">Karabasan piyasa durumuna göre ayrım: veri yok (işlem kaydında durum tutulmuyor).</p></div>')


def _maliyet_karti(veri: dict) -> str:
    m = veri["maliyet"]
    if not m["islem"]:
        return '<div class="kose kart"><h3>Komisyon ve kayma</h3><p class="bos">Henüz kapanmış işlem yok.</p></div>'
    if m["pay_yuzde"] is not None:
        pay = f'Komisyon brüt kârın yaklaşık <strong class="{"uyari" if m["pay_yuzde"] >= 50 else "notr"}">%{s.sayi(m["pay_yuzde"], 0)}</strong>\'ini yiyor.'
    else:
        pay = 'Brüt sonuç zaten eksi; komisyon zararı büyütüyor.'
    botlar = "".join(
        f'<li><span class="kriter-ad">{escape(str(b["kod"]))}</span>'
        f'<span class="analiz-not">komisyon ≈ {s.sayi(b["komisyon"])} · net <span class="{s._isaret_sinifi(b["net"])}">{s.isaretli(b["net"])}</span>'
        + (f' · ek kaymalı net <span class="{s._isaret_sinifi(b["ek_kaymali_net"])}">{s.isaretli(b["ek_kaymali_net"])}</span>'
           if b.get("ek_kaymali_net") is not None else "")
        + f'<span class="alt">gidiş-dönüş teminatın %{s.sayi(b["gidis_donus_yuzde"], 2)}\'i</span></span></li>'
        for b in m["botlar"])
    return f"""<div class="kose kart"><h3>Komisyon ve kayma</h3>
<dl class="olcu sonuc">
<div><dt>Yaklaşık komisyon</dt><dd class="eksi">{s.isaretli(-m["komisyon"])}<span class="alt">USDT · {m["islem"]} işlem</span></dd></div>
<div><dt>Brüt (komisyon önce)</dt><dd class="{s._isaret_sinifi(m["brut"])}">{s.isaretli(m["brut"])}<span class="alt">USDT</span></dd></div>
<div><dt>Net (kayıttaki)</dt><dd class="{s._isaret_sinifi(m["net"])}">{s.isaretli(m["net"])}<span class="alt">USDT</span></dd></div>
<div><dt>Sınavın ek kayma payı</dt><dd>{s.isaretli(-m["ek_kayma_tutar"])}<span class="alt">USDT · işlem başına %{s.sayi(m["ek_kayma_yuzde"], 2)}</span></dd></div>
</dl>
<p>{pay} Bu pay büyürse kenar incelir: sınav sonu kararında dikkate al.</p>
<ul class="analiz-liste">{botlar}</ul>
<p class="g-not">Yaklaşık: komisyon iki taraflı, her taraf pozisyonun (teminat × kaldıraç) taraf başı oranı sayıldı; çıkış fiyatı farkı
ve fonlama ödemesi ayrıca hesaplanmadı (kayıttaki net sonuçta içindedir). Gerçek kayma (emrin istenen fiyattan sapması): veri yok, sanal işlemde ölçülmez;
sınav her işlemden ek pay düşerek sınar.</p></div>"""


def _sure_karti(veri: dict) -> str:
    su = veri["sureler"]
    if not (su["kazanan_adet"] + su["kaybeden_adet"]):
        return '<div class="kose kart"><h3>İşlem süresi</h3><p class="bos">Henüz kapanmış işlem yok.</p></div>'
    ks = lambda x: s._sure(x) if x is not None else "–"  # noqa: E731
    if not su["yeterli"]:
        yorum = "Veri az: karşılaştırma için her yanda en az 5 işlem gerekir."
    elif su["kat"] and su["kat"] >= 1.5:
        yorum = (f"▲ Kaybeden işlemler kazananlardan {s.sayi(su['kat'], 1)} kat uzun açık kalıyor. "
                 "Stoplu sistemde beklenen bir durum olabilir; izle, büyürse Claude'a sor.")
    else:
        yorum = "Kaybedenler kazananlardan belirgin uzun tutulmuyor."
    en_cok = max((r["ort"] or 0 for r in su["nedenler"]), default=0) or 1
    nedenler = s._yatay_cubuklar(
        [(f'{r["neden"]}', r["ort"] or 0, "notr", f'{ks(r["ort"])}<span class="alt"> {r["adet"]} işlem</span>')
         for r in su["nedenler"]], en_cok, tek_yon=True)
    return f"""<div class="kose kart"><h3>İşlem süresi</h3>
<dl class="olcu sonuc">
<div><dt>Kazanan ortalama</dt><dd class="arti">{ks(su["kazanan_ort"])}<span class="alt">{su["kazanan_adet"]} işlem</span></dd></div>
<div><dt>Kaybeden ortalama</dt><dd class="eksi">{ks(su["kaybeden_ort"])}<span class="alt">{su["kaybeden_adet"]} işlem</span></dd></div>
</dl><p class="g-not">{escape(yorum)}</p><h4>Çıkış nedenine göre</h4>{nedenler}</div>"""


def _ders_karti(veri: dict, saat_dilimi: str) -> str:
    satirlar = []
    for d in veri["stop_dersleri"]:
        son = d.get("son_ders")
        son_metin = (f'<span class="alt">Son ders {s._tarih_saat(son["zaman"], saat_dilimi)}: {escape(str(son.get("metin") or son.get("ad") or ""))}</span>'
                     if son else '<span class="alt">Henüz ders yok.</span>')
        satirlar.append(f'<li><div class="disiplin-satir"><span class="disiplin-ad">{escape(str(d["kod"]))}'
                        f' · stop {s.kisa_yuzde(d["stop_yuzde"])}</span>'
                        f'<span class="disiplin-rozet karar {escape(str(d["karar_kod"] or ""))}">{escape(d["karar_adi"])}</span></div>'
                        f'<span class="alt">{d["stop_sayisi"]} stop izlendi.</span>{son_metin}</li>')
    if not satirlar:
        govde = '<p class="bos">Bot yok.</p>'
    else:
        govde = f'<ul class="disiplin-liste">{"".join(satirlar)}</ul>'
    return (f'<div class="kose kart"><h3>Stop genişliği dersi</h3>'
            f'<p class="alt">Stop daha geniş olsaydı ne olurdu? Karar ayarı değiştirmez; "dar" çıkarsa yalnız ayrı bir sanal bot önerilir.</p>'
            f'{govde}<p class="g-not"><a href="#dersler">Dersler ekranına git ›</a></p></div>')


def _dikkat_kutusu(veri: dict) -> str:
    maddeler = veri.get("dikkat") or []
    if not maddeler:
        govde = '<p>Bugün dikkat gerektiren bir şey görünmüyor.</p>'
    else:
        govde = "<ol>" + "".join(
            f'<li><strong>{escape(m["ne"])}</strong>{escape(m["sayi"])}<span class="alt disiplin-yap">Ne yapmalı: {escape(m["yapmali"])}</span></li>'
            for m in maddeler) + "</ol>"
        if len(maddeler) < 3:
            govde += '<p class="alt">Bugün başka dikkat gerektiren bir şey görünmüyor.</p>'
    return (f'<div id="disiplin-dikkat" class="kose kart disiplin-dikkat disiplin-genis"><h3>Bugün dikkat edilecek 3 şey</h3>{govde}'
            '<p class="g-not">Seçim kurala göre: önce kural ihlali, sonra sessiz bot, açık pozisyon riski, kayıp serisi, '
            'komisyon payı, stop yoğun dilim. Uydurma yok; yalnız bu ekrandaki sayılar.</p></div>')


def ekran(ozet: dict, saat_dilimi: str) -> str:
    veri = (ozet.get("ek") or {}).get("disiplin") or {}
    ihlal = sum(1 for d in veri.get("denetimler", []) if d["durum"] == "ihlal")
    dikkat = len(veri.get("dikkat") or [])
    if not veri.get("islem_sayisi"):
        ust = "Henüz kapanmış işlem yok; denetimler veri geldikçe dolar."
    else:
        ust = (f'{veri["islem_sayisi"]} işlem · kural ihlali {ihlal} · '
               f'<a href="#disiplin-dikkat">bugün dikkat: {dikkat}</a>')
    return f"""<section id="disiplin" class="ekran">
<h2 class="ekran-baslik">Disiplin</h2>
<p class="ekran-ozet">{ust}</p>
<details class="aciklama-kutu"><summary>Bu ekran ne gösteriyor?</summary>
<p>İşlemlerin kalitesi: stoplar nerede yoğunlaşıyor, komisyon ne kadar yiyor, kaybedenler ne kadar tutuluyor ve botlar kendi
kurallarına uyuyor mu. Hepsi sanal işlem kaydından hesaplanır; hiçbir ayarı değiştirmez. Sınav sürerken strateji ayarı değişmez.</p></details>
<div class="g-kartlar">
{_denetim_karti(veri, saat_dilimi)}
{_stop_karti(veri)}
{_maliyet_karti(veri)}
{_sure_karti(veri)}
{_ders_karti(veri, saat_dilimi)}
{_dikkat_kutusu(veri)}
</div>
</section>"""
