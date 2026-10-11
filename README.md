# Karabasan Bot

Binance için sık ve küçük kârlı işlem botu. Ne zaman çalışacağına "Karabasan"
adlı piyasa ortamı motoru karar verir. Tasarımın tamamı tasarım raporundadır;
bu depo o raporun koda dökülmüş halidir.

**Şu anki aşama: laboratuvar sürümü.** Bu sürüm yalnız sanal işlem yapar.
Binance API anahtarı istemez, borsaya emir gönderemez.

Her şey telefondan yönetilir: sunucu kendini kurar, her adımı Telegram'dan
bildirir, yeni kodu kendisi alır. Bilgisayar ve terminal gerekmez.

## Bu sürümde ne var

| Parça | Dosya | Durum |
| --- | --- | --- |
| Gösterge blokları | `karabasan/gostergeler.py` | Yazıldı, test edildi |
| Kural dosyası motoru | `karabasan/kural.py` | Yazıldı, test edildi |
| On iki strateji (S1-S6, Smartmoney ve beş ters yönlü hal) | `karabasan/stratejiler/*.json` | Yazıldı, test edildi; Smartmoney gerçek veride henüz sınanmadı |
| Karabasan puanı, durumlar, vetolar | `karabasan/puan.py` | Yazıldı, test edildi |
| Filtre (Elek) | `karabasan/filtre.py` | Yazıldı, test edildi |
| Karne ve sınav karar ölçütleri | `karabasan/karne.py` | Yazıldı, test edildi |
| Bağımsız benzetim | `karabasan/benzetim.py` | Yazıldı, test edildi |
| Dominans ve TOTAL2 kaydedicisi | `karabasan/kayitci.py` | Yazıldı; ağ bağlantısı sunucuda sınanacak |
| Stop sonrası izleme ve dersler | `karabasan/stop_sonrasi.py` | Yazıldı, sahte fiyat sunucusuyla test edildi; gerçek Binance verisiyle sunucuda ilk kez çalışacak |
| Hazır motor bağlantısı | `user_data/strategies/karabasan_stratejileri.py` | Yazıldı; ilk on bot için sunucuda doğrulandı. Günlük mumların motordan alınması (Smartmoney) sunucuda ilk kez çalışacak |
| Sanal botların yapılandırması | `araclar/yapilandirma_uret.py` | Yazıldı, test edildi |
| Sonuç özeti ve Türkçe sonuç sayfası | `karabasan/sonuc.py`, `sayfa.py`, `panel.py` | Yazıldı, sahte kayıtlarla test edildi; gerçek kayıtlarla sunucuda sınanacak |
| Telegram habercisi ve komutlar | `karabasan/haberci.py` | Yazıldı, taklit Telegram ile test edildi |
| Kurulum ve uyum denemesi | `kurulum/sunucu_blogu.sh`, `kur.sh`, `araclar/uyum_denemesi.sh` | Yazıldı, taklit komutlarla prova edildi; sunucuda ilk kez çalışacak |
| Kendiliğinden güncelleme, özel ağ | `araclar/oto_guncelle.sh`, `araclar/ozel_ag.sh` | Yazıldı, taklit komutlarla prova edildi |
| Sunucudaki Claude | `araclar/claude_sunucu.sh` | Yazıldı, taklit komutlarla prova edildi; gerçek girişle sunucuda sınanacak |

Henüz yok (sıradaki parçalar): Karabasan'ın canlı ölçüm servisi, sanal
işlemlerin Karabasan durumuyla etiketlenmesi, haftalık rapor ve 30. gün karar
raporu, 12 aylık geçmiş testi raporu. Gerçek para ile ilgili hiçbir kod (emir
yürütücü, risk yöneticisi) bu aşamada yoktur.

## Dürüst not: nerede sınandı, nerede sınanmadı

Kod 354 otomatik testten geçiyor. Testler arasında şunlar var: göstergelerin
ve stratejilerin geleceğe bakmadığı, kâr hedefi ve stop hesabı,
Karabasan'ın "açılması yavaş, kapanması hızlı" davranışı, veto süreleri,
filtrenin elenme nedenleri, sınavın yedi karar ölçütü, sonuç sayfasının sahte
kayıt dosyalarından doğru sayıları çıkarması, Telegram habercisinin yalnız
sahibini dinlemesi.

