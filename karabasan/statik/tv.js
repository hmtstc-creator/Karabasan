/* Karabasan TV panosu: yalnız okur (GET /api/ozet), hiçbir şeyi değiştirmez. Eski TV tarayıcıları için ES5 + XHR.
   Ekranlar SURE_MS'de bir döner; veri YENILE_MS'de bir yenilenir. Veri gelmezse son bilinen hal "eski" uyarısıyla durur. */
(function () {
'use strict';
var SURE_MS = 12000, YENILE_MS = 60000, ESKI_SN = 300;
var ana = document.getElementById('ana'), noktalar = document.getElementById('noktalar'), notYer = document.getElementById('not');
var ozet = null, alinan = 0, sira = 0, hata = false;

function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
function tr(n, k) { return Number(n).toLocaleString('tr-TR', { minimumFractionDigits: k, maximumFractionDigits: k }); }
function para(n) { n = Number(n) || 0; return (n > 0 ? '+' : n < 0 ? '−' : '') + tr(Math.abs(n), 2); }
function sinif(n) { return n > 0 ? 'arti' : n < 0 ? 'eksi' : 'sl'; }
function saatYaz() {
  var d = new Date(); var p = function (x) { return (x < 10 ? '0' : '') + x; };
  document.getElementById('saat').textContent = p(d.getHours()) + ':' + p(d.getMinutes());
}

function ekranGenel(o) {
  var t = o.toplam || {};
  return '<div class="buyuk"><div class="tv-baslik">Toplam sonuç (sanal)</div>' +
    '<div class="sayi r ' + sinif(t.net_tutar) + '">' + para(t.net_tutar) + '</div><div class="alt">USDT</div></div>' +
    '<div class="uclu">' +
    '<div><b class="r ' + sinif(t.son_24s_net_tutar) + '">' + para(t.son_24s_net_tutar) + '</b><span>son 24 saat</span></div>' +
    '<div><b class="r">' + (t.islem_sayisi || 0) + '</b><span>işlem</span></div>' +
    '<div><b class="r ay">' + (t.acik_pozisyon || 0) + '</b><span>açık işlem</span></div>' +
    '<div><b class="r ' + (t.acik_stopta_kayip < 0 ? 'eksi' : 'sl') + '">' + para(t.acik_stopta_kayip) + '</b><span>stop olursa</span></div></div>';
}

function ekranBotlar(o) {
  var s = '<div class="tv-baslik">Botlar</div><div class="botlar">';
  (o.botlar || []).forEach(function (b) {
    s += '<div class="bot"><div class="ad"><b>' + esc(b.kod) + '</b><span>' + (b.calisiyor ? 'çalışıyor' : 'durdu') + (b.kaldirac ? ' · ' + b.kaldirac + ' kat' : '') + '</span></div>' +
      '<div class="net r ' + sinif(b.net_tutar) + '">' + para(b.net_tutar) + ' <small class="sl" style="font-size:.35em">USDT</small></div>' +
      '<div class="sat">' + (b.islem_sayisi || 0) + ' işlem · ' + (b.kazanma_orani == null ? '–' : '%' + tr(b.kazanma_orani, 0) + ' kazanan') + ' · ' + (b.acik_pozisyon || 0) + ' açık</div></div>';
  });
  return s + '</div>';
}

function ekranGunler(o) {
  var g = (o.gunluk || []).slice(-14), en = 0.01, i;
  for (i = 0; i < g.length; i++) en = Math.max(en, Math.abs(g[i].net_tutar || 0));
  var s = '<div class="tv-baslik">Gün gün sonuç (son ' + g.length + ' gün, USDT)</div><div class="cubuklar"><div class="sifir" style="top:50%"></div>';
  for (i = 0; i < g.length; i++) {
    var n = g[i].net_tutar || 0, h = Math.abs(n) / en * 46, gun = String(g[i].gun || '').slice(5).replace('-', '.');
    var st = n >= 0 ? 'bottom:50%;height:' + h + '%;background:#6fdcae' : 'top:50%;height:' + h + '%;background:#ff8a7a';
    var et = n >= 0 ? 'bottom:' + (50 + h) + '%' : 'top:' + (50 + h) + '%';
    s += '<div class="cubuk"><i style="' + st + '"></i><strong class="r ' + sinif(n) + '" style="' + et + '">' + tr(n, 1) + '</strong><em class="r" style="bottom:-3.8vh">' + esc(gun) + '</em></div>';
  }
  return s + '</div><div class="tv-not2">Yeşil: kazançlı gün · kırmızı: zararlı gün</div>';
}

function ekranAcik(o) {
  var a = o.acik_islemler || [];
  if (!a.length) return '<div class="tv-baslik">Açık işlemler</div><div class="bos2">Şu an açık işlem yok.</div>';
  var s = '<div class="tv-baslik">Açık işlemler (' + a.length + ')</div><table class="liste"><tr><th>Bot</th><th>Coin</th><th>Giriş fiyatı</th><th class="s">Stop olursa</th></tr>';
  a.slice(0, 8).forEach(function (x) {
    s += '<tr><td>' + esc(String(x.bot || '').replace('-vadeli', '').toUpperCase()) + '</td><td>' + esc(String(x.parite || '').split('/')[0]) +
      '</td><td class="r">' + esc(x.giris_fiyati) + '</td><td class="s r ' + sinif(x.stopta_kayip) + '">' + (x.stopta_kayip == null ? '–' : para(x.stopta_kayip)) + '</td></tr>';
  });
  return s + '</table>' + (a.length > 8 ? '<div class="tv-not2">… ve ' + (a.length - 8) + ' işlem daha</div>' : '');
}

var EKRANLAR = [ekranGenel, ekranBotlar, ekranGunler, ekranAcik];

function noktaYaz() {
  var s = ''; for (var i = 0; i < EKRANLAR.length; i++) s += '<span' + (i === sira ? ' class="on"' : '') + '></span>';
  noktalar.innerHTML = s;
}
function durumYaz() {
  var yas = alinan ? Math.round((Date.now() - alinan) / 1000) : null;
  if (hata && yas === null) { notYer.textContent = 'Veri alınamadı. Yeniden deniyor…'; notYer.className = 'tv-not uyari'; return; }
  if (yas !== null && yas > ESKI_SN) { notYer.textContent = 'Dikkat: veri ' + Math.round(yas / 60) + ' dakikadır yenilenemiyor.'; notYer.className = 'tv-not uyari'; return; }
  notYer.textContent = 'Sanal işlem. Gerçek para yok.'; notYer.className = 'tv-not';
}
function ciz() {
  if (!ozet) return;
  var v = ozet.donem === 'sinav' ? 'Sınav ' + ozet.gun + ' / ' + ozet.sinav_gun + '. gün' : ozet.donem === 'isinma' ? 'Isınma dönemi' : 'Sanal dönem';
  var t = ozet.toplam || {};
  document.getElementById('sinav').textContent = v + ' · ' + (t.calisan_bot || 0) + ' / ' + (t.bot_sayisi || 0) + ' bot çalışıyor';
  ana.innerHTML = EKRANLAR[sira](ozet); noktaYaz(); durumYaz();
}
function don() {
  sira = (sira + 1) % EKRANLAR.length;
  ana.className = 'tv-ana gizli';
  setTimeout(function () { ciz(); ana.className = 'tv-ana'; }, 500);
}

function yukle() {
  var x = new XMLHttpRequest();
  x.open('GET', '/api/ozet', true); x.timeout = 20000;
  x.onload = function () {
    if (x.status !== 200) { hata = true; durumYaz(); return; }
    try { ozet = JSON.parse(x.responseText); alinan = Date.now(); hata = false; ciz(); } catch (e) { hata = true; durumYaz(); }
  };
  x.onerror = x.ontimeout = function () { hata = true; durumYaz(); };
  x.send();
}

// Sabit ekran görüntüsü için: /tv?ekran=2 (1'den başlar) dönmeyi durdurur ve o ekranı gösterir.
var m = /[?&]ekran=(\d+)/.exec(location.search), sabit = m ? Math.min(Math.max(parseInt(m[1], 10), 1), EKRANLAR.length) - 1 : -1;
if (sabit >= 0) sira = sabit;
saatYaz(); setInterval(saatYaz, 20000);
yukle(); setInterval(yukle, YENILE_MS); setInterval(durumYaz, 30000);
if (sabit < 0) setInterval(don, SURE_MS);
// Ekranın uyumaması için (destekleyen tarayıcıda); desteklemeyenler sessizce geçer.
try { if (navigator.wakeLock) navigator.wakeLock.request('screen').catch(function () {}); } catch (e) { /* yok say */ }
})();
