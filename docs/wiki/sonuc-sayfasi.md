# Sonuç sayfası: görünüm, ekranlar, işlem grafiği

> Rapor, Analiz, Grafikler, Zaman, İşlem grafiği, premium görünüm, uzman toplantısı.
> Kaynak: CLAUDE.md'nin 9 Kasım 2026 öncesi hali (sözcüğü sözcüğüne taşındı).

**Rapor ekranı (12 Ekim 2026, Ahmet'in isteği).** "Ortadaki değer kalsın; bir rapor
sayfası yap, bot seçimi olsun, her botun günlük kâr / zararını gösterelim." Sonuç
sayfasına altıncı ekran: bot seçimi (Bütün botlar + her bot), seçilen botun toplamı,
artıda biten gün, en iyi / en kötü gün, son 30 günün çubuk grafiği, gün gün tablo.
Ana ekrandaki halkanın ortası değişmedi. Not: halkanın ortası "toplam sanal sonuç"tur
(ısınma / sınav başından beri); Ahmet onu son 24 saat sanıyor, ona söylendi. Sayfa
yalnız buradaki Chromium'da (390 px ve 1280 px, betikli ve betiksiz) denendi.

**Premium görünüm (6 Kasım 2026, Ahmet'in isteği).** Sonuç sayfasının CSS'ine `sayfa.STIL` sonunda bir "Premium katman" eklendi
(koyu lacivert zemin, şampanya altını vurgu, cam kartlar, yuvarlak köşeler, bulanık alt / üst gezinti). Yalnız görünüm: ekranlar,
sınıf adları, betik ve izin başlığı aynı; 591 test geçti. Yalnız buradaki Chromium'da (390 ve 1280 px) denendi. Ahmet'in
telefonundaki tarayıcıda görülmedi. Aynı gün çalışma notları ve kurallar claude.ai'de bir belgeye de yazıldı
(https://claude.ai/artifact/7UUxEcuWXbwaN8ZgbAxbmf). PlanningExpert sitesinin yedeklenip arşivlenmesi istendi; o site bu
depoda değil, sunucuda ve burada erişilemiyor (karar bekliyor).

**Analiz ekranı (6 Kasım 2026, Ahmet'in isteği).** Sonuç sayfasına yedinci ekran "Analiz" eklendi (`sayfa._analiz_ekrani`):
bot başına net sonuç (sıfırın iki yanında çubuk), kazanma / başa baş / beklenti / kâr faktörü tablosu, çıkış nedenleri, ortalama işlem süresi.
Yalnız okur; ayar yazmaz. Kazanma ve başa baş oranları zaten yüzde olarak gelir (`karne.py`); ekranda bir daha 100 ile çarpılmaz
(testli). Yalnız buradaki Chromium'da (390 px) denendi.

**Uzman toplantısı ve site geliştirmesi (6 Kasım 2026, Ahmet'in isteği).** Dört alt ajan (mimari, programlama, kripto
trader, görsel tasarım) 5'er geri bildirim verdi; 20 madde birleştirildi. Uygulanan:
- Analiz ekranı yeniden yazıldı: bot başına karne kartı (kazanma, işlem başına USDT ve %, ort. kazanç / kayıp USDT, en kötü
  işlem, en uzun kayıp serisi, kâr faktörü, "bir kayıp kaç kazancı siler"), coin bazında sonuç ve tek coin payı, çıkış nedenleri
  (`sonuc.CIKIS_NEDENI`'nin Türkçe değerleriyle eşleşir), süre çubuğu soldan ve `_sure` ile. Başa baş rengi en az 5 kayıp yoksa
  verilmez. İşlemsiz bot "henüz işlem yok" der, %0 göstermez.
- `sonuc.py`: `risk_olcumleri`, `guven_etiketi` (gün bazında t; < 10 gün "Veri az", |t| ≥ 2,5 belirgin), `parite_ozeti`,
  `acik_risk` (açık pozisyonun stop fiyatı ve stopta yaklaşık kaybı; ek giriş bekleyen / yapılmış SMK2 / SMDK2 ayrı hesap,
  komisyon hariç), `toplam.acik_stopta_kayip`. İşlemler ekranında "hepsi stopa giderse" şeridi; bot kartında güven rozeti.
- Panel: içerik özetinden ETag ve 304, istenirse gzip, `Cache-Control: private, no-cache`, son başarılı özet (hata olursa eski
  özet sunulur, 20 sn sonra yeniden denenir), `/saglik` özetin yaşını yazar (hiç özet yoksa 503), hata sayfası ayrıntı yerine
  kimlik gösterir (ayrıntı kayıtta), ek başlıklar (X-Frame-Options, Permissions-Policy, COOP, CORP).
- Betik: 15 sn zaman sınırı, üst üste istek yok, gizli sekmede tazelemez, hata türüne göre mesaj ve son başarılı saat.
- Görünüm: ayrı uyarı rengi (`--uyari` turuncu; ses vermeyen bot dilimleri ve üstte uyarı şeridi), alt gezinti telefonda
  8 eşit sütun ve kısa adlar (`GEZINTI_ADLARI`), kartlarda bulanıklık kaldırıldı (yalnız gezintide), köşe ölçüleri 8 / 12 / 20.
- Ertelenen: (1) karne USDT'yi yüzde × 50 ile hesaplıyor; ek girişli işlemde `stake_amount` toplam teminatsa SMK2 / SMDK2'nin
  net ve düşüş değerleri küçük çıkar. Sunucudaki kayıtla doğrulanmadan `karne.py`'ye dokunulmadı (sınav ölçütlerini etkiler).
  (2) Bot başına eğri, gezinti simgeleri, diğer ekranlarda açıklamaları `<details>` içine alma, `EKRANLAR` yeniden yapısı
  (yalnız "her ekran bir kez" testi eklendi), Caddy için fail2ban, `/defter` önbelleği.
- 617 test geçiyor. Yalnız buradaki Chromium'da (390 px) görüldü; Ahmet'in iPhone Safari'sinde denenmedi.

**Yeni sayfalar, başlık ve menü (6 Kasım 2026, 2. tur; Ahmet'in isteği).** Ekran sırası: ana, botlar, işlemler, dersler, rapor,
grafikler, zaman, analiz, sınav, kriterler.
- **Grafikler** (`_grafikler_ekrani`): botların birikimli seyri (zaman eksenli çok çizgi, en çok 8 bot, renk bota bağlı
  `SERI_RENKLERI`), tepeden düşüş (alan), işlem sonuçlarının dağılımı (sıfıra hizalı histogram), süre ve sonuç (saçılım).
- **Zaman** (`_zaman_ekrani`): açılış saatine (Bükreş) ve haftanın gününe göre net sonuç çubukları; "az işlemli saat şansa açık" uyarısı.
- Veri `sonuc.grafik_verisi` (`zamanli_egri`, `dusus_egrisi`, `zaman_dagilimi`, `sonuc_dagilimi`, `sure_sonuc_noktalari`), `ozet["grafik"]`.
- Grafikler satır içi SVG (`_Cerceve`, `_guzel_adimlar`); ipuçları `<title>` ile, betiksiz de çalışır.
- Başlık: yapışkan çubuk (marka, çalışan bot / toplam etiketi, "Menü" açılır menüsü: `<details class="menu">`, bütün ekranlar
  ve kısa açıklamaları `MENU_ACIKLAMA`). Alt çubuk telefonda yalnız 5 sekme (`ALT_CUBUK`); masaüstünde alt çubuk yok, menü var.
- 627 test geçiyor. Yalnız buradaki Chromium'da (390 ve 1280 px) görüldü.

**İşlem grafiği (6 Kasım 2026, 3. tur; Ahmet'in isteği: "bot seçip işleme tıklayınca grafikte nerede girip çıktığımı göreyim").**
- Ekran `islemgrafik` (`sayfa._islem_grafigi_ekrani`): bot seçimi betiksiz (gizli seçim düğmeleri `ig-<k>`, en çok 16 bot), seçilen
  botun açık işlemleri ve son 40 kapanmış işlemi (`ozet["islem_listesi"]`, `sonuc.ISLEM_LISTESI_SAYISI`); her satır `/islem?bot=..&id=..`.
- `karabasan/islem_grafik.py` + panel `/islem`: işlemi botun SQLite kaydında bulur (`islem_bul`; yalnız `BOTLAR`'daki bot adları,
  kimlik yalnız rakam), süreye göre mum aralığı seçer (1m…1d, en çok 240 mum, işlemin iki yanında pay), Binance'in açık
  `klines` adresinden indirir, mum grafiği çizer: giriş / çıkış işaretleri (açığa satışta giriş aşağı ok), işlem süresi bandı,
  giriş fiyatı, stop, iz tetiği / hedef çizgileri. Kapanmış işlemin mumları bir kez indirilir (`MumOnbellegi`), açıkta 60 sn.
  Ağ hatasında sayfa düşmez, "alınamadı" der. Sayfada betik yok.
- Alt çubuk: Ana, Botlar, İşlemler (= İşlem grafiği), Grafik, Analiz. Betik tazelemede bütün seçili düğmeleri korur.
- **Gerçek sunucuda ilk kez:** panelin kapsayıcısından `fapi.binance.com/fapi/v1/klines`'a ulaşması (stop sonrası izleme `kayitci`
  kapsayıcısında ulaşıyor; panel kapsayıcısının ağı aynı olmalı, doğrulanmadı), sayfanın açılış süresi. 638 test geçiyor.

## Coin listesi (`/coinler`, 10 Kasım 2026)

`karabasan/coinler.py`: Binance vadeli `exchangeInfo` (işlemde, sürekli, USDT) + `ticker/24hr` (`quoteVolume`). Stable coinler `STABLE` kümesiyle çıkarılır (botların `SABIT_COINLER` listesini kapsar; test bunu doğrular). Hacim sınırı `?hacim=<milyon USDT>` (varsayılan 5, botlarla aynı); sayfada kutu ve hazır düğmeler var, betik yok. 5 dakika önbellek. Tablo hacme göre sıralı: coin, hacim, fiyat, 24 saatlik değişim. Yalnız bilgi: botların işlem evreni (`yapilandirma_uret.py`) değişmedi. Sınanmayan: gerçek Binance yanıtı (burada erişim yok; testler sahte veriyle).

**Beş ek ekran: Risk, Rejim, Likidite, Güven, Disiplin (10 Kasım 2026; Ahmet'in isteği, istem: `site-yeni-sayfalar-istemi.md`).**
Beş ekip (her biri trader + görsel + programcı rolünde; 15 yerine 5 ajan, maliyet yüzünden) birer ekran yazdı. Yalnız Menü'de
açılır; alt çubuk ve eski ekranlar aynı. Hepsi yalnız okur, betik eklemez, bot ayarı yazmaz.
- Bağlantı: `karabasan/ek_sayfalar.py` (`EK_EKRANLAR`, `EK_MENU_ACIKLAMA`). `sonuc.genel_ozet` her ekran için `sonuc_<ad>.hesapla(baglam)`
  çağırır (`ozet["ek"]`); `sayfa.html_uret` `sayfa_<ad>.ekran()` ve `STIL`'i ekler. Bir ekran hata verirse yalnız o "hazırlanamadı" der.
- **Risk:** açık pozisyonların stopta kaybı (toplam bütçe = 4 × 1.000 USDT payda), "hepsi stopa giderse", tepeden düşüş ve su altı süresi,
  yön / coin yoğunlaşması (hepsi açığa satış), son 14 günün günlük teminat kullanımı, SMK2 / SMDK2 ek giriş yapılmış / bekleyen ayrı.
  "Düşük / orta / yüksek" (%1, %3) yalnız okuma kolaylığı, botların kuralı değil. Karne ile kayıtlı net farkı (ek girişli işlem) yan yana.
- **Rejim:** **canlı Karabasan puanı, durumu ve veto kaydı yoktur** (büyük uyarı kutusu). Kurallar (ağırlık, eşik, veto) `puan.py`'den
  metin olarak okunur; `kuresel.csv`'den son 30 günün dominans / TOTAL2 seyri ve kayıt boşlukları; işlem kaydından yeniden kurulan
  "art arda stop" pencereleri (canlı motor kaydı değil). Bulgu: botlar `izinli_durumlar`'a bakmıyor (aşağıda).
- **Likidite:** coin başına fonlama (short için alır / öder), açık faiz değişimi (1 / 4 / 24 saat), spread, 24 saatlik hacim ve kaba "sıkışma
  riski" etiketi (eşikler **sınanmadı**, sayfa da söyler); BTC defter dengesi `defter.sqlite`'tan; tasfiye kümeleri "veri yok". Veriyi yalnız
  panel süreci arka planda çeker (`panel.main` → `sonuc_likidite.ag_ac()`), 5 dakikada bir en çok 13 GET (`fapi.binance.com`, anahtarsız);
  hatada bekleme 5 dk'dan 1 saate kadar ikiye katlanır. Telegram dosya hali ve testlerde ağ kapalı ("yalnız canlı sayfada dolar").
- **Güven:** tek cümlelik hüküm, bot başına gün bazında t ve p (Student t, standart kütüphane), 100 işlem sayacı ve hız, kazanma oranı
  Wilson %95 aralığı ile başa baş karşılaştırması, en iyi / en kötü coin ve en iyi gün çıkarılınca sonuç, 12 aylık test farkı, çoklu bakış
  uyarısı (17 bakış). Yeşil rozet çıtası: t ≥ 2,5, p ≤ %1, ≥ 100 işlem, aralık başa başın üstünde, tek coine / güne bağlı değil.
- **Disiplin:** yedi kural denetimi (günlük bütçe, aynı coinde iki pozisyon, 1 kat botta ek giriş, tek ek giriş hakkı, stoptan sonra bekleme,
  stopun üstünde kayıp, sessiz bot: temiz / ihlal / denetlenemedi), stopa giden işlemlerin saat (4 saatlik) / gün / coin / bot kırılımı,
  yaklaşık komisyon ve ek kayma payı, kazanan / kaybeden süresi, stop genişliği dersi bağı, "bugün dikkat edilecek 3 şey" (kural tabanlı).
- Testler: 866 (1 atlanan: Güven'in pandas'sız `hesapla` denemesi; `sonuc` → `karne` pandas ister, panel kapsayıcısında sorun değil).
  Yalnız buradaki Chromium'da sahte veriyle 390 ve 1280 px, betikli ve betiksiz denendi; yatay taşma yok.
- **Gerçek sunucuda ilk kez:** bütün hesaplar gerçek kayıtla; Likidite'nin Binance yanıt biçimleri (ezberden yazıldı) ve HTTP 451 olasılığı;
  büyük `kuresel.csv`'nin sondan okunması; Disiplin'in bekleme ve stop taşma denetimleri gerçek veride yanlış alarm verebilir;
  ek girişlerin `orders` tablosundan okunması; Ahmet'in iPhone Safari'si.