Kodun yazıldığı ortamdan paket deposuna, Docker'a ve Binance'e erişim yoktu.
Bu yüzden şunlar ancak sunucuda sınanabilir:

1. Hazır motorun (Freqtrade) strateji sınıflarımızı yükleyip çalıştırması.
2. Kurulum betiğinin Ubuntu'da baştan sona çalışması. Betik burada yalnız
   taklit komutlarla (sahte `docker`, `tailscale`, `apt-get`) prova edildi.
3. Binance, CoinGecko ve Telegram ile gerçek bağlantı.
4. Sonuç sayfasının hazır motorun gerçek kayıt dosyalarını okuması.

Sunucu 10 Ekim 2026'da kuruldu; ikinci ve üçüncü madde doğrulandı, on sanal
bot çalışıyor. İlk madde hâlâ açık: ilk uyum denemesi hazır motorun geçmiş
testini bir ayar hatası yüzünden çalıştıramadı ve bunu fark etmeyip "geçti"
yazdı. Denetim düzeltildi; karşılaştırma yeniden çalıştırılacak.

Kurulumun 9. adımı olan **uyum denemesi** ilk madde içindir: botları
başlatmadan önce her stratejiyi gerçek Binance verisinde hazır motorla
geçmiş testinden geçirir, aynı veride bizim bağımsız benzetimimizi de
çalıştırır ve sonucu bir dosyaya yazar. Bir adım kalırsa botlar başlamaz;
rapor Telegram'dan gelir.

## İlk kurulum (telefondan)

Hazırlık: Telegram'da `@BotFather` ile bir bot aç ve verdiği kodu not et;
telefona Tailscale uygulamasını kurup giriş yap.

1. Hetzner'de sunucu oluştur: Ubuntu 24.04, CX33 (4 çekirdek, 8 GB), konum
   Almanya ya da Finlandiya, SSH anahtarı yok. "Cloud config" kutusuna
   [`kurulum/sunucu_blogu.sh`](kurulum/sunucu_blogu.sh) dosyasının içeriğini
   yapıştır ve `BURAYA_TELEGRAM_KODU` yazısını botun koduyla değiştir.
2. Telegram'da botunu aç, "Başlat"a bas.
3. Sunucu her adımı Telegram'a yazar. Bir Tailscale bağlantısı yollar; ona
   dokunup onayla.
4. Uyum denemesi raporu dosya olarak gelir (10-20 dakika sürer).
5. "Kurulum tamam" mesajı gelince sanal botlar çalışıyordur.

Kurulum on adımdır ve 30-40 dakika sürer. Bir adımda durursa bot kurulum
kaydını dosya olarak yollar; düzeltme ana dala işlenince sunucu 5 dakika
içinde kendiliğinden yeniden dener.

Kurulum bitince botlar bir **ısınma haftasına** girer: sanal işlem yaparlar
ama 30 günlük sınavın saati henüz başlamaz. Bu hafta, tesisatın gerçek
veride doğru çalıştığını görmek içindir. Sınavın saatini Telegram'da
`/sinav_baslat` komutu başlatır; saat bir kez başlar, geri alınamaz.

## Sonuçlar nerede

| Nerede | Ne |
| --- | --- |
| Telegram, `/durum` | Kaç bot çalışıyor, kaç işlem kapandı, toplam sanal sonuç |
| Telegram, her sabah 09:00 | Günlük özet (Bükreş saati) |
| `http://karabasan:8080` | Sonuç sayfası; yalnız Tailscale açıkken açılır |
| Telegram, `/sayfa` | Aynı sayfa, dosya olarak |

Sonuç sayfasında beş ekran var; telefonda altta, bilgisayarda üstte duran
şeritten geçilir:

- **Ana ekran:** ortada bir gösterge halkası. Dış halkadaki her dilim bir bottur
  (yeşil artıda, kırmızı ekside, sarı kesikli "ses yok"); iç halka sınavın 30
  günüdür; ortadaki sayı toplam sanal sonuçtur. Altında görevdeki bot sayısı,
  son 24 saat, toplam sonucun seyri ve botların sıralaması durur.
- **Botlar:** her stratejinin ne yaptığı düz Türkçeyle, kâr hedefi, stop, en
  uzun süre, işlem sayısı, kazanma ve başabaş oranı, net sonuç, çıkış nedenleri.
- **İşlemler:** açık pozisyonlar ve son kapanan 30 işlem. Stop olan işlemin
  altında, izlendikten sonra, "stop şu kadar geniş olsaydı ne olurdu" yazar.
