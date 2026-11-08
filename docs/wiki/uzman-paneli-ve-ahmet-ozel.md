# Uzman paneli, panel sınaması ve Ahmet Özel stratejisi

> ZSD, TRG, ASYA, FON aileleri; Ahmet Özel 1. ve 2. sürüm; panel sonuçları.
> Kaynak: CLAUDE.md'nin 9 Kasım 2026 öncesi hali (sözcüğü sözcüğüne taşındı).

**Uzman paneli: dört bot önerisi (12 Ekim 2026, Ahmet'in isteği; Ahmet "başla, sen karar ver" dedi).**
Ahmet "botların mantığı çok kötü; 5 farklı okuldan muhalif uzmanlar tartışsın, ortak bir
strateji çıksın, 4 bot öner" dedi. Beş yapay zekâ ajanı rol yaptı (gerçek kişi değil; Ahmet'e
söylendi): SMC, kantitatif, trend (CTA), mikro yapı / türev, risk. Üç tur: açılış, çürütme,
ortak taslağa oy. Ortak teşhis: girişlerde bilgi yok, kayıp komisyon; "sık küçük vuruş"
taker komisyonuyla kurtarılamaz ("küçük" = işlem başına küçük risk, "sık" = çok coin).
- Bot 1 ZSD "Zorla satış dönüşü" (alım, 15 dk; 5 / 5 şartlı kabul): BTC 1 s ≤ −%2; coin 15 dk
  kapanışı Bollinger(20; 2,5σ) altı, hacim ≥ 4 × son 96 mumun ortancası; onay mumu önceki
  tepenin üstünde → piyasa emri. Çıkış: 1 s Bollinger orta bandı ya da %2,5; stop 2 × ATR(1 s)
  %2–3,5; 8 s. En çok 4 pozisyon, aynı şokta en çok 3. Denemeler: temel, + fonlama ≥ 0, +
  günlük > EMA50; plasebo BTC şartsız; bilgi satırı "iğne önceki gün dibini deldi mi".
- Bot 2 ve 3 TREND-G alım / açığa satış (günlük 28 g kapanış kanalı kırılımı, EMA20/50 yönü,
  fonlama süzgeci ±%0,03, giriş 1 s açılış; çıkış 14 g karşı kanal, iz tetik %6 mesafe %3,
  stop %8, 10 gün; 3 kabul / 2 şartlı): kanal 14 / 28 / 56 raporlanır, canlıya 28; aynı yönde
  en çok 5; yıl bazında 3 / 4; BTC'yi tutma karşılaştırması; "en iyi 3 gün" ölçütü yerine
  "≥ 3 coin ve en iyi 3 işlem çıkınca kayıp ≤ %2".
- Bot 4 ASYA AVI (SMC seans likidite avı; 4 şartlı, CTA ret): yalnız tek deneme, plasebolarla
  yan yana (12:00–18:59 penceresi, saat şartsız); süpürme ≥ 0,5 × ATR, stop ≥ max(%1,2;
  1,5 × ATR), 07:00–08:59'da en çok 2 giriş, eşzamanlı 2; hüküm ≥ 100 ayrı sinyal günü.
