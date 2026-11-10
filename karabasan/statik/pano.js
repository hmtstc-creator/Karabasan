/* Karabasan panosu: Uzay, Ayar ve geçmiş test, Ajan. Yalnız bu sunucudaki /api/ adresleriyle konuşur.
   Buradaki hiçbir şey canlı botu değiştirmez: ayarlar denemedir, kayıtlar deneme listesidir. */
(function () {
'use strict';
var $ = function (i) { return document.getElementById(i); };
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
function tr(x, n) { return Number(x).toFixed(n == null ? 2 : n).replace('.', ','); }
function isr(x, n) { return (x > 0 ? '+' : x < 0 ? '−' : '') + tr(Math.abs(x), n); }
function sayiYaz(x) { return String(Math.round(x * 10000) / 10000).replace('.', ','); }
function kis(x, a, b) { return Math.max(a, Math.min(b, x)); }
function pop(m) { var n = 0; while (m) { n += m & 1; m = Math.floor(m / 2); } return n; }
function sinif(x) { return x > 0 ? 'arti' : x < 0 ? 'eksi' : ''; }
var AZHAREKET = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
function sakla(ad, v) { try { localStorage.setItem(ad, JSON.stringify(v)); } catch (e) { /* özel pencere */ } }
function oku(ad, yoksa) { try { var v = JSON.parse(localStorage.getItem(ad)); return v == null ? yoksa : v; } catch (e) { return yoksa; } }

function api(yol, govde) {
  var sec = govde ? { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Karabasan': '1' }, body: JSON.stringify(govde) } : {};
  sec.credentials = 'same-origin';
  return fetch(yol, sec).then(function (y) {
    return y.text().then(function (m) {
      var v; try { v = JSON.parse(m); } catch (e) { v = null; }
      if (!y.ok || !v) throw new Error(v && v.hata ? v.hata : (y.status === 405 ? 'Bu adresten yazma kapalı.' : 'Sunucu yanıt vermedi (' + y.status + ').'));
      return v;
    });
  }, function () { throw new Error('Bağlantı kurulamadı.'); });
}

/* ------------------------------------------------------------------ durum */
var BOTLAR = ['smk-vadeli', 'smdk-vadeli', 'smk2-vadeli', 'smdk2-vadeli'];
var bot = oku('kb-bot', BOTLAR[0]); if (BOTLAR.indexOf(bot) < 0) bot = BOTLAR[0];
var ayarlar = oku('kb-ayar', {});          // bot → {degerler:{yol:sayı}, pasif:[...]}
var semalar = {};                          // bot → /api/bot yanıtı
var ozet = null;                           // /api/ozet
var gorunum = 'uzay';
function ayar() { var a = ayarlar[bot]; if (!a || typeof a !== 'object') a = ayarlar[bot] = { degerler: {}, pasif: [] }; if (!a.degerler) a.degerler = {}; if (!Array.isArray(a.pasif)) a.pasif = []; return a; }
function degisti() { var a = ayar(); return Object.keys(a.degerler).length > 0 || a.pasif.length > 0; }
function sema() { return semalar[bot]; }
function botKodu(b) { return (b || bot).replace('-vadeli', '').toUpperCase(); }
function tumSayilar(s) { var l = []; s.sartlar.forEach(function (x) { l = l.concat(x.sayilar); }); return l.concat(s.gostergeler, s.giris_emri, s.cikis, s.pozisyon); }
function canliDeger(yol) { var l = tumSayilar(sema()); for (var i = 0; i < l.length; i++) if (l[i].yol === yol) return l[i].deger; return null; }
function simdikiDeger(s) { var d = ayar().degerler[s.yol]; return d == null ? s.deger : d; }

/* ------------------------------------------------------------------ uzay: veri */
var GRUP_RENK = ['#cfcfcf', '#7fc8ff', '#f3d9a4', '#6fdcae'];
var U = null, COIN = [], NC = 0, ADIM = 288, NS = 10, G = 1.0;
var T = 287, oynuyor = false, secili = -1, ustunde = -1, kirli = true, sekme = 'coin', uzaySira = 0, uzayYukleniyor = false;
var F = { enEksik: 99, grup: [true, true, true, true], acik: false, iz: true, et: true, ara: '' };
var S = [], gor = [], hed = new Float32Array(0), sim = new Float32Array(0), ekr = new Float32Array(0);
var seri = { yak: [], gir: [] }, olay = [], olayCan = 0, acik = {};
function H(c, b) { var ad = COIN[c].ad, h = b * 7919; for (var i = 0; i < ad.length; i++) h = (h * 31 + ad.charCodeAt(i)) % 104729; var s = Math.sin(h * 12.9898) * 43758.5453; return s - Math.floor(s); }
function durumAt(c, i) {
  var m = COIN[c].eksik[i] || 0, un = 0, vx = 0, vy = 0, say = [0, 0, 0, 0];
  for (var k = 0; k < NS; k++) if (Math.floor(m / Math.pow(2, k)) % 2) { var g = U.sartlar[k].grup, a = g * Math.PI / 2 + Math.PI / 4; un++; vx += Math.cos(a); vy += Math.sin(a); say[g]++; }
  var gr = -1, en = 0; for (var q = 0; q < 4; q++) if (say[q] > en) { en = say[q]; gr = q; }
  return { un: un, g: gr, vx: vx, vy: vy, m: m };
}
function konumAt(c, i, s, o, k) {
  s = s || durumAt(c, i);
  var oz = H(c, 31) * 6.283, aci = Math.atan2(s.vy + .25 * Math.sin(oz), s.vx + .25 * Math.cos(oz)) + (H(c, 99) - .5) * .9;
  var r = s.un ? s.un * G + (H(c, 12) - .5) * .5 : .12 + .22 * H(c, 12);
  var f = COIN[c].fiyat, y = f[0] ? kis((f[i] / f[0] - 1) * 20, -2.2, 2.2) * (s.un ? 1 : .15) : 0;
  o[k] = r * Math.cos(aci); o[k + 1] = y; o[k + 2] = r * Math.sin(aci);
}
var _a = [0, 0, 0], _b = [0, 0, 0], _c = [0, 0, 0];
function konum(c, t, o, k) {
  t = kis(t, 0, ADIM - 1); var i0 = Math.floor(t), i1 = Math.min(ADIM - 1, i0 + 1), f = t - i0;
  konumAt(c, i0, null, _a, 0); if (f < 1e-6) { o[k] = _a[0]; o[k + 1] = _a[1]; o[k + 2] = _a[2]; return; }
  konumAt(c, i1, null, _b, 0); o[k] = _a[0] + (_b[0] - _a[0]) * f; o[k + 1] = _a[1] + (_b[1] - _a[1]) * f; o[k + 2] = _a[2] + (_b[2] - _a[2]) * f;
}
function adimNo() { return kis(Math.round(T), 0, ADIM - 1); }
function gorunur(c, s) {
  if (s.un > F.enEksik) return false; if (s.g >= 0 && !F.grup[s.g]) return false;
  if (F.acik && !acik[COIN[c].ad]) return false; if (F.ara && COIN[c].ad.indexOf(F.ara) < 0) return false; return true;
}
function saatYaz(i) { var d = new Date(new Date(U.bitis).getTime() - (ADIM - 1 - i) * U.adim_dakika * 60000); return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2); }
function eksikYazi(s) { return s.un ? s.un + ' şart eksik' : 'girişte'; }

function uzayYukle(sessiz) {
  var sira = ++uzaySira, a = ayar(), q = '/api/uzay?bot=' + encodeURIComponent(bot);
  if (degisti()) q += '&ayar=' + encodeURIComponent(JSON.stringify(a));
  uzayYukleniyor = true;
  if (!sessiz || !U) { $('uzayDurum').hidden = false; $('uzayDurum').textContent = U ? 'Yeniden hesaplanıyor…' : 'Mumlar indiriliyor ve şartlar hesaplanıyor…'; }
  api(q).then(function (v) {
    if (sira !== uzaySira) return;
    uzayYukleniyor = false; uzayKur(v); if (gl) $('uzayDurum').hidden = true;
  }, function (h) { if (sira !== uzaySira) return; uzayYukleniyor = false; $('uzayDurum').hidden = false; $('uzayDurum').textContent = h.message + ' Biraz sonra yeniden denenecek.'; });
}
function uzayKur(v) {
  var sonda = !U || T >= ADIM - 1.05, eskiSecili = secili >= 0 && COIN[secili] ? COIN[secili].ad : null;
  U = v; COIN = v.coinler.filter(function (c) { return c.eksik && c.eksik.length; });
  NC = COIN.length; ADIM = v.adim || 1; NS = v.sartlar.length;
  if (hed.length !== NC * 3) { hed = new Float32Array(NC * 3); sim = new Float32Array(NC * 3); ekr = new Float32Array(NC * 3); S = new Array(NC); gor = new Array(NC); coinleriKur(); for (var c = 0; c < NC; c++) konum(c, ADIM - 1, sim, c * 3); }
  secili = -1; if (eskiSecili) for (var i = 0; i < NC; i++) if (COIN[i].ad === eskiSecili) secili = i;
  $('zamanK').max = ADIM - 1; if (sonda || T > ADIM - 1) { T = ADIM - 1; $('zamanK').value = T; }
  $('enEksik').max = NS; if (F.enEksik > NS) { F.enEksik = NS; } $('enEksik').value = Math.min(F.enEksik, NS); enEksikYaz();
  $('uzayRozet').hidden = !v.degisti;
  acikHesapla(); akisHesapla(); kirli = true; if (sekme === 'hizli') hizliSay();
}
function enEksikYaz() { $('enEksikYazi').textContent = F.enEksik >= NS ? 'hepsi (' + NS + ')' : F.enEksik; }
function acikHesapla() { acik = {}; if (!ozet) return; (ozet.acik_islemler || []).forEach(function (i) { if (i.bot === bot) acik[String(i.parite).split('/')[0]] = i; }); }
function akisHesapla() {
  seri.yak = []; seri.gir = []; olay = []; olayCan = 0; var once = [], onceC = [];
  for (var t = 0; t < ADIM; t++) {
    var y = 0, g = 0;
    for (var c = 0; c < NC; c++) {
      var u = pop(COIN[c].eksik[t]), uc = COIN[c].canli ? pop(COIN[c].canli[t]) : u;
      if (u === 0) { g++; if (t && once[c] > 0) olay.push({ c: c, t: t }); } else if (u <= 2) y++;
      if (uc === 0 && t && onceC[c] > 0) olayCan++; once[c] = u; onceC[c] = uc;
    }
    seri.yak.push(y); seri.gir.push(g);
  }
  var mx = Math.max(4, Math.max.apply(0, seri.yak.concat(seri.gir))), h = '', w = 960 / ADIM, d = 'M0 54';
  seri.yak.forEach(function (v, i) { d += 'L' + (i * w).toFixed(1) + ' ' + (52 - 44 * v / mx).toFixed(1) + 'L' + ((i + 1) * w).toFixed(1) + ' ' + (52 - 44 * v / mx).toFixed(1); });
  h += '<path d="' + d + 'L960 54Z" fill="#cfcfcf" fill-opacity=".22"/>';
  seri.gir.forEach(function (v, i) { if (v) h += '<rect x="' + (i * w).toFixed(1) + '" y="' + (52 - 44 * v / mx).toFixed(1) + '" width="' + Math.max(1.5, w - .6).toFixed(1) + '" height="' + (44 * v / mx).toFixed(1) + '" fill="#f3d9a4"/>'; });
  olay.forEach(function (o) { h += '<rect x="' + (o.t * w).toFixed(1) + '" y="0" width="1.5" height="6" fill="#f3d9a4"/>'; });
  h += '<rect x="0" y="52" width="960" height="1" fill="#2b2b2b"/><rect id="imlec" x="0" y="0" width="2" height="54" fill="#f4f4f4"/>';
  $('akis').innerHTML = h;
}

/* ------------------------------------------------------------------ uzay: üç boyut */
var cv = $('cv'), kap = $('uzay'), etk = $('etiketler'), gl = null, sahne, kam, mesh = [], isik = [], hale = [], kuyruk = [], sap = null, cekIsik, W = 1, Hh = 1;
var yor = { th: .7, ph: 1.02, d: 15, hth: .7, hph: 1.02, hd: 15, dokundu: false }, ETs = [], SEKs = [], HALs = [], IZ = 24, parlak, cember, kure, AY3, MOR3, BEYAZ3, v3;
function doku(ciz) { var k = document.createElement('canvas'); k.width = k.height = 128; ciz(k.getContext('2d')); return new THREE.CanvasTexture(k); }
function sahneKur() {
  if (!window.THREE) throw new Error('three yok');
  gl = new THREE.WebGLRenderer({ canvas: cv, antialias: true }); gl.setPixelRatio(Math.min(2, window.devicePixelRatio || 1)); gl.setClearColor(0x000000, 1);
  sahne = new THREE.Scene(); sahne.fog = new THREE.Fog(0x000000, 22, 60); kam = new THREE.PerspectiveCamera(42, 1, .1, 300);
  AY3 = new THREE.Color(0xf3d9a4); MOR3 = new THREE.Color(0x5f5f5f); BEYAZ3 = new THREE.Color(0xfff6de); v3 = new THREE.Vector3();
  parlak = doku(function (x) { var g = x.createRadialGradient(64, 64, 0, 64, 64, 64); g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(.25, 'rgba(255,255,255,.35)'); g.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = g; x.fillRect(0, 0, 128, 128); });
  cember = doku(function (x) { x.strokeStyle = '#fff'; x.lineWidth = 7; x.beginPath(); x.arc(64, 64, 54, 0, 6.283); x.stroke(); });
  kure = new THREE.SphereGeometry(1, 18, 14);
  var yp = new Float32Array(1500 * 3);
  for (var i = 0; i < 1500; i++) { var u = Math.random() * 2 - 1, a = Math.random() * 6.283, rr = 38 + Math.random() * 30, q = Math.sqrt(1 - u * u); yp[i * 3] = rr * q * Math.cos(a); yp[i * 3 + 1] = rr * u; yp[i * 3 + 2] = rr * q * Math.sin(a); }
  var yg = new THREE.BufferGeometry(); yg.setAttribute('position', new THREE.BufferAttribute(yp, 3));
  sahne.add(new THREE.Points(yg, new THREE.PointsMaterial({ color: 0xd6d6d6, size: .22, transparent: true, opacity: .75, fog: false })));
  for (var k = 1; k <= 10; k++) {
    var hp = []; for (var j = 0; j < 128; j++) { var aa = j / 128 * 6.283; hp.push(k * G * Math.cos(aa), 0, k * G * Math.sin(aa)); }
    var hg = new THREE.BufferGeometry(); hg.setAttribute('position', new THREE.Float32BufferAttribute(hp, 3));
    sahne.add(new THREE.LineLoop(hg, new THREE.LineBasicMaterial({ color: k <= 2 ? 0xf3d9a4 : 0xcfcfcf, transparent: true, opacity: k <= 2 ? .5 : .2 })));
  }
  var bp = []; for (var g = 0; g < 4; g++) { var ba = g * Math.PI / 2; bp.push(.7 * Math.cos(ba), 0, .7 * Math.sin(ba), 10.4 * Math.cos(ba), 0, 10.4 * Math.sin(ba)); }
  var bg = new THREE.BufferGeometry(); bg.setAttribute('position', new THREE.Float32BufferAttribute(bp, 3));
  sahne.add(new THREE.LineSegments(bg, new THREE.LineBasicMaterial({ color: 0xf4f4f4, transparent: true, opacity: .13 })));
  sahne.add(new THREE.Mesh(new THREE.SphereGeometry(.3, 32, 24), new THREE.MeshBasicMaterial({ color: 0xfff1cf })));
  cekIsik = new THREE.Sprite(new THREE.SpriteMaterial({ map: parlak, color: 0xf3d9a4, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true })); cekIsik.scale.set(3.6, 3.6, 1); sahne.add(cekIsik);
  ['Büyük yön', 'Bölge', 'Tetik', 'Hacim'].forEach(function (ad, i) { var e = document.createElement('div'); e.className = 'sek'; e.style.color = GRUP_RENK[i]; e.textContent = ad; etk.appendChild(e); SEKs.push(e); });
  [1, 2, 4, 6, 8, 10].forEach(function (k) { var e = document.createElement('div'); e.className = 'hal'; e.textContent = k + ' eksik'; e.dataset.k = k; etk.appendChild(e); HALs.push(e); });
  new ResizeObserver(boyut).observe(kap); boyut();
}
function coinleriKur() {
  if (!gl) return;
  mesh.concat(isik, hale, kuyruk, sap ? [sap] : []).forEach(function (o) { if (o) sahne.remove(o); });
  ETs.forEach(function (e) { e.remove(); }); mesh = []; isik = []; hale = []; kuyruk = []; ETs = [];
  for (var c = 0; c < NC; c++) {
    var m = new THREE.Mesh(kure, new THREE.MeshBasicMaterial({ color: 0xcfcfcf, transparent: true })); sahne.add(m); mesh.push(m);
    var sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: parlak, color: 0xcfcfcf, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true })); sahne.add(sp); isik.push(sp);
    var hl = new THREE.Sprite(new THREE.SpriteMaterial({ map: cember, color: 0x6fdcae, depthWrite: false, transparent: true })); hl.visible = false; sahne.add(hl); hale.push(hl);
    var kg = new THREE.BufferGeometry(); kg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(IZ * 3), 3));
    var kl = new THREE.Line(kg, new THREE.LineBasicMaterial({ color: 0xcfcfcf, transparent: true, opacity: .35 })); sahne.add(kl); kuyruk.push(kl);
    var e = document.createElement('div'); e.className = 'et'; e.dataset.c = c; e.hidden = true; etk.appendChild(e); ETs.push(e);
  }
  var sg = new THREE.BufferGeometry(); sg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(Math.max(1, NC) * 6), 3));
  sap = new THREE.LineSegments(sg, new THREE.LineBasicMaterial({ color: 0xcfcfcf, transparent: true, opacity: .13 })); sahne.add(sap);
}
function boyut() { W = kap.clientWidth; Hh = kap.clientHeight; if (!gl || !W || !Hh) return; gl.setSize(W, Hh, false); kam.aspect = W / Hh; kam.updateProjectionMatrix(); if (!yor.dokundu) { yor.hd = yor.d = W / Hh < .9 ? 24 : W / Hh < 1.3 ? 19 : 15.5; } }
function acikKz(i, fiyat) { var g = Number(i.giris_fiyati); if (!g || !fiyat) return null; return (i.yon === 'alim' ? (fiyat - g) : (g - fiyat)) / g * 100; }

