# Yeni pano: Karabasan Uzayı, geçmiş test laboratuvarı ve ajan

> 10 Kasım 2026, Ahmet'in isteği. Sitenin ana sayfası artık bu panodur; önceki bütün ekranlar `/klasik` adresinde durur.

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
