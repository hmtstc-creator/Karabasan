"""Risk ekranı (10 Kasım 2026): sermaye koruma gözüyle. Veri `sonuc_risk.hesapla`'dan gelir.

Betik yok; seçim gerekirse `<details>`. Renkler sayfa.STIL'in değişkenlerinden.
"""

from __future__ import annotations

from datetime import datetime
from html import escape

from . import sayfa as s

# Sayfanın kendi okuma eşikleri (bütçe yüzdesi). Bot kuralı değildir; yalnız etiket içindir.
SEVIYE_ORTA = 1.0
SEVIYE_YUKSEK = 3.0

STIL = """
.risk-olcu{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0;margin:12px 0 0;border-top:1px solid var(--cizgi)}
.risk-olcu div{padding:10px 8px 8px 0;min-width:0}
.risk-olcu dt{color:var(--soluk);font-size:.75rem}
.risk-olcu dd{margin:0;font:700 1.25rem/1.25 var(--rakam);overflow-wrap:anywhere}
.risk-olcu dd .alt{font-family:var(--govde);font-size:.75rem}
.risk-eylem{margin:10px 0 0;padding:8px 10px;border-left:3px solid var(--holo);background:var(--yuzey);
border-radius:8px;font-size:.8125rem;color:var(--buz);max-width:70ch}
.risk-eylem::before{content:"Ne yapmalı: ";font-weight:700;color:var(--holo)}
.risk-seviye{display:inline-flex;align-items:center;gap:4px;padding:2px 10px;border-radius:999px;font-size:.75rem;
font-weight:700;border:1px solid currentColor;vertical-align:middle}
.risk-liste{list-style:none;margin:12px 0 0;padding:0}
.risk-liste li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 10px;align-items:baseline;
padding:10px 0;border-top:1px solid var(--cizgi);min-height:44px}
.risk-liste .risk-sag{font:700 1rem var(--rakam);text-align:right;white-space:nowrap}
.risk-liste .alt{grid-column:1/-1}
.risk-kart h3{margin-top:0}
.risk-veri-yok{color:var(--soluk);font-style:italic}
"""


def _veri(ozet: dict) -> dict:
    return (ozet.get("ek") or {}).get("risk") or {}


def _usdt(v, isaret=True) -> str:
    if v is None:
        return '<span class="risk-veri-yok">veri yok</span>'
    return (s.isaretli(v) if isaret else s.sayi(v)) + '<span class="alt"> USDT</span>'


def _pct(v) -> str:
    return '<span class="risk-veri-yok">veri yok</span>' if v is None else s.yuzde(abs(v), 2)


def _seviye(yuzde_) -> str:
    """Bütçe yüzdesine göre yazılı etiket (renk körlüğü için simgeli)."""
    if yuzde_ is None:
        return '<span class="risk-seviye notr">● veri yok</span>'
    v = abs(yuzde_)
    if v >= SEVIYE_YUKSEK:
        return '<span class="risk-seviye eksi">▲ yüksek</span>'
    if v >= SEVIYE_ORTA:
        return '<span class="risk-seviye uyari">● orta</span>'
    return '<span class="risk-seviye arti">▼ düşük</span>'


def _eylem(metin: str) -> str:
    return f'<p class="risk-eylem">{escape(metin)}</p>'


def _gun(v) -> str:
    if v is None:
        return '<span class="risk-veri-yok">veri yok</span>'
    if v < 1:
        return s._sure(v * 1440)
    return f"{s.sayi(v, 1)} gün"


# --------------------------------------------------------------------------
# Kartlar
# --------------------------------------------------------------------------


