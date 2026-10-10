# Karabasan Bot

Binance için sık ve küçük kârlı işlem botu. Ne zaman çalışacağına "Karabasan"
adlı piyasa ortamı motoru karar verir. Tasarımın tamamı tasarım raporundadır;
bu depo o raporun koda dökülmüş halidir.

**Şu anki aşama: laboratuvar sürümü, 1. parça.** Bu sürüm yalnız sanal işlem
yapar. Binance API anahtarı istemez, borsaya emir gönderemez.

## Bu sürümde ne var

| Parça | Dosya | Durum |
| --- | --- | --- |
| Gösterge blokları | `karabasan/gostergeler.py` | Yazıldı, test edildi |
| Kural dosyası motoru | `karabasan/kural.py` | Yazıldı, test edildi |
| Altı strateji (S1-S4, S1K, S2K) | `karabasan/stratejiler/*.json` | Yazıldı, test edildi |
| Karabasan puanı, durumlar, vetolar | `karabasan/puan.py` | Yazıldı, test edildi |
| Filtre (Elek) | `karabasan/filtre.py` | Yazıldı, test edildi |
| Karne ve sınav karar ölçütleri | `karabasan/karne.py` | Yazıldı, test edildi |
| Bağımsız benzetim | `karabasan/benzetim.py` | Yazıldı, test edildi |
| Dominans ve TOTAL2 kaydedicisi | `karabasan/kayitci.py` | Yazıldı; ağ bağlantısı sunucuda sınanacak |
| Hazır motor bağlantısı | `user_data/strategies/karabasan_stratejileri.py` | Yazıldı; gerçek motorla sunucuda sınanacak |
| On sanal botun yapılandırması | `araclar/yapilandirma_uret.py` | Yazıldı, test edildi |
| Kurulum ve uyum denemesi | `kur.sh`, `araclar/uyum_denemesi.sh` | Yazıldı; sunucuda ilk kez çalışacak |

Henüz yok (sıradaki parçalar): Karabasan'ın canlı ölçüm servisi, sanal
işlemlerin Karabasan durumuyla etiketlenmesi, haftalık Telegram raporu,
12 aylık geçmiş testi raporu, Türkçe panel. Gerçek para ile ilgili hiçbir
kod (emir yürütücü, risk yöneticisi) bu aşamada yoktur.

## Dürüst not: nerede sınandı, nerede sınanmadı

Çekirdek mantık 122 otomatik testten geçiyor. Testler arasında şunlar var:
göstergelerin ve altı stratejinin geleceğe bakmadığı, kâr hedefi ve stop
hesabı, Karabasan'ın "açılması yavaş, kapanması hızlı" davranışı, veto
süreleri, filtrenin elenme nedenleri ve sınavın yedi karar ölçütü.

Kodun yazıldığı ortamdan paket deposuna, Docker'a ve Binance'e erişim yoktu.
Bu yüzden üç şey ancak sunucuda sınanabilir:

1. Hazır motorun (Freqtrade) strateji sınıflarımızı yükleyip çalıştırması.
2. Kurulum betiğinin Ubuntu'da baştan sona çalışması.
3. Binance ve CoinGecko'dan canlı veri akışı.

Kurulumun 8. adımı olan **uyum denemesi** tam bunun içindir: botları
başlatmadan önce her stratejiyi gerçek Binance verisinde hazır motorla
geçmiş testinden geçirir, aynı veride bizim bağımsız benzetimimizi de
çalıştırır ve sonucu bir dosyaya yazar. Bir adım kalırsa botlar başlamaz.

## İlk kurulum

Hazırlık adımları (repo, giriş anahtarı, sunucu, Tailscale, Telegram)
tasarım raporunun "Kurulum ve yol haritası" bölümündedir. Sunucu hazır
olunca, sunucuya bağlan:

```
ssh root@SUNUCU_IP_ADRESI
```

ve şu üç bloğu sırayla yapıştır. `KULLANICI_ADIN` yerine GitHub kullanıcı
adını yaz.

**1. Sunucuya depoyu okuma anahtarı üret:**

```
apt-get update -y && apt-get install -y git
ssh-keygen -t ed25519 -N "" -f /root/.ssh/karabasan_depo -C karabasan-sunucu
cat /root/.ssh/karabasan_depo.pub
```

Ekrana çıkan tek satırı kopyala. GitHub'da depoyu aç: Settings, Deploy keys,
Add deploy key. Satırı yapıştır, "Allow write access" kutusunu İŞARETLEME, kaydet.

**2. Depoyu indir:**

