# Karabasan Bot: Claude için çalışma notları

Bu dosya, bu depoda çalışan her Claude oturumunun ilk okuması gereken özettir.
Ayrıntılı tasarım, kararlar ve gerekçeleri tasarım raporundadır:
https://claude.ai/code/artifact/9a7d204e-36c4-4ce2-891a-70bff31cf7c5

## Proje

Binance için sık ve küçük kârlı (%1–1,5) işlem botu. Ne zaman çalışacağına
"Karabasan" adlı piyasa ortamı motoru karar verir (0–100 puan, dört durum,
veto kuralları). Tek kullanıcılıdır; tek bir VPS'te Docker ile çalışır.
Emir yürütme ve geçmiş testi için hazır motor olarak Freqtrade kullanılır;
bizim kodumuz onun üstündedir.

## Kullanıcı

Ahmet. Kod bilmiyor. Türkçe yaz. Teknik terim kullanacaksan ilk geçtiği yerde
açıkla. Önceliği para kazanmak değil, parayı kaybetmemek.

**Yalnız telefon kullanıyor; bilgisayarı ve terminali yok.** Ondan isteyeceğin
her şey telefondan yapılabilir olmalı: Telegram'da bir komut yazmak, bir
bağlantıya dokunmak, bir dosyayı bu sohbete iletmek, Hetzner'in web panelinde
bir düğmeye basmak. Ona asla SSH ya da terminal komutu verme. Sunucuda bir şey
değişecekse kodu değiştirip ana dala işle; sunucu kendisi alır.

**GitHub'da onay beklenmez.** Ahmet açıkça istedi: değişiklikleri doğrudan
`main` dalına işle, birleştirme isteği açıp onay bekleme.

## Ana dal canlıdır

Sunucu 5 dakikada bir `main` dalını denetler, yeni kodu alır ve `kur.sh`'ı
yeniden çalıştırır (`araclar/oto_guncelle.sh`). Yani `main`'e işlediğin her
şey birkaç dakika içinde sunucuda çalışır ve Ahmet'e Telegram'dan bildirilir.

- Testler geçmeden `main`'e işleme. Yarım iş işleme.
- `karabasan/stratejiler/`, `kural.py`, `gostergeler.py`, `botlar.py` ya da
  `user_data/strategies/` değişirse bütün botlar yeniden başlar. Sınav sürerken
  bunlara yalnız hata düzeltmek için dokun (3. kural).
- `kur.sh` her güncellemede baştan sona çalışır; her adımı yeniden
  çalıştırılabilir (yapılmışı atlayan) biçimde yaz.
- Kurulum yarım kaldıysa sunucu aynı kodla yeniden denemez; yeni bir sürüm
  gelince dener. Düzeltmeyi işlemen yeterlidir.
- Depo herkese açıktır. Gizli hiçbir şey, sunucu adresi dahil, depoya girmez.

## Değişmez kurallar

1. **Gerçek para kodu yok.** Şu anki aşama yalnız sanal işlemdir: `dry_run`
   her zaman `true`, Binance API anahtarı yok. Ahmet 30 günlük sınavın
   sonunda açıkça karar vermeden, borsaya gerçek emir gönderen hiçbir kodu
   yazma, açma ya da yapılandırma.
2. **Gizli bilgi depoya girmez.** `.env`, anahtarlar, parolalar asla işlenmez.
3. **Sınav başladıktan sonra strateji ayarı değişmez.** Yalnız hata düzeltilir.
   Yeni fikir, yeni bir sanal bot ve kendi 30 günü demektir.
4. **İşlem mantığı `karabasan/` paketinde yaşar** ve orada test edilir.
   `user_data/strategies/` yalnız ince bir bağlantı katmanıdır; oraya mantık koyma.
5. **Geleceğe bakmak yasak.** Yeni bir gösterge ya da kural eklersen, sonradan
   gelen verinin geçmişteki sinyali değiştirmediğini sınayan testi de ekle
   (örnek: `test_sinyaller_gelecege_bakmaz`).
6. **Zararda ekleme kapalıdır.** Kaldıraç sınavda 1 kattır.
7. **Rapor ile kod aynı şeyi söylemeli.** Bir eşiği, ağırlığı ya da kuralı
   değiştirirsen tasarım raporunu da güncelle.
8. **Sınanmamış şeyi sınanmış gibi anlatma.** Aşağıdaki ortam sınırı yüzünden
   bazı parçalar yalnız sunucuda sınanabilir; bunu Ahmet'e her zaman açık söyle.

## Test

```
python3 -m unittest discover -s testler -t .
```

Yalnız Python, numpy ve pandas gerekir. `pytest` kullanılmıyor.

**Ortam sınırı:** Claude'un bulut çalışma alanından paket deposuna (PyPI, npm),
Docker'a ve Binance'e erişim yoktur. Freqtrade burada kurulamaz. Bu yüzden
`testler/sahte/freqtrade/` motorun arayüzünü taklit eden sahte bir kopyadır;
`test_motor_baglantisi.py` bağlantı katmanının kendi mantığını sınar, gerçek
motorla uyumu sınamaz. Gerçek sınama sunucuda `araclar/uyum_denemesi.sh` ile
yapılır ve çıktısı `user_data/logs/uyum_denemesi.txt` dosyasına yazılır.

**Sunucunun kendi Python'unda numpy ve pandas yoktur.** `kur.sh`'ın doğrudan
çağırdığı kod (`karabasan/haberci.py`'nin `gonder`, `belge`, `bekle` işleri,
`karabasan/botlar.py`, `araclar/yapilandirma_uret.py`) yalnız standart
kütüphaneyle çalışmalıdır. Bunu sınayan testler var; bozma.

**Sunucu betikleri burada çalıştırılamaz.** `kur.sh`, `oto_guncelle.sh` ve
`ozel_ag.sh` yalnız taklit komutlarla (sahte `docker`, `tailscale`, `apt-get`,
`systemctl` ve sahte bir Telegram sunucusu) prova edildi. Bir betiği
değiştirirsen aynı provayı yeniden kur ve çalıştır; sonra Ahmet'e yine de
"gerçek sunucuda ilk kez çalışacak" de.

**Sunucudan bilgi almak:** Ahmet Telegram'da `/kurulum`, `/uyum` ya da
`/gunluk` yazar, gelen dosyayı bu sohbete iletir. Başka yolun yok.

## Yapı

