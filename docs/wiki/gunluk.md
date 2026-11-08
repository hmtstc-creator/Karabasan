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

## Açık işler (güncel)

1. Uyum 23 ve 12 aylık test 11 raporlarını sunucudaki oturumdan oku, Ahmet'e özetle (stop %9, SMK2 / SMDK2).
2. Ahmet'in yön kararı: 12 aylık testler ve panel sınaması kenar göstermedi; long botu isteği (Ahmet 9 Kasım'da 2 long + 2 short beklediğini söyledi, bugün dördü de short).
3. Gerçek sunucuda ilk kez çalışacaklar: Caddy'nin yeni ayarı (POST /ayar/kayit), kayıt dosyasına yazma, /ayar gerçek Binance verisiyle.
