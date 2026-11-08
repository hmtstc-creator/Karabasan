# Stop %9, SMK2 / SMDK2 (2 kat, zararda ek giriş)

> 22 Ekim 2026 kararı ve ek girişli işlemin gösterimi (8 Kasım).
> Kaynak: CLAUDE.md'nin 9 Kasım 2026 öncesi hali (sözcüğü sözcüğüne taşındı).

**Stop %9 ve iki kaldıraçlı bot (22 Ekim 2026, Ahmet'in isteği).** Stop sonrası izleme SMK için ilk dersi
yazdı: "stop dar görünüyor; 3 kat geniş olsaydı 30 stopta +26,66 USDT daha iyi". Ahmet: "iki botun stoplarını
genişlet; iki bot daha ekle, x2 vadeli, stoptan %1 önce ilk tutarın 2 katı kadar alttan yeniden al, satış
fiyatını güncelle". Önce 6. kuralı hatırlattım (zararda ekleme kapalı, kaldıraç 1 kat); Ahmet açıkça yine istedi.
- SMK / SMDK stopu %3 → %9 (yerinde; iz süren stop aynı). SMK2 / SMDK2: aynı kural + `kaldirac: 2` +
  `zararda_ekleme {stopa_kala_yuzde 1, kat 2}`: fiyat ilk girişten %8 aleyhe gidince ilk teminatın 2 katı
  bir kez daha girilir. Stop fiyatı ilk girişe göre kalır (motor ek girişte stopu yeniden kurmaz; benzetim
  de öyle); iz süren stop ortalama girişten. "Satış fiyatını güncelle" böyle yorumlandı. Ek girişten sonra
  stop olan işlem ilk teminatın ~%22'si (~11 USDT); eklemesiz SMK'da bir stop ~4,5 USDT.
- Motor: `leverage()` kuralın kaldıracını verir; motor oranları teminata göre ölçtüğü için `stoploss`,
  `trailing_stop_positive(_offset)` ve `minimal_roi` kaldıraçla çarpılır (fiyattaki uzaklık aynı kalsın).
  `position_adjustment_enable` + `max_entry_position_adjustment = 1` + `adjust_trade_position` (karar
  `kural.ekleme_gerekli`'de). Ek girişte `custom_entry_price` limit uzaklığı uygulamaz. Bu iki botun
  `dry_run_wallet`'ı 3.000 (ek girişler parasızlıktan kalmasın); sayfa yüzdeleri 1.000'e göre.
- Stop sonrası izleme ve tarama SMK2 / SMDK2'yi atlar. SMK / SMDK'nın eski %3 stoplu işlemleri yeni ayarın
  dersine katılmaz (`stop_sonrasi.ESKI_STOPLAR`, sonuçtan okunur).
- `UYUM_SURUMU=23`, `YILLIK_SURUMU=11`. Yapay veride (180 gün) dördü de ekside; ek girişliler daha çok
  (SMK −6,40, SMK2 −19,57): beklenen, anlamı yok.
- **Gerçek motorda ilk kez:** `adjust_trade_position`'ın bu imzayla canlı ve geçmiş testinde çağrılması
  (geçmiş testinde motor ek girişi büyük olasılıkla mumun açılışından yapar, benzetim seviyeden: fark
  uyum raporunda görülür), kaldıraçla stop / iz oranlarının fiyat uzaklığına doğru çevrildiği,
  `nr_of_successful_entries` / `has_open_orders` alanları, 2 kat kaldıraçla vadeli sanal işlemin açılması
  (50 USDT x 2 = 100 USDT; BTC belki artık işlem görür), açık işlemlerin stopunun yeniden başlatmada %9'a
  çekilmesi. Uyum 23 raporunda SMK2 / SMDK2 satırlarına ve "yalnız motor" eşleşmelerine bak.
- **12 aylık test 11 (22.10.2025–22.10.2026, hazırlandı 22 Ekim 06:34 UTC; Ahmet iletti).** SMK 510 işlem
  %88,0 kazanma +22,13 USDT, düşüş %5,3, çeyrek 2 / 4; SMDK 439 / %88,2 / +13,60 / %5,2 / 2 / 4; SMK2 525 /
  %89,1 / +29,68 / %10,9 / 3 / 4; SMDK2 448 / %89,1 / −8,89 / %11,9 / 2 / 4. Son çeyrekte (07.2026–) dördü de
  ekside (SMK2 −34,70). Stop %3 → %9 (test 10'a göre, dönem bir hafta kaymış): SMK +16,73 → +22,13, SMDK
  +20,33 → +13,60; toplamda değişiklik yok. Ek girişli işlemler: SMK2 62 (50'si yine stop), net −512,40;
  SMDK2 53, net −476,51 (işlem başına ~−8,3 / −9,0 USDT). Ek giriş, yalnız kaldıracın yapacağından
  (≈ 2 × SMK) kötü: SMK2 +29,68 < 44,26, SMDK2 −8,89 < 27,20; kaldıraç düşüşü de ikiye katladı. Uyum 23
  raporu henüz okunmadı (sunucu oturumuna bulut oturumundan mesaj izni 22 Ekim'de kaydedilemedi).

**Ek girişli işlemde ilk giriş (8 Kasım 2026, Ahmet iPhone ekran görüntüsü gönderdi: "bar gelmeyen yerde nasıl alım yapıyor?").**
Hazır motor, zararda ek girişten sonra `trades.open_rate`'e ORTALAMA girişi yazar. İşlem grafiği bunu ilk girişin zamanına koyuyordu:
SMDK2 SPCX işleminde giriş işareti mumların %5 üstünde (133,17; gerçek ilk giriş ~126,4) ve stop 145,16 (doğrusu ilk girişin %9'u ≈ 137,8; işlem
137,54'te stopla kapanmıştı) çiziliyordu. İşlem doğru çalışmıştı, yalnız gösterim yanlıştı. Düzeltme: `sonuc._giris_emirleri` botun `orders`
tablosundan gerçekleşmiş giriş emirlerini okur (`islem["ilk_giris_fiyati"]`, `islem["ek_girisler"]`; tablo yoksa `open_rate`); işlem grafiği ilk girişi,
ek girişi (turuncu işaret) ve ortalamayı ayrı çizer, stop ilk girişten, iz tetiği ortalamadan; `sonuc.acik_risk` da ilk girişi kullanır; `/ayar` grafiği
benzetimin `ilk_giris_fiyati`'ni kullanır ve ek girişi `kural.ekleme_fiyati` seviyesinde işaretler. Gerçek `orders` tablosu (motorun sütun adları:
`ft_trade_id`, `ft_order_side`, `average`, `filled`, `order_filled_date`) yalnız sahte tabloyla denendi; sunucuda ilk kez gerçek kayıtla görülecek.