function hedefle() {
  if (!U || !NC) return;
  var n0 = 0, n1 = 0, n2 = 0, enY = -1, enD = 99, i = adimNo(), say = [0, 0, 0, 0];
  for (var c = 0; c < NC; c++) {
    var s = durumAt(c, i); S[c] = s; gor[c] = gorunur(c, s); konum(c, T, hed, c * 3);
    if (s.un === 0) n0++; else if (s.un <= 2) n1++; else n2++;
    if (s.g >= 0) say[s.g]++;
    if (s.un > 0 && s.un < enD) { enD = s.un; enY = c; }
    if (gl && (s.un <= 1 || c === secili || c === ustunde)) { var p = kuyruk[c].geometry.attributes.position; for (var j = 0; j < IZ; j++) { var ox = 0, oy = 0, ozz = 0; for (var w = 0; w < 4; w++) { konum(c, T - j - w, _c, 0); ox += _c[0]; oy += _c[1]; ozz += _c[2]; } p.array[j * 3] = ox / 4; p.array[j * 3 + 1] = oy / 4; p.array[j * 3 + 2] = ozz / 4; } p.needsUpdate = true; }
  }
  $('s0').textContent = n0; $('s1').textContent = n1; $('s2').textContent = n2;
  var su = T >= ADIM - 1.02; $('anEt').textContent = (su ? 'Şu an' : 'Saat ' + saatYaz(i) + ' itibarıyla') + ' · ' + botKodu() + (U.degisti ? ' · senin ayarınla' : '');
  var gir = []; for (c = 0; c < NC; c++) if (S[c].un === 0) gir.push(COIN[c].ad);
  $('cevap').textContent = n0 ? (n0 + ' coin girişte: ' + gir.slice(0, 4).join(', ') + (n0 > 4 ? '…' : '') + '.')
    : (enY < 0 ? 'Girişte coin yok.' : 'Girişte coin yok. En yakın ' + COIN[enY].ad + ': ' + S[enY].un + ' şart eksik.');
  for (var q = 0; q < 4; q++) { var e = $('gs' + q); if (e) e.textContent = say[q]; }
  $('saat').textContent = su ? 'şimdi' : saatYaz(i); var im = $('imlec'); if (im) im.setAttribute('x', (T / Math.max(1, ADIM - 1) * 958).toFixed(1));
  if (sekme === 'coin') coinYaz();
}
function kare(z) {
  requestAnimationFrame(kare);
  if (gorunum !== 'uzay' || document.hidden) return;
  if (oynuyor) { T += .35; if (T >= ADIM - 1) { T = ADIM - 1; oyna(false); } $('zamanK').value = T; kirli = true; }
  if (kirli) { hedefle(); kirli = false; }
  if (!gl || !U) return;
  if (!yor.dokundu && !AZHAREKET) yor.hth += .0009;
  yor.th += (yor.hth - yor.th) * .12; yor.ph += (yor.hph - yor.ph) * .12; yor.d += (yor.hd - yor.d) * .12;
  kam.position.set(yor.d * Math.sin(yor.ph) * Math.cos(yor.th), yor.d * Math.cos(yor.ph), yor.d * Math.sin(yor.ph) * Math.sin(yor.th)); kam.lookAt(0, -.4, 0); kam.updateMatrixWorld();
  var nab = 1 + .08 * Math.sin(z * .003); cekIsik.scale.set(3.6 * nab, 3.6 * nab, 1);
  var sp = sap.geometry.attributes.position, hiz = AZHAREKET ? 1 : .1, sonFiyat = adimNo();
  for (var c = 0; c < NC; c++) {
    var i = c * 3; sim[i] += (hed[i] - sim[i]) * hiz; sim[i + 1] += (hed[i + 1] - sim[i + 1]) * hiz; sim[i + 2] += (hed[i + 2] - sim[i + 2]) * hiz;
    var s = S[c]; if (!s) continue;
    var g = gor[c], yak = kis(s.un / 5, 0, 1), sec = c === secili || c === ustunde;
    var boy = (.11 + .1 * (1 - c / Math.max(1, NC))) * (s.un ? 1 : 1.5) * (sec ? 1.35 : 1), rk = s.un ? AY3.clone().lerp(MOR3, yak) : BEYAZ3, m = mesh[c];
    m.position.set(sim[i], sim[i + 1], sim[i + 2]); m.scale.setScalar(boy); m.material.color.copy(rk); m.material.opacity = g ? 1 : .1;
    var is = isik[c]; is.position.copy(m.position); is.scale.setScalar(boy * (s.un ? 5 + 4 * (1 - yak) : 11)); is.material.color.copy(rk); is.material.opacity = g ? (.25 + .6 * (1 - yak)) : 0;
    var ac = acik[COIN[c].ad], hl = hale[c]; hl.visible = !!ac;
    if (ac) { var kz = acikKz(ac, COIN[c].fiyat[sonFiyat]); hl.position.copy(m.position); hl.scale.setScalar(boy * 5.5); hl.material.color.setHex(kz != null && kz < 0 ? 0xff8a7a : 0x6fdcae); hl.material.opacity = g ? 1 : .12; }
    var kl = kuyruk[c]; kl.visible = F.iz && g && (s.un <= 1 || sec); kl.material.color.copy(rk); kl.material.opacity = sec ? .9 : .18 + .4 * (1 - yak);
    sp.array[c * 6] = sim[i]; sp.array[c * 6 + 1] = g ? sim[i + 1] : 0; sp.array[c * 6 + 2] = sim[i + 2]; sp.array[c * 6 + 3] = sim[i]; sp.array[c * 6 + 4] = 0; sp.array[c * 6 + 5] = sim[i + 2];
    v3.set(sim[i], sim[i + 1], sim[i + 2]).project(kam); ekr[i] = (v3.x * .5 + .5) * W; ekr[i + 1] = (-v3.y * .5 + .5) * Hh; ekr[i + 2] = v3.z;
    var e = ETs[c], gos = F.et && g && v3.z < 1 && (s.un <= 2 || sec || !!ac || F.ara.length > 1);
    if (gos) {
      if (e.hidden) e.hidden = false; e.style.transform = 'translate(' + (ekr[i] + 9).toFixed(1) + 'px,' + (ekr[i + 1] - 9).toFixed(1) + 'px)';
      var yz = esc(COIN[c].ad) + '<small>' + (s.un ? s.un + ' eksik' : 'giriş') + '</small>'; if (e._y !== yz) { e.innerHTML = yz; e._y = yz; }
      var sn = 'et' + (c === secili ? ' sec' : s.un ? '' : ' gir'); if (e.className !== sn) e.className = sn;
    } else if (!e.hidden) e.hidden = true;
  }
  sp.needsUpdate = true;
  var uzak = Math.min(10, NS) + .6;
  for (var q = 0; q < 4; q++) { var a = q * Math.PI / 2 + Math.PI / 4; v3.set(uzak * Math.cos(a), 0, uzak * Math.sin(a)).project(kam); SEKs[q].hidden = v3.z > 1; SEKs[q].style.transform = 'translate(-50%,-50%) translate(' + ((v3.x * .5 + .5) * W).toFixed(1) + 'px,' + ((-v3.y * .5 + .5) * Hh).toFixed(1) + 'px)'; SEKs[q].style.opacity = F.grup[q] ? 1 : .3; }
  HALs.forEach(function (e) { var k = +e.dataset.k; v3.set(k * G, 0, 0).project(kam); e.hidden = v3.z > 1 || k > NS; e.style.transform = 'translate(' + ((v3.x * .5 + .5) * W + 4).toFixed(1) + 'px,' + ((-v3.y * .5 + .5) * Hh + 3).toFixed(1) + 'px)'; });
  gl.render(sahne, kam);
}
var imler = {}, basX = 0, basY = 0, oynadi = false, araUz = 0;
function enYakin(x, y) { var en = -1, ed = 26 * 26; for (var c = 0; c < NC; c++) { if (!gor[c] || ekr[c * 3 + 2] > 1) continue; var dx = ekr[c * 3] - x, dy = ekr[c * 3 + 1] - y, d = dx * dx + dy * dy; if (d < ed) { ed = d; en = c; } } return en; }
function yer(e) { var r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
cv.addEventListener('pointerdown', function (e) { try { cv.setPointerCapture(e.pointerId); } catch (h) { /* yok */ } imler[e.pointerId] = [e.clientX, e.clientY]; basX = e.clientX; basY = e.clientY; oynadi = false; cv.classList.add('surukle'); var k = Object.keys(imler); if (k.length === 2) araUz = Math.hypot(imler[k[0]][0] - imler[k[1]][0], imler[k[0]][1] - imler[k[1]][1]); });
cv.addEventListener('pointermove', function (e) {
  var p = imler[e.pointerId];
  if (!p) { var y = yer(e), u = enYakin(y[0], y[1]); if (u !== ustunde) { ustunde = u; kirli = true; cv.style.cursor = u >= 0 ? 'pointer' : ''; } return; }
  var k = Object.keys(imler);
  if (k.length === 2) { imler[e.pointerId] = [e.clientX, e.clientY]; var d = Math.hypot(imler[k[0]][0] - imler[k[1]][0], imler[k[0]][1] - imler[k[1]][1]); if (araUz && d) yor.hd = kis(yor.hd * araUz / d, 6, 46); araUz = d; yor.dokundu = true; oynadi = true; return; }
  var dx = e.clientX - p[0], dy = e.clientY - p[1]; imler[e.pointerId] = [e.clientX, e.clientY];
  if (Math.abs(e.clientX - basX) + Math.abs(e.clientY - basY) > 6) { oynadi = true; yor.dokundu = true; }
  if (oynadi) { yor.hth += dx * .006; yor.hph = kis(yor.hph - dy * .005, .12, 1.5); }
});
function birak(e) { delete imler[e.pointerId]; cv.classList.remove('surukle'); araUz = 0; if (e.type === 'pointerup' && !oynadi) { var y = yer(e); sec(enYakin(y[0], y[1])); } }
cv.addEventListener('pointerup', birak); cv.addEventListener('pointercancel', birak);
cv.addEventListener('wheel', function (e) { e.preventDefault(); yor.hd = kis(yor.hd * Math.exp(e.deltaY * .0012), 6, 46); yor.dokundu = true; }, { passive: false });
etk.addEventListener('click', function (e) { var t = e.target.closest('.et'); if (t) sec(+t.dataset.c); });

/* ------------------------------------------------------------------ uzay: paneller */
function sec(c) { secili = c; if (c >= 0) sekmeAc('coin'); else coinYaz(true); }
function sekmeAc(s) {
  sekme = s; document.querySelectorAll('#uzaySekme button').forEach(function (b) { b.setAttribute('aria-selected', b.dataset.s === s); });
  ['coin', 'hizli', 'rapor'].forEach(function (x) { $('p-' + x).hidden = x !== s; });
  if (s === 'coin') coinYaz(true); if (s === 'hizli') hizliYaz(); if (s === 'rapor') raporYaz();
}
$('uzaySekme').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) sekmeAc(b.dataset.s); });
var sonCoin = 0;
function coinYaz(zorla) {
  var simdi = performance.now(); if (!zorla && oynuyor && simdi - sonCoin < 150) return; sonCoin = simdi; var el = $('p-coin');
  if (!U || !NC) { el.innerHTML = '<p class="kucuk">Veri bekleniyor…</p>'; return; }
  var i = adimNo();
  if (secili < 0 || secili >= NC) {
    var sira = []; for (var c = 0; c < NC; c++) sira.push(c); sira.sort(function (a, b) { return S[a].un - S[b].un; });
    el.innerHTML = '<div class="blok"><span class="ust">Girişe en yakın sekiz coin</span><p class="kucuk">Uzayda bir coine ya da buradan bir satıra dokun: hangi şartı geçtiğini, hangisinde takıldığını gör.</p></div><div class="liste">' +
      sira.slice(0, 8).map(function (c) { var s = S[c]; return '<button type="button" data-c="' + c + '"><b>' + esc(COIN[c].ad) + '</b><span>' + (s.un ? esc(U.gruplar[s.g].ad) + ' bekliyor' : 'Bütün şartlar doğru') + '</span><span class="r ' + (s.un ? '' : 'ayr') + '">' + eksikYazi(s) + '</span></button>'; }).join('') + '</div>';
    return;
  }
  var c2 = secili, co = COIN[c2], s2 = durumAt(c2, i), dg = co.fiyat[0] ? (co.fiyat[i] / co.fiyat[0] - 1) * 100 : 0, ac = acik[co.ad];
  var yol = '', w = 300 / ADIM, enUn = Math.max(1, NS);
  for (var t = 0; t < ADIM; t++) { var u = pop(co.eksik[t]), yy = (4 + u / enUn * 42).toFixed(1); yol += (t ? 'L' : 'M') + (t * w).toFixed(1) + ' ' + yy + 'L' + ((t + 1) * w).toFixed(1) + ' ' + yy; }
  var acYazi = '';
  if (ac) { var kz = acikKz(ac, co.fiyat[ADIM - 1]); acYazi = '<p class="kucuk">Açık işlem: giriş ' + sayiYaz(ac.giris_fiyati) + ', stop ' + sayiYaz(ac.stop_fiyati) + (kz == null ? '' : ', şu an yaklaşık <b class="r ' + sinif(kz) + '">' + isr(kz, 1) + '%</b>') + '. Uzayda çevresindeki halka bunu gösterir.</p>'; }
  el.innerHTML = '<div class="blok"><span class="ust">' + botKodu() + ' botunun gözünden' + (U.degisti ? ' · senin ayarınla' : '') + '</span><div class="dugmeler"><span class="coin-ad">' + esc(co.ad) + '</span><span class="r ' + sinif(dg) + '">' + isr(dg, 1) + '% / pencere</span></div>' +
    '<p>' + (s2.un ? '<b class="ayr">' + s2.un + ' şart eksik.</b> Çoğu şu bölgede: ' + esc(U.gruplar[s2.g].ad.toLocaleLowerCase('tr-TR')) + ' (' + esc(U.gruplar[s2.g].aciklama) + ').' : '<b class="ayr">Bütün şartlar doğru: giriş anı.</b>') + '</p>' + acYazi + '</div>' +
    '<div class="blok"><h2>24 saatte girişe ne kadar yaklaştı?</h2><svg viewBox="0 0 300 50" preserveAspectRatio="none" class="egri" style="height:50px"><rect x="0" y="3.5" width="300" height="1" fill="#f3d9a4" fill-opacity=".6"/><path d="' + yol + '" fill="none" stroke="#cfcfcf" stroke-width="1.5" vector-effect="non-scaling-stroke"/><rect x="' + (T / Math.max(1, ADIM - 1) * 298).toFixed(1) + '" y="0" width="2" height="50" fill="#f4f4f4"/></svg><p class="kucuk">Çizgi üstteki altın çizgiye değdiği an bütün şartlar doğrudur.</p></div>' +
    '<div><h2>Şartlar, tek tek</h2>' + U.sartlar.map(function (x, k) {
      var gec = !(Math.floor(s2.m / Math.pow(2, k)) % 2), dogru = 0; for (var t = 0; t < ADIM; t++) if (!(Math.floor(co.eksik[t] / Math.pow(2, k)) % 2)) dogru++;
      var oran = Math.round(100 * dogru / ADIM);
      return '<div class="satir"><span class="' + (x.pasif ? 'uy' : gec ? 'arti' : 'eksi') + '">' + (x.pasif ? '–' : gec ? '✓' : '✕') + '</span><span>' + esc(x.yazi) + (x.pasif ? ' <span class="uy">(pasif)</span>' : '') + '</span><span class="r sl">%' + oran + '</span><div class="iz"><span style="width:' + oran + '%"></span></div></div>';
    }).join('') + '<p class="kucuk" style="padding-top:8px">Yüzde ve çubuk: bu şartın son 24 saatin ne kadarında doğru olduğu.</p></div>' +
    '<div class="dugmeler"><button class="dugme mor" type="button" data-test="' + esc(co.ad) + '">Bu coinde geçmiş test</button><button class="dugme" type="button" data-c="-1">Seçimi kaldır</button></div>';
}
$('p-coin').addEventListener('click', function (e) {
  var t = e.target.closest('[data-test]'); if (t) { lab.coinler = [t.dataset.test]; sakla('kb-lab', { gun: lab.gun, coinler: lab.coinler }); location.hash = 'lab'; return; }
  var b = e.target.closest('[data-c]'); if (b) sec(+b.dataset.c);
});
function hizliYaz() {
  var s = sema(), el = $('p-hizli'); if (!s) { el.innerHTML = '<p class="kucuk">Yükleniyor…</p>'; return; }
  el.innerHTML = '<div class="blok"><span class="ust">Son 24 saatte giriş anı</span><div class="ikili"><div><b class="ayr" id="aSen">–</b><div class="kucuk">senin ayarın</div></div><div><b class="sl" id="aCan">–</b><div class="kucuk">canlı ayar</div></div></div>' +
    '<p class="kucuk">Bir şartı gevşet ya da pasif yap: coinler uzayda içeri akar. Sıkılaştır: dışarı savrulurlar. Hesap sunucuda yapılır, birkaç saniye sürer. Canlı botlar değişmez.</p>' +
    '<div class="dugmeler"><a class="dugme mor" href="#lab">Bütün ayarlar ve geçmiş test</a><button class="dugme" type="button" id="hizliSifirla">Canlı ayara dön</button></div><p class="hata-kutu" id="hizliHata" hidden></p></div>' +
    '<div id="hizliSartlar">' + s.sartlar.map(sartHtml).join('') + '</div>';
  hizliSay();
}
function hizliSay() {
  if ($('aSen')) { $('aSen').textContent = olay.length; $('aCan').textContent = U && U.degisti ? olayCan : olay.length; }
  if (!U || !NC) return; var i = adimNo();
  document.querySelectorAll('#hizliSartlar .sart').forEach(function (el) {
    var k = +el.dataset.sira, n = 0, tek = 0;
    for (var c = 0; c < NC; c++) { var m = COIN[c].eksik[i]; if (!(Math.floor(m / Math.pow(2, k)) % 2)) n++; else if (pop(m) === 1) tek++; }
    var e = el.querySelector('.sart-say'); if (e) e.innerHTML = 'şu an geçen: ' + n + ' / ' + NC + ' coin' + (tek ? ' · <span class="uy">' + tek + ' coini tek başına tutuyor</span>' : '');
  });
}
$('p-hizli').addEventListener('click', function (e) { if (e.target.id === 'hizliSifirla') { ayarlar[bot] = { degerler: {}, pasif: [] }; ayarDegisti(true); hizliYaz(); } });
function raporYaz() {
  var el = $('p-rapor'), h = '<div class="blok"><span class="ust">Giriş anları · son 24 saat' + (U && U.degisti ? ' · senin ayarınla' : '') + '</span><p class="kucuk">Birine dokun: zaman o ana sarılır, coin seçilir. Bunlar şartların doğru olduğu anlardır; canlı botun gerçekten işlem açtığı anlar klasik ekranlardadır.</p><div class="liste" id="olaylar">' +
    (olay.length ? olay.slice(-14).reverse().map(function (o) { return '<button type="button" data-t="' + o.t + '" data-c="' + o.c + '"><b>' + saatYaz(o.t) + '</b><span>' + esc(COIN[o.c].ad) + ' girişe düştü</span><span class="r ayr">git</span></button>'; }).join('') : '<p class="kucuk">Son 24 saatte giriş anı yok.</p>') + '</div></div>';
  if (ozet) {
    h += '<div class="blok"><h2>Canlı botlar (sınav başından beri, sanal)</h2><div class="kaydir"><table><thead><tr><th>Bot</th><th>İşlem</th><th>Kazanan</th><th>Net USDT</th></tr></thead><tbody>' +
      ozet.botlar.map(function (b) { return '<tr><td>' + esc(b.kod) + '</td><td>' + b.islem_sayisi + '</td><td>' + (b.kazanma_orani == null ? '–' : '%' + tr(b.kazanma_orani, 0)) + '</td><td class="' + sinif(b.net_tutar) + '">' + isr(b.net_tutar || 0) + '</td></tr>'; }).join('') +
      '</tbody></table></div><p class="kucuk">Toplam: <b class="r ' + sinif(ozet.toplam.net_tutar) + '">' + isr(ozet.toplam.net_tutar || 0) + ' USDT</b>, ' + ozet.toplam.islem_sayisi + ' işlem, ' + ozet.toplam.acik_pozisyon + ' açık işlem. Hepsi stopa giderse yaklaşık <b class="r eksi">' + isr(ozet.toplam.acik_stopta_kayip || 0) + ' USDT</b>.</p></div>';
    var g = (ozet.gunluk || []).slice(-28);
    if (g.length) {
      var mx = Math.max.apply(0, g.map(function (x) { return Math.abs(x.net_tutar || 0); })) || 1;
      h += '<div class="blok"><h2>Gün gün (son ' + g.length + ' gün, USDT)</h2><div class="takvim">' + g.map(function (x) { var v = x.net_tutar || 0, a = Math.round((Math.min(1, Math.abs(v) / mx) * .7 + .12) * 100); return '<div title="' + esc(x.gun) + '" style="background:color-mix(in srgb,var(--' + (v >= 0 ? 'arti' : 'eksi') + ') ' + a + '%,var(--yuzey2))">' + isr(v, 1) + '</div>'; }).join('') + '</div></div>';
    }
  }
  h += '<a class="dugme" href="/klasik">Ayrıntılı rapor, dersler ve işlem grafikleri (klasik ekranlar)</a>';
  el.innerHTML = h;
}
$('p-rapor').addEventListener('click', function (e) { var b = e.target.closest('#olaylar button'); if (!b) return; T = +b.dataset.t; $('zamanK').value = T; oyna(false); kirli = true; sec(+b.dataset.c); });

