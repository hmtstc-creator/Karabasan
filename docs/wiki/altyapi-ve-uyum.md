# Altyapı ve uyum denemeleri (Ekim 2026)

> Sunucu kurulumu, bağlantı katmanının doğrulanması, uyum denemelerinin sonuçları (4, 11, 13, 16. ve 17.).
> Kaynak: CLAUDE.md'nin 9 Kasım 2026 öncesi hali (sözcüğü sözcüğüne taşındı).

**Sunucu çalışıyor.** Ahmet 10 Ekim 2026 akşamı Hetzner'de CX33 sunucuyu
blokla oluşturdu; kurulum gerçek sunucuda ilk denemede baştan sona çalıştı ve
on sanal bot başladı (motor: freqtrade 2026.9). Isınma dönemi 10 Ekim'de
başladı; 30 günlük sınavın saati henüz başlatılmadı ve aşağıdaki ilk iki iş
bitmeden başlatılmamalı.

**Bağlantı katmanı doğrulandı (11 Ekim 2026).** Hazır motorun 30 günlük
geçmiş testi ile bağımsız benzetim aynı sonucu veriyor (işlem / kazanma / net
USDT; önce motor, sonra benzetim): S1 spot 72 / %37,5 / −10,44 ile 73 / %37,0 /
−10,72; S2 spot 198 / %40,4 / −9,02 ile 194 / %40,2 / −9,32; S3 spot 187 /
%52,9 / −7,32 ile 183 / %54,6 / −4,12; S4 spot 46 / %58,7 / +1,21 ile 42 /
%57,1 / +0,07. Çıkışlar tasarlandığı gibi: hedefe ulaşan işlemler hedef eksi
gidiş-dönüş komisyonu kadar kazanıyor (S1'de +%1,05), stoplar −%1,14, süre
aşımı tam süresinde. Yani olumsuz sonuçlar yazılım hatası değil.

**Vadelide 50 USDT ile BTC işlem görmüyor.** Altı vadeli geçmiş testinin
hepsinde BTC'de sıfır işlem var; spot'ta BTC normal. En olası neden Binance'in
BTC vadeli sözleşmesindeki en küçük emir tutarı (100 USDT); doğrulanmadı.
Bağımsız benzetim bu kuralı bilmediği için vadelide yaklaşık beşte bir daha
fazla işlem sayar; karşılaştırırken BTC'yi düş (`karsilastir.py` coin başına
sayıyı yazar).

**Uyum denemesinin iki hatası (düzeltildi).** İlk çalıştırmada on geçmiş testi
de ayar hatasıyla durdu (bot dosyasındaki yer tutucu `jwt_secret_key` çok
kısa) ama betik "geçti" yazdı; betik artık çıktıda hata satırı ve sonuç tablosu
arıyor. İkinci denemede `arac` servisine `.env` verildi; geçmiş testleri çalıştı
ama bu kez yapılandırma dosyası almayan üç adım (strateji listesi, iki veri
indirme) kaldı. Kalıcı çözüm: `arac` `.env` okumaz, `geri_test_*.json` geçerli
uzunlukta yer tutucu taşır. `kur.sh` denemeyi `UYUM_SURUMU` değişince yeniden
çalıştırır.

**İlk gerçek sonuçlar olumsuz.** Bağımsız benzetim, son 30 günün gerçek
verisinde (BTC, ETH, SOL, XRP, DOGE; komisyon dahil; Karabasan süzgeci yok):
S1 spot 73 işlem %37 kazanma −10,72 USDT; S2 194 / %40 / −9,32; S3 183 / %55 /
−4,12; S4 42 / %57 / +0,07; S1K 104 / %45 / −2,01; S2K 189 / %31 / −17,61;
vadeli sonuçlar spot ile neredeyse aynı. Canlı sanal botların ilk 6 saati:
36 işlem, −10,44 USDT, on botun onu da ekside. Ahmet'e söylendi. Bu veriye
bakarak strateji ayarı değiştirme (geçmişe ezber); önce karşılaştırma,
Karabasan ölçümü ve 12 aylık geçmiş testi.