def _acik_karti(r: dict) -> str:
    a, b = r["acik"], r["butce"]
    if not a["adet"]:
        govde = '<p class="bos">Şu an açık pozisyon yok; stopa giderek kaybedilecek para yok.</p>'
        return f'<div class="kose kart risk-kart"><h3>Açık risk</h3>{govde}</div>'
    bilinmeyen = (f'<p class="g-not uyari">▲ {a["bilinmeyen"]} pozisyonun stop fiyatı hesaplanamadı (giriş fiyatı ya da stop '
                  "kaydı yok); toplam bunları içermiyor.</p>" if a["bilinmeyen"] else "")
    satirlar = []
    for x in r["acik"]["botlar"]:
        if not x["adet"]:
            sag, alt = "–", "açık pozisyon yok"
        else:
            sag = _usdt(x["stopta_kayip"])
            alt = (f'{x["adet"]} pozisyon · teminat {s.sayi(x["teminat"], 0)} USDT · kendi bütçesinin '
                   f'{_pct(x["butce_yuzde"])} kadarı stopta · {s.sayi(x["kaldirac"], 0)} kat'
                   + (" · zararda ek girişli" if x["ekleme"] else ""))
        satirlar.append(f'<li><span><span class="kod">{escape(x["kod"])}</span></span>'
                        f'<span class="risk-sag eksi">{sag}</span><span class="alt">{alt}</span></li>')
    return f"""<div class="kose kart risk-kart">
<h3>Açık risk <span class="alt">hepsi stopa giderse, komisyon hariç</span></h3>
<dl class="risk-olcu">
<div><dt>Stoptaki toplam kayıp</dt><dd class="eksi">{_usdt(a["stopta_kayip"])}</dd></div>
<div><dt>Toplam bütçeye oranı</dt><dd>{_pct(a["butce_yuzde"])} {_seviye(a["butce_yuzde"])}
<span class="alt">payda {s.sayi(b["toplam"], 0) if b["toplam"] else "–"} USDT</span></dd></div>
<div><dt>Açık pozisyon</dt><dd>{a["adet"]}</dd></div>
<div><dt>Bağlı teminat</dt><dd>{_usdt(a["teminat"], isaret=False)}<span class="alt"> bütçenin {_pct(a["teminat_yuzde"])} kadarı</span></dd></div>
</dl>
{bilinmeyen}
{_eylem("Bu sayı toplam bütçenin %3 kadarını geçerse yeni bir şey yapma, Claude'a hangi pozisyonların biriktiğini sor; "
        "sınav sırasında botlara elle müdahale etme.")}
<ul class="risk-liste">{"".join(satirlar)}</ul>
<p class="g-not">Stop fiyatı ilk girişe göredir; ek girişli botlarda henüz yapılmamış ek girişin kaybı da eklenmiştir.
Kayma (emrin istenen fiyattan kötü dolması) ve komisyon dahil değildir; gerçek kayıp biraz daha büyük olabilir.</p>
</div>"""


def _senaryo_karti(r: dict) -> str:
    sen, d = r.get("senaryo"), r["dusus"]["toplam"]
    if not sen:
        return ('<div class="kose kart risk-kart"><h3>Hepsi stopa giderse</h3>'
                '<p class="bos">Şu an açık pozisyon yok; stopa gidecek bir şey yok.</p></div>')
    derin = ("▲ Bu, şimdiye kadarki en derin düşüşten daha derin olur." if sen["en_derinden_derin"]
             else "Bu, şimdiye kadarki en derin düşüşü geçmez.")
    return f"""<div class="kose kart risk-kart">
<h3>Hepsi stopa giderse</h3>
<dl class="risk-olcu">
<div><dt>Tepeden düşüş olurdu</dt><dd class="eksi">{_usdt(sen["dusus"])}</dd></div>
<div><dt>Toplam bütçenin</dt><dd>{_pct(sen["dusus_yuzde"])} {_seviye(sen["dusus_yuzde"])}</dd></div>
</dl>
<p class="g-not">Bugünkü düşüş ({s.isaretli(d["simdiki"]) if d["simdiki"] is not None else "veri yok"} USDT) ile açık
pozisyonların stoptaki kaybının toplamı. {escape(derin)}</p>
{_eylem("Bu sayı en derin düşüşü geçiyorsa durum bu sınavın en kötü anına yakın demektir: izle, Claude'a sor; "
        "sınav sonu kararında bu senaryoyu dikkate al.")}
</div>"""