$('gruplar').innerHTML = ['Büyük yön', 'Bölge', 'Tetik', 'Hacim'].map(function (ad, i) { return '<label class="tik"><input type="checkbox" data-g="' + i + '" id="fg' + i + '" checked><i style="background:' + GRUP_RENK[i] + '"></i>' + ad + '<span class="r" id="gs' + i + '">0</span></label>'; }).join('');
$('gruplar').addEventListener('change', function (e) { F.grup[+e.target.dataset.g] = e.target.checked; kirli = true; });
$('enEksik').addEventListener('input', function (e) { F.enEksik = +e.target.value; enEksikYaz(); kirli = true; });
$('ara').addEventListener('input', function (e) { F.ara = e.target.value.trim().toLocaleUpperCase('en-US'); kirli = true; });
$('fAcik').addEventListener('change', function (e) { F.acik = e.target.checked; kirli = true; });
$('fIz').addEventListener('change', function (e) { F.iz = e.target.checked; });
$('fEt').addEventListener('change', function (e) { F.et = e.target.checked; });
function oyna(d) { oynuyor = d; $('oyna').textContent = d ? '❚❚' : '▶'; $('oyna').setAttribute('aria-label', d ? 'Durdur' : 'Oynat'); }
$('oyna').addEventListener('click', function () { if (!oynuyor && T >= ADIM - 1.05) T = 0; oyna(!oynuyor); });
$('zamanK').addEventListener('input', function (e) { T = +e.target.value; oyna(false); kirli = true; });
$('simdi').addEventListener('click', function () { T = ADIM - 1; $('zamanK').value = T; oyna(false); kirli = true; });