```
export GIT_SSH_COMMAND="ssh -i /root/.ssh/karabasan_depo -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
git clone git@github.com:KULLANICI_ADIN/karabasan-bot.git /opt/karabasan-bot
git -C /opt/karabasan-bot config core.sshCommand "ssh -i /root/.ssh/karabasan_depo -o IdentitiesOnly=yes"
```

**3. Kur:**

```
bash /opt/karabasan-bot/kur.sh
```

Betik dokuz adımdır. 4. adımda bir Tailscale bağlantısı gösterir; onu
tarayıcında açıp onaylarsın. 8. adım (uyum denemesi) 10-20 dakika sürer.
Bir yerde durursa ekranda hangi dosyayı göndermen gerektiği yazar.

Kurulum bitince botlar bir **ısınma haftasına** girer: sanal işlem yaparlar
ama 30 günlük sınavın saati henüz başlamaz. Bu hafta, tesisatın gerçek
veride doğru çalıştığını görmek ve sıradaki parçaları eklemek içindir.

## Komisyon oranları

Başlangıç değerleri `karabasan/botlar.py` içindedir:

```
"komisyon_yuzde": { "spot": 0.075, "vadeli": 0.05 }
```

Değerler yüzdedir ve taraf başınadır: 0.075, %0,075 demektir. Sınavda tüm
emirler piyasa emri olduğu için alıcı (taker) oranı kullanılır. Hesabındaki
oranlar farklıysa Claude'a yaz; değeri depoda o günceller, sen sunucuda
şunu çalıştırırsın:

```
bash /opt/karabasan-bot/guncelle.sh
```

## Günlük kullanım

| İş | Komut |
| --- | --- |
| Botların durumu | `cd /opt/karabasan-bot && docker compose ps` |
| Bir botun kayıtları | `docker compose logs --tail 50 s1-spot` |
| Hepsini durdur | `docker compose stop` |
| Yeniden başlat | `docker compose up -d` |
| Yeni kodu al | `bash /opt/karabasan-bot/guncelle.sh` |
| Uyum denemesini yeniden çalıştır | `bash araclar/uyum_denemesi.sh` |

Bot ekranları, Tailscale açıkken `http://karabasan:8081` ile
`http://karabasan:8090` arasındadır (hazır motorun kendi İngilizce ekranı;
Türkçe panel sıradaki parçalardandır). Kullanıcı adı `karabasan`, parola
`.env` dosyasındadır.

## On sanal bot

| Bot | Strateji | Piyasa | Yön | Ekran |
| --- | --- | --- | --- | --- |
| s1-spot | S1 Trend içi geri çekilme | Spot | Alım | 8081 |
| s2-spot | S2 Hacimli kırılım | Spot | Alım | 8082 |
| s3-spot | S3 Bant içi dönüş | Spot | Alım | 8083 |
| s4-spot | S4 Ortalamaya dönüş | Spot | Alım | 8084 |
| s1-vadeli | S1 | Vadeli, 1 kat | Alım | 8085 |
| s2-vadeli | S2 | Vadeli, 1 kat | Alım | 8086 |
| s3-vadeli | S3 | Vadeli, 1 kat | Alım | 8087 |
| s4-vadeli | S4 | Vadeli, 1 kat | Alım | 8088 |
| s1k-vadeli | S1K Trend içi tepki satışı | Vadeli, 1 kat | Açığa satış | 8089 |
| s2k-vadeli | S2K Hacimli aşağı kırılım | Vadeli, 1 kat | Açığa satış | 8090 |

Her botun 1.000 USDT sanal bakiyesi vardır, işlem başına 50 USDT kullanır,
aynı anda en fazla 20 pozisyon açar. Tüm emirler piyasa emridir ve karşı
taraftan fiyatlanır; bu, sonuçları olduğundan iyi göstermemek için seçilmiş
kötümser bir varsayımdır.

## Strateji dosyası

Bir strateji kod değil, `karabasan/stratejiler/` klasöründe bir JSON
dosyasıdır. Örnek (`S1.json`, kısaltılmış):

```
{
  "kod": "S1",
  "ad": "Trend içi geri çekilme",
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
  `en_yuksek`, `en_dusuk`, `hacim_ort`, `degisim_yuzde`.
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
- `.env` dosyası (bot ekranlarının parolası) depoya girmez.
- Bot ekranları yalnız sunucunun kendisine açılır (`127.0.0.1`); dışarıdan
  erişimi yalnız Tailscale özel ağı taşır.
- Kurulum betiği parolayla SSH girişini kapatır ve güvenlik duvarını açar.
- Sunucudaki depo anahtarı salt okunurdur; sunucu depoya yazamaz.
