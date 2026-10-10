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
| On strateji (S1-S6 ve dört ters yönlü hali) | `karabasan/stratejiler/*.json` | Yazıldı, test edildi; S5 ve S6 gerçek veride henüz sınanmadı |
| Karabasan puanı, durumlar, vetolar | `karabasan/puan.py` | Yazıldı, test edildi |
| Filtre (Elek) | `karabasan/filtre.py` | Yazıldı, test edildi |
| Karne ve sınav karar ölçütleri | `karabasan/karne.py` | Yazıldı, test edildi |
| Bağımsız benzetim | `karabasan/benzetim.py` | Yazıldı, test edildi |
| Dominans ve TOTAL2 kaydedicisi | `karabasan/kayitci.py` | Yazıldı; ağ bağlantısı sunucuda sınanacak |
| Hazır motor bağlantısı | `user_data/strategies/karabasan_stratejileri.py` | Yazıldı; gerçek motorla sunucuda sınanacak |
| On sanal botun yapılandırması | `araclar/yapilandirma_uret.py` | Yazıldı, test edildi |
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

Kod 249 otomatik testten geçiyor. Testler arasında şunlar var: göstergelerin
ve altı stratejinin geleceğe bakmadığı, kâr hedefi ve stop hesabı,
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
5. "Kurulum tamam" mesajı gelince on sanal bot çalışıyordur.

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

Sonuç sayfası her botun işlem sayısını, kazanma ve başabaş oranını, net
sonucunu, en büyük düşüşünü ve sınavın yedi ölçütünün ara durumunu gösterir.

## Telegram komutları

| Komut | Ne yapar |
| --- | --- |
| `/durum` | Genel durum |
| `/botlar` | Her botun sonucu |
| `/sayfa` | Sonuç sayfasını dosya olarak yollar |
| `/gunluk` | On botun son kayıt satırları; `/gunluk s1-spot` tek bot |
| `/uyum` | Uyum denemesi raporu |
| `/olcum` | Karabasan geçmiş ölçümü: stratejilerin sonucu piyasa durumuna göre |
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
`http://karabasan:8081` ile `http://karabasan:8090` arasındadır. Kullanıcı adı
`karabasan`, parola sunucudaki `.env` dosyasındadır. Günlük kullanımda
gerekmez; sonuç sayfası ve Telegram yeterlidir.

## On sanal bot

| Bot | Strateji | Ne yapar | Piyasa | Ekran |
| --- | --- | --- | --- | --- |
| s1-spot | S1 Yükselişte düşüşü al | Yükselen trendde aşırı satımdan dönüşü alır | Spot | 8081 |
| s2-spot | S2 Tepe kırılımını al | Son 4 saatin tepesi hacimle kırılınca alır | Spot | 8082 |
| s3-spot | S3 Yatay piyasada dipten al | Yatay piyasada bandın dibinden dönüşü alır | Spot | 8083 |
| s4-spot | S4 Sert düşüşten dönüşü al | Fiyat gün içi ortalamadan çok uzaklaşınca dönüşü alır | Spot | 8084 |
| s1k-vadeli | S1K Düşüşte yükselişi sat | S1'in tersi: düşen trendde tepkiyi açığa satar | Vadeli, 1 kat | 8085 |
| s2k-vadeli | S2K Dip kırılımını sat | S2'nin tersi: dip hacimle kırılınca açığa satar | Vadeli, 1 kat | 8086 |
| s5-vadeli | S5 Momentum vuruşu (MACD + RSI) | MACD yukarı kesip RSI yükselirken hacimli mumda alır; küçük hedef, hızlı çıkış | Vadeli, 1 kat | 8087 |
| s5k-vadeli | S5K Momentum vuruşu, satış | S5'in tersi | Vadeli, 1 kat | 8088 |
| s6-vadeli | S6 Likidite avı sonrası alım (akıllı para + RSI) | Fiyat son 2 saatin dibinin altına sarkıp yeniden üstünde kapanınca alır | Vadeli, 1 kat | 8089 |
| s6k-vadeli | S6K Likidite avı sonrası satış | S6'nın tersi | Vadeli, 1 kat | 8090 |

Her botun 1.000 USDT sanal bakiyesi vardır, işlem başına 50 USDT kullanır,
aynı anda en fazla 20 pozisyon açar. Tüm emirler piyasa emridir ve karşı
taraftan fiyatlanır; bu, sonuçları olduğundan iyi göstermemek için seçilmiş
kötümser bir varsayımdır.

S5 ve S6, 11 Ekim 2026'da eklendi ve S1-S4'ün "vadeli alım" botlarının yerine
geçti. O dört bot spot'taki ikizleriyle aynı işlemleri açıyordu. Yeni
stratejiler vadelide çalışır, çünkü komisyon daha düşüktür ve açığa satış
yalnız orada mümkündür. Vadelide 50 USDT'lik işlem tutarıyla BTC işlem görmez.

S6 "akıllı para" fikirlerinin yalın bir halidir: yalnız likidite avını
(stopların süpürülmesi) ve seviyenin geri alınmasını arar. Emir bloğu ve
fiyat boşluğu (FVG) gibi parçalar yoktur.

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
  (`macd_cizgi`, `macd_sinyal`, `macd_fark` sütunlarını üretir).
- İşlemler: `>`, `<`, `>=`, `<=`, `yukari_keser`, `asagi_keser`.
- Bağlaçlar: `hepsi` (ve), `herhangi` (veya); iç içe yazılabilir.
- Kâr hedefi ve stop fiyat hareketidir: 1.2, fiyat %1,2 lehe gidince kapat demektir.
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
