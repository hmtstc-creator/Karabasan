# Kalıcı günlük

Karar ve değişikliklerin kısa, tarihli kaydı (en yeni altta). Ayrıntı ilgili konu sayfasındadır. Her oturum sonunda bir satır eklenir.

| Tarih | Karar / değişiklik | Neden | Sayfa |
| --- | --- | --- | --- |
| 2026-10-10 | Hetzner CX33 sunucu kuruldu, sanal bot dönemi başladı | Ahmet'in kararı | altyapi-ve-uyum |
| 2026-10-15 | Yalnız SMK ve SMDK (açığa satış) kaldı; SM / SMD / Sniper / RSI emekli | Ahmet: "sadece 2 bot kalsın" | stratejiler-ilk-donem |
| 2026-10-22 | Stop %3 → %9; SMK2 / SMDK2 eklendi (2 kat, zararda bir ek giriş) | Ahmet'in açık isteği (6. kural istisnası) | stop9-ve-kaldirac |
| 2026-11-06 | Parolalı internet erişimi; Analiz, Grafikler, Zaman, İşlem grafiği ekranları | Ahmet'in isteği | internet-erisimi, sonuc-sayfasi |
| 2026-11-07/08 | /ayar kriter laboratuvarı, /detay bot detayı, Dersler bot seçimi | Ahmet'in isteği | kriter-ayar-laboratuvari |
| 2026-11-08 | Ek girişli işlemde ilk giriş doğru çizilir (orders tablosu) | Ahmet iPhone ekran görüntüsü | stop9-ve-kaldirac |
| 2026-11-09 | /ayar: şart ve çıkış parçaları pasif / etkili; botun bütün sayıları adlı kayıt (ad değiştirme dahil); Caddy yalnız POST /ayar/kayit'e izin verir | Ahmet: "her parametreyi ben seçeyim, ayrı kayıt, pasif seçeneği" | kriter-ayar-laboratuvari |
| 2026-11-09 | CLAUDE.md 108 KB → ~10 KB; geçmiş `docs/wiki/` konu sayfalarına taşındı; `/yenikonu` komutu eklendi | Ahmet: "her sorduğumda 150 bin token harcama; kalıcı arşive not al" | README |
| 2026-11-08 | /ayar tarama tablosuna "Sinyal" sütunu ve "her satırda 0 işlem" açıklaması | Ahmet: "ne değiştirirsem her satırda sıfır yazıyor". Hata değil: giriş şartları birlikte çok seyrek doğru, tek sayı oynatmak işlem açmıyor (yapay veride 4 botta satırların ~%88'i 0 işlem) | kriter-ayar-laboratuvari |
| 2026-11-09 | Site için 5 trader / 5 görsel / 5 programcı ajanlı "yeni sayfalar" istemi yazıldı (kod yok, çalıştırılmadı) | Ahmet'in isteği | site-yeni-sayfalar-istemi |
| 2026-11-10 | Sonuç sayfasına `/coinler` (menüde "Coin listesi"): Binance vadeli USDT coinleri, stable hariç, 24 saatlik USDT hacim sınırını geçenler (varsayılan 5 milyon, botlarla aynı; sınır sayfadan seçilir). Yalnız bakmak için; botların evrenini değiştirmez | Ahmet: "sitede Binance'deki tüm coinler olsun, stable hariç, hacim filtresi koy" | sonuc-sayfasi |
| 2026-11-10 | Yeni pano canlıda: ana sayfa Karabasan Uzayı (coinlerin girişe uzaklığı, üç boyut), ayar ve geçmiş test laboratuvarı, ajan (Opus 5.5, düşük çaba; arşivli hafıza). Eski sayfa `/klasik`. Renk siyah. Caddy `/api/*` yazma yoluna izin verir | Ahmet: "akıl almaz bir site; coinleri uzayda göster; ayarlarımla anında geçmiş test; siteye ajan ekle; canlıya al; mordan siyaha çevir" | pano-uzay-ajan |
| 2026-11-10 | Ana sayfa yine kazancı gösteren sonuç sayfası (`/` = `/klasik`); yeni pano silinmedi, `/pano`'ya taşındı (Menü'de "Yeni pano") | Ahmet: "kaç para kazandığımı gösteren ekranlar kayboldu, tüm ekranları geri getir, senin sayfalarını da silme" | pano-uzay-ajan |

## Açık işler (güncel)

1. Uyum 23 ve 12 aylık test 11 raporlarını sunucudaki oturumdan oku, Ahmet'e özetle (stop %9, SMK2 / SMDK2).
2. Ahmet'in yön kararı: 12 aylık testler ve panel sınaması kenar göstermedi; long botu isteği (Ahmet 9 Kasım'da 2 long + 2 short beklediğini söyledi, bugün dördü de short).
3. Gerçek sunucuda ilk kez çalışacaklar: Caddy'nin yeni ayarı (POST /ayar/kayit), kayıt dosyasına yazma, /ayar gerçek Binance verisiyle.
4. Gerçek sunucuda ilk kez: `/coinler` Binance `exchangeInfo` + `ticker/24hr` çağrıları (panel kapsayıcısından). Ahmet botların evreni de aynı süzgeçle genişlesin isterse ayrı karar (3. kural: sınav sürerken bot ayarı değişmez).
5. Yeni pano gerçek sunucuda ilk kez çalışıyor: mum dosyalarının okunması, Binance çekimi, WebGL, Caddy `/api/*`, Anthropic çağrısı (liste: pano-uzay-ajan). Ahmet anahtarı girince ajanın ilk gerçek yanıtına bak.
6. Ahmet ajan için Anthropic API anahtarı alacak (console.anthropic.com; abonelikten ayrı fatura) ve panoda Ajan sekmesinden girecek.