def _dusus_karti(r: dict) -> str:
    d = r["dusus"]["toplam"]
    if not d["islem_sayisi"]:
        return ('<div class="kose kart risk-kart"><h3>Tepeden düşüş</h3>'
                '<p class="bos">Henüz kapanmış işlem yok; düşüş ölçülemez.</p></div>')
    veri_az = (f'<p class="g-not uyari">● Veri az ({d["islem_sayisi"]} işlem): bu düşüş ileride çok daha derin olabilir.</p>'
               if d.get("veri_az") else "")
    su = (f'Şu an su altında: {_gun(d["su_alti_gun"])} süredir tepenin altında.' if d["su_altinda"]
          else "Şu an tepede (su altında değil).")
    grafik = s._dusus_grafigi([(t, v) for t, _, v in d["noktalar"]])
    satirlar = []
    for x in r["dusus"]["botlar"]:
        if not x["islem_sayisi"]:
            satirlar.append(f'<li><span><span class="kod">{escape(x["kod"])}</span></span>'
                            '<span class="risk-sag">–</span><span class="alt">henüz kapanmış işlem yok</span></li>')
            continue
        satirlar.append(
            f'<li><span><span class="kod">{escape(x["kod"])}</span></span>'
            f'<span class="risk-sag eksi">{s.isaretli(x["en_derin"])}</span>'
            f'<span class="alt">en derin (kendi bütçesinin {_pct(x["en_derin_yuzde"])} kadarı) · şimdi '
            f'{s.isaretli(x["simdiki"])} USDT · en uzun su altı {_gun(x["en_uzun_su_alti_gun"])}'
            + (f' · {_gun(x["su_alti_gun"])} süredir su altında' if x["su_altinda"] else "") + "</span></li>")
    return f"""<div class="kose kart risk-kart">
<h3>Tepeden düşüş <span class="alt">bütün botlar birlikte, kapanmış işlemler</span></h3>
<dl class="risk-olcu">
<div><dt>Şimdiki düşüş</dt><dd class="{s._isaret_sinifi(d["simdiki"])}">{_usdt(d["simdiki"])}<span class="alt"> bütçenin {_pct(d["simdiki_yuzde"])} kadarı</span></dd></div>
<div><dt>En derin düşüş</dt><dd class="eksi">{_usdt(d["en_derin"])}<span class="alt"> bütçenin {_pct(d["en_derin_yuzde"])} kadarı</span></dd></div>
<div><dt>En uzun su altı</dt><dd>{_gun(d["en_uzun_su_alti_gun"])}</dd></div>
<div><dt>Şu an</dt><dd>{"▼ su altında" if d["su_altinda"] else "● tepede"}</dd></div>
</dl>
<p class="g-not">{escape(su)} "Su altı": toplam sonuç son ulaştığı en yüksek değerin altında kalıyor.</p>
{veri_az}
{grafik}
{_eylem("Su altında kalınan gün sayısı uzarsa (örneğin 7 günü geçerse) botlar kaybını geri alamıyor demektir: "
        "Claude'a sor ve sınav sonu kararında bunu ağır say. Sınav ölçütü en çok %5 düşüştür (bot başına).")}
<ul class="risk-liste">{"".join(satirlar)}</ul>
<p class="g-not">Açık pozisyonların kâğıt üstü kârı / zararı dahil değildir (anlık fiyat verisi bu sayfada yok).</p>
</div>"""