- **Dersler:** stop sonrası izleme. Stop olan her işlem kendi süresi dolana
  kadar izlenir; stop 1,5 / 2 / 3 kat geniş olsaydı toplam sonucun ne kadar
  değişeceği bot başına gösterilir. Karar ("stop dar görünüyor", "stop
  yerinde", "kararsız") en az 30 stop birikince çıkar ve ders olarak
  kaydedilir. Karar hiçbir ayarı değiştirmez; "stop dar" çıkarsa geniş stoplu
  hal ayrı bir sanal botla denenir.
- **Sınav:** 30 günlük cetvel, yedi ölçüt ve her botun ölçütlerdeki durumu.

Sayfa dakikada bir kendini tazeler; sunucuya ulaşamazsa bunu üstte sarı bir
şeritle söyler. Karabasan piyasa durumu henüz canlı ölçülmediği için ana
ekranda "henüz canlı ölçülmüyor" yazar.

## Telegram komutları

| Komut | Ne yapar |
| --- | --- |
| `/durum` | Genel durum |
| `/botlar` | Her botun sonucu |
| `/sayfa` | Sonuç sayfasını dosya olarak yollar |
| `/gunluk` | Botların son kayıt satırları; `/gunluk s1-vadeli` tek bot |
| `/uyum` | Uyum denemesi raporu |
| `/olcum` | Karabasan geçmiş ölçümü: stratejilerin sonucu piyasa durumuna ve stop genişliğine göre |
| `/yillik` | 12 aylık geçmiş testi: her bot son bir yılda ne yapardı, dört çeyrek ayrı |
| `/defter` | Emir defteri denemesi: BTC/USDT tahminleri ve sanal işlemlerin özeti, ayrıca tek sayfalık dosya |
| `/dersler` | Stop sonrası izleme: stop daha geniş olsaydı ne olurdu, bot başına |
| `/kurulum` | Kurulum kaydı |
| `/sinav_baslat` | 30 günlük sınavın saatini başlatır (onay ister) |
| `/claude` | Sunucudaki Claude'un durumu; giriş yapılmadıysa giriş bağlantısı ister |
| `/claude KOD` | Giriş sayfasında çıkan tek kullanımlık kodu sunucuya iletir |
| `/yardim` | Komut listesi |

Bot yalnız "Başlat"a ilk basan kişiyi dinler. Hiçbir komut borsaya emir
göndermez ya da botların ayarını değiştirmez.

## Sunucudaki Claude

Kurulum, Claude Code'u da sunucuya kurar. Bir kerelik giriş telefondan
yapılır: bot bir bağlantı yollar, Claude hesabıyla girilir, sayfada çıkan kod
bota `/claude KOD` diye yazılır. Sonra telefondaki Claude uygulamasının Code
bölümünde "Karabasan sunucu" adlı oturum görünür; orada yazılanlar sunucunun
içinde çalışır. Kayıtları okumak gibi işler onaysız, sunucuda bir şeyi
değiştiren komutlar onayla çalışır. Claude Pro ya da Max aboneliği gerekir.

Bu oturum sanal sınav aşaması içindir. Gerçek paraya geçilirse kapatılır ya
da kısıtlanır.

## Güncelleme

Sunucu 5 dakikada bir bu deponun `main` dalını denetler. Yeni kod varsa alır,
yalnız değişenle ilgili servisleri yeniden başlatır ve Telegram'dan haber
verir. Sanal işlem kayıtları silinmez. Hazır motorun sürümü kendiliğinden
yenilenmez; sınav boyunca aynı kalır.

## Komisyon oranları

Başlangıç değerleri `karabasan/botlar.py` içindedir:

```
"komisyon_yuzde": { "spot": 0.075, "vadeli": 0.05 }
```

Değerler yüzdedir ve taraf başınadır: 0.075, %0,075 demektir. Sınavda tüm
emirler piyasa emri olduğu için alıcı (taker) oranı kullanılır. Hesabındaki
oranlar farklıysa Claude'a yaz; değeri depoda o günceller, sunucu kendisi alır.

Bot ekranları (hazır motorun kendi İngilizce ekranı), Tailscale açıkken
`http://karabasan:8081` ile `http://karabasan:8085` arasındadır. Kullanıcı adı
`karabasan`, parola sunucudaki `.env` dosyasındadır. Günlük kullanımda
gerekmez; sonuç sayfası ve Telegram yeterlidir.

## Sanal botlar

| Bot | Strateji | Ne yapar | Piyasa | Ekran |
| --- | --- | --- | --- | --- |
| sm-vadeli | SM Smartmoney: geri çekilme sonrası yapı kırılımıyla alım | Günlük trend ve 1 saatlik yapı yukarıyken, 15 dakikalıkta geri çekilmeden sonra 5 dakikalık yapı yukarı kırılınca alır | Vadeli, 1 kat | 8081 |
| smk-vadeli | SMK Smartmoney: tepki sonrası yapı kırılımıyla satış | SM'nin tersi | Vadeli, 1 kat | 8082 |
| smd-vadeli | SMD Smartmoney + uyumsuzluk + emir defteri: alım | SM'nin bütün koşulları, son 1 saatte en az bir göstergede boğa uyumsuzluğu, girişte emir defterinde alıcılar belirgin kalabalık | Vadeli, 1 kat | 8083 |
| smdk-vadeli | SMDK Smartmoney + uyumsuzluk + emir defteri: satış | SMD'nin tersi | Vadeli, 1 kat | 8084 |
| sniper5-vadeli | SNIPER Sniper: dip sonrası CHoCH + FVG ile kısa vuruş | 5 dakikalıkta dip görülüp yapı yukarı dönünce, hızlı alım izi (FVG), momentum, RSI ve hacim onayıyla alır; %1,2 kâr, %1,5 stop, en çok 3 saat | Vadeli, 1 kat | 8085 |

**12 Ekim 2026'dan beri yalnız Smartmoney çalışır (Ahmet'in isteğiyle).** Aynı
gün 12 aylık geçmiş testi (11.10.2025–11.10.2026) on iki botun hepsini ekside
gösterdi; hiçbiri dört çeyreğin üçünde artıda değildi. Öbür on stratejinin
kural dosyaları kayıt için `karabasan/stratejiler/emekli/` altında durur (neden
çıkarıldıkları oradaki BENIOKU.md'de). Smartmoney de o testte eksideydi
(SM −30,17, SMK −26,69 USDT); en az kaybedenler onlardı.

Smartmoney botlarında çıkış: kâr hedefi %0,8, stop %3, 1 kat vadeli. Komisyon gidiş-dönüş %0,1
olduğu için kazanan işlem net yaklaşık +%0,7, stop olan işlem −%3,1 getirir;
başa baş için işlemlerin yaklaşık %82'si kazanmalıdır. Vadelide 50 USDT'lik
işlem tutarıyla BTC işlem görmez.

Her botun 1.000 USDT sanal bakiyesi vardır, işlem başına 50 USDT kullanır,
aynı anda en fazla 20 pozisyon açar. Tüm emirler piyasa emridir ve karşı
taraftan fiyatlanır; bu, sonuçları olduğundan iyi göstermemek için seçilmiş
kötümser bir varsayımdır.

### Smartmoney + uyumsuzluk + emir defteri (SMD ve SMDK)

12 Ekim 2026'da Ahmet'in isteğiyle eklendi; geçmiş testi yapılmadan, ileriye
dönük izlenmek üzere. Üç parçayı birleştirir:

1. **Smartmoney'nin dört katmanı aynen.** Günlük trend, 1 saatlik yapı,
   15 dakikalıkta geri çekilme, 5 dakikalıkta hacimli yapı kırılımı.
2. **Uyumsuzluk.** Ahmet'in gönderdiği TradingView göstergesinin (LonesomeTheBlue,
   "Divergence for Many Indicators v4") fikri; kod kopyalanmadı, Python'da baştan
   yazıldı (`karabasan/gostergeler.py`, `uyumsuzluk`). On gösterge: MACD, MACD
   histogramı, RSI, stokastik, CCI, momentum, OBV, hacim ağırlıklı MACD, Chaikin
   para akışı, para akışı endeksi. Alımda son 12 mumda (1 saat) en az birinde boğa
   uyumsuzluğu aranır. Örnek: fiyat yeni dip yaparken gösterge yeni dip yapmıyor.
   Ya da fiyat daha yüksek dip yaparken gösterge daha düşük dip yapıyor; buna
   "gizli" uyumsuzluk denir ve trendin sürdüğünü gösterir. Dip ve tepeler her iki
   yanında 5 mum olan noktalardır; bir nokta ancak 5 mum sonra kesinleşir. Geleceğe
   bakılmaz.
