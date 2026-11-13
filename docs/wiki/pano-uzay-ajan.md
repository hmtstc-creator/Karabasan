# Yeni pano: Karabasan Uzayı, geçmiş test laboratuvarı ve ajan

> 10 Kasım 2026, Ahmet'in isteği. Sitenin ana sayfası artık bu panodur; önceki bütün ekranlar `/klasik` adresinde durur.
>
> **Düzeltme (10 Kasım 2026 akşamı):** Ahmet "kaç para kazandığımı gösteren ekranlar kayboldu, tüm ekranları geri getir, senin
> sayfalarını da silme" dedi. Ana sayfa (`/`) yine eski sonuç sayfasıdır (`/klasik` aynı); pano silinmedi, `/pano` adresinde ve
> sonuç sayfasının Menü'sünde "Yeni pano". Panonun üst bağlantısı "Kazanç ve bütün ekranlar" `/`'a döner.
>
> **Birleştirme (10 Kasım 2026 gecesi):** Ahmet "uzay sayfası ve yeni format nereye gitti? Eski ile yeni formatın hepsini bütün yapıp
> yeni formatta yapman lazım" dedi. Ana sayfa (`/`) yeniden panodur ve ilk sekmesi **Sonuçlar**'dır: üstte 16 ekranın yatay kayan listesi
> (`/api/ekranlar`, `sayfa.EKRANLAR` sırası), altta çerçevede `/klasik?gomulu=1` (eski sonuç sayfası; kendi başlığı ve alt çubuğu gizli,
> site bağlantıları bütün pencerede açılır). Eski sayfanın rengi panonunkine çekildi (`sayfa.SIYAH_STIL`: siyah zemin, düz kartlar, ay sarısı).
> Çerçeve yalnız aynı kökenden: `/klasik?gomulu=1` `X-Frame-Options: SAMEORIGIN` ve `frame-ancestors 'self'`; düz `/klasik` yine `DENY`.
> Pano izin başlığına `frame-src 'self'` eklendi. Ekran geçişi çerçevede `history.replaceState` ile (# ile gezinmek dış sayfayı kaydırıyordu).
> Adresler: `#sonuc` (Ana ekran), `#sonuc-rapor`, `#sonuc-risk` vb. Pano açılamazsa `/` eski sayfaya döner. 872 test; yalnız buradaki
> Chromium'da sahte veriyle 390 ve 1280 px denendi, yatay taşma ve konsol hatası yok. **Gerçek sunucuda ilk kez:** çerçevenin Caddy
> arkasında (parolalı) açılması, iPhone Safari'de çerçeve içi kaydırma.

> **Gezinti toparlandı (11 Kasım 2026):** Ahmet "panoya geçince site başka yere geçiyor, sayfalar ve erişimler karışık" dedi. Neden: alt sayfaların
> "Ana sayfa" bağlantıları eski `/klasik` sayfasına dönüyordu. Şimdi hepsi panoya (`/#sonuc-...`) döner ve ortak şeridi (`karabasan/site_gezinti.py`)
> taşır; pano üst çubuğunda Kriter ayarı ve Coin listesi de var. Erişim haritası: `/` pano (Sonuçlar, Uzay, Ayar ve geçmiş test, Ajan);
> `/ayar` `/detay` `/islem` `/coinler` `/defter` alt sayfalar; `/klasik` yalnız çerçevenin kaynağı (tek başına yedek). Gerçek telefonda ilk kez görülecek.

## Ahmet ne istedi

- "Sabit bir kalıpta kaldı; bütün sitenin görselliğini ve mimarisini değiştir." İlk öneri (telefon ölçüsünde dört ekran) yetersiz bulundu:
  "coinleri uzayda göster, alıma yaklaşanlar, uzak kalanlar, filtreler; yalnız telefon değil, PC dashboard da olmalı."
- Uzay önerisini beğendi ve şunları ekledi: bütün detay ayarları kontrol edebileceği ekranlar; "daha önce indirdiğimiz verilerle, yaptığım
  ayarlarla anında sitede geçmiş test"; sitede bir ajan ("Opus 5.5, düşük çaba; parametreler ve sonuçlar hakkında konuşayım, geri bildirim
  versin, gerekirse sitede güncelleme yapsın; ana ekranda altta dursun, ayar sayfasına bağlı olsun; konuşmalar wiki düzeninde arşivlensin,
  unutmasın, geçmişten ders alsın; sonra daha sağlıklı bot ayarları üretsin"). "Siteyi hazırla ve canlıya al."
- Renk: "mordan siyaha çevir" (aynı gün). Zemin siyah, vurgu ay sarısı, ikincil vurgu açık gri.

## Mimari

| Parça | Dosya | Ne yapar |
| --- | --- | --- |
| Sayfa | `karabasan/statik/pano.html`, `pano.css`, `pano.js` | Tek sayfa, üç görünüm (`#uzay`, `#lab`, `#ajan`); altta her görünümde ajan çubuğu. Dış kaynak yok. |
| Üç boyut | `karabasan/statik/three.min.js` (three.js r128, MIT) | Depoda durur; izin başlığı yalnız `script-src 'self'` verir. Yazı tipi: `bricolage*.woff2` (OFL). `LISANSLAR.txt`. |
| Bağlantı | `karabasan/pano.py` | `/`, `/s/<dosya>`, `/api/...` adresleri; `panel.py` bunlara yönlendirir. |
| Uzay hesabı | `karabasan/uzay.py` | 21 coin, son 24 saat, 5 dk mum: her mumda hangi giriş şartı eksik (bit maskesi). `MumDeposu` yalnız eksik son kısmı indirir. `bot_semasi` botun bütün ayarlanabilir sayılarını verir. |
| Geçmiş test | `karabasan/gecmis_test.py` | Denenen ayarı sunucudaki mum dosyalarında çalıştırır (12 aylık testle aynı benzetim motoru). 30 / 90 / 180 / 365 gün. Arka planda, ilerleme göstergeli. |
| Ajan | `karabasan/ajan.py` | Claude Opus 5.5 (`claude-opus-5-5`), çaba `low`. Anthropic Messages API'sine `urllib` ile bağlanır. Araç döngüsü, arşiv, anahtar. |

**Uzayın anlamı:** merkez = bütün şartlar doğru (giriş anı); halka = eksik şart sayısı (tam sayı); bölge = eksik şartların çoğunun ait
olduğu grup (Büyük yön: günlük / saatlik; Bölge: 15 dk; Tetik: 5 dk; Hacim); yükseklik = 24 saatlik pencerenin başından beri fiyat
değişimi; halka içindeki coin = o botun açık işlemi. Dört bot da açığa satış yaptığı için "girişe yaklaşan" = açığa satışa yaklaşan.
Uzayda sabit 21 coin vardır; canlı botlar hacme göre seçilen daha geniş listede işlem yapar (sayfada yazıyor).

**Geçmiş test:** veri `user_data/data/binance/futures/<COIN>_USDT_USDT-<dilim>-futures.feather` (12 aylık test ve panel sınamasının
indirdikleri). Dosyası olmayan coin 90 güne kadar olan dönemlerde Binance'ten o an indirilir, uzun dönemde atlanır ve sonuçta yazılır.
Sonuç: bütün dönem, **seçim (ilk %70) / doğrulama (son %30)**, dört parça, coin coin, çıkış nedenleri, ölçütler, ayar canlıdan farklıysa
aynı dönemde canlı ayar. Uyarılar: 30'dan az işlem; doğrulamada 10'dan az işlem; seçim artıda ama doğrulama değil. Karabasan süzgeci
uygulanmaz (12 aylık testte de uygulanmıyor). Buradaki ölçüm: 2 coin × 365 gün × 2 kural ≈ 2,6 sn (yapay veri).

**Ajanın sınırları (bilerek dar):** araçları `canli_sonuclar`, `parametreler`, `uzay_durumu`, `gecmis_testi`, `ayar_kaydet`,
`kayitlari_listele`, `ders_yaz`, `arsivde_ara`. Canlı botu, kural dosyasını, sitenin kodunu, sunucuyu değiştiremez; kabuk komutu
çalıştıramaz. "Sitede güncelleme" = laboratuvara adlı kayıt yazmak ("Ajan: …"); Ahmet panoda "Laboratuvara yükle" ile açar. Kayıt canlıya
gitmez (3. kural). Bir soruda en çok 8 araç turu; günde en çok 80 mesaj (`GUNLUK_MESAJ_SINIRI`). Sistem yönergesi ajana geçmiş testin kanıt
olmadığını, 12 aylık testlerde kenar çıkmadığını ve doğrulama dönemine bakmasını söyler; "kazandırır" demesi yasak.

**Ajanın hafızası** (`user_data/kayit/ajan/`, sunucuda kalır; depoya girmez): `README.md` (dizin), `konusmalar/GGGG-AA-GG.md` (gün gün,
Bükreş saati), `dersler.md` (kalıcı notlar; her konuşmanın başında okunur), `mesajlar.jsonl`, `sayac.json`. Her soruda ajana ders defteri
ve son 16 mesaj verilir; daha eskisini `arsivde_ara` ile bulur. Sunucudaki Claude oturumu bu klasörü onaysız okuyabilir (`kayit` izni).

**Anahtar:** Ahmet panoda Ajan sekmesinden girer (POST `/api/ajan/anahtar`). `user_data/gizli/ajan_anahtar` (0600) dosyasına yazılır;
hiçbir yanıtta, kayıtta ya da arşivde görünmez. `user_data/gizli/` `.gitignore`'da ve sunucu oturumunun `deny` listesinde.
Ajan Anthropic'in ücretli API'sini kullanır (Claude aboneliğinden ayrı fatura): Opus 5.5 girdi 4 USD, çıktı 20 USD / milyon token;
bir soru kabaca birkaç sent. Sayfa günün yaklaşık tutarını gösterir.

**API ayrıntısı:** `anthropic-version: 2026-10-21`; `output_config: {effort: "low"}`; düşünme ayarı gönderilmez (Opus 5.5'te kapatılamaz);
`fallbacks: "default"` + `anthropic-beta: server-side-fallback-2026-07-01` (güvenlik süzgeci reddederse yedek model). Araç turunda
yanıtın içeriği (düşünme blokları dahil) değiştirilmeden geri gönderilir. Önceki konuşma asistan mesajı olarak değil, metin olarak
verilir (düşünme blokları konuşmaya bağlı olduğu için). Neden kütüphane değil: panel hazır motorun görüntüsünde çalışır, orada
Anthropic kütüphanesi yok; özel görüntü kurmak bütün botları yeniden başlatırdı.

## Adresler ve güvenlik

- `/` pano; `/klasik` eski sayfa (eski sayfaların "Ana sayfa" bağlantıları `/klasik#...` oldu); `/ayar`, `/detay`, `/islem`, `/defter` aynı.
- Yazma yolları: eski `/ayar/kayit` ve yeni `/api/test`, `/api/kayit`, `/api/ajan`, `/api/ajan/anahtar`. Hepsi `X-Karabasan: 1` başlığı
  ister, gövde en çok 32 KB. Caddy kuralı: `not path /ayar/kayit /api/*` (parolalı; ötesi 405). Yeni internet kapısı açılmadı.
- Hiçbir adres emir göndermez, bot ayarı ya da kural dosyası değiştirmez (testli: kural dosyalarının özeti testten önce ve sonra aynı).

## Sınanan / sınanmayan

Sınanan (burada, 751 test geçiyor): uzay maskesi kural motorunun sinyaliyle birebir; geleceğe bakmama; pasif şart; geçersiz ayar; geçmiş testin
toplamları; ajanın araç döngüsü, kaydı, hafızası, sınırları; anahtarın hiçbir yanıtta görünmemesi; izin başlığı; klasör dışına çıkamama.
Pano buradaki Chromium'da 1440 px ve 390 px'te, yapay veri ve sahte Anthropic yanıtıyla uçtan uca denendi.

**Gerçek sunucuda ilk kez çalışacaklar:**
1. Mum dosyalarını okumak (feather / pyarrow buradaki ortamda yok; taklit okuyucuyla denendi). Dosya adları ve hangi coinlerin hazır olduğu.
2. Binance'ten 21 coinin mumlarını çekmek (panel açılırken arka planda; ilk açılış onlarca saniye sürebilir).
3. Anthropic API'sine gerçek çağrı (model adı, `effort`, `fallbacks` alanları yalnız belgeye göre yazıldı; hiç gerçek çağrı yapılmadı).
4. Caddy ayarının `/api/*` ile yeniden yazılması; panelin `user_data/gizli/` ve `user_data/kayit/ajan/` altına yazması.
5. Üç boyutun Ahmet'in telefonunda ve bilgisayarında açılması (WebGL); açılmazsa sayfa bunu yazar, paneller çalışır.
6. Kapsayıcıda `Europe/Bucharest` saat dilimi verisi (yoksa arşiv saatleri UTC olur).

## Henüz yok

- Karabasan puanı panoda gösterilmiyor (canlıda ölçülmüyor).
- Uzaydaki "girişe uzaklık" tam sayıdır (eksik şart sayısı); eşiğe ne kadar kaldığı (sürekli uzaklık) hesaplanmıyor.
- Ajan canlıya ayar taşıyamaz ve taşımamalı; yeni sanal bot isteği yine bulut oturumuna gelir.
- Klasik ekranların (Dersler, Analiz, Zaman, İşlem grafiği) yeni görünüme taşınması.

## 10 Kasım 2026 (2. tur): ücretsiz sağlayıcı ve geliştirme raporu

Ahmet: "Ajan için para ödemek istemiyorum, Gemini ya da DeepSeek'teki en mantıklı free ajanlardan bağlayalım." Sonra: "Ajanı bağladıktan
sonra benim değerlerimi organize etmeli, feedback raporu hazırlayıp sana sunmalı ve botları geliştirmeli."

**Sağlayıcı seçimi** (`ajan.SAGLAYICILAR`, panoda Ajan sekmesi): varsayılan **Google Gemini ücretsiz katmanı**; DeepSeek ve Claude Opus 5.5
seçenek olarak kaldı. Neden Gemini: kart istemeyen ücretsiz bir API katmanı var ve araç kullanmayı (function calling) destekliyor.
DeepSeek'in API'si ücretli (ucuz, ama bakiye yüklemek gerekir); bu yüzden varsayılan değil. Gemini ve DeepSeek "OpenAI uyumlu" sohbet
adresiyle çağrılır (`oa_cagir`), aynı araçlar ve sınırlarla. Gemini'de model adı boşsa anahtarın gördüğü modeller listelenir ve en yeni
kararlı "flash" seçilir (`gemini_model_sec`); model kaldırılırsa (404) liste yenilenir. Panoda model adı elle de yazılabilir.
Çaba: `reasoning_effort: "low"` gönderilir; model tanımazsa (400) onsuz bir kez daha denenir. Anahtarlar sağlayıcı başına ayrı dosya:
`user_data/gizli/ajan_anahtar_gemini` vb. Seçim: `user_data/kayit/ajan/ayar.json`.

**Düzeltme (13 Kasım 2026):** Gemini anahtar biçim denetimi noktayı kabul etmiyordu; Google'ın yeni anahtarları `AQ.` ile başlar ve içinde nokta vardır, bu yüzden Ahmet'in anahtarı "anahtara benzemiyor" diye reddedildi. Denetim `[A-Za-z0-9_\-.]` olarak genişletildi (`ajan.SAGLAYICILAR`), `sk-` ile başlayanlar yine reddedilir; test: `test_varsayilan_saglayici_gemini_ve_anahtarlar_ayri`. Gerçek sunucuda ilk kez: yeni biçimli anahtarla Gemini'ye gerçek çağrı (sınanmadı; yalnız biçim denetimi sınandı).

**503 (13 Kasım 2026):** Anahtar kaydedildi ama soruda 503 geldi: Google "model aşırı yüklü" der, anahtar sorunu değildir. Artık `_http` Gemini / DeepSeek çağrısını 3 kez dener (3 sn, 6 sn bekleyerek), 503 mesajı "çok yoğun" der; model otomatik seçiliyse ve 500 / 503 sürerse `yedek_model`'e (gemini-2.5-flash) geçilir, elle yazılmış model adına dokunulmaz. Test: `test_yogunlukta_503_yedek_modele_gecer`. Sunucuda sınanmadı; 503 panonun kendisinden (güncelleme sırasında kapsayıcı yeniden başlarken Caddy) geliyorsa bu değişiklik çözmez.

Ahmet'e söylenenler: ücretsiz katmanın dakikalık ve günlük soru sınırı vardır, dolunca ajan o gün yanıt vermez (sayfa "kotası doldu" der).
Google ücretsiz katmanda gönderilen verileri ürünlerini geliştirmek için kullanabilir; bu sistemde giden veri sanal bot sonuçları ve
ayarlardır, gizli bilgi gitmez. **Güncel ücretsiz kota ve model adları bu oturumda internetten doğrulanamadı** (arama sınırı doldu);
kod model adını sabitlemediği için ad değişse de çalışır.

**Geliştirme raporu:** Ajan sekmesinde "Rapor hazırlat" düğmesi (ya da sohbette istemek). Ajan sırasıyla `tum_kayitlar` (bütün botların
bütün kayıtları, canlı değerle yan yana), `canli_sonuclar`, `gecmis_testi` (umut veren kayıtlar ve tek değişiklikli adaylar, canlıyla
aynı dönem, en az 90 gün) çalıştırır ve `rapor_yaz` ile kaydeder. Bölümler: Özet; Ahmet'in değerleri (gruplanmış, yinelenenler
birleştirilmiş); Canlı botların durumu; Test edilen adaylar (seçim / doğrulama ayrı); Öneri (en çok bir iki yeni sanal bot adayı ya da
"öneri yok" ve nedeni); Riskler; **Claude için yapılacaklar** (kopyalanabilir maddeler). Ajan Ahmet'in kayıtlarını silmez, adını
değiştirmez; "düzenleme" raporda yapılır.

Dosyalar: `user_data/kayit/ajan/raporlar/GGGG-AA-GG-SSDD.md` (dizin `README.md`'de). Panoda Ajan sekmesi → Geliştirme raporu listesi.

**"Botları geliştirmeli" nasıl olur:** ajan canlı botu değiştiremez (3. kural; sınav sürüyor). Akış: rapor → Ahmet okur → Ahmet bulut
oturumuna "raporu oku" der → bulut oturumu raporu sunucu oturumundan okur (aşağıda), önerilen adayı Ahmet'e anlatır → Ahmet onaylarsa
**yeni bir sanal bot** olarak kurulur ve kendi 30 gününe başlar. Canlı dört bot dokunulmadan kalır.

**Bulut oturumu raporu nasıl okur:** sunucu oturumuna (`list_sessions` → "Karabasan sunucu") "yalnız Read aracını kullan, Bash kullanma;
`user_data/kayit/ajan/README.md`'yi ve en yeni `user_data/kayit/ajan/raporlar/*.md` dosyasını oku, aynen yaz" diye mesaj gönder
(`kayit` altı onaysız okunur). Oturum kapalıysa Ahmet panodaki raporu açıp metni bu sohbete yapıştırır.

Sınanan: sahte Gemini yanıtlarıyla araç döngüsü (düşünme imzası korunarak), {yol, deger} listesi biçiminde ayar, model seçimi ve
yenilenmesi, kota hatası, rapor dosyası, panoda rapor açma (Chromium 1440 px). **Gerçek sunucuda ilk kez:** Gemini'ye gerçek çağrı
(OpenAI uyumlu adres, `reasoning_effort`, araç şeması), model listesi, ücretsiz kotanın ajanın araç turlarına yetip yetmediği
(rapor tek istekte 5–10 çağrı yapabilir).
