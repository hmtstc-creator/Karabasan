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
| `karabasan/gostergeler.py` | Gösterge blokları (EMA, RSI, MACD, Bollinger, ATR, VWAP, üst dilim hizalama) ve `piyasa_yapisi` (salınımlar, yapı kırılımı BOS / CHoCH, denge, emir blokları) |
| `karabasan/kural.py` | Kural dosyası (JSON) okuma, doğrulama, sinyal üretme. Bir gösterge `dilim` ile istediği üst dilimde hesaplanır (`"ust"`, `"15m"`, `"1h"`, `"1d"`). `borsa_dilimleri` içindeki dilimlerin mumları taban mumlardan toplanmaz, `ek_veri` ile dışarıdan verilir (motor, araçlar); boş tablo "veri yok, sinyal de yok" demektir |
| `karabasan/stratejiler/*.json` | On iki strateji: S1–S6 ve SM (alım), S1K, S2K, S5K, S6K ve SMK (açığa satış). Her birinin `ad` alanı ne yaptığını söyleyen düz addır; sayfada ve Telegram'da o görünür. SM / SMK'nın adı Ahmet'in isteğiyle "Smartmoney" diye başlar |
| `karabasan/puan.py` | Karabasan puanı, durum makinesi, vetolar |
| `karabasan/filtre.py` | Filtre (Elek): dört katman, elenme nedenleri |
| `karabasan/karne.py` | İşlem ölçümleri ve 30. günün yedi karar ölçütü |
| `karabasan/benzetim.py` | Bağımsız, kötümser mum bazlı benzetim |
| `karabasan/botlar.py` | On iki sanal botun listesi (4 spot alım, 8 vadeli), komisyon başlangıç değerleri. Uyum denemesi ve analiz bot listesini ve indirilecek ek dilimleri (`ek_dilimler`) buradan okur. Yeni bot listenin sonuna eklenir ki öncekilerin kapısı ve açılış sırası değişmesin |
| `karabasan/kayitci.py` | BTC dominansı ve TOTAL2'yi 10 dakikada bir kaydeder; aynı döngüde stop sonrası izleme turunu çalıştırır |
| `karabasan/stop_sonrasi.py` | Stop sonrası izleme: stop olan işlemi kendi süresi dolana kadar izler, stop 1,5 / 2 / 3 kat geniş olsaydı ne olurdu hesaplar, bot başına karar çıkarır (yetersiz, dar, yerinde, kararsız), karar değişince ders yazar. Mumlar Binance'in herkese açık, anahtarsız fiyat verisinden gelir. Çıktı: `user_data/kayit/stop_sonrasi.json`. **Hiçbir ayarı değiştirmez** |
| `karabasan/gecmis_olcum.py` | Karabasan puanını geçmiş mumlardan geriye dönük hesaplar (yaklaşık: dominans ve TOTAL2 yerine altcoin vekili); işlemleri açıldıkları andaki durumla etiketler |
| `karabasan/sonuc.py` | Botların SQLite kayıtlarını salt okunur okuyup özet çıkarır; dönem (ısınma, sınav, bitti) |
| `karabasan/sayfa.py`, `karabasan/panel.py` | Türkçe sonuç sayfası ve sunucusu (8080; `/`, `/veri.json`, `/saglik`). Beş ekran: ana ekran (gösterge halkası), botlar, işlemler, dersler (stop sonrası izleme), sınav; ekran listesi `sayfa.EKRANLAR`'dadır, biçim ve betik oradan üretilir. Sunucudan açılan hali tek bir satır içi betik taşır (ekran geçişi, dakikada bir yerinde tazeleme); `panel.py` izin başlığını (CSP) o betiğin özetinden üretir. Telegram'ın `/sayfa` ile yolladığı dosya betiksizdir, ekranlar alt alta görünür |
| `karabasan/haberci.py` | Telegram: kurulum bildirimleri, günlük özet, susan bot uyarısı, yeni ders bildirimi, komutlar (`/dersler` dahil) |
| `user_data/strategies/karabasan_stratejileri.py` | Freqtrade bağlantı katmanı. Kural `borsa_dilimleri` istiyorsa o mumları motordan ister (`informative_pairs`, `dp.get_pair_dataframe`) ve kural motoruna aktarır; veri gelmezse boş tablo verir ve kayda bir kez yazar |
| `araclar/yapilandirma_uret.py` | Bot yapılandırmalarını ve `docker-compose.yml`'i üretir |
| `araclar/uyum_denemesi.sh`, `araclar/karsilastir.py` | Sunucudaki uyum denemesi |
| `karabasan/eslestirme.py`, `araclar/islem_eslestir.py` | Uyum denemesinin son bölümü: motorun işlem listesini (`--export trades`, `user_data/backtest_results/`) benzetimle işlem işlem eşleştirir; yalnız bilgi verir, denemenin geçip kalmasını etkilemez |
| `araclar/analiz.sh`, `araclar/karabasan_gecmis.py` | Sunucudaki tek seferlik ölçüm: 80 günlük veri indirir, stratejilerin sonucunu Karabasan durumuna göre ayırır ve stop genişliğini sınar (aynı sinyaller, stop 1,5 / 2 / 3 kat; dönemin iki yarısı ayrı). `kur.sh` içinde `ANALIZ_SURUMU`; Telegram'da `/olcum` |
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