3. **Girişte emir defteri onayı.** Sinyal gelince motor emir defterini okur. Alımda
   en iyi 20 kademede alıcılar satıcılardan en az %22 kalabalık değilse (dengesizlik
   en az 0,1) işlem açılmaz. Defterin tamamı ve mikro fiyat da aynı yönü göstermelidir.
   Açığa satışta tersi. Geçmiş testinde geçmişin defteri olmadığı için bu adım
   orada atlanır.

Çıkış Smartmoney ile aynı: hedef %0,8, stop %3, en uzun 4 saat. Kazandıracağı
bilinmiyor; amaç, defter ve uyumsuzluk onayının Smartmoney'nin sonucunu
değiştirip değiştirmediğini canlıda yan yana görmek (SM ile SMD, SMK ile SMDK).

### Sniper (SNIPER)

12 Ekim 2026'da Ahmet'in isteğiyle. Amaç: 5 / 15 dakikalık grafikte dip görmüş
bir coinde, düşüş sonra sürse bile arada %1–1,5'lik kısa bir vuruş yapıp çıkmak.
İlk hali (günlük trend takibi, haftalarca açık kalan işlemler) Ahmet'in amacına
uymadığı için aynı gün çıkarıldı (`stratejiler/emekli/SNIPERG.json`).