/* ------------------------------------------------------------------ ayar satırları (uzay ve laboratuvar ortak) */
function pasifMi(an) { return ayar().pasif.indexOf(an) >= 0; }
function sayiHtml(s) {
  var v = simdikiDeger(s), deg = Math.abs(v - s.deger) > 1e-9;
  return '<div class="sayi' + (deg ? ' degisti' : '') + '" data-yol="' + esc(s.yol) + '"><div class="sayi-ad">' + esc(s.ad) + (s.aciklama ? '<small>' + esc(s.aciklama) + '</small>' : '') + '</div>' +
    '<button type="button" data-y="-1" aria-label="Azalt">−</button><input type="number" inputmode="decimal" step="' + s.adim + '" value="' + v + '" aria-label="' + esc(s.ad) + '"><button type="button" data-y="1" aria-label="Artır">+</button>' +
    '<input type="range" min="' + s.alt + '" max="' + Math.max(s.ust, v) + '" step="' + s.adim + '" value="' + v + '" aria-label="' + esc(s.ad) + ' kaydırıcı">' +
    '<div class="canli"' + (deg ? '' : ' hidden') + '><span>canlı: ' + sayiYaz(s.deger) + '</span><button type="button" data-geri="1">canlıya dön</button></div></div>';
}
function sartHtml(x) {
  var an = 'k' + x.sira, p = pasifMi(an);
  return '<div class="sart' + (p ? ' pasif' : '') + '" data-sira="' + x.sira + '"><div class="sart-bas"><span class="sart-no">' + (x.sira + 1) + '</span><span class="sart-ad">' + esc(x.yazi) + '</span>' +
    '<label class="tik"><input type="checkbox" data-pasif="' + an + '"' + (p ? ' checked' : '') + '>Pasif</label></div>' +
    '<div class="kucuk">' + esc(x.anlam || '') + '</div><div class="sart-say kucuk r"></div>' + x.sayilar.map(sayiHtml).join('') + '</div>';
}
function sayiBul(yol) { var l = tumSayilar(sema()); for (var i = 0; i < l.length; i++) if (l[i].yol === yol) return l[i]; return null; }
function sayiKoy(el, v) {
  var s = sayiBul(el.dataset.yol); if (!s || isNaN(v)) return;
  v = s.tam ? Math.round(v) : Math.round(v * 10000) / 10000; if (v < 0) v = 0;
  var a = ayar(); if (Math.abs(v - s.deger) < 1e-9) delete a.degerler[s.yol]; else a.degerler[s.yol] = v;
  document.querySelectorAll('.sayi[data-yol="' + s.yol + '"]').forEach(function (d) {
    var deg = s.yol in a.degerler, n = d.querySelector('input[type=number]'), r = d.querySelector('input[type=range]');
    if (document.activeElement !== n) n.value = v; if (+r.max < v) r.max = v; r.value = v;
    d.classList.toggle('degisti', deg); d.querySelector('.canli').hidden = !deg;
  });
  ayarDegisti();
}
function ayarOlaylari(kok) {
  kok.addEventListener('input', function (e) { var d = e.target.closest('.sayi'); if (d && (e.target.type === 'range' || e.target.type === 'number') && e.target.value !== '') sayiKoy(d, parseFloat(String(e.target.value).replace(',', '.'))); });
  kok.addEventListener('change', function (e) {
    var an = e.target.dataset && e.target.dataset.pasif; if (!an) return;
    var a = ayar(), i = a.pasif.indexOf(an); if (e.target.checked && i < 0) a.pasif.push(an); if (!e.target.checked && i >= 0) a.pasif.splice(i, 1);
    document.querySelectorAll('[data-pasif="' + an + '"]').forEach(function (k) { k.checked = e.target.checked; var s = k.closest('.sart'); if (s) s.classList.toggle('pasif', e.target.checked); });
    ayarDegisti();
  });
  kok.addEventListener('click', function (e) {
    var b = e.target.closest('button'), d = e.target.closest('.sayi'); if (!b || !d) return; var s = sayiBul(d.dataset.yol); if (!s) return;
    if (b.dataset.geri) sayiKoy(d, s.deger); else if (b.dataset.y) sayiKoy(d, simdikiDeger(s) + s.adim * (+b.dataset.y));
  });
}
ayarOlaylari($('p-hizli')); ayarOlaylari($('parametreler'));
var uzayZam = 0, testZam = 0;
function ayarDegisti(hemen) {
  sakla('kb-ayar', ayarlar); degisimYaz();
  clearTimeout(uzayZam); clearTimeout(testZam);
  if (gorunum === 'uzay') uzayZam = setTimeout(function () { uzayYukle(); }, hemen ? 0 : 600);
  else uzayBayat = true;
  if (gorunum === 'lab' && $('otoTest').checked) testZam = setTimeout(testCalistir, hemen ? 0 : 900);
}
var uzayBayat = false;
function degisimYaz() {
  var a = ayar(), n = Object.keys(a.degerler).length + a.pasif.length, e = $('degisimSayisi');
  e.textContent = n ? n + ' değişiklik (deneme)' : 'Canlı ayar'; e.className = 'cip' + (n ? ' ayr' : '');
}

