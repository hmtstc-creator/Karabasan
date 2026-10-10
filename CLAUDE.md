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

Ahmet. Kod bilmiyor. Türkçe yaz. Ona verilen her komut kopyala-yapıştır
hazır olmalı; ne yaptığını bir cümleyle açıkla. Teknik terim kullanacaksan
ilk geçtiği yerde açıkla. Önceliği para kazanmak değil, parayı kaybetmemek.

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
| `user_data/strategies/karabasan_stratejileri.py` | Freqtrade bağlantı katmanı |
| `araclar/yapilandirma_uret.py` | Bot yapılandırmalarını ve `docker-compose.yml`'i üretir |
| `araclar/uyum_denemesi.sh`, `araclar/karsilastir.py` | Sunucudaki uyum denemesi |
| `kur.sh`, `guncelle.sh` | Sunucu kurulumu ve güncelleme |

Üretilen dosyalar (`docker-compose.yml`, `user_data/config/`, `.env`) depoya
girmez; sunucuda `araclar/yapilandirma_uret.py` ve `kur.sh` üretir.

## Durum

Laboratuvar sürümünün 1. parçası yazıldı; çekirdek 122 testten geçiyor.
Henüz hiçbir şey sunucuda çalışmadı.

Sıradaki işler, öncelik sırasıyla:

1. Ahmet sunucuyu kurunca uyum denemesi raporunu incele; hazır motorla
   uyumsuzluk çıkarsa bağlantı katmanını düzelt.
2. Karabasan canlı ölçüm servisi: Binance mumları ve `kayitci` kaydından
   puanı 5 dakikada bir hesaplayıp kaydetsin (`puan.py` hesap kısmı hazır).
3. Sanal işlemlerin açıldıkları andaki Karabasan durumu ve filtre puanlarıyla
   etiketlenmesi (botların SQLite kayıtları ile Karabasan kaydının birleşimi).
4. Haftalık Telegram raporu ve 30. gün karar raporu (`karne.sinav_karari`).
5. 12 aylık geçmiş testi ve raporu.
6. Türkçe panel (tek adres; şimdilik Freqtrade'in kendi ekranı kullanılıyor).

## Sunucuda doğrulanacak varsayımlar

Bunlar belgeye göre yazıldı, çalıştırılarak doğrulanmadı:

- Freqtrade'in strateji sınıflarını `__init_subclass__` ile doldurulan
  özelliklerle (`timeframe`, `minimal_roi`, `stoploss`, `can_short`) yüklemesi.
- `minimal_roi` değerinin komisyon sonrası kâr oranı olarak yorumlanması
  (`botlar.net_hedef_orani` bu varsayıma göre çevirir).
- Sanal modda vadeli işlemlerde fonlama ücretinin işlenmesi.
- Vadeli veri dosyalarının adı (`araclar/karsilastir.py` içindeki desen).
- `tailscale serve --bg --tcp` ile bot ekranlarının özel ağa açılması.
- Kapsayıcıdaki kullanıcının kimliğinin 1000 olması (`chown` buna göre).