Laboratuvar sürümünün 1. ve 2. parçası yazıldı; 354 test geçiyor.

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
- On iki botun belleği ölçülmedi (sunucu 8 GB). `kur.sh` her çalışmanın
  sonunda `free -m` çıktısını kurulum kaydına yazar; sunucudaki Claude
  `docker stats --no-stream` ile bakabilir. Bellek yetmezse botlar yeniden
  başlayıp durur ve "susan bot" uyarısı gelir; o zaman bot sayısını azalt.
- `ozel_ag.sh` artık adres değişmese de çalışmayan köprüleri açar; yoksa
  sonradan eklenen botların kapıları (8091, 8092) özel ağa taşınmazdı.
- Haberci, açılışından sonraki yarım saat boyunca hiç kayıt yazmamış botu
  "susmuş" saymaz. Yoksa listeye bot eklenen her güncellemede, yeni bot
  sırası gelip açılana kadar (8-10 dakika) Ahmet'e yanlış alarm giderdi.

Sıradaki işler, öncelik sırasıyla:

0. Altıncı uyum denemesi ve dördüncü geçmiş ölçüm raporlarında SM / SMK'ya
   bak: motor günlük veriyi aldı mı, işlem sayıları benzetimle tutuyor mu,
   ilk gerçek sonuç ne? Sonucu Ahmet'e rakamla ve "tek dönem" uyarısıyla söyle.

1. Karabasan canlı ölçüm servisi: Binance mumları ve `kayitci` kaydından
   puanı 5 dakikada bir hesaplayıp kaydetsin (`puan.py` hesap kısmı hazır).
   Geçmiş ölçüm (yaklaşık) süzgecin hiçbir stratejiyi artıya çevirmediğini
   söyledi; canlı ölçüm bunu gerçek dominans ve TOTAL2 verisiyle sınar.
2. Sanal işlemlerin açıldıkları andaki Karabasan durumu ve filtre puanlarıyla
   etiketlenmesi (botların SQLite kayıtları ile Karabasan kaydının birleşimi).
3. 12 aylık geçmiş testi ve raporu (sonucu `user_data/gecmis_test.json`'a
   yazılır; 7. ölçüt bunu okur). S3 / S4'ün Kırmızı'da kazanması burada da
   görülüyor mu, bak.
4. Beşinci uyum denemesinin eşleştirme bölümünü oku (sunucudaki Claude
   okuyup iletebilir): açığa satıştaki %10 fazla işlemin nedeni benzetimde mi,
   motorda mı? Benzetimde bir hata çıkarsa düzelt; motorun bilinen bir
   davranışıysa benzetime ekle ya da burada not et.
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
- On iki botun 8 GB bellekte rahat çalışması.

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