/* ------------------------------------------------------------------ laboratuvar */
var lab = oku('kb-lab', {}); if (!lab || typeof lab !== 'object') lab = {}; if ([30, 90, 180, 365].indexOf(lab.gun) < 0) lab.gun = 90; if (!Array.isArray(lab.coinler)) lab.coinler = [];
var sonuclar = {}, testSira = 0, testCalisiyor = false;
function grupHtml(baslik, sayilar, pasifler, acik) {
  if (!sayilar.length && !pasifler.length) return '';
  return '<details class="grup"' + (acik ? ' open' : '') + '><summary>' + baslik + ' <small>' + sayilar.length + ' sayı</small></summary>' +
    pasifler.map(function (p) { return '<label class="tik"><input type="checkbox" data-pasif="' + esc(p.anahtar) + '"' + (pasifMi(p.anahtar) ? ' checked' : '') + '>' + esc(p.ad) + ': pasif yap</label>'; }).join('') +
    sayilar.map(sayiHtml).join('') + '</details>';
}
function labYaz() {
  var s = sema(); if (!s) return;
  $('labBaslik').textContent = s.kod + ' bot ayarı'; $('labAciklama').textContent = s.ad + ' · ' + (s.yon === 'aciga_satis' ? 'açığa satış' : 'alım') + ' · ' + s.dilim + ' mum';
  var p = function (adlar) { return s.pasif.filter(function (x) { return adlar.indexOf(x.anahtar) >= 0; }); };
  $('parametreler').innerHTML = '<details class="grup" open><summary>Giriş şartları <small>' + s.sartlar.length + ' şart, hepsi aynı anda doğru olmalı</small></summary>' + s.sartlar.map(sartHtml).join('') + '</details>' +
    grupHtml('Göstergeler', s.gostergeler, [], false) + grupHtml('Giriş emri', s.giris_emri, p(['giris_limiti']), true) +
    grupHtml('Çıkış', s.cikis, p(['kar_hedefi_yuzde', 'iz_suren_stop', 'sure_asimi_dakika', 'bekleme_dakika']), true) + grupHtml('Pozisyon', s.pozisyon, p(['zararda_ekleme']), true);
  $('donem').innerHTML = s.donemler.map(function (g) { return '<button type="button" data-g="' + g + '" aria-pressed="' + (g === lab.gun) + '">' + g + ' gün</button>'; }).join('');
  var hazir = s.hazir_coinler, hepsi = hazir.slice(); s.uzay_coinleri.forEach(function (c) { if (hepsi.indexOf(c) < 0) hepsi.push(c); });
  if (!lab.coinler.length) lab.coinler = (hazir.length ? hazir : s.uzay_coinleri).slice(0, 6);
  $('coinler').innerHTML = hepsi.map(function (c) { return '<button type="button" data-coin="' + esc(c) + '" class="' + (hazir.indexOf(c) < 0 ? 'yok' : '') + '" aria-pressed="' + (lab.coinler.indexOf(c) >= 0) + '">' + esc(c) + '</button>'; }).join('');
  $('coinNot').textContent = hazir.length ? 'Düz çerçeveli coinlerin mumları sunucuda hazır (' + hazir.length + ' coin). Kesik çerçeveliler yalnız ' + s.indirme_siniri + ' güne kadar olan dönemlerde, o an indirilerek test edilir.'
    : 'Sunucuda indirilmiş mum dosyası bulunamadı; coinler ' + s.indirme_siniri + ' güne kadar olan dönemlerde o an indirilerek test edilir.';
  $('donemNot').textContent = 'Dönem ikiye ayrılır: ilk %70 "seçim", son %30 "doğrulama". Doğrulama, ayarı seçerken bakmadığın dönem gibi düşünülür.';
  kayitlariYaz(); degisimYaz(); sonucYaz();
}
$('donem').addEventListener('click', function (e) { var b = e.target.closest('button'); if (!b) return; lab.gun = +b.dataset.g; sakla('kb-lab', lab); labYaz(); });
$('coinler').addEventListener('click', function (e) { var b = e.target.closest('button'); if (!b) return; var c = b.dataset.coin, i = lab.coinler.indexOf(c); if (i >= 0) lab.coinler.splice(i, 1); else lab.coinler.push(c); b.setAttribute('aria-pressed', i < 0); sakla('kb-lab', lab); });
$('coinHepsi').addEventListener('click', function () { var s = sema(); lab.coinler = (s.hazir_coinler.length ? s.hazir_coinler : s.uzay_coinleri).slice(0, 21); sakla('kb-lab', lab); labYaz(); });
$('coinTemizle').addEventListener('click', function () { lab.coinler = []; sakla('kb-lab', lab); document.querySelectorAll('#coinler button').forEach(function (b) { b.setAttribute('aria-pressed', 'false'); }); });
$('canliyaDon').addEventListener('click', function () { ayarlar[bot] = { degerler: {}, pasif: [] }; labYaz(); ayarDegisti(true); });
$('testCalistir').addEventListener('click', function () { testCalistir(); });
function testCalistir() {
  if (!lab.coinler.length) { sonuclar[bot] = { hata: 'En az bir coin seç.' }; sonucYaz(); return; }
  var sira = ++testSira, a = ayar(), b = bot; testCalisiyor = true; $('ayarHata').hidden = true;
  sonuclar[b] = { ilerleme: { biten: 0, toplam: lab.coinler.length, coin: '' }, onceki: sonuclar[b] && sonuclar[b].sonuc ? sonuclar[b].sonuc : (sonuclar[b] || {}).onceki };
  sonucYaz();
  api('/api/test', { bot: b, degerler: a.degerler, pasif: a.pasif, coinler: lab.coinler, gun: lab.gun }).then(function (v) {
    (function sor() {
      if (sira !== testSira) return;
      api('/api/test?id=' + v.id).then(function (d) {
        if (sira !== testSira) return;
        if (d.durum === 'bitti') { testCalisiyor = false; sonuclar[b] = { sonuc: d.sonuc, sure: d.sure }; sonucYaz(); }
        else if (d.durum === 'hata') { testCalisiyor = false; sonuclar[b] = { hata: d.hata }; sonucYaz(); }
        else { sonuclar[b].ilerleme = d; ilerlemeYaz(); setTimeout(sor, 500); }
      }, function (h) { testCalisiyor = false; sonuclar[b] = { hata: h.message }; sonucYaz(); });
    })();
  }, function (h) { if (sira !== testSira) return; testCalisiyor = false; sonuclar[b] = { hata: h.message }; sonucYaz(); });
}
function ilerlemeYaz() { var s = sonuclar[bot], e = $('ilerleme'); if (!s || !s.ilerleme || !e) return; var i = s.ilerleme, y = i.toplam ? 100 * i.biten / i.toplam : 3; e.firstChild.style.width = Math.max(3, y) + '%'; $('ilerlemeYazi').textContent = i.durum === 'sirada' ? 'Sırada bekliyor…' : (i.coin ? i.coin + ' hesaplanıyor (' + (i.biten + 1) + ' / ' + i.toplam + ')' : 'Hazırlanıyor…'); }
function kartHtml(ad, o, vurgu) { return '<div class="kart' + (vurgu ? ' vurgu' : '') + '"><span>' + ad + '</span><b class="' + sinif(o.net_usdt) + '">' + isr(o.net_usdt) + '</b><span>USDT · ' + o.islem + ' işlem' + (o.kazanma_orani == null ? '' : ' · %' + tr(o.kazanma_orani, 0) + ' kazanan') + '</span></div>'; }
function egriHtml(r) {
  var a = r.egri || [], b = r.canli ? r.canli.egri || [] : [], t0 = new Date(r.baslangic + 'T00:00:00Z').getTime(), t1 = new Date(r.bitis.replace(' ', 'T') + ':00Z').getTime();
  var tum = a.concat(b).map(function (p) { return p[1]; }).concat([0]), mn = Math.min.apply(0, tum), mx = Math.max.apply(0, tum); if (mx - mn < 1e-9) { mx += 1; mn -= 1; }
  var X = function (z) { return (4 + 592 * kis((new Date(z).getTime() - t0) / Math.max(1, t1 - t0), 0, 1)).toFixed(1); }, Y = function (v) { return (8 + 124 * (1 - (v - mn) / (mx - mn))).toFixed(1); };
  var yol = function (n) { var d = 'M4 ' + Y(0); n.forEach(function (p) { d += 'L' + X(p[0]) + ' ' + Y(p[1]); }); return d; };
  var dx = X(r.dogrulama_baslangic + 'T00:00:00Z');
  return '<svg class="egri" viewBox="0 0 600 150" preserveAspectRatio="none" role="img" aria-label="Birikimli net sonuç eğrisi">' +
    '<rect x="' + dx + '" y="0" width="' + (596 - dx).toFixed(1) + '" height="140" fill="#f3d9a4" fill-opacity=".07"/><rect x="' + dx + '" y="0" width="1" height="140" fill="#f3d9a4" fill-opacity=".6"/>' +
    '<rect x="4" y="' + Y(0) + '" width="592" height="1" fill="#2b2b2b"/>' +
    (b.length ? '<path d="' + yol(b) + '" fill="none" stroke="#9b9b9b" stroke-width="1.4" vector-effect="non-scaling-stroke" stroke-dasharray="4 3"/>' : '') +
    '<path d="' + yol(a) + '" fill="none" stroke="#f3d9a4" stroke-width="1.8" vector-effect="non-scaling-stroke"/></svg>' +
    '<p class="kucuk">Birikimli net sonuç (USDT, işlem başına ' + tr(r.islem_tutari, 0) + ' USDT ile). Altın çizgi: test edilen ayar' + (b.length ? '; kesik çizgi: canlı ayar' : '') + '. Açık renkli bölge doğrulama dönemi (' + esc(r.dogrulama_baslangic) + ' sonrası).</p>';
}
function olcutHtml(r) {
  var o = r.ozet, c = r.canli ? r.canli.ozet : null, y = function (v, n, son) { return v == null ? '–' : tr(v, n) + (son || ''); };
  var sil = function (x) { return x.ort_kazanc ? Math.abs(x.ort_kayip) / x.ort_kazanc : null; };
  var satirlar = [['Kazanma oranı', y(o.kazanma_orani, 0, '%'), c && y(c.kazanma_orani, 0, '%')], ['Başa baş için gereken oran', y(o.basabas_orani, 0, '%'), c && y(c.basabas_orani, 0, '%')],
    ['İşlem başına net', y(o.islem_basina_yuzde, 2, '%'), c && y(c.islem_basina_yuzde, 2, '%')], ['Ortalama kazanç', y(o.ort_kazanc, 2, '%'), c && y(c.ort_kazanc, 2, '%')],
    ['Ortalama kayıp', y(o.ort_kayip, 2, '%'), c && y(c.ort_kayip, 2, '%')], ['Bir kayıp kaç kazancı siler', y(sil(o), 1), c && y(sil(c), 1)],
    ['Kâr faktörü', y(o.kar_faktoru, 2), c && y(c.kar_faktoru, 2)], ['En kötü işlem', y(o.en_kotu_yuzde, 1, '%'), c && y(c.en_kotu_yuzde, 1, '%')],
    ['En uzun kayıp serisi', o.en_uzun_kayip_serisi, c && c.en_uzun_kayip_serisi], ['Tepeden en büyük düşüş (bakiyeye göre)', y(o.dusus_yuzde, 2, '%'), c && y(c.dusus_yuzde, 2, '%')]];
  return '<div class="olcut"><span class="bs">Ölçüt</span><span class="bs">Test edilen</span><span class="bs">' + (c ? 'Canlı' : '') + '</span>' + satirlar.map(function (s) { return '<span>' + s[0] + '</span><span>' + s[1] + '</span><span class="sl">' + (s[2] == null || s[2] === false ? '' : s[2]) + '</span>'; }).join('') + '</div>';
}
function sonucYaz() {
  var el = $('sonuc'), s = sonuclar[bot];
  if (!s) { el.innerHTML = '<div class="blok"><span class="ust">Geçmiş test</span><h1>Ayarını geçmişte dene.</h1><p class="kucuk">Soldan dönemi ve coinleri seç, ortadan ayarı değiştir. Test sunucudaki indirilmiş mumlarda çalışır; birkaç coin ve 90 gün birkaç saniye, bütün coinler ve 365 gün bir dakikaya yakın sürer.</p><p class="kucuk">Sonuç geçmişi gösterir, geleceği değil. Çok ayar denedikçe birinin şans eseri iyi görünmesi kolaylaşır; bu yüzden her sonuçta "doğrulama" dönemi ayrı yazılır.</p></div>'; return; }
  if (s.hata) { el.innerHTML = '<div class="blok"><span class="ust">Geçmiş test</span><p class="hata-kutu">' + esc(s.hata) + '</p></div>'; return; }
  var h = '';
  if (s.ilerleme) h += '<div class="blok"><span class="ust">Test çalışıyor</span><div class="ilerleme" id="ilerleme"><span></span></div><p class="kucuk" id="ilerlemeYazi">Hazırlanıyor…</p></div>';
  var r = s.sonuc || s.onceki;
  if (r) {
    var o = r.ozet, ayniMi = JSON.stringify(r.ayar) === JSON.stringify({ degerler: ayar().degerler, pasif: ayar().pasif.slice().sort() });
    h += '<div class="blok"><span class="ust">' + (s.sonuc ? '' : 'Önceki sonuç · ') + esc(r.baslangic) + ' → ' + esc(r.bitis.slice(0, 10)) + ' · ' + r.coinler.length + ' coin' + (s.sure ? ' · ' + tr(s.sure, 1) + ' sn' : '') + '</span>' +
      '<h1><span class="r ' + sinif(o.net_usdt) + '">' + isr(o.net_usdt) + ' USDT</span> · ' + o.islem + ' işlem' + (o.kazanma_orani == null ? '' : ', %' + tr(o.kazanma_orani, 0) + ' kazanan') + '</h1>' +
      (s.sonuc && !ayniMi ? '<p class="uyari-kutu">Ayar bu testten sonra değişti; sonuç eski ayara ait.</p>' : '') +
      r.uyarilar.map(function (u) { return '<p class="uyari-kutu">' + esc(u) + '</p>'; }).join('') + '</div>';
    if (r.canli) h += '<div class="kart2">' + kartHtml('Test edilen ayar', o, true) + kartHtml('Canlı ayar, aynı dönem', r.canli.ozet) + '</div>';
    h += '<div class="blok"><h2>Seçim ve doğrulama</h2><div class="kart2">' + kartHtml('Seçim (ilk %70)', r.secim) + kartHtml('Doğrulama (son %30)', r.dogrulama, true) + '</div>' +
      (r.canli ? '<p class="kucuk">Canlı ayarın doğrulama dönemi: <b class="r ' + sinif(r.canli.dogrulama.net_usdt) + '">' + isr(r.canli.dogrulama.net_usdt) + ' USDT</b>, ' + r.canli.dogrulama.islem + ' işlem.</p>' : '') + '</div>';
    h += '<div class="blok"><h2>Seyir</h2>' + egriHtml(r) + '</div>';
    h += '<div class="blok"><h2>Ölçütler</h2>' + olcutHtml(r) + '</div>';
    var cm = Math.max.apply(0, r.ceyrekler.map(function (c) { return Math.abs(c.net_usdt); })) || 1;
    h += '<div class="blok"><h2>Dönemin dört parçası</h2>' + r.ceyrekler.map(function (c) { return '<div class="neden"><span class="r">' + esc(c.baslangic.slice(2)) + '</span><div class="cubuk"><span style="width:' + (100 * Math.abs(c.net_usdt) / cm).toFixed(0) + '%;background:var(--' + (c.net_usdt >= 0 ? 'arti' : 'eksi') + ')"></span></div><span class="r ' + sinif(c.net_usdt) + '" style="text-align:right">' + isr(c.net_usdt, 1) + '</span></div>'; }).join('') + '<p class="kucuk">Sonuç dört parçanın çoğunda aynı yöndeyse daha güvenilirdir; tek bir iyi parça şans olabilir.</p></div>';
    h += '<div class="blok"><h2>Coin coin</h2><div class="kaydir"><table><thead><tr><th>Coin</th><th>İşlem</th><th>Kazanan</th><th>Net USDT</th></tr></thead><tbody>' + r.coinler.map(function (c) { return '<tr><td>' + esc(c.coin) + (c.kaynak === 'indirildi' ? ' <span class="sl">(indirildi)</span>' : '') + '</td><td>' + c.islem + '</td><td>' + c.kazanan + '</td><td class="' + sinif(c.net_usdt) + '">' + isr(c.net_usdt) + '</td></tr>'; }).join('') + '</tbody></table></div></div>';
    var nd = Object.keys(o.nedenler), nm = Math.max.apply(0, nd.map(function (k) { return o.nedenler[k]; })) || 1;
    if (nd.length) h += '<div class="blok"><h2>İşlemler nasıl kapandı?</h2>' + nd.map(function (k) { return '<div class="neden"><span>' + esc(k) + '</span><div class="cubuk"><span style="width:' + (100 * o.nedenler[k] / nm).toFixed(0) + '%"></span></div><span class="r" style="text-align:right">' + o.nedenler[k] + '</span></div>'; }).join('') + '</div>';
    if (r.islemler.length) h += '<details class="grup"><summary>Son ' + r.islemler.length + ' işlem</summary><div class="kaydir"><table><thead><tr><th>Coin</th><th>Giriş</th><th>Çıkış nedeni</th><th>Net %</th></tr></thead><tbody>' + r.islemler.slice().reverse().map(function (i) { return '<tr><td>' + esc(i.coin) + '</td><td>' + esc(i.giris.slice(5)) + '</td><td>' + esc(i.neden) + '</td><td class="' + sinif(i.net_yuzde) + '">' + isr(i.net_yuzde) + '</td></tr>'; }).join('') + '</tbody></table></div></details>';
    if (r.notlar.length) h += '<div class="blok"><h2>Veri notları</h2>' + r.notlar.map(function (n) { return '<p class="kucuk">' + esc(n) + '</p>'; }).join('') + '</div>';
    h += '<div class="dugmeler"><button class="dugme mor" type="button" id="sonucuSor">Ajana sor: bu sonucu yorumla</button></div><p class="kucuk">Bağımsız benzetimdir; Karabasan süzgeci uygulanmaz, komisyon dahildir. Canlı botun birebir aynısını yapacağı anlamına gelmez.</p>';
  }
  el.innerHTML = h; ilerlemeYaz();
}
$('sonuc').addEventListener('click', function (e) { if (e.target.id === 'sonucuSor') ajanGonder('Laboratuvardaki son geçmiş test sonucunu yorumlar mısın? Güvenilir mi, riskleri ne, canlı ayara göre nasıl?'); });
function kayitlariYaz() {
  var s = sema(), l = s.kayitlar || [];
  $('kayitlar').innerHTML = l.length ? l.map(function (k) { var n = Object.keys(k.degerler || {}).length + (k.pasif || []).length; return '<div class="kayit" data-id="' + esc(k.id) + '"><b>' + esc(k.ad) + '</b><span class="kucuk">' + n + ' değişiklik · ' + esc(String(k.guncelleme || '').slice(0, 10)) + '</span><div class="dugmeler"><button class="dugme mor" data-e="ac" type="button">Yükle</button><button class="dugme" data-e="ustune" type="button">Üstüne yaz</button><button class="dugme" data-e="adlandir" type="button">Adını değiştir</button><button class="dugme" data-e="sil" type="button">Sil</button></div></div>'; }).join('') : '<p class="kucuk">Henüz kayıt yok.</p>';
}
function kayitIste(govde) { $('kayitHata').hidden = true; govde.bot = bot; return api('/api/kayit', govde).then(function (v) { sema().kayitlar = v.kayitlar; kayitlariYaz(); return v; }, function (h) { $('kayitHata').hidden = false; $('kayitHata').textContent = h.message; }); }
$('kayitEkle').addEventListener('click', function () { var a = ayar(); kayitIste({ eylem: 'kaydet', ad: $('kayitAd').value, degerler: a.degerler, pasif: a.pasif }).then(function (v) { if (v) $('kayitAd').value = ''; }); });
$('kayitlar').addEventListener('click', function (e) {
  var b = e.target.closest('button'); if (!b) return; var d = b.closest('.kayit'), id = d.dataset.id, a = ayar(), k = (sema().kayitlar || []).filter(function (x) { return x.id === id; })[0];
  if (b.dataset.e === 'ac' && k) kayitYukle(k);
  else if (b.dataset.e === 'ustune') kayitIste({ eylem: 'ustune', kimlik: id, ad: '', degerler: a.degerler, pasif: a.pasif });
  else if (b.dataset.e === 'sil') { if (b.dataset.emin) kayitIste({ eylem: 'sil', kimlik: id }); else { b.dataset.emin = '1'; b.textContent = 'Emin misin? Sil'; } }
  else if (b.dataset.e === 'adlandir') { var ad = $('kayitAd').value.trim(); if (!ad) { $('kayitHata').hidden = false; $('kayitHata').textContent = 'Yeni adı üstteki "Kayıt adı" kutusuna yaz, sonra yeniden "Adını değiştir"e bas.'; $('kayitAd').focus(); } else kayitIste({ eylem: 'adlandir', kimlik: id, ad: ad }).then(function (v) { if (v) $('kayitAd').value = ''; }); }
});
function kayitYukle(k) {
  var d = {}, s = sema(); Object.keys(k.degerler || {}).forEach(function (yol) { var c = canliDeger(yol); if (c != null && Math.abs(k.degerler[yol] - c) > 1e-9) d[yol] = k.degerler[yol]; });
  var gecerli = s.sartlar.map(function (x) { return 'k' + x.sira; }).concat(s.pasif.map(function (x) { return x.anahtar; }));
  ayarlar[bot] = { degerler: d, pasif: (k.pasif || []).filter(function (p) { return gecerli.indexOf(p) >= 0; }) };
  labYaz(); ayarDegisti(true);
}