def _yogunlasma_karti(r: dict) -> str:
    y = r["yogunlasma"]
    if not r["acik"]["adet"]:
        return ('<div class="kose kart risk-kart"><h3>Yoğunlaşma</h3>'
                '<p class="bos">Şu an açık pozisyon yok; yoğunlaşma yok.</p></div>')
    en = y["en_buyuk_coin"]
    ortak = "".join(
        f'<li><span>{s._parite(c["parite"])}</span><span class="risk-sag eksi">{s.isaretli(c["stopta_kayip"])}</span>'
        f'<span class="alt">{len(c["botlar"])} botta açık: {escape(", ".join(c["botlar"]))} · stopta birlikte kaybeder</span></li>'
        for c in y["ortak_coinler"])
    coin_cubuk = s._yatay_cubuklar(
        [(str(c["parite"]), c["pay"] or 0.0, "notr", f'{s.yuzde(c["pay"], 0)}<span class="alt"> {c["adet"]} poz.</span>')
         for c in y["coinler"][:8]], 100.0, tek_yon=True)
    yon = (f'▼ %{s.sayi(y["aciga_satis_pay"], 0)} açığa satış' if (y["aciga_satis_pay"] or 0) >= 50
           else f'▲ %{s.sayi(y["alim_pay"], 0)} alım')
    return f"""<div class="kose kart risk-kart">
<h3>Yoğunlaşma <span class="alt">kaldıraçlı büyüklüğe göre (teminat × kaldıraç)</span></h3>
<dl class="risk-olcu">
<div><dt>Tek yön payı</dt><dd>{yon}</dd></div>
<div><dt>En büyük coin</dt><dd>{s._parite(en["parite"])}<span class="alt"> payı %{s.sayi(en["pay"], 0)}</span></dd></div>
<div><dt>Kaldıraçlı büyüklük</dt><dd>{_usdt(y["nominal_toplam"], isaret=False)}<span class="alt"> bütçenin {_pct(y["nominal_yuzde"])} kadarı</span></dd></div>
<div><dt>Birden çok botta açık coin</dt><dd>{len(y["ortak_coinler"])}</dd></div>
</dl>
<p class="g-not">Dört bot da yalnız açığa satış (fiyat düşerse kazanır) yapar. Piyasa birden yükselirse bütün açık
pozisyonlar aynı anda zarar eder; çeşitlendirme yoktur.</p>
{coin_cubuk}
{_eylem("Tek coinin payı yarıyı geçerse ya da aynı coin birden çok botta açıksa, o coin sert yükselirse kayıp katlanır: izle, "
        "Claude'a sor. Sınav sonu kararında botların aynı işlemi tekrar mı ettiğini dikkate al.")}
{f'<ul class="risk-liste">{ortak}</ul>' if ortak else '<p class="g-not">Aynı coin birden çok botta açık değil.</p>'}
</div>"""


def _gunluk_karti(r: dict) -> str:
    gunler = r.get("gunluk") or []
    if not gunler or all(g["en_cok"] <= 0 for g in gunler):
        return ('<div class="kose kart risk-kart"><h3>Günlük bütçe kullanımı</h3>'
                '<p class="bos">Veri yok: son günlerde hiç pozisyon açılmadı.</p></div>')
    cubuklar = [(g["gun"][8:10], g["yuzde"] or 0.0,
                 f'{g["gun"]}: en çok {s.sayi(g["en_cok"], 0)} USDT teminat aynı anda açık '
                 f'(bütçenin %{s.sayi(g["yuzde"] or 0.0, 1)}){"" if g["tamam"] else ", gün sürüyor"}') for g in gunler]
    en = max(gunler, key=lambda g: g["en_cok"])
    bugun = gunler[-1]
    return f"""<div class="kose kart risk-kart">
<h3>Günlük bütçe kullanımı <span class="alt">son {len(gunler)} gün, UTC</span></h3>
<dl class="risk-olcu">
<div><dt>Bugün en çok</dt><dd>{_pct(bugun["yuzde"])}<span class="alt"> {s.sayi(bugun["en_cok"], 0)} USDT</span></dd></div>
<div><dt>En yoğun gün</dt><dd>{_pct(en["yuzde"])}<span class="alt"> {escape(en["gun"])}</span></dd></div>
</dl>
{s._cubuk_grafigi(cubuklar, yukseklik=160.0, etiket_adim=2)}
<p class="g-not">Her çubuk: o gün aynı anda açık teminatın en büyük toplamı, toplam bütçenin yüzdesi olarak (kaldıraçsız).</p>
{_eylem("Bu oran sürekli yükseliyorsa botlar aynı anda daha çok para bağlıyor demektir; kötü bir günde kayıp da büyür. "
        "İzle; yarıyı geçerse Claude'a sor.")}
</div>"""