Altı koşul birlikte aranır (yalnız alım):

1. **Dip görülmüş:** son 3 saatte 15 dakikalık RSI 35'in altına inmiş.
2. **Yapı dönmüş (CHoCH):** son 1 saatte 5 dakikalıkta düşüş yapısının ilk yukarı
   kırılımı olmuş ve yapı hâlâ yukarı. Salınım uzunluğu 3 mum.
3. **Hızlı alım izi (FVG):** son 30 dakikada bir boğa FVG'si oluşmuş, ya da fiyat
   açık bir boğa FVG'sine geri çekilip üstünde kapanmış. FVG ("fair value gap",
   adil değer boşluğu): üç mumluk hızlı yükselişte birinci mumun tepesi ile üçüncü
   mumun dibi arasında hiç işlem görmeden geçilen fiyat aralığı. En az %0,05
   boyunda olmalı; fiyat altında kapanınca ya da 3 saat dolunca geçersiz.
4. **Momentum:** MACD histogramı sıfırın üstünde.
5. **RSI:** 5 dakikalık RSI 50 ile 70 arasında (yukarı dönmüş, şişmemiş).
6. **Hacim:** son 15 dakikada bir mumun hacmi 20 mumluk ortalamanın 1,5 katından fazla.

Çıkış: %1,2 kâr, %1,5 stop ya da en çok 3 saat; stoptan sonra aynı coine 30 dakika
girilmez. Komisyon gidiş-dönüş %0,1 olduğu için kazanan işlem net ~%1,1, kaybeden
~−%1,6 getirir; başa baş için işlemlerin yaklaşık %59'u kazanmalıdır.

Kavramlar (CHoCH, BOS, FVG) yaygın "akıllı para" kavramlarının bu depo için
yazılmış bağımsız uygulamasıdır (`karabasan/gostergeler.py`: `piyasa_yapisi`,
`fvg`). Yapay rastgele veride coin başına günde yaklaşık 1 işlem açtı ve komisyon
kadar kaybetti (%52 kazanma); yani kendiliğinden kâr üretmiyor, gerçek piyasada
bir kenarı olup olmadığı canlıda ve 12 aylık testte görülecek. Garantiye yakın
işlem diye bir şey yoktur: hiçbir koşul birleşimi her seferinde kazandırmaz.

### Emir defteri denemesi (BTC/USDT vadeli)

12 Ekim 2026'da Ahmet'in fikriyle eklendi. Botlardan ve stratejilerden ayrı
çalışan bir servistir (`defter`). Yalnız ileriye dönük çalışır, çünkü geçmiş
emir defteri verisi elde yok.

- Her saniye Binance'in herkese açık emir defterini okur: en iyi 100 alış ve
  100 satış kademesi.
- Defterden alış / satış dengesizliği, en büyük emirlerin (duvarların)
  uzaklığı ve alış-satış makası çıkarılır. Son fiyat hareketi, 1 dakikalık
  mumlardan RSI, hacim ve son bir saatin dibi / tepesi (destek / direnç) eklenir.