/* ------------------------------------------------------------------ ajan */
var mesajlar = [], ajanDurum = null, ajanMesgul = false;
var ONERILER = ['Canlı sonuçları yorumla', 'Şu an denediğim ayarı değerlendir', 'Daha sağlıklı bir ayar öner, test et ve kaydet', 'Kayıtlı değerlerimi düzenle ve geliştirme raporu hazırla'];
var RAPOR_ISTEMI = 'Geliştirme raporu hazırla: kayıtlı bütün değerlerimi oku ve düzenle, botların durumuna bak, umut veren ayarları canlı ayarla aynı dönemde test et, raporu kaydet ve bana kısaca özetle.';
function mdHtml(m) {
  var h = '', liste = false;
  String(m || '').split('\n').forEach(function (s) {
    var t = esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<span class="r">$1</span>');
    var madde = /^\s*[-•*]\s+/.test(s), baslik = /^#{1,4}\s+/.test(s);
    if (madde) { if (!liste) { h += '<ul>'; liste = true; } h += '<li>' + t.replace(/^\s*[-•*]\s+/, '') + '</li>'; return; }
    if (liste) { h += '</ul>'; liste = false; }
    if (!s.trim()) return;
    h += baslik ? '<p><b>' + t.replace(/^#{1,4}\s+/, '') + '</b></p>' : '<p>' + t + '</p>';
  });
  return h + (liste ? '</ul>' : '');
}
function balonHtml(m) {
  var h = '<div class="balon ' + (m.rol === 'ahmet' ? 'ahmet' : 'ajan') + '">' + (m.bekliyor ? '<p class="sl">Düşünüyor…</p>' : m.rol === 'ahmet' ? '<p>' + esc(m.metin) + '</p>' : mdHtml(m.metin));
  if (m.hata) h += '<p class="eksi">' + esc(m.hata) + '</p>';
  if (m.araclar && m.araclar.length) h += '<div class="adim">' + m.araclar.map(esc).join(' · ') + '</div>';
  if (m.eylemler && m.eylemler.length) h += '<div class="dugmeler">' + m.eylemler.map(function (e) { return e.tur === 'rapor' ? '<button class="dugme mor" type="button" data-rapor="' + esc(e.ad) + '">Raporu aç: ' + esc(e.baslik || e.ad) + '</button>' : e.tur === 'kayit' ? '<button class="dugme mor" type="button" data-kayit="' + esc(e.kimlik) + '" data-bot="' + esc(e.bot) + '">Laboratuvara yükle: ' + esc(e.ad) + '</button>' : ''; }).join('') + '</div>';
  return h + '</div>';
}
function sohbetYaz() {
  var bos = '<p class="kucuk">' + (ajanDurum && !ajanDurum.anahtar_var ? 'Ajan henüz açık değil: önce <a href="#ajan">Ajan sekmesinden</a> ücretsiz Gemini anahtarını gir.' : 'Henüz konuşma yok. Aşağıdan bir soru sor ya da hazır sorulardan birine dokun.') + '</p>';
  var son = mesajlar.slice(-40).map(balonHtml).join('') || bos;
  $('sohbetAkis').innerHTML = son; $('dokGovde').innerHTML = mesajlar.slice(-8).map(balonHtml).join('') || bos;
  var g = $('dokGovde'); g.scrollTop = g.scrollHeight;
  var oh = ONERILER.map(function (o) { return '<button type="button">' + esc(o) + '</button>'; }).join(''); $('oneriler').innerHTML = oh; $('dokOneri').innerHTML = oh;
  $('dokGonder').disabled = $('sohbetGonder').disabled = ajanMesgul;
}
function baglamTopla() {
  var a = ayar(), b = { ekran: gorunum === 'uzay' ? 'Uzay (ana ekran)' : gorunum === 'lab' ? 'Ayar ve geçmiş test' : 'Ajan', bot: bot, degerler: a.degerler, pasif: a.pasif };
  if (gorunum === 'uzay' && U && NC) {
    var i = adimNo(), yakin = []; for (var c = 0; c < NC; c++) yakin.push({ coin: COIN[c].ad, eksik: pop(COIN[c].eksik[i]) });
    yakin.sort(function (x, y) { return x.eksik - y.eksik; }); b.uzay = { zaman: saatYaz(i), en_yakin: yakin.slice(0, 8), son_24s_giris_ani: olay.length, canli_ayarla_giris_ani: U.degisti ? olayCan : olay.length };
    if (secili >= 0 && COIN[secili]) b.coin = COIN[secili].ad;
  }
  var s = sonuclar[bot] && sonuclar[bot].sonuc;
  if (s) b.son_gecmis_test = { donem: s.baslangic + ' → ' + s.bitis, gun: s.gun, ayar: s.ayar, coinler: s.coinler.map(function (c) { return c.coin; }), ozet: s.ozet, secim: s.secim, dogrulama: s.dogrulama, canli_ozet: s.canli ? s.canli.ozet : null, canli_dogrulama: s.canli ? s.canli.dogrulama : null, uyarilar: s.uyarilar };
  return b;
}
function ajanGonder(metin) {
  metin = String(metin || '').trim(); if (!metin || ajanMesgul) return;
  $('sohbetHata').hidden = true; dokAc(true);
  var bek = { rol: 'ajan', metin: '', bekliyor: true, araclar: [] }; mesajlar.push({ rol: 'ahmet', metin: metin }); mesajlar.push(bek); ajanMesgul = true; sohbetYaz();
  var bitir = function (hata) { ajanMesgul = false; bek.bekliyor = false; if (hata) bek.hata = hata; sohbetYaz(); ajanDurumYukle(); };
  api('/api/ajan', { mesaj: metin, baglam: baglamTopla() }).then(function (v) {
    (function sor() {
      api('/api/ajan?id=' + v.id).then(function (d) {
        bek.araclar = d.adimlar || [];
        if (d.durum === 'bitti') { bek.metin = d.yanit; bek.eylemler = d.eylemler || []; bitir(); if (bek.eylemler.length) { botYukle(true); arsivYukle(); } }
        else if (d.durum === 'hata') bitir(d.hata);
        else { sohbetYaz(); setTimeout(sor, 1200); }
      }, function (h) { bitir(h.message); });
    })();
  }, function (h) { bitir(h.message); });
}
function dokAc(ac) { var d = $('dok'); d.classList.toggle('acik', ac); $('dokAc').setAttribute('aria-expanded', ac); $('dokOneri').hidden = !ac; if (ac) { var g = $('dokGovde'); g.scrollTop = g.scrollHeight; } }
$('dokAc').addEventListener('click', function () { dokAc(!$('dok').classList.contains('acik')); });
$('dokGonder').addEventListener('click', function () { var e = $('dokYaz'); ajanGonder(e.value); e.value = ''; });
$('dokYaz').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); $('dokGonder').click(); } });
$('sohbetGonder').addEventListener('click', function () { var e = $('sohbetYaz'); ajanGonder(e.value); e.value = ''; });
function oneriTik(e) { var b = e.target.closest('button'); if (b) ajanGonder(b.textContent); }
$('oneriler').addEventListener('click', oneriTik); $('dokOneri').addEventListener('click', oneriTik);
function raporAc(ad) { location.hash = 'ajan'; var m = $('arsivMetin'); m.hidden = false; m.textContent = 'Yükleniyor…'; api('/api/ajan/arsiv?gun=' + encodeURIComponent('rapor:' + ad)).then(function (v) { m.textContent = v.metin; m.scrollIntoView(); }, function (h) { m.textContent = h.message; }); }
function eylemTik(e) {
  var r = e.target.closest('[data-rapor]'); if (r) { dokAc(false); raporAc(r.dataset.rapor); return; }
  var b = e.target.closest('[data-kayit]'); if (!b) return; var hedef = b.dataset.bot, id = b.dataset.kayit;
  var yukle = function () { var k = (sema().kayitlar || []).filter(function (x) { return x.id === id; })[0]; if (k) { kayitYukle(k); location.hash = 'lab'; dokAc(false); } };
  if (hedef !== bot) botSec(hedef).then(yukle); else botYukle(true).then(yukle);
}
$('dokGovde').addEventListener('click', eylemTik); $('sohbetAkis').addEventListener('click', eylemTik);
var secSag = null;
function ajanDurumYukle() {
  return api('/api/ajan/durum').then(function (d) {
    ajanDurum = d; if (!secSag) secSag = d.saglayici;
    var s = d.saglayicilar.filter(function (x) { return x.kod === secSag; })[0] || d.saglayicilar[0];
    $('ajanModel').textContent = d.saglayici_adi + (d.model ? ' · ' + d.model : '') + ', düşük çaba' + (d.ucretsiz ? ' · ücretsiz' : '');
    $('ajanDurum').innerHTML = (d.anahtar_var ? '<span class="arti">' + esc(d.saglayici_adi) + ' anahtarı kayıtlı, ajan açık.</span>' : '<span class="uy">' + esc(d.saglayici_adi) + ' anahtarı girilmemiş, ajan kapalı.</span>') +
      '<br>Bugün ' + d.bugun_mesaj + ' / ' + d.gunluk_sinir + ' mesaj' + (d.bugun_yaklasik_usd != null ? ' · yaklaşık ' + tr(d.bugun_yaklasik_usd, 2) + ' USD' : d.ucretsiz ? ' · ücretsiz katman' : '');
    $('saglayici').innerHTML = d.saglayicilar.map(function (x) { return '<button type="button" data-k="' + x.kod + '" aria-pressed="' + (x.kod === secSag) + '">' + esc(x.ad) + (x.ucretsiz ? ' (ücretsiz)' : '') + (x.kod === d.saglayici ? ' ✓' : '') + '</button>'; }).join('');
    $('saglayiciNot').innerHTML = esc(s.not) + ' Anahtar: <span class="r">' + esc(s.anahtar_adresi) + '</span> (' + esc(s.anahtar_ipucu) + '). ' + (s.anahtar_var ? '<span class="arti">Bu sağlayıcının anahtarı kayıtlı.</span>' : '') +
      (s.kod !== d.saglayici ? ' <button class="dugme mor" type="button" id="sagSec">Ajanı bununla çalıştır</button>' : ' <span class="ayr">Ajan şu an bununla çalışıyor.</span>');
    $('anahtar').placeholder = s.anahtar_ipucu; $('anahtarEt').textContent = s.ad + ' API anahtarı';
    $('modelAd').placeholder = s.varsayilan_model || (s.kendiliginden ? 'boş = en yeni flash modeli' : ''); $('modelAd').value = s.model || '';
    $('modelSimdi').textContent = s.model ? s.model : (s.kendiliginden ? 'kendiliğinden' : s.varsayilan_model);
    $('dokYaz').placeholder = d.anahtar_var ? 'Ajana sor: bu sonuç ne anlama geliyor?' : 'Ajan kapalı: önce Ajan sekmesinden anahtar gir';
    sohbetYaz();
  }, function () { /* sessiz */ });
}
function ayarIste(govde) { $('anahtarHata').hidden = true; return api('/api/ajan/ayar', govde).then(function () { ajanDurumYukle(); }, function (h) { $('anahtarHata').hidden = false; $('anahtarHata').textContent = h.message; }); }
$('saglayici').addEventListener('click', function (e) { var b = e.target.closest('button'); if (!b) return; secSag = b.dataset.k; ajanDurumYukle(); });
$('saglayiciNot').addEventListener('click', function (e) { if (e.target.id === 'sagSec') ayarIste({ saglayici: secSag }); });
$('modelKaydet').addEventListener('click', function () { ayarIste({ saglayici: ajanDurum ? ajanDurum.saglayici : secSag, model: $('modelAd').value.trim() }).then(function () { if (ajanDurum && ajanDurum.saglayici !== secSag) ayarIste({ saglayici: secSag, model: $('modelAd').value.trim() }); }); });
function anahtarIste(govde) { govde.saglayici = secSag; $('anahtarHata').hidden = true; api('/api/ajan/anahtar', govde).then(function () { $('anahtar').value = ''; if (!govde.sil && ajanDurum && ajanDurum.saglayici !== secSag && !ajanDurum.anahtar_var) ayarIste({ saglayici: secSag }); else ajanDurumYukle(); }, function (h) { $('anahtarHata').hidden = false; $('anahtarHata').textContent = h.message; }); }
$('anahtarKaydet').addEventListener('click', function () { anahtarIste({ anahtar: $('anahtar').value.trim() }); });
$('anahtarSil').addEventListener('click', function (e) { if (e.target.dataset.emin) { delete e.target.dataset.emin; e.target.textContent = 'Anahtarı sil'; anahtarIste({ sil: true }); } else { e.target.dataset.emin = '1'; e.target.textContent = 'Emin misin? Sil'; } });
$('raporIste').addEventListener('click', function () { ajanGonder(RAPOR_ISTEMI); });
$('raporlar').addEventListener('click', function (e) { var b = e.target.closest('[data-rapor]'); if (b) raporAc(b.dataset.rapor); });
function arsivYukle() {
  api('/api/ajan/arsiv').then(function (v) {
    $('raporlar').innerHTML = (v.raporlar || []).length ? '<div class="liste">' + v.raporlar.slice(0, 12).map(function (r) { return '<button type="button" data-rapor="' + esc(r.ad) + '"><b>' + esc(r.ad.slice(5, 10)) + '</b><span>' + esc(r.baslik) + '</span><span class="r ayr">aç</span></button>'; }).join('') + '</div>' : '<p class="kucuk">Henüz rapor yok.</p>';
    $('arsivGunler').innerHTML = '<button class="dugme mor" type="button" data-gun="dersler">Dersler</button>' + v.gunler.slice(0, 30).map(function (g) { return '<button class="dugme" type="button" data-gun="' + esc(g.gun) + '">' + esc(g.gun.slice(5)) + ' · ' + g.mesaj + '</button>'; }).join('');
  }, function () { /* sessiz */ });
}
$('arsivGunler').addEventListener('click', function (e) { var b = e.target.closest('button'); if (!b) return; var m = $('arsivMetin'); m.hidden = false; m.textContent = 'Yükleniyor…'; api('/api/ajan/arsiv?gun=' + encodeURIComponent(b.dataset.gun)).then(function (v) { m.textContent = v.metin; }, function (h) { m.textContent = b.dataset.gun === 'dersler' ? 'Henüz ders yok.' : h.message; }); });