- 4. aday oylaması oybirliğiyle C: fonlama aşırılıkları önce yalnız sayılır (bot değil).
- Ortak kurallar: piyasa emri; kayma = max(%0,05; sinyal mumu aralığının %10'u), TREND-G'de
  en az %0,10; fonlama gerçek oranla; tutar = 1 USDT / stop (en çok 100); bot freni (24 s'te
  %2) ve StoplossGuard (trend botları seri kuralından muaf); portföy freni (aynı yönde toplam
  en çok 10, toplam 24 s zarar %2 → hepsi 24 s durur; kayıtçı + `confirm_trade_entry` + portföy
  benzetimi, yeni iş); stop ≤ 1,5 × hedef / tetik.
- Sınama: 4 yıl (Ekim 2022–Ekim 2026), son yıl ayrılmış ve bir kez açılır; o anki hacme göre ~20
  parite (Binance'ten silinmiş coinlerin verisi motorla inmez, yanılgı kısmen kalır); deneme
  defteri (eski 112 deneme dahil); kural dosyaları son yıl açılmadan işlenir; plasebo aynı
  benzetimde aynı kurallarla; gün bazında t ≥ 2,5; maliyet iki katında ≥ 0. 30 günlük canlı
  sınav yalnız uyumu sınar. Panel çoğunun elenmesini bekliyor.
- Şimdiki botlar: yeni botlar sunucuya çıkınca dördü durur, biri kontrol kalır (SM 3 oy, SMD 2).
- Gereken altyapı: BTC referans sütunu (informative pair), fonlama verisi (motor ve benzetim),
  `custom_stake_amount`, ATR'ye bağlı stop, protections ve benzetimdeki karşılığı, portföy
  freni, 4 yıllık veri indirme, seans aralığı göstergesi.
- Karşılaştırma botu: SM (karar Claude'un, Ahmet "sen karar ver" dedi; panelde 3 / 2 oy).
- **1. aşama yapıldı (12 Ekim 2026): panel sınaması** (Yapı tablosunda `sinama.py`, `fonlama.py`,
  `aday/`). Kural motoruna referans parite, gösterge kaydırma, ortanca hacim, fonlama, ATR stopu,
  portföy ve bilgi alanları eklendi; benzetim `_Yurutucu` / `aday_islemler` olarak bölündü
  (eski sonuçlar birebir aynı, 493 eski test değişmeden geçti). Canlı botlara, ayarlara
  dokunulmadı (kural.py değiştiği için botlar bir kez yeniden başlar). Deneme sayısı: ZSD 3, TRG 3,
  TRGK 3 (+ plasebolar). Panelin eşiklerinden seçilenler (bölünenlerde orta değer): ZSD stop
  tavanı %3,5, BTC şoku −%2 / 1 saat, 24 saatte en çok 3 giriş; TRG kanal çıkışı giriş
  kanalının yarısı (14→7, 28→14, 56→28); "en iyi 3 gün" ölçütü trend botlarına uygulanmaz.
  ASYA AVI ve fonlama sayımı sonraki aşama (`zaman_araligi` göstergesi, iğne altına stop, 1,5R hedef).
  Yalnız yapay veride sınandı; gerçek veri ve indirme sunucuda ilk kez (`PANEL_SURUMU=1`).

**Panel sınamasının ilk sonucu: üç aile de kaldı (`PANEL_SURUMU=1`, 12 Ekim 2026 17:25 UTC,
Ahmet iletti; geliştirme dönemi 13.10.2022–12.10.2025, 20 coin, eksik veri yok, fonlama indi).**
- ZSD: 68 işlem (41 ayrı gün), %52,9 kazanma, −3,41 USDT, işlem başına net −%0,125 (komisyon
  öncesi −%0,026); t −0,54; yıllar −2,44 / −2,71 / +1,74; rastgele plaseboya fark t 0,49. ZSDF
  −3,54, ZSDT −4,60. Bilgi: BTC şartı işe yarıyor gibi (BTC şartsız ZSDP 462 işlem, −%0,356;
  fark +%0,23) ama maliyeti karşılamıyor. Önceki gün dibini delen işlemler −%0,093, delmeyenler
  −%0,240 (az örnek).
- TRG (alım): TRG28 410 işlem, %55,4, −29,06 USDT, komisyon öncesi −%0,41; üç kanal da ekside
  (−39,08 / −29,06 / −16,67); rastgele alım plasebosundan kötü (t −1,83). Neden: iz süren stop
  (%6'da başlar, %3 geride) kazananı ~%+3'te keser, stop %8: asimetri yine ters; 14 günlük kanal
  çıkışı neredeyse hiç çalışmadı (6 / 410). Yani sınanan şey gerçek trend takibi değil, dar izli
  kırılım oldu. Değiştirmek yeni deneme demektir (bütçe 3 doldu); Ahmet'e söylendi, yapılmadı.
- TRGK (açığa satış): TRGK28 390 işlem, %57,7, +0,50 USDT (komisyon öncesi +%0,09), t 0,02;
  yıllar +10,09 / −5,32 / −4,27. Rastgele açığa satıştan belirgin iyi (t 3,15; rastgele satış
  −%1,09 kaybettirdi, yükselen piyasa) ama mutlak sonuç sıfır.
- Panel portföyü 868 işlem, −31,97 USDT. Ayrılmış yıl açılmadı (geçen yok).
- **2. aşama eklendi (`PANEL_SURUMU=2`):** ASYA / ASYAK (seans likidite avı) ve iki plasebosu,
  fonlama aşırılığı sayımı. Deneme defteri 123. Yapay veride (küçük fitilli rastgele yürüyüş) ASYA
  neredeyse hiç sinyal vermiyor (300 günde 0-2); gerçek veride sayısı bilinmiyor, 100 ayrı günden
  azsa "HÜKÜM YOK" yazar.

**Panel sınamasının ikinci sonucu (`PANEL_SURUMU=2`, 12 Ekim 2026 20:00 UTC, Ahmet iletti).**
ZSD / TRG / TRGK aynı (kaldı). ASYA: 85 işlem (68 ayrı gün, hüküm için 100 gerekirdi), %30,6
kazanma, −32,98 USDT, komisyon öncesi −%0,61, t −3,03 (belirgin kaybettiriyor; rastgele girişten
kötü, t −1,77); saat şartsız plasebo ondan iyi (−%0,62'ye karşı −%0,715). ASYAK: 143 işlem, −31,35,
t −2,31, kaldı; iki plasebo da ondan iyi. Seans likidite avı iddiası bu veride çürüdü. Panel
portföyü 1.096 işlem, −96,30 USDT. Fonlama sayımı: 3 yılda kalabalık alımda 359, açığa satışta 212
olay (BNB 59, BCH 39, TRX 35 satış tarafında); panelin "100'den çoksa bot" kuralıyla 3. aşama:
FON / FONK (mikro yapı uzmanının FONLAMA-SIKIŞMA önerisi: fonlama ≥ %0,05 ve son 3 ort. ≥ %0,03,
fiyat günlük EMA20'nin %8 ötesi, 1 s yapı dönüşü ya da 4 mumun ucunun kırılması; stop %4, iz %3 /
%1,5, 72 saat, en çok 3 pozisyon; risk yöneticisinin "eşzamanlı sınır yok" itirazıyla 3 eklendi),
tek deneme, fonlama şartsız plaseboyla. `PANEL_SURUMU=3`, deneme defteri 125.

**Ahmet Özel (13 Ekim 2026, Ahmet'in kendi stratejisi; "komiteye sun, limitleri belirle, adı
ahmetozel olsun, test et").** Ahmet'in metni: haftalıkta FVG ve destek / direnç; EMA ve SMA; CHoCH /
BOS; günlük trend aşağı ve kırılmadıysa teyit barından sonra açığa satış, yukarı ve destekten döndüyse
alım; ortalamalar doğru olmalı; MACD dönüş vermeli. Beş uzmanlı komite (yine yapay zekâ rolleri)
yorumladı; çoğunluk kararı aday kural olarak yazıldı (`aday/AHMETOZEL*.json`, panel sınamasında iki
aile, `PANEL_SURUMU=4`, deneme defteri 131):
- Günlük taban. Günlük yapı (salınım 5) yukarı ve son 10 günün hepsinde yukarı ("kırılmadı" = son 10
  günde ters CHoCH yok; `en_dusuk` göstergesi `yapi_yon` sütunundan). EMA20 > EMA50, kapanış > SMA200.
- Destek: haftalık (günlükten toplanır, Pazartesi başlar) son onaylı salınım dibi (uzunluk 3) ya da açık
  haftalık boğa FVG'nin üstü (en az %1,5, ömür 26 hafta). Son 3 günde dip ≤ destek + 0,5 × ATR(14) ve
  bugün destek üstünde kapanış (yeni: `atr` mutlak ATR türü, işlenende `ekle`).
- Teyit barı: kapanış > önceki günün tepesi. MACD(12,26,9) histogramı son 3 günde 0'ı yukarı kesmiş.
- Giriş ertesi açılış, piyasa emri; kayma en az %0,10, aralık payı yok (günlük mum).
- Stop: son 5 günün dibinin 0,5 × ATR altı; en az 1 × ATR ve %3, en çok %10. Denemeler: 1 hedef 2R /
  30 gün (canlıya gidecek), 2 hedef 3R / 30 gün, 3 hedef yok, günlük yapı ters dönünce (CHoCH) çık /
  60 gün. Portföy: 4 pozisyon, 24 saatte 3 giriş, coin başına günde 1, seri stop kilidinden muaf.
- Açığa satış (AHMETOZELK) aynası: haftalık salınım tepesi ya da ayı FVG'nin altı, kapanış < önceki
  günün dibi, histogram aşağı keser, stop son 5 günün tepesi + 0,5 × ATR.
- Plasebolar: P1 destek / direnç / FVG şartı yok (karar bunu kullanır: asıl kural işlem başına en az
  0,15R iyi olmalı), P2 MACD şartı yok (yalnız bilgi). Karar ayrıca: işlem başına ≥ 0,15R, ortalama
  kazanç / kayıp ≥ 1,5, en büyük düşüş ≤ 15 USDT, en az 60 işlem ve 40 ayrı gün (azsa HÜKÜM YOK) +
  panelin ortak ölçütleri (t ≥ 2,5, maliyet iki katı, yıllar, rastgele giriş plasebosu, en iyi 3 gün,
  alımda BTC ilişkisi).
- Yapay rastgele veride (günlük, %3,5 oynaklık) coin başına 3 yılda 1-4 sinyal: gerçek veride de az
  işlem çıkabilir ve sonuç "HÜKÜM YOK" olabilir. Komitenin beklentisi: alım tarafı büyük olasılıkla BTC
  yönünü taşır (BTC ilişkisi ölçütü bunu yakalar); açığa satış tarafı daha umutlu. Ahmet'e söylendi.

**Panel sınamasının dördüncü sonucu (`PANEL_SURUMU=4`, 13 Ekim 2026 12:16 UTC; sunucudaki
oturumdan okundu).** ZSD / TRG / TRGK / ASYA / ASYAK önceki gibi. FONK: 129 işlem, −28,08 USDT,
t −2,97, fonlama şartsız plasebodan da kötü: KALDI. FON: 104 işlem, −9,60, t −0,89, rastgele girişten
farksız: KALDI. Panelin önerileri tükendi. Panel portföyü 1.376 işlem, −139,82 USDT.
- AHMETOZEL (alım): 26 işlem (24 gün), %42,3 kazanma, +3,52 USDT, +0,14R / işlem, kazanç / kayıp 1,68,
  t 0,47, yıllar −3,66 / +2,31 / +4,87, maliyet iki katında +3,00, BTC ilişkisi 0,03; rastgele aynı
  süreli alım işlem başına +%0,79 (fark t 0,18). HÜKÜM YOK (60 işlem gerekir). Deneme 2 (3R) +5,41,
  deneme 3 (yapı dönünce çık) +18,02 (25 işlem, %24 kazanma, kazanç / kayıp 6,59; +17,60'ı 2. yıldan).
  Destek / FVG şartsız plasebo P1: 111 işlem, +0,14R, +15,81 (fark −0,01R: destek şartı katkı
  göstermiyor, yalnız işlem sayısını azaltıyor). MACD şartsız P2: 104 işlem, −0,20R (MACD dönüşü
  +0,34R fark; az örnek).
- AHMETOZELK (açığa satış): 21 işlem, %19 kazanma, −9,38; üç deneme de ekside; direnç şartsız P1
  −0,11R (direnç şartı −0,33R kötüleştiriyor). HÜKÜM YOK ama yön olumsuz. Komitenin beklentisinin tersi.
- Ahmet'e söylendi; sonraki adım onun kararı (kurallara dokunmadan daha fazla coin / daha eski yıllar
  ile sınamak ya da P1 benzeri yeni deneme).

**Ahmet Özel 2. sürüm (13 Ekim 2026, Ahmet'in kriter sayfasındaki 17 isteği; `PANEL_SURUMU=5`).**
Uygulanan: günlük salınım 5→2 ve haftalık salınım 3→2 (Ahmet 1 istedi; motor en az 2 kabul eder,
tek mumluk salınım gürültü), "kırılmadı" 10→2 gün, EMA 20/50→9/21, SMA 200→50, FVG en az %1,5→0,9,
yaklaşma 0,5→0,3 ATR ve 3→2 gün, MACD dönüşü 3→1 gün, stop son 5→2 günün dibi, stop en az %3→2,
hedef 2→1,5R (deneme 2: 3R aynı), süre 30→15 gün (deneme 3: 60→30), pozisyon 4→10, 24 saatte giriş
3→50. Reddedilen: "en az farklı gün" 40→2 (karar ölçütünü gevşetmek; 40 kaldı). Kural dosyaları yerinde
değişti (1. sürüm git geçmişinde ve yukarıdaki sonuçta), gösterge adları değere bağlı olmaktan çıktı
(`ema_kisa`, `ema_uzun`, `sma_uzun`, `yon_n`, `dip_n` / `tepe_n`). Deneme defteri: `ONCEKI_DENEME`
118 (1. sürümün 6 denemesi eklendi), toplam 137. Yapay veride sinyal 1. sürümden de az (seri başına ~1).

**Ahmet Özel 2. sürümün sonucu (`PANEL_SURUMU=5`, 13 Ekim 2026 17:55 UTC; sunucudaki oturumdan okundu).**
Alım: 10 işlem (9 gün), %40 kazanma, −0,27 USDT, −0,03R / işlem; 3R denemesi +0,69, yapı dönünce çık −4,35.
Açığa satış: 11 işlem, %27, −5,52; üç deneme de ekside. İkisi de HÜKÜM YOK; 1. sürümden kötü ve daha az
işlem. Destek / FVG şartsız P1: alım 124 işlem −0,01R (şart yine katkı göstermiyor). MACD şartsız P2:
alım −0,25R (MACD dönüşü iki sürümde de +0,2-0,3R fark; tek tutarlı ipucu, az örnek). Diğer aileler aynı.
- **On yedinci uyum denemesi (12 Ekim 13:31 UTC) geçti.** Eşleşen işlemlerin net toplamı motor / benzetim:
  SM 47 işlem −4,76 / −2,94, SMK 21: −7,01 / −8,66, SMD 40: −2,80 / −0,84, SMDK 18: −4,50 / −5,89, Sniper 39:
  −12,34 / −11,04. İz süren stopta benzetim neredeyse hep daha geç kapatıyor; işlem başına alımda benzetim
  ~%0,1 iyimser, açığa satışta ~%0,25 kötümser. Fark işlem başına %0,2 eşiğinin çoğunlukla altında:
  benzetim değiştirilmedi.
- **Stop sonrası izleme gerçek veride çalışıyor (13 Ekim 19:12 UTC):** `stop_sonrasi.json`'da 145 işlem,
  2 başarısız, henüz ders yok (bot başına 30 stop gerekir).