- Bu sayılardan fiyatın 5 ve 15 dakika sonra yüzde kaç değişeceği tahmin
  edilir. Tahmin, servisin kendi kaydından öğrenen basit bir modelle yapılır.
  Model en az 3 saatlik kayıt birikmeden tahmin vermez.
- Tahmin edilen hareket %0,15'ten büyükse (gidiş-dönüş komisyon %0,10 ve pay)
  sanal pozisyon açılır. Alım ya da açığa satış; 1 kat; 100 USDT. Hedef
  tahmin edilen fiyattır, stop aynı uzaklıkta ters yöndedir. Süre dolunca o
  anki fiyattan kapanır. Her ufukta aynı anda tek işlem açık olur.
- Başarılı işlem: komisyon düşüldükten sonra artıda kapanan. 1 kat kaldıraçta
  tasfiye (likidasyon) için fiyatın yaklaşık %100 ters gitmesi gerekir. Bu
  yüzden her işlem için "en kötü an" da kaydedilir: fiyat en çok ne kadar
  ters gitti.

Sonuçlar sonuç sayfasında `/defter` adresinde ve Telegram'da `/defter` ile
görülür. Sayfa, modelin "fiyat değişmez" tahmininden iyi olup olmadığını da
gösterir. Kayıt: `user_data/kayit/defter.sqlite`, saniyelik kayıtlar 8 gün
saklanır. Borsaya hiçbir emir gönderilmez, anahtar kullanılmaz.

### Smartmoney (SM ve SMK)

11 Ekim 2026'da, Ahmet'in gönderdiği "Smart Money Concepts" göstergesindeki
kavramlardan yola çıkılarak eklendi (iki bot). Göstergenin kodu kopyalanmadı (lisansı ticari kullanıma izin vermiyor);
aynı kavramlar `karabasan/gostergeler.py` içindeki `piyasa_yapisi` ile baştan
yazıldı. Dört katman birlikte aranır (alım hali; satış hali her birinin tersidir):

| Katman | Dilim | Koşul |
| --- | --- | --- |
| Günlük trend | 1 gün | Son kapanan günün kapanışı, 20 günlük üstel ortalamanın üstünde |
| Yapı | 1 saat | Son yapı kırılımı yukarı (BOS ya da CHoCH); RSI 70'in altında |
| Geri çekilme | 15 dakika | Son bir saatte fiyat aralığın alt yarısına ("indirimli bölge") inmiş ya da bir alım bloğuna dokunmuş |
| Tetik | 5 dakika | Bu mumda yapı yukarı kırılıyor; RSI 50 ile 70 arasında; hacim son 20 mumun ortalamasının 1,2 katından fazla |

