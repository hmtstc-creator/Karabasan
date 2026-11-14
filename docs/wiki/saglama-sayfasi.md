# Sağlama sayfası (/sagla)

14 Kasım 2026. Ahmet: "Kazanılan paranın doğru olduğunu kanıtlayan bir sayfa; matematikteki sağlama gibi. 600 küsür kâr gerçek mi, hikaye mi?"

## Ne yapar
`karabasan/saglama.py` kayıt dosyalarını (`user_data/db/<bot>.sqlite`, salt okunur) sonuç sayfasından BAĞIMSIZ okur:

1. **Toplam sağlaması:** kayıttaki `close_profit_abs` toplamı = sayfanın bot toplamı (aynı dönem süzgeci).
2. **Emirden yeniden hesap:** her işlemin kârı `orders` tablosundaki gerçekleşen miktar × ortalama fiyattan, komisyon (`fee_*_cost`, yoksa oran) ve fonlama düşülerek baştan hesaplanır; kayıtlı kârla karşılaştırılır (tolerans: 0,02 USDT ya da kârın %0,5'i). Emir kaydı bulunan işlem oranı %95'in altındaysa sonuç "belirsiz" olur.
3. **Mantık:** çıkış girişten önce, çift kayıt, fiyatsız işlem, stop'ta kâr, kâr hedefinde zarar.
4. **Yoğunlaşma:** en iyi 5 işlem çıkınca kâr ne kalıyor (uyarı; hüküm bozmaz).
5. **Fiyat gerçekliği** (`/sagla?mum=1`, isteğe bağlı): bot başına 10 örnek işlemin giriş ve çıkış fiyatı o dakikanın Binance 1 dakikalık mum aralığında mı (±%0,2). Binance'e ulaşılamazsa "belirsiz"; sonuç 1 saat saklanır.

Kural: çalışamayan denetim hiçbir zaman yeşil sayılmaz ("belirsiz"). Hüküm: tutarsızlık varsa TUTMADI, belirsiz varsa BELİRSİZ, hepsi geçtiyse TUTTU.

## Neyi kanıtlamaz
Defterin içeride tutarlı olduğunu kanıtlar. Sanal (dry-run) emirlerin gerçek hesapta aynı kârı getireceğini kanıtlamaz: kayma, derinlik, reddedilme, gecikme yoktur. Sayfa bunu her zaman yazar.

## Bağlantılar
`panel.py` (`/sagla`), `site_gezinti.py` ("Sağlama"), test: `testler/test_saglama.py`. Bot ayarına, stratejiye dokunmaz (3. kural).

## Gerçek sunucuda ilk kez
- Gerçek `orders` ve `trades` sütunları (özellikle `fee_open_cost`, `funding_fees`, `ft_order_side`) bu sürümle ilk kez sınanacak; sütun adı farklıysa denetim "belirsiz" ya da "hata" çıkabilir, bu kodun değil kaydın okunmasının sınavıdır.
- Binance mum çağrısı (`?mum=1`) sunucudan ilk kez.
- 14 Kasım'da sunucu oturumuna bulut oturumundan mesaj gidemedi (oturum Ahmet'in kendi bilgisayarında; `confirm_repository_trust` kartı Ahmet'in onayını bekliyor). Bu yüzden "600 küsür kâr" rakamının gerçek sunucudaki sağlama sonucu henüz görülmedi.