| Yol | İçerik |
| --- | --- |
| `karabasan/gostergeler.py` | Gösterge blokları (EMA, RSI, MACD, Bollinger, ATR, VWAP, üst dilim hizalama), `piyasa_yapisi` (salınımlar, yapı kırılımı BOS / CHoCH, denge, emir blokları), `uyumsuzluk` (10 göstergede normal / gizli boğa ve ayı uyumsuzluğu sayısı; kural türü `"uyumsuzluk"`, sütunlar `<ad>_boga`, `<ad>_ayi`) `donchian_topluluk` (emekli SNIPERG: birkaç uzunlukta Donchian kanal modelinin trendde olan payı, 0–1) ve `fvg` (adil değer boşluğu; kural türü `"fvg"`, sütunlar `<ad>_boga`, `<ad>_boga_ust`, `<ad>_boga_alt` ve ayı karşılıkları) |
| `karabasan/kural.py` | Kural dosyası (JSON) okuma, doğrulama, sinyal üretme. Bir gösterge `dilim` ile istediği üst dilimde hesaplanır (`"ust"`, `"15m"`, `"1h"`, `"1d"`). `borsa_dilimleri` içindeki dilimlerin mumları taban mumlardan toplanmaz, `ek_veri` ile dışarıdan verilir (motor, araçlar); boş tablo "veri yok, sinyal de yok" demektir. `giris_limiti` varsa giriş limit emirdir: `giris_limit_yuzde` (ATR × kat, kırpılmış), `limit_fiyati` |
| `karabasan/stratejiler/*.json` | 12 Ekim 2026'dan beri beş strateji: SM, SMD ve SNIPER (alım), SMK ve SMDK (açığa satış). Çıkarılan kurallar (S1–S7 ve ters yönlüleri, Sniper'ın ilk hali SNIPERG) `stratejiler/emekli/` altında durur; `tum_kurallar()` orayı okumaz ama `kural_yukle("S1")` koduyla bulur (eski raporlar ve testler için). Hangi botun çalıştığını yalnız `botlar.BOTLAR` belirler. Her birinin `ad` alanı ne yaptığını söyleyen düz addır; sayfada ve Telegram'da o görünür. SM / SMK'nın adı Ahmet'in isteğiyle "Smartmoney" diye başlar |
| `karabasan/puan.py` | Karabasan puanı, durum makinesi, vetolar |
| `karabasan/filtre.py` | Filtre (Elek): dört katman, elenme nedenleri |
| `karabasan/karne.py` | İşlem ölçümleri ve 30. günün yedi karar ölçütü |
| `karabasan/benzetim.py` | Bağımsız, kötümser mum bazlı benzetim (limitli girişte emrin dolduğu mumda hedef sayılmaz; iz süren stop bir mumun tepesiyle ancak sonraki mumdan itibaren taşınır). `hazir_tablo` ile sinyaller bir kez hesaplanıp farklı çıkışlarla denenir |
| `karabasan/tarama.py`, `araclar/tarama.py`, `araclar/tarama.sh` | Çıkış varyasyonu taraması: her botun girişleriyle 20 çıkış ayarı (`VARYASYONLAR`; V01 canlı ayar), son 365 gün, ilk 9 ay seçim / son 3 ay doğrulama. Veriyi 12 aylık test indirir; `kur.sh`'ta ondan hemen sonra, `TARAMA_SURUMU`. Çıktı `user_data/logs/tarama.txt` (Telegram `/tarama`). Hiçbir ayarı değiştirmez |
| `karabasan/botlar.py` | Sanal botların listesi (12 Ekim 2026'dan beri `sm-vadeli` 8081, `smk-vadeli` 8082, `smd-vadeli` 8083, `smdk-vadeli` 8084, `sniper5-vadeli` 8085; 1 kat vadeli), komisyon başlangıç değerleri. Uyum denemesi ve analiz bot listesini ve indirilecek ek dilimleri (`ek_dilimler`) buradan okur. Yeni bot listenin sonuna eklenir ki öncekilerin kapısı ve açılış sırası değişmesin |
| `karabasan/kayitci.py` | BTC dominansı ve TOTAL2'yi 10 dakikada bir kaydeder; aynı döngüde stop sonrası izleme turunu çalıştırır |
| `karabasan/stop_sonrasi.py` | Stop sonrası izleme: stop olan işlemi kendi süresi dolana kadar izler, stop 1,5 / 2 / 3 kat geniş olsaydı ne olurdu hesaplar, bot başına karar çıkarır (yetersiz, dar, yerinde, kararsız), karar değişince ders yazar. Mumlar Binance'in herkese açık, anahtarsız fiyat verisinden gelir. Çıktı: `user_data/kayit/stop_sonrasi.json`. **Hiçbir ayarı değiştirmez** |
| `karabasan/gecmis_olcum.py` | Karabasan puanını geçmiş mumlardan geriye dönük hesaplar (yaklaşık: dominans ve TOTAL2 yerine altcoin vekili); işlemleri açıldıkları andaki durumla etiketler |
| `karabasan/sonuc.py` | Botların SQLite kayıtlarını salt okunur okuyup özet çıkarır; dönem (ısınma, sınav, bitti) |
| `karabasan/sayfa.py`, `karabasan/panel.py` | Türkçe sonuç sayfası ve sunucusu (8080; `/`, `/veri.json`, `/saglik`). Altı ekran: ana ekran (gösterge halkası), botlar, işlemler, dersler (stop sonrası izleme), rapor (bot seçimli günlük kâr / zarar; seçim betiksiz, gizli seçim düğmeleri + biçim kuralları; veri `sonuc.gunluk_ozet` / `gunluk_toplam`, gün sınırı `sonuc.SAAT_DILIMI`), sınav; ekran listesi `sayfa.EKRANLAR`'dadır, biçim ve betik oradan üretilir. Sunucudan açılan hali tek bir satır içi betik taşır (ekran geçişi, dakikada bir yerinde tazeleme); `panel.py` izin başlığını (CSP) o betiğin özetinden üretir. Telegram'ın `/sayfa` ile yolladığı dosya betiksizdir, ekranlar alt alta görünür |
| `karabasan/haberci.py` | Telegram: kurulum bildirimleri, günlük özet, susan bot uyarısı, yeni ders bildirimi, komutlar (`/dersler` dahil) |
| `karabasan/defter.py`, `karabasan/defter_servisi.py`, `karabasan/defter_sayfa.py` | Emir defteri denemesi (BTC/USDT vadeli, ileriye dönük, sanal): her saniye herkese açık defteri okur (`/fapi/v1/depth`, 100 kademe), dakikada bir 1 dk mumları; 15 özellik (dengesizlik, mikro fiyat, duvarlar, son getiriler, oynaklık, RSI, hacim, destek / direnç) ile 5 / 15 dk sonrası için sırt regresyonu (sabit terimsiz, yalnız olgunlaşmış kayıttan, 48 saat pencere, 3 saat ısınma, 5 dk'da bir eğitim). Tahmin ≥ %0,15 ise sanal pozisyon (100 USDT, hedef = tahmin, stop aynı uzaklık, süre = ufuk, ufuk başına tek işlem). Kayıt `user_data/kayit/defter.sqlite` (8 gün). Docker servisi `defter`; sayfa `/defter` (panel), Telegram `/defter`. Botlardan bağımsız |
| `user_data/strategies/karabasan_stratejileri.py` | Freqtrade bağlantı katmanı. Kural `borsa_dilimleri` istiyorsa o mumları motordan ister (`informative_pairs`, `dp.get_pair_dataframe`) ve kural motoruna aktarır; veri gelmezse boş tablo verir ve kayda bir kez yazar |
| `araclar/yapilandirma_uret.py` | Bot yapılandırmalarını ve `docker-compose.yml`'i üretir |
| `araclar/uyum_denemesi.sh`, `araclar/karsilastir.py` | Sunucudaki uyum denemesi |
| `karabasan/eslestirme.py`, `araclar/islem_eslestir.py` | Uyum denemesinin son bölümü: motorun işlem listesini (`--export trades`, `user_data/backtest_results/`) benzetimle işlem işlem eşleştirir; yalnız bilgi verir, denemenin geçip kalmasını etkilemez |
| `karabasan/yillik.py`, `araclar/yillik_test.py`, `araclar/yillik_test.sh` | 12 aylık geçmiş testi: bir yıllık vadeli veriyi indirir (5m/15m 400 gün, 1d 600 gün), her botu son 365 günde bağımsız benzetimle çalıştırır, sonucu dört çeyreğe böler; bilgi için aynı sinyallerle "stop = hedef" sütunu. Çıktı `user_data/logs/yillik_test.txt` (Telegram'da `/yillik`) ve `user_data/gecmis_test.json` (sınavın 7. ölçütü). `kur.sh` içinde `YILLIK_SURUMU` |
| `araclar/analiz.sh`, `araclar/karabasan_gecmis.py` | Sunucudaki tek seferlik ölçüm: 80 günlük veri indirir, stratejilerin sonucunu Karabasan durumuna göre ayırır ve stop genişliğini sınar (aynı sinyaller, stop 1,5 / 2 / 3 kat; dönemin iki yarısı ayrı). `kur.sh` içinde `ANALIZ_SURUMU`; Telegram'da `/olcum` |
| `kurulum/sunucu_blogu.sh` | Ahmet'in sunucuyu oluştururken "Cloud config" kutusuna yapıştırdığı blok |
| `kur.sh` | Kurulum; soru sormaz, her adımı Telegram'a yazar, her güncellemede yeniden çalışır |
| `araclar/oto_guncelle.sh` | 5 dakikada bir `main`'i denetler, yeni kodu alır, `kur.sh`'ı çalıştırır |
| `araclar/takas.sh` | 2 GB takas alanı (swap); `kur.sh` 2. adımda çağırır, kurulu olanı atlar |
| `araclar/ozel_ag.sh` | Tailscale onay bağlantısını Telegram'dan yollar; kapıları özel ağ adresine taşır |
| `araclar/claude_sunucu.sh` | Claude Code'u sunucuya kurar; girişi Telegram üzerinden yaptırır; uzaktan yönetim oturumunu (Remote Control) açık tutar |
| `.claude/settings.json` | Sunucudaki oturumun onay sormadan çalıştırabileceği salt okunur komutlar; gizli dosyaları okuma yasağı |

Üretilen dosyalar (`docker-compose.yml`, `user_data/config/`, `.env`,
`telegram.env`) depoya girmez; sunucuda `araclar/yapilandirma_uret.py` ve
`kur.sh` üretir.

Sunucudaki durum dosyaları: `user_data/isinma_baslangici.txt` (botların ilk
başladığı an), `user_data/sinav_baslangici.txt` (Ahmet Telegram'da
`/sinav_baslat evet` yazınca oluşur; bir kez yazılır, değiştirilmez),
`user_data/kurulum_tamam`, `user_data/logs/uyum_gecti`,
`user_data/telegram_sohbet.txt` (botun dinlediği tek sohbet),
`user_data/arsiv/` (uyum ve ölçüm raporlarının tarihli kopyaları).

Telegram komutları yalnız okur ve bildirir. Emir gönderen, ayar değiştiren ya
da sunucuda serbest komut çalıştıran bir Telegram komutu ekleme. Tek istisna
`/claude` komutudur: `user_data/claude_*.istek` adlı bir dosya bırakır (giriş
bağlantısı iste ya da tek kullanımlık giriş kodunu ilet); dosyanın içeriği
komut olarak çalıştırılmaz, yalnız bekleyen giriş ekranına harfi harfine yazılır.

## Sunucudaki Claude oturumu

Ahmet'in isteğiyle sunucuda da bir Claude Code oturumu çalışır
(`claude remote-control`, adı "Karabasan sunucu"); Ahmet ona telefonundaki
Claude uygulamasından bağlanır. **Çalışma klasörün `/opt/karabasan-bot` ise ve
makinenin adı `karabasan` ise o oturum sensin.** O zaman şunlar geçerlidir:

- Sunucunun içindesin, root yetkisiyle. Burada yaptığın her şey canlı sistemi
  etkiler. Değiştiren komutlardan önce Ahmet onay verir; yine de önce ne
  yapacağını bir cümleyle söyle.
- **Bu klasör canlı dağıtımdır, çalışma kopyası değildir.** 5 dakikada bir
  `main` ile eşitlenir (`git reset --hard origin/main`); izlenen dosyalarda
  yaptığın değişiklik bir sonraki güncellemede silinir. Sunucudan GitHub'a
  yazma yetkisi yoktur. Kalıcı bir düzeltme gerekiyorsa: sorunu ve önerdiğin
  değişikliği kısa ve kopyalanabilir biçimde yaz; Ahmet bunu GitHub'a
  yazabilen bulut oturumuna iletir. Acil bir geçici düzeltme yaparsan bunun
  geçici olduğunu açıkça söyle.
- En değerli işin teşhistir: `docker compose ps`, `docker compose logs`,
  `user_data/logs/` altındaki kayıtlar, `user_data/db/*.sqlite` (yalnız
  okuyarak), `araclar/uyum_denemesi.sh`. Bulut oturumu bunları göremez.
- **Raporlar burada, Ahmet'in iletmesine gerek yok.** Telegram'a giden her
  dosya bu sunucudaki bir dosyanın kopyasıdır: `user_data/logs/uyum_denemesi.txt`
  (uyum denemesi), `user_data/logs/karabasan_gecmis.txt` (Karabasan geçmiş
  ölçümü ve stop genişliği), `user_data/logs/kurulum.txt`, `user_data/logs/claude.txt`.
  Her raporun tarihli eski halleri `user_data/arsiv/` altındadır (11 Ekim 2026'dan
  beri; en yeni 80 dosya). Ahmet "raporu oku" derse dosyayı kendin aç, sonucu
  düz Türkçe ve rakamla özetle, kanıtlanmamış şeyi kanıtlanmış gibi anlatma.
- Gizli dosyaları okuma, içeriklerini yazma: `.env`, `telegram.env`,
  `/root/karabasan.env`, `/root/.claude/.credentials.json`.
- Değişmez kurallar burada da geçerlidir: gerçek para kodu ya da anahtarı yok,
  sınav sürerken strateji ayarı değişmez, internete kapı açılmaz. Üretilen
  dosyaları (`docker-compose.yml`, `user_data/config/`) elle düzenleme;
  üreteç her güncellemede yeniden yazar.
- Botları durdurmak ya da yeniden başlatmak sınav kaydını etkiler (bir saatten
  uzun kesinti o günü sınavdan düşürür). Ahmet açıkça istemeden yapma.
- Gerçek paraya geçilirse bu oturum kapatılır ya da ciddi biçimde kısıtlanır;
  borsa anahtarının durduğu sunucuda root yetkili bir oturum bırakılmaz.

## Durum

Laboratuvar sürümünün 1. ve 2. parçası yazıldı; 493 test geçiyor.

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

**Bot dizilişi 11 Ekim 2026'da değişti (Ahmet'in isteğiyle).** Ahmet MACD + RSI
momentum ve "akıllı para + RSI" stratejileri istedi; ikisi alım ve açığa satış
halleriyle eklendi (S5, S5K, S6, S6K). Bellek zorlanmasın diye S1–S4'ün
"vadeli alım" botlarının yerine geçtiler; o dördü spot'taki ikizleriyle aynı
işlemleri açıyordu. S6 akıllı para kavramlarının yalın halidir: yalnız
likidite avı ve seviyenin geri alınması; emir bloğu ve FVG yok. Yeni
stratejiler yapay veride (rastgele yürüyüş) komisyon kadar kaybediyor, yani
kendiliğinden kâr üretmiyorlar; gerçek verideki sonuçları henüz görülmedi
(`ANALIZ_SURUMU=2` ve `UYUM_SURUMU=4` ile sunucuda çalışacak). Ahmet
"en kazançlısı bu olacak" diye bekliyor; ona bunun henüz tahmin olduğu ve çok
fikir denedikçe birinin şans eseri iyi görünme olasılığının arttığı söylendi.
Strateji adları da ne yaptığını söyleyen düz adlarla değiştirildi.

**Stop sonrası izleme (11 Ekim 2026, Ahmet'in isteğiyle).** Ahmet "stop
olunca fiyatı izlemeye devam et; stopu esnetsem belki kazandırırdı, bunu
derslerine al ve kararlarını güncelle" dedi. Yapılan: `stop_sonrasi.py` canlı
stopları izler, sayfada Dersler ekranı ve Telegram'da `/dersler` gösterir,
geçmiş ölçüm raporu stop genişliğini yeniden benzetimle sınar. **Sistem stopu
kendi kendine değiştirmez** ve değiştirmemeli: karar yalnız öneridir, geniş
stoplu hal ayrı bir sanal botla denenir (3. kural ve tasarım raporundaki
"öneri ve onay" ilkesi). "Stop dar" demek bilerek zordur: en az 30 izlenmiş
stop, ortalama farkın standart hatasının en az 2 katı olması, stop başına en
az %0,15 iyileşme ve iyileşmenin en az dörtte birinin dönemin her iki
yarısından gelmesi. Neden: rastgele üretilmiş veride bile bazı seçenekler iyi
görünüyordu (ilk kural S3'e yapay veride "dar" dedi; kural bunun üzerine
sıkılaştırıldı). On bot × üç seçenek sınandığı için yine de arada bir şans eseri
"dar" çıkabilir; bu yüzden sonuç ayar değil, yeni bir sanal bot önerisidir.
Ahmet'e söylendi.

Ahmet 11 Ekim'de Tailscale bağlantısını henüz onaylamamıştı. **Sunucudaki
Claude oturumu çalışıyor (11 Ekim 2026, doğrulandı).** `claude remote-control`
gerçek sunucuda açıldı; `--spawn=same-dir` ile üçüncü soru ("Choose [1/2]")
çıkmadı. O oturum arşivdeki raporları kendisi okuyup özetini Ahmet üzerinden
bu oturuma iletiyor.

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

**Karabasan geçmiş ölçümü (`ANALIZ_SURUMU=3`, 11 Ekim 2026; sunucudaki
Claude'un özeti).** Süzgeç on stratejinin hiçbirini artıya çevirmiyor.
Hiçbir strateji "Stop dar" çıkmadı: S5K "yerinde", S1, S4 ve S1K "yetersiz",
diğerleri "kararsız". Yeni bot önerisi yok. Not edilecek bir gözlem: S3 ve
S4 Kırmızı durumda kazanıyor (S4: 28 işlem, %68 kazanma, +2,76 USDT). Bu
tek bir dönem ve az işlemdir; ayar değil, ileride "yalnız Kırmızı'da çalışan
S3 / S4" diye ayrı bir sanal bot fikri olarak duruyor. Ahmet'e önermeden önce
12 aylık veride (3. iş) aynı şey görülmeli.

**Smartmoney (11 Ekim 2026, Ahmet'in isteğiyle).** Ahmet LuxAlgo'nun "Smart
Money Concepts" göstergesinin kodunu gönderdi; "bunu çalıştırdığımız botta
izlemek istiyorum, adı smartmoney olsun, yalnız 5 dk / 15 dk / 1 saat
yetmeyebilir, günlük trend, RSI ve hacim de önemli" dedi. Yapılan: iki yeni
kural (SM alım, SMK açığa satış) ve iki yeni sanal bot (`sm-vadeli` 8091,
`smk-vadeli` 8092); mevcut on bota dokunulmadı, toplam on iki bot. Dört katman:
günlük trend (kapanış, 20 günlük üstel ortalamanın hangi yanında), 1 saatlik
yapının yönü ve RSI'ı, 15 dakikalıkta geri çekilme (denge çizgisinin öte yanı
ya da emir bloğuna dokunuş, son 12 mumda), 5 dakikalıkta yapı kırılımı + RSI
aralığı + hacim. Çıkış %1,2 / %0,8 / 240 dk. Ayrıntı README'de.

- Göstergenin kodu kopyalanmadı: lisansı CC BY-NC-SA (ticari kullanım yok) ve
  depo herkese açık. Kavramlar `g.piyasa_yapisi` ile baştan yazıldı. FVG ve
  eşit tepe / dip kullanılmadı. Ahmet'e söylendi.
- Günlük mum için kural motoruna iki şey eklendi: göstergede açık dilim
  (`"dilim": "1d"`) ve `borsa_dilimleri`. Günlük mumlar 5 dakikalıklardan
  toplanamaz (60 günlük geçmiş, alınabilen 2000 mumu aşar); motor onları
  borsadan ayrıca getirir. **Bu yol gerçek motorda henüz çalışmadı**; yalnız
  sahte veri sağlayıcıyla sınandı. `UYUM_SURUMU=6` ile sunucuda ilk kez
  çalışacak: uyum denemesi vadeli için 200 günlük `1d` verisini de indirir,
  bağımsız benzetim aynı dosyayı okur. Raporda SM / SMK'nın motor ve benzetim
  işlem sayıları yakın olmalı. Motor "hiç işlem açmadı" derken benzetim işlem
  buluyorsa günlük veri motora ulaşmamıştır; raporda "1d mumları alınamadı"
  uyarısını ara.
- Yapı göstergesi durum taşır (son tepe, son dip, yön, bloklar). Verinin
  nereden başladığına bağlı kalmasın diye blokların ömrü vardır (20 × uzunluk
  mum) ve `gereken_mum` yapı için 30 × uzunluk mum ister (SM'de 1 saatlik yapı
  yüzünden 1810). Yapay veride, ısınmadan sonra sütunların birebir aynı çıktığı
  sınanıyor (`test_sinyal_veri_baslangicindan_bagimsizdir`); gerçek veride
  motor ile benzetim arasında yine de birkaç işlemlik fark çıkabilir.
- Yalnız yapay veride denendi: rastgele yürüyüşte komisyon kadar kaybediyor,
  coin başına günde yarım işlem kadar açıyor (alım ve satış birlikte). Gerçek
  verideki sonucu bilinmiyor; Ahmet'e "henüz tahmin" dendi. Aynı uyarı
  geçerli: çok fikir denedikçe birinin şans eseri iyi görünme olasılığı artar.
- On iki botun belleği ölçüldü (11 Ekim 2026, sunucudaki Claude): toplam
  7,6 GB, kullanılan ~6,2 GB, boşta ~1,4 GB; bot başına ~440 MB, haberci /
  kayıtçı / panel birlikte ~64 MB. Takas alanı yoktu, "bellek bitti" kaydı
  yok. Risk uyum denemesi ve geçmiş ölçümüdür (ek `arac` kapsayıcısı). Bu
  yüzden `kur.sh` 2. adımda `araclar/takas.sh` ile 2 GB takas alanı kurar
  (`/swapfile`, `/etc/fstab`'a bir kez, `vm.swappiness=10`); kurulamazsa
  yalnız uyarı yazar. Bir bot daha eklemek ~440 MB ister: 13. bot boşluğun
  üçte birini yer; eklemeden önce yerine bir botu çıkarmayı düşün.
- `ozel_ag.sh` artık adres değişmese de çalışmayan köprüleri açar; yoksa
  sonradan eklenen botların kapıları (8091, 8092) özel ağa taşınmazdı.
- Haberci, açılışından sonraki yarım saat boyunca hiç kayıt yazmamış botu
  "susmuş" saymaz. Yoksa listeye bot eklenen her güncellemede, yeni bot
  sırası gelip açılana kadar (8-10 dakika) Ahmet'e yanlış alarm giderdi.

**Hedef %0,8, stop %3, hepsi vadeli (12 Ekim 2026, Ahmet'in isteğiyle).**
Ahmet "en başarısız iki botu değiştir, amacımız 1 kat vadelide %0,8 yakalamak"
dedi; stopu kendisi %3 seçti (önerilen "stop hedeften geniş olmasın"dı) ve
spot botların da vadeliye taşınmasını istedi. Yapılan:
- On iki stratejinin hepsinde hedef %0,8, stop %3; süre aşımları aynen kaldı.
  Başa baş için işlemlerin %81,6'sı kazanmalı (vadeli, gidiş-dönüş %0,1). Stop
  sonrası ölçüm daha önce hiçbir stratejide "stop dar" dememişti; Ahmet'e söylendi.
- S1–S4 spot'tan vadeliye taşındı (`s1-spot` → `s1-vadeli`; eski kayıtlar
  sayılmaz, kapılar aynı). Vadelide BTC işlem görmüyor (50 USDT < en küçük tutar).
- En çok kaybeden iki strateji çıkarıldı: S6 (motor −18,11 USDT) ve S2K
  (benzetim −17,61 USDT). Yerlerine S7 / S7K geldi: 15 dakikalık, 1 saatlik
  trend yönünde, 200 mumluk ortalamanın doğru yanında, 2 mumluk RSI aşırı uca
  gidince (alımda < 10, satışta > 90) trend yönünde küçük tepkiyi hedefler
  (Connors RSI(2) fikri). Yalnız yapay veride sınandı (rastgele yürüyüşte
  %70 kazanma, komisyon kadar kayıp; yani kendiliğinden kâr yok).
- `UYUM_SURUMU=7`, `ANALIZ_SURUMU=5`: sunucuda uyum denemesi ve geçmiş ölçüm
  yeni ayarla yeniden çalışır; botlar yeniden başlar (ısınma, sınav başlamadı).
- Tasarım raporu güncellendi (strateji tablosu ve 12 Ekim notu).
- Ahmet TradingView'den kod verebileceğini söyledi; verirse kavramı yeniden
  yaz, lisansı kopyalamaya izin vermiyorsa kodu kopyalama (Smartmoney'deki gibi).

**%0,8 / %3 ayarının ilk gerçek sonucu olumsuz (11 Ekim 2026; uyum 7 ve
geçmiş ölçüm 5, sunucudaki Claude'un özeti).** On iki botun on biri ekside;
yalnız S4 artıda (+0,7 USDT). Kazanma oranları %33–73, başa baş için gereken
%81,6'nın çok altında. Çıkışların çoğu süre aşımı: fiyat süre içinde ne %0,8
lehe ne %3 aleyhe gidiyor. Ahmet'e söylendi. Ayar değiştirmeden önce Ahmet'e
sor; sınav başlamadı ama her değişiklik yeni bir geçmişe ezber denemesidir.

- s2/s3/s4-vadeli'nin 07:40–07:57 UTC sessizliği hata değildi: kapsayıcılar
  yeni adlarıyla 07:56'da ilk kez oluşturuldu. Bellek bitmedi (OOM yok,
  yeniden başlama 0). Takas 2 GB açık ve kullanılmıyor (doğrulandı); 12 bot
  açıkken kullanılabilir bellek ~1,3 GB.
- İşlem işlem eşleştirme (uyum 7): 12 botun 11'inde motor ile benzetim birebir
  ya da ±2 işlem. S2'de 26 "yalnız motor" işlem vardı, benzetimde o an açık işlem
  yoktu. Neden bulundu ve düzeltildi: hazır motor bir mumda önce girişe, sonra
  çıkışa bakar; hedef ya da stopla mumun içinde kapanan işlemden sonra o mumun
  sinyaliyle bir sonraki mumda yeniden girer. Benzetim o sinyali atlıyordu
  (`i = j + 1`). S2 art arda kırılım sinyali verdiği ve %0,8 hedef çoğu kez
  giriş mumunda görüldüğü için fark orada büyüdü. Süre aşımında motor bir
  sonraki mumun açılışında kapatır ve o mumda girmez; benzetim bunu korur.
  Açığa satıştaki eski ~%10 farkın da büyük ölçüde bu olduğu tahmin ediliyor;
  doğrulanmadı. `UYUM_SURUMU=8` ile yeniden karşılaştırılacak; S2'de "yalnız
  motor" sayısı 0'a yakın inmeli.

**12 aylık geçmiş testinin sonucu: hiçbir stratejide kenar yok (12 Ekim 2026;
11.10.2025–11.10.2026, %0,8 / %3, ETH SOL XRP DOGE, bağımsız benzetim).**
On iki botun on ikisi de yıl sonunda ekside; hiçbiri dört çeyreğin üçünde
artıda değil (en iyisi S4: 2 / 4). Toplam −1.053 USDT (12 × 1.000 USDT
bakiyede yaklaşık −%8,8). En az kaybeden SMK −26,69, SM −30,17, S4 −31,12;
en çok S6K −164,08, S3 −135,64, S5K −129,82. En büyük düşüş %3,2–16,8.
Kazanma %39–63, başa baş %81,6. İşlem başına net −%0,04 ile −%0,14; gidiş
dönüş komisyon %0,10 olduğundan komisyon öncesi sonuç sıfıra yakın: girişler
yazı turadan iyi değil, kayıp çoğunlukla komisyon. Çıkışların yarıdan fazlası
süre aşımı. "Stop = hedef" sütunu da hepsini ekside bırakıyor (yalnız bilgi).
Rapor: `user_data/logs/yillik_test.txt`. Ahmet'e söylendi; gerçek paraya geçme
önerilmedi. Bu stratejilerin ayarıyla oynamak sonucu kurtarmaz (her ayar yeni
bir ezber denemesi); yön kararı Ahmet'in.

**Yalnız Smartmoney kaldı (12 Ekim 2026, Ahmet'in isteğiyle).** Ahmet "mevcut
stratejileri sil, sadece smartmoney tut; sonra yeni bir strateji üstünde
çalışacağız" dedi. `BOTLAR` artık iki bot: `sm-vadeli` (8081), `smk-vadeli`
(8082). Öbür on kural `stratejiler/emekli/`'ye taşındı (silinmedi; neden
`emekli/BENIOKU.md`'de). Sunucuda `docker compose up --remove-orphans` eski on
kapsayıcıyı kaldırır; bellek ~4,4 GB boşalır. Eski botların SQLite kayıtları
`user_data/db/`'de kalır, okunmaz. Eski kapılar (8083–8092) için Tailscale
köprüleri kalabilir; boşa dinler, zararsız. `UYUM_SURUMU=9`.
- Testler: sonuç sayfası, Telegram, stop sonrası, geçmiş ölçüm ve 12 aylık test
  testleri çeşitli bot davranışlarını kurmak için eski on iki botluk listeyle
  çalışır (`testler.veri.ESKI_BOTLAR`, `eski_bot_listesi_baslat` modül başında).
  Bağlantı katmanı testleri tek dilimli kuralları emekli dosyalardan deneme
  sınıfı olarak yükler (`StratejiSiniflari.emekli`).
- Smartmoney'nin 12 aylık sonucu da ekside (SM −30,17, SMK −26,69 USDT); en az
  kaybedenler olduğu için tutuldu, kazandırdığı için değil. Ahmet'e söylendi.
- Sıradaki iş Ahmet'le yeni bir strateji. Yeni strateji = yeni kural dosyası ve
  `BOTLAR`'ın sonuna yeni bot; önce 12 aylık testten geçsin (`YILLIK_SURUMU`
  artır), sonuç dört çeyreğin en az üçünde artı değilse Ahmet'e açıkça söyle.

**Emir defteri denemesi (12 Ekim 2026, Ahmet'in isteğiyle).** Ahmet "yalnız
BTC vadeli, alım ve satış; her saniye emir defterine bakıp 5 ve 15 dakika sonra
fiyatın ne olacağını hacim, RSI, destek / direnç ile kestir, kazanç görürsen
pozisyon aç; geçmişe dönük değil ileriye dönük test et; mevcut sayfaları bozmadan
ayrı bir özet sayfası yap" dedi. Yapılan: `defter` servisi ve `/defter` sayfası
(Yapı tablosunda). Mevcut botlara, sayfaya ve ayarlara dokunulmadı.
- Tahmin için önceden yazılmış bir formül yok; model servisin kendi kaydından
  öğrenir ve yalnız sonucu belli olmuş anlardan öğrenir (5. kural testleri
  `test_defter.py`'de). Sabit eğilim terimi yok (yoksa son saatlerin ortalama
  hareketini geleceğe taşıyordu; yapay piyasada bu yüzden "değişmez"den kötü çıktı).
- Yapay piyasada (defterde gerçekten ipucu olan) model yeterli kayıttan sonra
  "değişmez" tahmininden iyi çıkıyor; bu yalnız düzeneğin çalıştığını gösterir.
  Gerçek BTC defterinde 5-15 dakikalık bir ipucu olup olmadığı bilinmiyor;
  Ahmet'e "kendi başına kazandıracağının bir garantisi yok" dendi. Sayfadaki
  ölçüt: tahmin hatası "değişmez" hatasından küçük ve yön isabeti %50'den
  belirgin büyük mü? Değilse işlemlerin sonucu şanstır.
- Sunucuda doğrulanacak: `fapi.binance.com/fapi/v1/depth`'e saniyede bir
  ulaşılabilmesi (ağırlık 5, dakikada 300; sınır 2.400), kapsayıcının
  `kayit/defter.sqlite` yazabilmesi, panel ve habercinin aynı dosyayı salt
  okunur açabilmesi (WAL). Sorun olursa `docker compose logs defter`.
- Sonuç sayfası sunucusu yalnız Tailscale ile açılır ve Ahmet henüz onaylamadı;
  bu yüzden Telegram `/defter` hem kısa özeti hem sayfayı dosya olarak yollar.

**SMD / SMDK: Smartmoney + uyumsuzluk + emir defteri (12 Ekim 2026, Ahmet'in
isteğiyle, "geçmiş testine gerek yok, ileriye dönük izleyelim").** SM / SMK'nın
bütün koşulları + son 12 mumda en az bir göstergede uyumsuzluk + girişte emir
defteri onayı. Kurallarda `"defter_onayi": {"en_az_dengesizlik": 0.1}`; karar
`karabasan.defter.defter_onayi`'de (ilk 20 kademe dengesizliği ≥ 0,1, defterin
tamamı ve mikro fiyat aynı yönde), çağrı bağlantı katmanının
`confirm_trade_entry`'sinde (`dp.orderbook(pair, 100)`; yalnız `dry_run` / `live`
kipinde; defter okunamazsa girmez). Çıkış SM ile aynı (%0,8 / %3 / 240 dk).
- Uyumsuzluk kavramı Ahmet'in gönderdiği TradingView göstergesinden (MPL 2.0);
  kod kopyalanmadı, `g.uyumsuzluk` baştan yazıldı. Parite başına 2.000 mumda
  ~0,15 sn (60 parite ~9 sn / 5 dk).
- Geçmiş testi, uyum denemesi ve 12 aylık test defter onayını uygulayamaz;
  oradaki SMD sayıları defter süzgeci olmadan, yani olduğundan fazladır.
  `UYUM_SURUMU=10` (yeni sınıflar gerçek motorda ilk kez yüklenecek).
- Sunucuda doğrulanacak: `dp.orderbook()`'un sanal modda vadeli defteri vermesi,
  `confirm_trade_entry`'nin bu motor sürümünde bu imzayla çağrılması, kayıttaki
  "defter onayladı / onaylamadı" satırları (`/gunluk smd-vadeli`).
- Bellek: dört bot (~1,8 GB) + defter servisi; sorun beklenmiyor.

**Sniper (12 Ekim 2026, Ahmet'in isteğiyle).** Ahmet "bütün interneti,
TradingView'ı araştır, en çok kazananları bul, 3Commas'ı da kullan; çok gelişmiş
bir bot koy, adı sniper olsun, diğerleriyle birlikte başlat" dedi. Araştırma
sonucu Ahmet'e söylendi: TradingView'deki "en çok kazanan" sonuçlar denetlenmemiş
ve çoğu geçmişe ezber; 3Commas borsa API anahtarı ister (1. ve 2. kural), pazar
yerindeki kazançlar kısa ve seçilmiş dönemler. Açık yayımlanmış, komisyon dahil
en güçlü kanıt günlük Donchian topluluğuyla trend takibi (Zarattini, Pagani,
Barbon, "Catching Crypto Trends", 2025). Yapılan:
- `g.donchian_topluluk` (kural türü `"donchian_topluluk"`, `uzunluklar` listesi):
  her model kapanış önceki N günün en yüksek kapanışını aşınca girer, izleyen stopu
  (N günlük en yüksek ve en düşük kapanışın ortası, yalnız yukarı) kırılınca çıkar.
  Değer trendde olan modellerin payıdır.
- Kural motoruna **çıkış sinyali** eklendi: `cikis > sinyal` (giriş koşuluyla aynı
  yazım). `sinyal_uret` `cikis_sinyal` sütunu koyar; bağlantı katmanı
  `populate_exit_trend`'de `exit_long` / `exit_short` yazar; benzetim sinyal
  mumunun ardından gelen mumun açılışında kapatır (neden `cikis_sinyali`).
  Sınırlar genişledi: hedef ≤ %200, stop ≤ %10, süre ≤ 90 gün.
- `SNIPER.json`: 1d taban dilim, dokuz uzunluk (5–360 gün), giriş pay 0,5'i yukarı
  keser, çıkış aşağı keser; hedef %200 (yani yok), stop %10, süre 90 gün;
  `gereken_mum` 735. Yalnız alım. Sadeleştirme: makaledeki model başına
  ağırlık ve oynaklığa göre büyüklük yok; sabit 50 USDT ve çoğunluk kararı.
- `ek_dilimler` taban dilimi 5m / 15m dışında olan kuralın dilimini de ekler;
  uyum denemesi ve analiz günlük veriyi 800 gün, 12 aylık test 1100 gün indirir.
  `UYUM_SURUMU=11`, `YILLIK_SURUMU=2` (12 aylık test SMD / SMDK / Sniper dahil
  yeniden çalışır; SMD'nin defter onayı orada uygulanamaz, raporda not var).
- Stop sonrası izleme sinyalle çıkan kuralları atlar (sabit hedef ve süreye göre
  kurulu; Sniper'da işlem 90 güne kadar sürer). 12 aylık rapor Sniper için
  "hedef yok", "kanal sinyali" çıkış sayısı yazar, "stop = hedef" satırı vermez.
- Yapay rastgele veride nötr (163 işlem, %32 kazanma, +3,98 USDT). Gerçek veride
  sonucu bilinmiyor. **Gerçek motorda ilk kez çalışacaklar:** 1d taban dilimli bir
  botun canlı (sanal) çalışması, 735 günlük başlangıç mumunun indirilmesi (Binance
  vadelide bu kadar geçmişi olmayan coinlerde sinyal yok), `exit_long` ile çıkış.
  Kayıtta "exit_signal" çıkışları görülmeli (`sonuc.py` "çıkış sinyali" der).
- Bellek: beş bot (~2,2 GB) + defter servisi.

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

**Sniper değişti: 5 dakikalık kısa vuruş (12 Ekim 2026, Ahmet'in isteği).**
Ahmet günlük trend takibini "rezalet" buldu: "hedefim 5-15 dk'lık grafiklerde dip
görmüş, belki düşüşe devam edecek ama orada %1–1,5 kâr varsa onu almak; 90 gün
unutmam; kısa ve sık vuruş; komisyon dahil %0,6–0,7'lik garantiye yakın işlemlerle
günde 1000 pozisyon olsa mükemmel; smart money ile CHoCH ve BOS'ları bul, FVG'leri
bul, RSI, hacim ve momentumla vurgunu yap" dedi. Yapılan:
- Eski kural `emekli/SNIPERG.json` (canlıda sonuç vermeden çıktı). Çıkış sinyali,
  `donchian_topluluk`, hedefsiz kural desteği kural motorunda kaldı; testleri
  `test_cikis_sinyali.py`'de SNIPERG ile.
- `g.fvg` (kural türü `"fvg"`, `omur` 3–500, `en_az_yuzde` 0–5): boğa boşluğu
  `low[t] > high[t-2]`; en yeni geçerli boşluğun sınırları; altında kapanış ya da
  ömür dolunca biter. Geleceğe bakmaz (testli).
- Yeni `SNIPER.json` (5m, alım): 15 dk RSI < 35 son 36 mumda (dip), 5 dk yapı
  (uzunluk 3) yukarı CHoCH son 12 mumda ve yön yukarı, boğa FVG son 6 mumda ya da
  açık boğa FVG'ye geri çekilip üstünde kapanış, MACD histogramı > 0, RSI 50–70,
  hacim > 1,5 × 20 ortalama son 3 mumda. Çıkış %1,2 / %1,5 / 180 dk, stop sonrası
  30 dk bekleme. Başa baş %59 (vadeli). Stopu Ahmet söylemedi; %1,5 seçildi ve söylendi.
- Bot adı `sniper5-vadeli` (eski `sniper-vadeli` kaydı karışmasın), kapı 8085 aynı.
  `UYUM_SURUMU=13`, `YILLIK_SURUMU=3`.
- Yapay rastgele veride coin başına günde ~1 işlem, %52 kazanma, işlem başına
  komisyon kadar kayıp: kendiliğinden kâr yok. 60 paritede günde ~60 işlem beklenir,
  1000 değil. Ahmet'e açıkça söylendi: "garantiye yakın %0,6–0,7" yok; 12 aylık
  testte kısa vadeli girişler yazı turadan iyi değildi, sık işlemde komisyon asıl
  düşmandır (günde 1000 işlem × %0,1 = sermayenin büyük kısmı).

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

**Limitli giriş ve RSI 80 / 20 (12 Ekim 2026, Ahmet'in isteği; yeni bot yok).**
Ahmet: "sinyal geldiği andan itibaren daha aşağıdan alım ya da yukarıdan açığa satış
yapman gerekiyor; sniper ve sm'ye odaklan, daha etkili göstergeler ekle; 5 dk'da
yükselmiş RSI 15 dk'da nerede, buna limit belirle; RSI 70 / 30 ise 80 / 20 yapıp
inceleyelim; mevcut botlarda güncelle, yeni bot ekleme." Yapılan (beş botun hepsi):
- Kural alanı `giris_limiti` (`atr_kat` 0,5, `en_az_yuzde` 0,1, `en_fazla_yuzde`
  0,6, `sure_dakika` 15): uzaklık = 0,5 × ATR yüzdesi (14 mum), kırpılmış. Bağlantı
  katmanı `custom_entry_price` ile sinyal mumunun (giriş mumundan bir önceki; tarih
  ≤ şimdi tabana yuvarlanmış − 1 mum) `giris_limit_yuzde` satırını okur
  (`dp.get_analyzed_dataframe`); okuyamazsa en küçük uzaklık. Yapılandırma:
  `order_types.entry = "limit"`, `unfilledtimeout.entry = 15` dk; çıkışlar piyasa.
- Benzetim: emir sinyal mumundan sonraki mumun açılışından hesaplanır, en çok 3
  mum bekler (o mumlar dahil), dolarsa limit fiyatından (kayma yok); dolmazsa son
  bekleyen mumun sinyali yeni emir açabilir. Dolduğu mumda hedef sayılmaz, stop sayılır.
- RSI: SM / SMD 1 s RSI < 80, 5 dk RSI 50–80, 15 dk RSI < 65; SMK / SMDK 1 s RSI
  > 20, 5 dk 20–50, 15 dk > 35; Sniper 5 dk 50–80, 15 dk < 50 (dip eşiği 15 dk
  RSI < 35 aynen: 20 yapılsa neredeyse hiç işlem açmazdı; Ahmet'e söylendi). Hepsinde
  5 dk RSI 3 mum öncesine göre dönmüş olmalı.
- `UYUM_SURUMU=14`, `YILLIK_SURUMU=4`. Yapay veride hepsi yine kenarsız (beklenen).
- **Gerçek motorda ilk kez:** `custom_entry_price`'ın bu imzayla çağrılması, geçmiş
  testinde limit emrin mumlar boyunca beklemesi ve süre dolunca iptali, dolduğu mumda
  çıkışların nasıl değerlendirildiği, `get_analyzed_dataframe`'in geçmiş testinde o
  ana kadar kesilmiş tablo vermesi. Uyum raporunda motor / benzetim farkı buradan
  çıkarsa önce eşleştirmedeki "yalnız motor / yalnız benzetim" satırlarına bak.

**On dördüncü uyum denemesi ve 12 aylık test (limitli giriş + RSI 80 / 20; 11 Ekim
2026 19:27 UTC, Ahmet iletti).** Beş bot geçti; motor yapılandırmadaki `"entry":
"limit"`'i aldı. Eşleştirmede "yalnız motor / yalnız benzetim" çiftleri aynı işlemdi:
motor açılışı emrin konduğu mum olarak yazıyor, benzetim dolduğu mumu yazıyordu (5–10 dk
fark; çıkış zamanları aynı, süre aşımı motorda konduğu andan). Benzetim buna uyduruldu
(`giris_zamani = tarih[i + 1]`, süre oradan; çıkışlara dolduğu mumdan bakılır).
`UYUM_SURUMU=15` eşleşmeyi yeniden sınar. Çıkış nedenleri iki tarafta neredeyse aynı
(SM motor hedef 32 / süre 36 / stop 4, benzetim 32 / 35 / 4): dolduğu mumda hedef
saymamak motorla uyumlu görünüyor.
- Son 30 gün (benzetim, BTC dahil; önceki ayar → yeni): SM 112 / %52 / −3,03 → 86 /
  %58 / −3,44; SMK 47 / %40 / −3,61 → 32 / %47 / −3,06; SMD 88 / %49 / −4,80 → 67 /
  %58 / −2,38; SMDK 36 / %33 / −3,03 → 28 / %46 / −1,61; **Sniper 102 / %56 / −1,87
  → 53 / %38 / −9,67** (stop 17 / 51). Limitli giriş Sniper'da ters seçim yaptı:
  fiyat dönüşte geri çekilmeden giderse emir dolmuyor, geri gelip düşmeye devam
  edince doluyor. Tek dönem; Ahmet'e söylendi, kendiliğinden geri alınmadı.
- 12 aylık test (11.10.2025–11.10.2026; raporda tarih yoktu, büyük olasılıkla yeni
  ayarla; artık rapor "Hazırlandı" satırı yazar): 5 / 5 bot ekside, hiçbiri 3 / 4
  çeyrekte artıda değil. SMD 362 işlem %55,8 −11,54; SM 471 / %53,9 / −20,47;
  SMDK 689 / %56,9 / −37,92; Sniper 613 / %45,7 / −43,07 (başa baş %59,3); SMK
  955 / %56,2 / −54,12. Toplam −167,12 USDT. İşlem başına net −%0,06 ile −%0,14,
  yani komisyon öncesi yine sıfıra yakın: kenar yok. Gerçek paraya geçme önerilmedi.

**İz süren stop, %3 stop, süre sınırı yok + 20 varyasyonluk tarama (12 Ekim 2026,
Ahmet'in isteği).** Ahmet: "Sniper'daki limitli girişi izleyelim. Belki kâr hedefini
2 yapsak yakalıyorduk, belki çok erken çıkıyoruz; trailing stop ekle, 1,2'de tetiklensin
0,9'a düşünce kapatsın, stop %3, saat limiti koyma; botları böyle güncelle. Ayrıca 20
farklı varyasyonla bir senelik test yapıp en kazançlıyı bul." Yapılan:
- Çıkış alanları: `kar_hedefi_yuzde` ve `sure_asimi_dakika` artık isteğe bağlı; yeni
  `iz_suren_stop` (`tetik_yuzde` 0,1–20, `mesafe_yuzde` 0,05–10, mesafe < tetik).
  Stoptan başka en az bir çıkış yolu zorunlu. `cikis_metni` düz Türkçe anlatır.
  `basabas_orani` sabit hedef yoksa None.
- Beş canlı kuralın çıkışı: `{"zarar_durdur_yuzde": 3.0, "iz_suren_stop": {"tetik_yuzde":
  1.2, "mesafe_yuzde": 0.3}}`. Tetik komisyon sonrası kârdır (motorun
  `trailing_stop_positive_offset`'i gibi); seviye en iyi fiyatın %0,3 gerisi
  (`trailing_stop_positive`). İlk anda çıkış ≈ fiyat %1,3 → ×0,997 ≈ %1,0 brüt, %0,9 net.
  Motor: `trailing_stop = True`, `trailing_only_offset_is_reached = True`,
  `minimal_roi = {"0": 100}` (hedef fiilen kapalı), `custom_exit` süre yoksa None.
- Benzetim: etkin stop = sabit stop ile iz seviyesinin yakını; önceki mumların en iyi
  fiyatından; mum stopun ötesinde açılırsa açılıştan kapanır (neden `iz_suren_stop`).
  Limitli girişte dolduğu mumun tepesi en iyi fiyata katılmaz. Motorun geçmiş testi
  mum içinde daha iyimser olabilir; 16. uyum denemesinde eşleştirmede görülür
  (`trailing_stop_loss` → `iz_suren_stop`, `exit_signal` → `cikis_sinyali`).
- Stop sonrası izleme ve 12 aylık testin "stop = hedef" sütunu sabit hedef / süre
  olmayan kuralları atlar (yani şu an bütün botları); Dersler ekranı boş kalır.
- Tarama: `karabasan/tarama.py` (Yapı tablosunda). Varyasyonlar: iz süren stop tetik
  {0,8; 1,2; 2} × mesafe {0,3; 0,6} × stop {1,5; 3} süresiz (12), V01 ile aynı iz /
  stop + 4 s ve 24 s süre (2), sabit hedef: 0,8/3/4 s (eski SM), 1,2/1,5/3 s (eski
  Sniper), 2/3/süresiz (Ahmet'in "hedef 2"si), 2/2/24 s, 1/1/4 s, 3/1,5/24 s (6).
  5 bot × 20 = 100 deneme; yapay veride ~110 sn. Rapor: her bot için 20 satır (yıl,
  ilk 9 ay, son 3 ay, en büyük düşüş), seçim dönemine göre en iyisi ve doğrulaması,
  yıl boyu en iyisi ("ezbere açık"), kaç denemenin artıda olduğu. Rastgele veride 100
  denemenin hiçbiri artıda değil (beklenen).
- `UYUM_SURUMU=16`, `YILLIK_SURUMU=5`, `TARAMA_SURUMU=1`. Süresiz işlemler yüzünden
  botlar daha az ve daha uzun işlem açar; 20 pozisyon sınırı dolabilir.
- **Gerçek motorda ilk kez:** iz süren stopun bu motorda canlı ve geçmiş testinde nasıl
  uygulandığı, `minimal_roi = {"0": 100}`, süresiz `custom_exit`.

**Çıkış taramasının ilk sonucu (11 Ekim 2026 20:54 UTC, Ahmet iletti; 11.10.2025–
11.10.2026, seçim 12.07.2026'ya kadar).** 100 denemenin 25'i yıl sonunda artıda; hem
ilk 9 ayda hem son 3 ayda artıda yalnız 2 (SMD V07 +5,41 / +1,23; SM V20 +1,62 /
+3,82): şanstan ayırt edilemez. Dürüst seçim (SMK V10) son 3 ayda −18,83.
- Tutarlı ders: beş botta da iz süren stoplu ayarlar sabit küçük hedeflerin (V15 eski
  SM, V16 eski Sniper, V19) belirgin önünde; eski ayarlar her botta en kötüler arasında.
  Şimdiki V01 yıl sonunda SM −9,88, SMK +14,16, SMD −0,37, SMDK +17,84, Sniper
  −18,19 (toplam ≈ +3,6); aynı girişler eski çıkışlarla ≈ −166. Yani "erken çıkıyoruz"
  gözlemi doğru çıktı; ama kenar yaratmadı, kaybı sıfıra çekti.
- Açığa satış botlarının (SMK, SMDK) artısı tamamen ilk 9 aydan; son 3 ayda 20
  varyasyonun 20'si de ekside. Piyasa yönü (düşüş dönemi) gibi görünüyor, beceri değil.
- Son 3 ayda V01 beş botta da ekside (toplam ≈ −59,9).
- Ahmet'e öneri: ayar değiştirme (en iyi görünenler doğrulamada kaybediyor); V01'de
  kal, canlı sonucu izle. Ayar değişikliği yalnız Ahmet isterse.

**Rapor ekranı (12 Ekim 2026, Ahmet'in isteği).** "Ortadaki değer kalsın; bir rapor
sayfası yap, bot seçimi olsun, her botun günlük kâr / zararını gösterelim." Sonuç
sayfasına altıncı ekran: bot seçimi (Bütün botlar + her bot), seçilen botun toplamı,
artıda biten gün, en iyi / en kötü gün, son 30 günün çubuk grafiği, gün gün tablo.
Ana ekrandaki halkanın ortası değişmedi. Not: halkanın ortası "toplam sanal sonuç"tur
(ısınma / sınav başından beri); Ahmet onu son 24 saat sanıyor, ona söylendi. Sayfa
yalnız buradaki Chromium'da (390 px ve 1280 px, betikli ve betiksiz) denendi.

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

**Uzman paneli: dört bot önerisi (12 Ekim 2026, Ahmet'in isteği; KARAR BEKLİYOR, kod yok).**
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
  freni, 4 yıllık veri indirme, seans aralığı göstergesi. Ahmet onaylamadan başlanmadı.

Sıradaki işler, öncelik sırasıyla:

0. On yedinci uyum denemesi: eşleşen işlemlerde motor / benzetim net farkı ve iz süren
   stopta benzetimin geç / erken kapattığı sayı (yukarıda). On altıncı geçti ve özetlendi.
   Ayar değişikliği yalnız Ahmet isterse. Ahmet Sniper'daki limitli girişi izlemek istedi
   (geri alınmadı).

1. Karabasan canlı ölçüm servisi: Binance mumları ve `kayitci` kaydından
   puanı 5 dakikada bir hesaplayıp kaydetsin (`puan.py` hesap kısmı hazır).
   Geçmiş ölçüm (yaklaşık) süzgecin hiçbir stratejiyi artıya çevirmediğini
   söyledi; canlı ölçüm bunu gerçek dominans ve TOTAL2 verisiyle sınar.
2. Sanal işlemlerin açıldıkları andaki Karabasan durumu ve filtre puanlarıyla
   etiketlenmesi (botların SQLite kayıtları ile Karabasan kaydının birleşimi).
3. 12 aylık geçmiş testi BİTTİ (yukarıda): 12 / 12 ekside. Açık soru: Karabasan
   durumuna göre ayırma bu testte yok (S3 / S4'ün Kırmızı'da kazanması).
4. (Büyük ölçüde bitti: neden benzetimdeki yeniden giriş kuralıydı, düzeltildi.
   8. uyum denemesinde doğrula.)
5. Haftalık Telegram raporu ve 30. gün karar raporu (`karne.sinav_karari`).
6. Sonuç sayfasına Karabasan durumu ve filtre hunisi (strateji ayrıntıları 11 Ekim'de eklendi; ana ekranda
   Karabasan için "henüz canlı ölçülmüyor" yazan bir şerit var, 1. iş bitince gerçek durumla değişecek).

## Sunucuda doğrulanacak varsayımlar

Sunucudaki ilk kurulumla doğrulananlar (10 Ekim 2026): Hetzner'in "Cloud
config" kutusundaki betiği ilk açılışta çalıştırması; `kur.sh`'ın Ubuntu
24.04'te baştan sona çalışması; Telegram bildirimleri ve sahibin `/start` ile
tanınması; hazır motorun on strateji sınıfını bulup yüklemesi; spot ve vadeli
veri indirme ve vadeli veri dosyalarının adı; on botun sanal modda çalışıp
işlem açması; `sonuc.py`'nin gerçek `trades` tablosunu okuması; botların
günlük dosyasına düzenli yazması ("Çalışan bot: 10 / 10").

Geçmiş testiyle doğrulananlar (11 Ekim 2026): `minimal_roi`, `stoploss`,
`can_short` ve süre aşımının (`custom_exit`) beklenen değerlerle uygulanması;
`minimal_roi`'nin komisyon sonrası oran olarak yorumlanması; geçmiş testi
çıktısında "BACKTESTING REPORT" başlığı; `claude auth login` akışının Telegram
üzerinden gerçek girişle çalışması; `claude remote-control`'ün açılış sorularının
metni, `--spawn=same-dir` verilince üçüncü sorunun çıkmaması ve uzak oturumun açılıp
çalışması; yeni dört stratejinin (S5, S5K, S6, S6K) motorda yüklenip işlem açması.

Bir ders: hazır motorun çıkış koduna tek başına güvenme. Ayar hatasında
`docker compose run` temiz kodla dönmüş göründü; nedeni bilinmiyor. Çıktıda
beklenen sonucu ara.

Bunlar belgeye göre yazıldı, çalıştırılarak doğrulanmadı:

- Smartmoney botlarının günlük mumları motordan alması: `informative_pairs()`'in
  `(parite, "1d")` döndürmesiyle motorun bu mumları canlıda indirip güncel
  tutması; `self.dp.get_pair_dataframe(pair=..., timeframe="1d")`'nin geçmiş
  testinde dosyadaki tüm günlük mumları, canlıda yalnız kapanmış günleri
  vermesi; vadelide varsayılan mum türünün doğru dosyayı bulması.
- `download-data --timeframes 1d --days 200` ile vadeli günlük verinin
  `user_data/data/binance/futures/<COIN>_USDT_USDT-1d-futures.feather` adıyla
  inmesi (araçlar bu adı arar; ad 5 dakikalık dosyalardan türetildi).
- `araclar/takas.sh`: `fallocate`, `mkswap`, `swapon` ve `sysctl` çağrıları yalnız sahte
  komutlarla denendi (`TakasAlaniTesti`). Gerçek sunucuda ilk kez çalışacak; sonucu kurulum
  kaydında "Takas alanı açıldı" ve `free -m`'in "Swap:" satırıyla görülür.

- 12 aylık test (`araclar/yillik_test.sh`): vadeli 5m / 15m için `--days 400 --prepend`
  (olmazsa `--erase`) ile bir yıllık verinin inmesi; `arac` kapsayıcısının
  `user_data/gecmis_test.json`'ı yazabilmesi. Yalnız yapay veriyle sınandı.
- `download-data --prepend` ile eldeki verinin başına 80 güne kadar eski veri
  eklenebilmesi (`analiz.sh`; olmazsa `--erase` ile baştan indirir).
- Binance'in BTC vadeli sözleşmesinde en küçük emir tutarının 100 USDT olduğu
  (vadeli geçmiş testlerinde BTC'de sıfır işlem olmasının açıklaması olarak).
- `geri_test_*.json` içindeki yer tutucu ekran değerlerinin hazır motorun
  yapılandırma denetiminden geçmesi (gerçek değerlerle geçtiği görüldü).
- Sanal modda vadeli işlemlerde fonlama ücretinin işlenmesi.
- Kapsayıcıdaki kullanıcının kimliğinin 1000 olması (`chown` buna göre).
- `tailscale status --json` çıktısındaki `BackendState` ve `AuthURL` alanları.
- `socat` köprüsünün sunucunun Tailscale adresinde dinleyebilmesi ve
  telefonun `http://karabasan:8080` adını çözebilmesi (MagicDNS).
- Motor görüntüsünde saat dilimi verisinin bulunması (yoksa sayfa UTC gösterir).
- Geçmiş testinde `--export trades` ile işlem listesinin
  `user_data/backtest_results/` altına yazılması ve sonuç dosyasının biçimi (zip içinde
  `strategy` → sınıf adı → `trades`; alanlar `pair`, `open_date`, `close_date`,
  `exit_reason`, `is_short`). Okuyucu düz `.json` dosyasını da kabul eder. Yalnız sahte
  sonuç dosyasıyla denendi. Dışa yazma kalırsa geçmiş testi adımı kalır; botlar yine
  çalışmaya devam eder.
- `.claude/settings.json` içindeki izin kurallarının yazımı.
- Stop sonrası izlemenin sunucudan Binance'in açık mum adreslerine (`api.binance.com/api/v3/klines`,
  `fapi.binance.com/fapi/v1/klines`) ulaşabilmesi ve yanıt biçimi; `kayitci` kapsayıcısının botların
  `db/*.sqlite` dosyalarını okuyup `kayit/stop_sonrasi.json` yazabilmesi. Yalnız sahte bir Binance
  sunucusuyla baştan sona denendi. Çalışmazsa Dersler ekranı "henüz izlenmiş stop yok" demeye devam eder
  ve `/gunluk` ile değil, `docker compose logs kayitci` ile görülür (sunucudaki Claude oturumu bakabilir).
- Yeni sonuç sayfası (11 Ekim 2026) yalnız buradaki Chromium'da, telefon ve masaüstü genişliğinde
  denendi: ekran geçişi, halkadaki dilime dokunma, yerinde tazeleme, bağlantı kopunca uyarı, betiksiz dosya
  hali. Ahmet'in telefonundaki tarayıcıda (Safari) ve Telegram'ın dosya görüntüleyicisinde denenmedi.