Çıkış: kâr hedefi %0,8, stop %3 (12 Ekim 2026'dan beri bütün botlarda aynı), en uzun süre 4 saat; stop sonrası aynı
coine 2 saat bekleme. Vadeli komisyonuyla zarar etmemek için gereken kazanma
oranı %45.

Kavramlar: bir mumun yükseği sonraki 5 mumun hepsinden yüksekse o mum bir
salınım tepesidir (dip bunun tersi). Fiyat son tepenin üstünde kapanırsa yapı
yukarı kırılmıştır. Alım bloğu, kırılan tepe ile kırılım arasındaki en düşük
mumun aralığıdır; fiyat altına sarkarsa ya da 100 mumdan eskiyse geçersiz olur.
Göstergedeki fiyat boşlukları (FVG) ve eşit tepe / dip işaretleri kullanılmadı.

Günlük mumlar 5 dakikalık mumlardan toplanamaz (20 günlük ortalama için
canlıda alınabilenden çok fazla mum gerekir); bu yüzden kural dosyasında
`"borsa_dilimleri": ["1d"]` yazar ve motor günlük mumları borsadan ayrıca
ister. Günlük veri gelmezse o paritede sinyal üretilmez.

Dürüst not: bu strateji yalnız yapay (rastgele üretilmiş) veride denendi;
orada, beklendiği gibi, komisyon kadar kaybediyor. Gerçek verideki ilk sonucu
uyum denemesi ve Karabasan geçmiş ölçümü raporlarıyla gelecek. Çok koşul bir
arada arandığı için öbür botlardan daha az işlem açması beklenir.

## Strateji dosyası

Bir strateji kod değil, `karabasan/stratejiler/` klasöründe bir JSON
dosyasıdır. Örnek (`S1.json`, kısaltılmış):

```
{
  "kod": "S1",
  "ad": "Yükselişte düşüşü al",
  "yon": "alim",
  "zaman_dilimi": "5m",
  "ust_zaman_dilimi": "1h",
  "gostergeler": {
    "ema50_1s": {"tur": "ema", "kaynak": "kapanis", "periyot": 50, "dilim": "ust"},
    "rsi14": {"tur": "rsi", "periyot": 14}
  },
  "giris": {"hepsi": [
    {"sol": "rsi14", "islem": "yukari_keser", "sag": 30},
    {"sol": "kapanis", "islem": ">", "sag": "acilis"}
  ]},
  "cikis": {"kar_hedefi_yuzde": 1.2, "zarar_durdur_yuzde": 1.0, "sure_asimi_dakika": 240},
  "izinli_durumlar": ["YESIL"],
  "bekleme_dakika": 240
}
```

- `yon`: `alim` ya da `aciga_satis` (açığa satış yalnız vadelide).
- Gösterge türleri: `ema`, `sma`, `rsi`, `bollinger`, `atr_yuzde`, `vwap`,
  `en_yuksek`, `en_dusuk`, `hacim_ort`, `degisim_yuzde`, `macd`
  (`macd_cizgi`, `macd_sinyal`, `macd_fark` sütunlarını üretir), `yapi`
  (piyasa yapısı; `periyot` salınım uzunluğudur ve `<ad>_yon`, `_kirilim`,
  `_donus`, `_tepe`, `_dip`, `_denge`, `_blok_ust`, `_blok_alt`, `_sblok_ust`,
  `_sblok_alt` sütunlarını üretir).
- Bir göstergenin `dilim` alanı `"ust"` (kuralın `ust_zaman_dilimi`) ya da
  doğrudan bir dilim (`"15m"`, `"1h"`, `"1d"`) olabilir; böylece tek kural
  birden çok dilim kullanır. Üst dilimin değeri ancak o mum kapanınca kullanılır.
- `borsa_dilimleri`: mumları 5 dakikalıklardan toplanmayıp borsadan ayrıca
  istenen dilimler (örnek: `["1d"]`). Günlük göstergeler için zorunludur.
- İşlemler: `>`, `<`, `>=`, `<=`, `yukari_keser`, `asagi_keser`.
- Bağlaçlar: `hepsi` (ve), `herhangi` (veya); iç içe yazılabilir.
- Kâr hedefi ve stop fiyat hareketidir: 0.8, fiyat %0,8 lehe gidince kapat demektir.
- Dosya hatalıysa bot başlamaz ve hatayı Türkçe söyler. Stop %10'dan,
  kâr hedefi %20'den büyük yazılamaz; bu sınırlar yazım hatalarına karşıdır.

Yeni strateji eklemek şu an için dosya eklemek ve bir bot tanımlamaktır;
bunu Claude'a tarif etmen yeterlidir. Panelden form ile ekleme sıradaki
parçalardandır.

## Testler

Yalnız Python, numpy ve pandas ister:

```
python3 -m unittest discover -s testler -t .
```

## Güvenlik

- Bu sürümde Binance API anahtarı yoktur ve gerekmez.
- Depo herkese açıktır; içinde parola, anahtar ya da sunucu adresi yoktur.
  `.env` (bot ekranlarının parolası) ve `telegram.env` (Telegram kodu) yalnız
  sunucuda durur, yalnız root okur.
- Sunucu internete hiçbir kapı açmaz. Giriş anahtarı tanımlı değilse SSH de
  kapalıdır. Sonuç sayfası ve bot ekranları yalnız sunucunun kendisini
  (`127.0.0.1`) ve Tailscale özel ağ adresini dinler.
- Telegram botu yalnız sahibinin sohbetini dinler ve yalnız okuma komutları
  tanır. Telegram kodunu yalnız haberci servisi görür; botlar görmez.
- Sunucu, bu deponun `main` dalına işlenen kodu kendiliğinden çalıştırır.
  Bu yüzden GitHub hesabının güvenliği sunucunun güvenliğidir: hesapta iki
  adımlı doğrulama açık olmalıdır. Gerçek paraya geçilirse kendiliğinden
  güncelleme yeniden değerlendirilir.
