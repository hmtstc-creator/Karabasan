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
  `user_data/strategies/` değişirse on bot yeniden başlar. Sınav sürerken
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
| `karabasan/gostergeler.py` | Gösterge blokları (EMA, RSI, MACD, Bollinger, ATR, VWAP, üst dilim hizalama) |
| `karabasan/kural.py` | Kural dosyası (JSON) okuma, doğrulama, sinyal üretme |
| `karabasan/stratejiler/*.json` | On strateji: S1–S6 (alım) ve S1K, S2K, S5K, S6K (açığa satış). Her birinin `ad` alanı ne yaptığını söyleyen düz addır; sayfada ve Telegram'da o görünür |
| `karabasan/puan.py` | Karabasan puanı, durum makinesi, vetolar |
| `karabasan/filtre.py` | Filtre (Elek): dört katman, elenme nedenleri |
| `karabasan/karne.py` | İşlem ölçümleri ve 30. günün yedi karar ölçütü |
| `karabasan/benzetim.py` | Bağımsız, kötümser mum bazlı benzetim |
| `karabasan/botlar.py` | On sanal botun listesi (4 spot alım, 6 vadeli), komisyon başlangıç değerleri. Uyum denemesi ve analiz bot listesini buradan okur |
| `karabasan/kayitci.py` | BTC dominansı ve TOTAL2'yi 10 dakikada bir kaydeder |
| `karabasan/gecmis_olcum.py` | Karabasan puanını geçmiş mumlardan geriye dönük hesaplar (yaklaşık: dominans ve TOTAL2 yerine altcoin vekili); işlemleri açıldıkları andaki durumla etiketler |
| `karabasan/sonuc.py` | Botların SQLite kayıtlarını salt okunur okuyup özet çıkarır; dönem (ısınma, sınav, bitti) |
| `karabasan/sayfa.py`, `karabasan/panel.py` | Türkçe sonuç sayfası ve sunucusu (8080; `/`, `/veri.json`, `/saglik`). Dört ekran: ana ekran (gösterge halkası), botlar, işlemler, sınav. Sunucudan açılan hali tek bir satır içi betik taşır (ekran geçişi, dakikada bir yerinde tazeleme); `panel.py` izin başlığını (CSP) o betiğin özetinden üretir. Telegram'ın `/sayfa` ile yolladığı dosya betiksizdir, dört ekran alt alta görünür |
| `karabasan/haberci.py` | Telegram: kurulum bildirimleri, günlük özet, susan bot uyarısı, komutlar |
| `user_data/strategies/karabasan_stratejileri.py` | Freqtrade bağlantı katmanı |
| `araclar/yapilandirma_uret.py` | Bot yapılandırmalarını ve `docker-compose.yml`'i üretir |
| `araclar/uyum_denemesi.sh`, `araclar/karsilastir.py` | Sunucudaki uyum denemesi |
| `araclar/analiz.sh`, `araclar/karabasan_gecmis.py` | Sunucudaki tek seferlik ölçüm: 80 günlük veri indirir, stratejilerin sonucunu Karabasan durumuna göre ayırır (`kur.sh` içinde `ANALIZ_SURUMU`; Telegram'da `/olcum`) |
| `kurulum/sunucu_blogu.sh` | Ahmet'in sunucuyu oluştururken "Cloud config" kutusuna yapıştırdığı blok |
| `kur.sh` | Kurulum; soru sormaz, her adımı Telegram'a yazar, her güncellemede yeniden çalışır |
| `araclar/oto_guncelle.sh` | 5 dakikada bir `main`'i denetler, yeni kodu alır, `kur.sh`'ı çalıştırır |
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
`user_data/telegram_sohbet.txt` (botun dinlediği tek sohbet).

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

Laboratuvar sürümünün 1. ve 2. parçası yazıldı; 265 test geçiyor.

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

Ahmet 11 Ekim'de Tailscale bağlantısını henüz onaylamamıştı. Sunucudaki
Claude 11 Ekim'de eklendi; Ahmet girişi Telegram üzerinden yaptı ve bot "giriş
tamam" dedi. Uzaktan yönetim oturumunun açıldığı henüz görülmedi.

Sıradaki işler, öncelik sırasıyla:

1. Karabasan geçmiş ölçümünün (`araclar/analiz.sh`) sunucudaki ilk raporunu
   oku: stratejiler yalnız izinli durumda çalışsaydı sonuç değişir miydi?
   Ahmet dosyayı iletecek. Üçüncü uyum denemesi beş adımda da temiz geçti.
2. Karabasan canlı ölçüm servisi: Binance mumları ve `kayitci` kaydından
   puanı 5 dakikada bir hesaplayıp kaydetsin (`puan.py` hesap kısmı hazır).
   Asıl soru bununla yanıtlanır: stratejiler yalnız "Yeşil" dönemde
   çalışsaydı sonuç artıya döner miydi?
3. Sanal işlemlerin açıldıkları andaki Karabasan durumu ve filtre puanlarıyla
   etiketlenmesi (botların SQLite kayıtları ile Karabasan kaydının birleşimi).
4. 12 aylık geçmiş testi ve raporu (sonucu `user_data/gecmis_test.json`'a
   yazılır; 7. ölçüt bunu okur).
5. Sunucudaki Claude oturumunun (`claude remote-control`) gerçekte açıldığını
   doğrula; takılırsa Ahmet `/gunluk claude` dosyasını iletir.
6. Haftalık Telegram raporu ve 30. gün karar raporu (`karne.sinav_karari`).
7. Sonuç sayfasına Karabasan durumu ve filtre hunisi (strateji ayrıntıları 11 Ekim'de eklendi; ana ekranda
   Karabasan için "henüz canlı ölçülmüyor" yazan bir şerit var, 2. iş bitince gerçek durumla değişecek).

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
üzerinden gerçek girişle çalışması.

Bir ders: hazır motorun çıkış koduna tek başına güvenme. Ayar hatasında
`docker compose run` temiz kodla dönmüş göründü; nedeni bilinmiyor. Çıktıda
beklenen sonucu ara.

Bunlar belgeye göre yazıldı, çalıştırılarak doğrulanmadı:

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
- `claude auth login` ekranının tmux içinde bağlantıyı ve kod sorusunu
  provadaki gibi göstermesi; `claude remote-control`'ün açılış sorularının
  ("Enable Remote Control? (y/n)", "Trust ...? [y/N]") metni ve oturum
  adresini ekrana yazması (`araclar/claude_sunucu.sh` bunlara göre yazıldı).
- `.claude/settings.json` içindeki izin kurallarının yazımı.
- Yeni sonuç sayfası (11 Ekim 2026) yalnız buradaki Chromium'da, telefon ve masaüstü genişliğinde
  denendi: ekran geçişi, halkadaki dilime dokunma, yerinde tazeleme, bağlantı kopunca uyarı, betiksiz dosya
  hali. Ahmet'in telefonundaki tarayıcıda (Safari) ve Telegram'ın dosya görüntüleyicisinde denenmedi.