def _ek_satir(x: dict, saat_dilimi: str, bekliyor: bool) -> str:
    ek = s.fiyat_metni(x["ek_giris_fiyati"]) if x["ek_giris_fiyati"] else "veri yok"
    parca = [f'ilk giriş {s.fiyat_metni(x["ilk_giris_fiyati"])}',
             (f"ek giriş beklenen seviye {ek}" if bekliyor else f"ek giriş {ek}, ortalama {s.fiyat_metni(x['ortalama_fiyat'])}"),
             f'stop {s.fiyat_metni(x["stop_fiyati"])}',
             f'teminat {s.sayi(x["teminat"], 0)} USDT (kaldıraçlı {s.sayi(x["nominal"], 0)})']
    if bekliyor:
        parca.append(f'ek girişte +{s.sayi(x["eklenecek_teminat"], 0)} USDT teminat daha bağlanır')
    return (f'<li><span><span class="kod">{escape(str(x["kod"]))}</span> {s._parite(x["parite"])}</span>'
            f'<span class="risk-sag eksi">{s.isaretli(x["stopta_kayip"]) if x["stopta_kayip"] is not None else "veri yok"}</span>'
            f'<span class="alt">{" · ".join(parca)} · açılış {s._tarih_saat(x["giris_zamani"], saat_dilimi)} · '
            f'kendi bütçesinin {_pct(x["stopta_kayip_yuzde"])} kadarı stopta</span></li>')


def _ekleme_karti(r: dict, saat_dilimi: str) -> str:
    e = r["ekleme"]
    if not e["botlar"]:
        return ('<div class="kose kart risk-kart"><h3>2 kat, zararda ek girişli botlar</h3>'
                '<p class="bos">Veri yok: ek girişli bot bulunamadı.</p></div>')
    k = e["ayar"][e["botlar"][0]]
    ilk = r["butce"]["ilk_tutar"] or 0.0
    # Ek girişten sonra stop: ilk kısım tam stop uzaklığında, eklenen kısım yalnız "stopa kala" kadar (acik_risk ile aynı).
    tam = (ilk * k["kaldirac"] * k["stop_yuzde"] + ilk * k["kat"] * k["kaldirac"] * k["stopa_kala_yuzde"]) / 100.0
    yapilan = "".join(_ek_satir(x, saat_dilimi, False) for x in e["yapilan"])
    bekleyen = "".join(_ek_satir(x, saat_dilimi, True) for x in e["bekleyen"])
    if e["kapanan_ekli_adet"]:
        fark = (e["kapanan_ekli_net"] or 0.0) - (e["kapanan_ekli_karne"] or 0.0)
        kapanan = (f'<p class="g-not">Ek girişli {e["kapanan_ekli_adet"]} işlem kapandı: kayıtlı net '
                   f'<strong class="{s._isaret_sinifi(e["kapanan_ekli_net"])}">{s.isaretli(e["kapanan_ekli_net"])} USDT</strong>, '
                   f'en kötüsü <strong class="eksi">{s.isaretli(e["kapanan_ekli_en_kotu"])} USDT</strong>. '
                   f'Sınav karnesi aynı işlemleri yüzde × {s.sayi(r["butce"]["ilk_tutar"], 0)} USDT ile '
                   f'{s.isaretli(e["kapanan_ekli_karne"])} USDT sayıyor (fark {s.isaretli(fark)} USDT).</p>')
    else:
        kapanan = '<p class="g-not">Henüz ek girişli kapanmış işlem yok.</p>'
    return f"""<div class="kose kart risk-kart">
<h3>2 kat, zararda ek girişli botlar <span class="alt">{escape(", ".join(e["botlar"]))}</span></h3>
<p class="g-not">Kaldıraç: teminatın {s.sayi(k["kaldirac"], 0)} katı büyüklükte işlem; kâr da zarar da o kadar büyür.
Fiyat ilk girişten %{s.sayi(k["stop_yuzde"] - k["stopa_kala_yuzde"], 0)} aleyhe gidince ilk tutarın {s.sayi(k["kat"], 0)} katı
kadar bir kez daha girilir; stop ilk girişe göre (%{s.sayi(k["stop_yuzde"], 0)}) yerinde kalır. Ek girişten sonra stop olan bir
işlem yaklaşık {s.sayi(tam, 1)} USDT kaybettirir (ilk teminatın %{s.sayi(tam / r["butce"]["ilk_tutar"] * 100, 0) if r["butce"]["ilk_tutar"] else "–"} kadarı,
komisyon hariç).</p>
<dl class="risk-olcu">
<div><dt>Ek giriş yapılmış</dt><dd class="{"eksi" if e["yapilan"] else "notr"}">{"▲ " if e["yapilan"] else ""}{len(e["yapilan"])}</dd></div>
<div><dt>Ek giriş bekleyen</dt><dd>{len(e["bekleyen"])}<span class="alt"> yolda +{s.sayi(e["bekleyen_ek_teminat"], 0)} USDT teminat</span></dd></div>
</dl>
{_eylem("Ek giriş yapılmış pozisyon stopa yalnız %1 uzaktadır ve en büyük tek kaybı o verir. Sayısı artarsa izle, "
        "Claude'a sor; sınav sonu kararında bu botların tek stopta ne kaybettiğini 1 katlı botlarla karşılaştır.")}
<h4 class="kucuk-baslik">Ek giriş yapılmış</h4>
{f'<ul class="risk-liste">{yapilan}</ul>' if yapilan else '<p class="g-not">Şu an ek giriş yapılmış açık pozisyon yok.</p>'}
<h4 class="kucuk-baslik">Ek giriş bekleyen (fiyat beklenen seviyeye gelirse yapılır)</h4>
{f'<ul class="risk-liste">{bekleyen}</ul>' if bekleyen else '<p class="g-not">Şu an ek giriş bekleyen açık pozisyon yok.</p>'}
<p class="g-not">Anlık fiyat bu sayfada yok: pozisyonun ek giriş seviyesine ya da stopa ne kadar yaklaştığı veri yok.</p>
{kapanan}
<p class="g-not uyari">● Bilinen belirsizlik: ek girişli işlemde motorun kayda yazdığı tutar toplam teminat olabilir; bu
sunucudaki kayıtla henüz doğrulanmadı. Bu ekran kayıtlı gerçek net tutarı kullanır; sınav karnesi ise yüzde × ilk tutar
ile hesaplar. İkisi farklıysa karnedeki USDT ve düşüş değerleri bu iki botta olduğundan küçük görünebilir.</p>
</div>"""