**Dördüncü uyum denemesi geçti (11 Ekim 2026; sunucudaki Claude'un özeti).**
Alım botları motorla birebir tutuyor (motor / benzetim, işlem / net USDT):
S5 211 / −7,64 ile 211 / −7,84; S6 214 / −18,11 ile 213 / −17,24. Açığa
satış botlarında motor her coinde yaklaşık %10 fazla işlem sayıyor (BTC
hariç; motor / benzetim): S2K 162 / 145, S5K 217 / 197, S6K 238 / 225,
S1K 86 / 83. Fark sistematik ama sonucun yönünü değiştirmiyor. Nedeni koddan
çıkarılamadı: benzetim ve motorun bilinen kuralları (stop önce, hedef fiyatı,
süre aşımı, stop sonrası bekleme) alım ve açığa satışta simetrik; alımda
tuttuğuna göre fark açığa satışa özgü bir şeyde. Tahminle düzeltme yapılmadı;
bunun yerine uyum denemesine işlem işlem eşleştirme eklendi (`UYUM_SURUMU=5`):
hangi işlemlerin yalnız motorda olduğunu, o sırada benzetimde hangi işlemin
açık olduğunu ve iki tarafın çıkış nedenlerini yazar. Beşinci raporda
"yalnız motor" satırlarına bak; farkın nedeni oradan okunur.


**On birinci uyum denemesi (11 Ekim 2026 14:20 UTC, Ahmet iletti).** Beş sınıf
da motorda yüklendi. Dört Smartmoney botu motorla işlem işlem tutuyor (motor /
benzetim, BTC hariç): SM 85 / 86, SMK 40 / 40, SMD 67 / 67, SMDK 32 / 32; "yalnız
motor" hepsinde 0. Yani benzetimdeki yeniden giriş düzeltmesi doğrulandı (eski
0. iş). Son 30 günde, komisyon dahil (benzetim, BTC dahil): SM 112 işlem %52 /
−3,03 USDT; SMK 46 / %41 / −3,03; SMD 88 / %49 / −4,80; SMDK 35 / %34 / −2,46.
SMD'nin sayıları defter onayı olmadan (geçmiş testi onu uygulayamaz).
- **Sniper'ın geçmiş testi kaldı:** "No data left after adjusting for startup
  candles". Neden: hazır motorun `download-data`'sı eldeki dosyaya yalnız sona
  ekler; günlük dosyalar önceki 200 / 600 günlük indirmelerden kaldığı için
  `--days 800` başa veri eklemedi (BTC 1d 2026-03-25'ten, diğerleri
  2025-02-18'den başlıyor; 735 günlük ısınma + 30 gün sığmıyor). Düzeltme: uyum
  denemesi ve analiz büyük dilimleri önce `--prepend` (olmazsa `--erase`), sonra
  düz indirmeyle sona ekleyerek indirir. `UYUM_SURUMU=12`. 12 aylık test zaten
  `--prepend` kullanıyordu.
- Benzetimin Sniper sonucu (eksik veriyle, BTC'de veri yetmediği için işlem yok):
  8 işlem, %0 kazanma, −20,39 USDT. **Bu ölçü Sniper için yanıltıcıdır:** 30 günlük
  pencerede yalnız kapanmış işlemler sayılır; trend takibinde kaybedenler hızlı
  kapanır, kazananlar açık kalır. Sniper'ı 12 aylık test ve canlı sonuç ölçer.


**On üçüncü uyum denemesi geçti (11 Ekim 2026 18:46 UTC, Ahmet iletti).** Beş
botun beşi de geçti. Yeni Sniper motorla tutuyor (BTC hariç): motor 90, benzetim
89, eşleşen 88; çıkışlar motor hedef 21 / süre aşımı 50 / stop 19, benzetim
21 / 50 / 18. İki "yalnız motor" işlem dönem başı (SOL 09-11 03:45) ve 10 dk
kayma (XRP 10-09). Son 30 gün: motor 90 işlem, %55,6 kazanma, −2,53 USDT;
benzetim (BTC dahil) 102 işlem, %55,9, işlem başına net −%0,037, −1,87 USDT.
Başa baş ~%59. Komisyon öncesi işlem başına ~+%0,06: sıfırdan ayırt edilemez,
tek dönem. Çıkışların yarısı süre aşımı (3 saatte ne %1,2 ne %1,5). SM / SMK /
SMD / SMDK önceki denemeyle aynı. "Found orphan containers (kb-sniper-vadeli)"
uyarısı beklenen: uyum 9. adımda, eski kapsayıcıyı 10. adımdaki
`up --remove-orphans` kaldırır.


**On altıncı uyum denemesi geçti (iz süren stop; 11 Ekim 2026 20:38 UTC, Ahmet iletti).**
Motor iz süren stopu aldı (`trailing_stop_positive` 0,003, `offset` 0,012,
`trailing_only_offset_is_reached`). Limitli girişte açılış zamanı düzeltmesi tuttu: işlem
sayıları birebir ya da ±2 (motor / benzetim / eşleşen, BTC hariç): SM 48 / 47 / 47, SMK
25 / 25 / 24, SMD 41 / 40 / 40, SMDK 21 / 21 / 20, Sniper 44 / 42 / 41; çıkış nedeni
sayıları iki tarafta aynı ya da bir eksik.
- Motor son 30 gün (BTC hariç; işlem / kazanma / net USDT): SM 48 / %68,8 / −4,25; SMK
  25 / %64,0 / −4,36; SMD 41 / %70,7 / −2,29; SMDK 21 / %66,7 / −2,43; Sniper 44 / %61,4 /
  −10,59; toplam −23,92. İz süren stop çıkışları ortalama +%1,13–1,19, stoplar −%3,09–3,11.
  Bu oranlarla başa baş için kazanma ~%73 olmalı (3,1 / (1,15 + 3,1)); hepsi altında.
- Benzetim (BTC dahil): SM 56 / %67,9 / −3,16; SMK 24 / %54,2 / −9,23; SMD 48 / %68,8 /
  −1,92; SMDK 21 / %57,1 / −6,47; Sniper 45 / %57,8 / −13,74; toplam −34,52. Aynı 30 günde
  eski çıkışlarla (14. deneme) −20,16 idi: bu ayda iz süren stop daha kötü (tek ay; 12 aylık
  taramada tersi çıkmıştı). İşlem sayısı azaldı (SM 86 → 56): işlemler uzun sürüyor
  (motorda ortalama 12-16 saat, stoplar 18-37 saat).
- Eşleşip aynı nedenle kapanan iz süren stopların neredeyse hepsi (SM 33'ün 31'i) iki
  tarafta başka mumda kapanıyor. Neden: motor geçmiş testinde stopu mumun tepesiyle aynı
  mumda taşıyıp aynı mumun dibine bakar (tepe önce geldi varsayımı, iyimser; çıkış hep
  tetik civarı +%1,15); benzetim bir sonraki mumdan taşır (kötümser ama trend sürerse daha
  geç ve yüksekten çıkar). Canlı bot fiyata birkaç saniyede bir bakar; ikisinin arasında
  bir yerdedir. Farkın büyüklüğünü ölçmek için eşleştirmeye eşleşen işlemlerin net
  toplamı ve iz süren stopta "benzetim daha geç / erken" sayısı eklendi (`UYUM_SURUMU=17`).
  Benzetim kendiliğinden değiştirilmedi; 17. rapordaki fark büyükse (işlem başına
  %0,2'den çok) benzetimi motora yaklaştırmak düşünülür, çünkü 12 aylık test ve tarama
  benzetimle yapılıyor.
