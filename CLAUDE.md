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
| `karabasan/gostergeler.py` | Gösterge blokları (EMA, RSI, Bollinger, ATR, VWAP, üst dilim hizalama) |
| `karabasan/kural.py` | Kural dosyası (JSON) okuma, doğrulama, sinyal üretme |
| `karabasan/stratejiler/*.json` | Altı strateji: S1–S4 (alım), S1K ve S2K (açığa satış) |
| `karabasan/puan.py` | Karabasan puanı, durum makinesi, vetolar |
| `karabasan/filtre.py` | Filtre (Elek): dört katman, elenme nedenleri |
| `karabasan/karne.py` | İşlem ölçümleri ve 30. günün yedi karar ölçütü |
| `karabasan/benzetim.py` | Bağımsız, kötümser mum bazlı benzetim |
| `karabasan/botlar.py` | On sanal botun listesi, komisyon başlangıç değerleri |
| `karabasan/kayitci.py` | BTC dominansı ve TOTAL2'yi 10 dakikada bir kaydeder |
| `karabasan/sonuc.py` | Botların SQLite kayıtlarını salt okunur okuyup özet çıkarır; dönem (ısınma, sınav, bitti) |
| `karabasan/sayfa.py`, `karabasan/panel.py` | Türkçe sonuç sayfası ve sunucusu (8080; `/`, `/veri.json`, `/saglik`) |
| `karabasan/haberci.py` | Telegram: kurulum bildirimleri, günlük özet, susan bot uyarısı, komutlar |
| `user_data/strategies/karabasan_stratejileri.py` | Freqtrade bağlantı katmanı |
| `araclar/yapilandirma_uret.py` | Bot yapılandırmalarını ve `docker-compose.yml`'i üretir |
| `araclar/uyum_denemesi.sh`, `araclar/karsilastir.py` | Sunucudaki uyum denemesi |
| `kurulum/sunucu_blogu.sh` | Ahmet'in sunucuyu oluştururken "Cloud config" kutusuna yapıştırdığı blok |
| `kur.sh` | Kurulum; soru sormaz, her adımı Telegram'a yazar, her güncellemede yeniden çalışır |
| `araclar/oto_guncelle.sh` | 5 dakikada bir `main`'i denetler, yeni kodu alır, `kur.sh`'ı çalıştırır |
| `araclar/ozel_ag.sh` | Tailscale onay bağlantısını Telegram'dan yollar; kapıları özel ağ adresine taşır |

Üretilen dosyalar (`docker-compose.yml`, `user_data/config/`, `.env`,
`telegram.env`) depoya girmez; sunucuda `araclar/yapilandirma_uret.py` ve
`kur.sh` üretir.

Sunucudaki durum dosyaları: `user_data/isinma_baslangici.txt` (botların ilk
başladığı an), `user_data/sinav_baslangici.txt` (Ahmet Telegram'da
`/sinav_baslat evet` yazınca oluşur; bir kez yazılır, değiştirilmez),
`user_data/kurulum_tamam`, `user_data/logs/uyum_gecti`,
`user_data/telegram_sohbet.txt` (botun dinlediği tek sohbet).

Telegram komutları yalnız okur ve bildirir. Emir gönderen, ayar değiştiren ya
da sunucuda serbest komut çalıştıran bir Telegram komutu ekleme.

## Durum

Laboratuvar sürümünün 1. ve 2. parçası yazıldı; 198 test geçiyor.
2. parça: sonuç sayfası, Telegram habercisi, telefondan kurulum ve
kendiliğinden güncelleme. Ahmet sunucuyu (Hetzner CX33) 10 Ekim 2026'da
kiralıyordu; kurulumun gerçek sunucudaki ilk sonucu henüz görülmedi.

Sıradaki işler, öncelik sırasıyla:

1. Ahmet'in ileteceği kurulum kaydını ve uyum denemesi raporunu incele;
   kurulum betiği ya da bağlantı katmanı bir yerde takıldıysa düzelt.
2. Karabasan canlı ölçüm servisi: Binance mumları ve `kayitci` kaydından
   puanı 5 dakikada bir hesaplayıp kaydetsin (`puan.py` hesap kısmı hazır).
3. Sanal işlemlerin açıldıkları andaki Karabasan durumu ve filtre puanlarıyla
   etiketlenmesi (botların SQLite kayıtları ile Karabasan kaydının birleşimi).
4. Haftalık Telegram raporu ve 30. gün karar raporu (`karne.sinav_karari`).
5. 12 aylık geçmiş testi ve raporu (sonucu `user_data/gecmis_test.json`'a
   yazılır; 7. ölçüt bunu okur).
6. Sonuç sayfasına Karabasan durumu, filtre hunisi ve strateji ayrıntıları.

## Sunucuda doğrulanacak varsayımlar

Bunlar belgeye göre yazıldı, çalıştırılarak doğrulanmadı:

- Freqtrade'in strateji sınıflarını `__init_subclass__` ile doldurulan
  özelliklerle (`timeframe`, `minimal_roi`, `stoploss`, `can_short`) yüklemesi.
- `minimal_roi` değerinin komisyon sonrası kâr oranı olarak yorumlanması
  (`botlar.net_hedef_orani` bu varsayıma göre çevirir).
- Sanal modda vadeli işlemlerde fonlama ücretinin işlenmesi.
- Vadeli veri dosyalarının adı (`araclar/karsilastir.py` içindeki desen).
- Kapsayıcıdaki kullanıcının kimliğinin 1000 olması (`chown` buna göre).
- Hetzner'in "Cloud config" kutusuna yapıştırılan `#!/bin/bash` ile başlayan
  metni ilk açılışta root olarak çalıştırması.
- Freqtrade'in `trades` tablosundaki sütun adları (`sonuc.py`: `pair`,
  `is_open`, `open_date`, `close_date`, `stake_amount`, `close_profit_abs`,
  `close_profit`, `exit_reason`, `is_short`, `enter_tag`).
- Freqtrade'in çalışırken günlük dosyasına en az 15 dakikada bir satır
  yazması (susan bot uyarısı ve sayfadaki "çalışıyor" bilgisi buna dayanır).
- `tailscale status --json` çıktısındaki `BackendState` ve `AuthURL` alanları.
- `socat` köprüsünün sunucunun Tailscale adresinde dinleyebilmesi ve
  telefonun `http://karabasan:8080` adını çözebilmesi (MagicDNS).
- Motor görüntüsünde saat dilimi verisinin bulunması (yoksa sayfa UTC gösterir).