def ekran(ozet: dict, saat_dilimi: str) -> str:
    r = _veri(ozet)
    if not r or r.get("hata") or "acik" not in r:
        return ('<section id="risk" class="ekran"><h2 class="ekran-baslik">Risk</h2>'
                '<p class="bos">Veri yok: risk ölçüleri hazırlanamadı.</p></section>')
    a, b = r["acik"], r["butce"]
    if a["adet"]:
        ust = (f'Hepsi stopa giderse ≈ <span class="eksi">{s.isaretli(a["stopta_kayip"])} USDT</span> '
               f'(toplam bütçenin {_pct(a["butce_yuzde"])} kadarı) · {a["adet"]} açık pozisyon')
    else:
        ust = "Açık pozisyon yok; şu an stopa giderek kaybedilecek para yok."
    payda = (f"{b['bot_sayisi']} bot × {s.sayi(b['bot_basi'], 0)} USDT = {s.sayi(b['toplam'], 0)} USDT"
             if b["toplam"] else "veri yok")
    return f"""<section id="risk" class="ekran">
<h2 class="ekran-baslik">Risk</h2>
<p class="ekran-ozet">{ust}</p>
<details class="aciklama-kutu"><summary>Bu ekran ne gösteriyor?</summary>
<p>Parayı korumak için bakılacak sayılar. Hepsi sanal işlemlerden; hiçbir ayarı değiştirmez.</p>
<p>Stop: zararı durdur emri; fiyat oraya gelince pozisyon zararına kapanır. Teminat: bir pozisyona bağlanan para.
Kaldıraç: teminatın kaç katı büyüklükte işlem açıldığı.</p>
<p>Bütçe yüzdeleri hangi paya göre: her botun kendi sanal bakiyesi var; toplam bütçe {escape(payda)}. Bot satırlarında
yüzde o botun kendi bakiyesine göredir. "Düşük / orta / yüksek" etiketi bu sayfanın okuma kolaylığıdır (%{s.sayi(SEVIYE_ORTA, 0)}
ve %{s.sayi(SEVIYE_YUKSEK, 0)} sınırları), botların kuralı değildir.</p>
<p>Tutarlar kayıtlı gerçek net tutardır (komisyon düşülmüş). Stoptaki kayıp komisyon ve kaymayı içermez.</p></details>
<div class="g-kartlar">
{_acik_karti(r)}
{_senaryo_karti(r)}
{_dusus_karti(r)}
{_yogunlasma_karti(r)}
{_gunluk_karti(r)}
{_ekleme_karti(r, saat_dilimi)}
</div>
</section>"""
