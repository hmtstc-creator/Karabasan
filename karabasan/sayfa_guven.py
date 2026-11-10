"""Güven ekranı: "Sonuçlara güvenebilir miyim?" (10 Kasım 2026). Betik yok; seçim <details> ile."""

from __future__ import annotations

from html import escape

from . import sayfa as s

STIL = """
.guven-hukum{margin:0 0 14px;padding:14px 16px;border-radius:var(--r-orta);border:1px solid var(--cizgi);
border-left:4px solid var(--soluk);background:var(--yuzey)}
.guven-hukum.eksi{border-left-color:var(--eksi)}.guven-hukum.arti{border-left-color:var(--arti)}
.guven-hukum.uyari{border-left-color:var(--uyari)}
.guven-hukum strong{display:block;font:700 1.25rem/1.3 var(--rakam)}
.guven-hukum p{margin:6px 0 0;color:var(--soluk);font-size:.9375rem}
.guven-kart{padding:16px;min-width:0}
.guven-ust{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
.guven-rozet{display:inline-flex;align-items:center;min-height:28px;padding:2px 10px;border-radius:999px;
border:1px solid currentColor;font-size:.8125rem;font-weight:700}
.guven-rozet.notr{color:var(--soluk)}.guven-rozet.uyari{color:var(--uyari)}
.guven-liste{list-style:none;margin:12px 0 0;padding:0}
.guven-liste li{padding:10px 0;border-top:1px solid var(--cizgi);min-width:0;overflow-wrap:anywhere}
.guven-liste b{display:block;font-size:.75rem;font-weight:600;color:var(--soluk);letter-spacing:.02em}
.guven-deger{font:700 1.0625rem/1.35 var(--rakam)}
.guven-eylem{display:block;margin-top:3px;color:var(--soluk);font-size:.8125rem}
.guven-aralik{display:block;width:100%;height:auto;margin-top:6px}
.guven-aralik .bant{fill:var(--holo);opacity:.55}.guven-aralik .zemin{fill:var(--yuzey2)}
.guven-aralik .basabas{stroke:var(--buz);stroke-width:2}
.guven-aralik text{fill:var(--soluk);font:500 11px var(--govde)}
.guven-kutu summary{min-height:44px}
"""

KONUM = {
    "ustunde": ("▲ başa başın üstünde", "arti"),
    "icinde": ("● başa baş aralığın içinde: şanstan ayırt edilemez", "notr"),
    "altinda": ("▼ başa başın altında", "eksi"),
    "veri_yok": ("veri yok", "notr"),
}
ISARET = {"arti": "▲ ", "eksi": "▼ ", "uyari": "● ", "notr": "● "}


def _p_metni(p) -> str:
    if p is None:
        return "–"
    if p < 0.001:
        return "%0,1'den az"
    return s.yuzde(p * 100, 1)


def _oge(baslik: str, deger: str, eylem: str, ek: str = "") -> str:
    return (f'<li><b>{baslik}</b><span class="guven-deger">{deger}</span>{ek}'
            f'<span class="guven-eylem">{eylem}</span></li>')


def _aralik_svg(aralik, basabas) -> str:
    if not aralik:
        return ""
    g = 300.0

    def x(v):
        return 4 + max(0.0, min(100.0, v)) / 100.0 * (g - 8)

    cizgi = ""
    if basabas is not None:
        cizgi = (f'<line class="basabas" x1="{x(basabas):.1f}" x2="{x(basabas):.1f}" y1="2" y2="26"/>'
                 f'<text x="{x(basabas):.1f}" y="38" text-anchor="middle">başa baş %{s.sayi(basabas, 0)}</text>')
    etiket = (f"Kazanma oranı %95 aralığı %{s.sayi(aralik[0], 0)}–%{s.sayi(aralik[1], 0)}"
              + (f", başa baş %{s.sayi(basabas, 0)}" if basabas is not None else ""))
    return (f'<svg class="guven-aralik" viewBox="0 0 {g:g} 42" role="img" aria-label="{escape(etiket)}">'
            f"<title>{escape(etiket)}</title>"
            f'<rect class="zemin" x="4" y="8" width="{g - 8:g}" height="12" rx="6"/>'
            f'<rect class="bant" x="{x(aralik[0]):.1f}" y="8" width="{max(2.0, x(aralik[1]) - x(aralik[0])):.1f}" '
            f'height="12" rx="6"/>{cizgi}</svg>')