/* ------------------------------------------------------------------ gezinti, bot, başlangıç */
function botKur() { $('botsec').innerHTML = BOTLAR.map(function (b) { return '<button type="button" data-b="' + b + '" aria-pressed="' + (b === bot) + '">' + botKodu(b) + '</button>'; }).join(''); }
function botYukle(sessiz) {
  return api('/api/bot?bot=' + encodeURIComponent(bot)).then(function (v) {
    semalar[bot] = v; if (v.botlar && v.botlar.length) BOTLAR = v.botlar; botKur();
    if (gorunum === 'lab') { if (sessiz) kayitlariYaz(); else labYaz(); } if (sekme === 'hizli' && !sessiz) hizliYaz();
  }, function (h) { $('ayarHata').hidden = false; $('ayarHata').textContent = h.message; });
}
function botSec(b) { bot = b; sakla('kb-bot', bot); botKur(); secili = -1; acikHesapla(); var p = botYukle(); uzayYukle(); return p; }
$('botsec').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b && b.dataset.b !== bot) botSec(b.dataset.b); });
// Sonuçlar sekmesi: eski ve yeni bütün sonuç ekranları, çerçevedeki /klasik?gomulu=1 sayfasında. #sonuc-<ekran> o ekranı açar.
var sonucEkran = 'ana';
function ekranListesi(liste) {
  $('ekranlar').innerHTML = liste.map(function (e) {
    return '<a href="#sonuc' + (e.kimlik === 'ana' ? '' : '-' + esc(e.kimlik)) + '" title="' + esc(e.aciklama) + '">' + esc(e.ad) + '</a>';
  }).join('');
  sonucIsaretle();
}
function sonucIsaretle() {
  document.querySelectorAll('#ekranlar a').forEach(function (a) {
    var k = a.getAttribute('href').replace(/^#sonuc-?/, '') || 'ana';
    if (k === sonucEkran) { a.setAttribute('aria-current', 'page'); var l = $('ekranlar'); l.scrollLeft = Math.max(0, a.offsetLeft - l.offsetLeft - 16); } else a.removeAttribute('aria-current');
  });
}
function sonucGoster(ekran) {
  sonucEkran = ekran || 'ana'; sonucIsaretle();
  sonucUygula();
}
// Çerçevedeki ekranı adres işaretiyle (#) değil geçmiş kaydıyla değiştir: # ile gezinmek dış sayfayı da kaydırıyordu.
function sonucUygula() {
  try {
    var w = $('sonucCerceve').contentWindow;
    if (!w || w.location.pathname !== '/klasik' || w.document.readyState === 'loading') return;
    if (w.location.hash.slice(1) === sonucEkran || (!w.location.hash && sonucEkran === 'ana')) return;
    w.history.replaceState(null, '', '#' + sonucEkran);
    w.dispatchEvent(new HashChangeEvent('hashchange'));
  } catch (h) { /* henüz yüklenmedi: yüklenince uygulanır */ }
}
function goster() {
  var ad = location.hash.slice(1), ekran = null;
  if (ad.indexOf('sonuc') === 0) { ekran = ad.slice(6) || 'ana'; ad = 'sonuc'; }
  if (['sonuc', 'uzay', 'lab', 'ajan'].indexOf(ad) < 0) ad = 'sonuc'; gorunum = ad;
  ['sonuc', 'uzay', 'lab', 'ajan'].forEach(function (x) { $('g-' + x).hidden = x !== ad; });
  $('botsec').hidden = ad === 'sonuc';   // bot seçimi Uzay ve laboratuvar içindir; Sonuçlar'ın kendi bot seçimi var
  if (ad === 'sonuc') sonucGoster(ekran);
  document.querySelectorAll('.gez a').forEach(function (a) { if (a.getAttribute('href') === '#' + ad) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  $('dok').hidden = ad === 'ajan'; window.scrollTo(0, 0);
  if (ad === 'uzay') { boyut(); kirli = true; if (uzayBayat) { uzayBayat = false; uzayYukle(); } if (sekme === 'hizli') hizliYaz(); }
  if (ad === 'lab' && sema()) labYaz();
  if (ad === 'ajan') { ajanDurumYukle(); arsivYukle(); sohbetYaz(); }
}
window.addEventListener('hashchange', goster);
function ozetYukle() {
  return api('/api/ozet').then(function (v) {
    ozet = v; var d = v.donem === 'sinav' ? 'Sınav ' + v.gun + ' / ' + v.sinav_gun + '. gün' : v.donem === 'isinma' ? 'Isınma dönemi' : 'Sanal dönem';
    $('sinav').textContent = d + ' · ' + v.toplam.calisan_bot + ' / ' + v.toplam.bot_sayisi + ' bot çalışıyor'; acikHesapla(); if (sekme === 'rapor') raporYaz();
  }, function () { $('sinav').textContent = 'Özet alınamadı'; });
}
botKur();
try { sahneKur(); } catch (h) { gl = null; $('uzayDurum').hidden = false; $('uzayDurum').textContent = 'Bu cihaz üç boyutlu çizimi açamadı. Yandaki paneller yine çalışır.'; cv.hidden = true; }
goster(); sohbetYaz();
$('sonucCerceve').addEventListener('load', function () {
  // Çerçevenin içinden başka ekrana geçilirse (ör. Ana ekrandaki bir bağlantı) üstteki liste de onu işaretlesin.
  sonucUygula();
  try { var w = $('sonucCerceve').contentWindow; w.addEventListener('hashchange', function () { sonucEkran = w.document.documentElement.getAttribute('data-ekran') || 'ana'; sonucIsaretle(); }); } catch (h) { /* farklı köken: yok say */ }
});
api('/api/ekranlar').then(ekranListesi, function () { /* liste alınamazsa sabit dört ekran kalır */ });
ozetYukle(); botYukle().then(function () { if (gorunum === 'lab') labYaz(); }); uzayYukle();
ajanDurumYukle(); api('/api/ajan/gecmis').then(function (v) { mesajlar = v.mesajlar || []; sohbetYaz(); }, function () { /* sessiz */ });
requestAnimationFrame(kare);
setInterval(function () { if (document.hidden) return; ozetYukle(); if (gorunum === 'uzay' && !uzayYukleniyor && !oynuyor && T >= ADIM - 1.05) uzayYukle(true); }, 150000);
})();