def _bot_karti(b: dict, v: dict) -> str:
    h = b["hukum"]
    ad = escape(str(b.get("ad") or b.get("bot") or "?"))
    if b["islem"] == 0:
        return (f'<div class="kose kart guven-kart"><div class="guven-ust"><h3>{ad}</h3>'
                f'<span class="guven-rozet notr">● Henüz işlem yok</span></div>'
                f'<p class="bos">Bu botun sınavda kapanmış işlemi yok; güven ölçülemez.</p></div>')
    ogeler = []
    # 1) t ve p
    if b["t"] is None:
        tdeger = f'Veri az ({b["gun"]} gün; en az 10 gün gerekir)'
    else:
        tdeger = f't {s.sayi(b["t"], 2)} · şans olasılığı {_p_metni(b["p"])} ({b["gun"]} gün)'
    ogeler.append(_oge("Gün bazında t değeri", tdeger,
                       "t, günlük sonucun ortalamasının dalgalanmasına oranıdır; ±2,5'e ulaşmadıkça "
                       "sonuç şanstan ayırt edilemez. Yükselirse: izle, sınav sonu kararında dikkate al."))
    # 2) işlem sayısı
    hiz = b.get("hiz")
    if hiz:
        if hiz["eksik"] == 0:
            hmetin = f'{b["islem"]} / {hiz["hedef"]} işlem: ölçüt sağlandı'
            heylem = "İşlem sayısı yeterli; artık öbür ölçütlere bak."
        elif hiz["gereken_gun"] is None:
            hmetin = f'{b["islem"]} / {hiz["hedef"]} işlem; hız ölçülemedi'
            heylem = "Henüz hız yok; birkaç gün izle."
        else:
            hmetin = (f'{b["islem"]} / {hiz["hedef"]} işlem; günde {s.sayi(hiz["gunluk_hiz"], 1)} işlemle '
                      f'{hiz["eksik"]} işlem için ~{s.sayi(hiz["gereken_gun"], 0)} gün gerekir')
            heylem = ("Bu hızla sınav bitmeden ulaşılmaz; karar az veriyle verilecek demektir, Claude'a sor."
                      if hiz["yetisir"] is False else "Bu hızla sınav içinde ulaşılır; izle.")
    else:
        hmetin = f'{b["islem"]} / {v["hedef_islem"]} işlem (sınav başlamadı)'
        heylem = "Sınav başlayınca sayılır."
    ogeler.append(_oge("İşlem sayısı yeterli mi", hmetin, heylem))
    # 3) Wilson
    konum_metni, konum_sinif = KONUM[b["konum"]]
    if b["wilson"]:
        wdeger = (f'%{s.sayi(b["kazanma_orani"], 0)} kazanma; %95 aralık %{s.sayi(b["wilson"][0], 0)}–'
                  f'%{s.sayi(b["wilson"][1], 0)} · <span class="{konum_sinif}">{konum_metni}</span>')
    else:
        wdeger = "veri yok"
    ogeler.append(_oge("Kazanma oranı, güven aralığıyla", wdeger,
                       "Aralık, gerçek kazanma oranının %95 olasılıkla bulunduğu bölgedir (Wilson yöntemi). "
                       "Aralık başa başın altına inerse: Claude'a sor.",
                       _aralik_svg(b["wilson"], b["basabas"])))
    # 4) coin
    c = b["coin"]
    if c["en_iyi"] is None:
        cdeger = "Tek coin işlem görmüş; bağımlılık ölçülemez"
    else:
        cdeger = (f'En iyi coin {s._parite(c["en_iyi"]["parite"])} çıkarılırsa '
                  f'<span class="{s._isaret_sinifi(c["en_iyisiz"])}">{s.isaretli(c["en_iyisiz"])} USDT</span>; '
                  f'en kötü {s._parite(c["en_kotu"]["parite"])} çıkarılırsa '
                  f'<span class="{s._isaret_sinifi(c["en_kotusuz"])}">{s.isaretli(c["en_kotusuz"])} USDT</span>')
        if c["tek_coine_bagli"]:
            cdeger += ' · <span class="uyari">● artı tek coine bağlı</span>'
    ogeler.append(_oge("Tek coine bağlı mı", cdeger,
                       "Artı tek coinden geliyorsa tekrar etmeyebilir; sınav sonu kararında dikkate al."))
    # 5) en iyi gün
    g = b["en_iyi_gun"]
    if g["kalan"] is None:
        gdeger = "Tek gün var; ölçülemez"
    else:
        gdeger = (f'En iyi gün ({escape(str(g["en_iyi_gun"]))}, {s.isaretli(g["en_iyi_gun_net"])} USDT) çıkarılırsa '
                  f'<span class="{s._isaret_sinifi(g["kalan"])}">{s.isaretli(g["kalan"])} USDT</span>')
        if g["tek_gune_bagli"]:
            gdeger += ' · <span class="uyari">● artı tek güne bağlı</span>'
    ogeler.append(_oge("En iyi gün çıkarılırsa", gdeger,
                       "Bütün kâr bir günden geliyorsa bu şanstır; izle."))
    # 6) 12 aylık test
    if b["gecmis_beklenti"] is None:
        tdeger2 = "12 aylık test sonucu sunucuda bu sayfaya ulaşmadı"
    else:
        tdeger2 = (f'12 aylık test {s.isaretli_yuzde(b["gecmis_beklenti"], 3)} · sanal '
                   f'{s.isaretli_yuzde(b["sanal_beklenti"], 3)} (fark {s.isaretli(b["beklenti_farki"], 3)} puan)')
        if b["sanal_beklenti"] is not None and (b["sanal_beklenti"] > 0) != (b["gecmis_beklenti"] > 0):
            tdeger2 += ' · <span class="uyari">● yönler ters</span>'
    ogeler.append(_oge("12 aylık test ile sanal işlem", tdeger2,
                       "İkisi de işlem başına net sonuç, işlem tutarının yüzdesi. Sanal çok daha iyiyse "
                       "bu ay şanslı olabilir; sınav sonu kararında dikkate al."))
    return (f'<div class="kose kart guven-kart"><div class="guven-ust"><h3>{ad}</h3>'
            f'<span class="guven-rozet {h["sinif"]}">{ISARET.get(h["sinif"], "")}{escape(h["metin"])}</span></div>'
            f'<p class="alt">{b["islem"]} işlem · net <span class="{s._isaret_sinifi(b["net_tutar"])}">'
            f'{s.isaretli(b["net_tutar"])} USDT</span></p>'
            f'<ul class="guven-liste">{"".join(ogeler)}</ul></div>')


def _neden(v: dict) -> str:
    t = v["toplam"]
    if t["islem"] == 0:
        return "Sınavda henüz kapanmış işlem yok; güven ölçülecek bir şey yok."
    parca = []
    if t["t"] is None:
        parca.append(f'Toplamda {t["gun"]} gün var; t değeri için en az 10 gün gerekir.')
    else:
        parca.append(f'Bütün botların günlük toplamında t {s.sayi(t["t"], 2)}, şans olasılığı {_p_metni(t["p"])} '
                     f'({t["gun"]} gün).')
    eksik = [b for b in v["botlar"] if b["islem"] < v["hedef_islem"]]
    if eksik:
        parca.append(f'{len(eksik)} / {len(v["botlar"])} bot sınav ölçütü olan {v["hedef_islem"]} işleme ulaşmadı.')
    parca.append("Yeşil rozet için hepsi gerekir: t en az 2,5, şans olasılığı en çok %1, en az "
                 f'{v["hedef_islem"]} işlem, kazanma aralığı başa başın üstünde, artı tek coine ya da tek güne bağlı değil.')
    return " ".join(parca)


def ekran(ozet: dict, saat_dilimi: str) -> str:
    v = (ozet.get("ek") or {}).get("guven") or {}
    t = v["toplam"]
    h = t["hukum"]
    if v["sinavda"]:
        sayac = f'Sınavın {v["sinav_gunu"]}. günü'
        if v["kalan_gun"] is not None:
            sayac += f'; karara {s.sayi(v["kalan_gun"], 0)} gün kaldı'
    else:
        sayac = "Sınav henüz başlamadı"
    kartlar = "".join(_bot_karti(b, v) for b in v["botlar"]) or '<p class="bos">Bot yok.</p>'
    ilk = h["metin"]
    return f"""<section id="guven" class="ekran">
<h2 class="ekran-baslik">Güven</h2>
<p class="ekran-ozet">Sonuçlara güvenebilir miyim? {escape(sayac)}.</p>
<div class="guven-hukum {h['sinif']}"><strong>Bugün için: {ISARET.get(h['sinif'], '')}{escape(ilk)}</strong>
<p>{_neden(v)}</p>
<p>Tek dönem uyarısı: bu 30 gün tek bir piyasa dönemidir; burada iyi görünen bir sonuç başka dönemde tekrar etmeyebilir.
12 aylık testlerde ve panel sınamasında hiçbir strateji kalıcı kenar (şanstan ayırt edilebilir, süren üstünlük) göstermedi.</p>
<p>Çoklu bakış uyarısı: {len(v['botlar'])} bot × {4} ölçü ve toplam, yani {v['bakis']} sayıya bakılıyor. Hiçbir botta
kenar olmasa bile en az birinin şans eseri "anlamlı" görünme olasılığı yaklaşık {s.yuzde(v['coklu_bakis_olasiligi'] * 100, 0)}.
Tek bir iyi sayıya güvenme.</p></div>
<div class="g-kartlar">{kartlar}</div>
<details class="aciklama-kutu guven-kutu"><summary>Bu sayılar nasıl hesaplanıyor</summary>
<p>Şans olasılığı (p değeri): kenar hiç yokken bu kadar iyi ya da kötü bir sonucun şans eseri çıkma olasılığı. {escape(v['yaklasim'])}</p>
<p>Kazanma aralığı Wilson yöntemiyle %95 güvenle hesaplanır. Başa baş oranı, ortalama kazanç ve kayıpla kâra
geçmek için gereken en düşük kazanma oranıdır.</p>
<p>İşlem hızı sınavın başından bugüne geçen günle ölçülür; sınav ölçütü {v['hedef_islem']} işlemdir.</p>
</details>
</section>"""
