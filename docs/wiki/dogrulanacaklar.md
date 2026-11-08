# Sunucuda doğrulanacak varsayımlar

> Çalışarak doğrulananlar ve henüz doğrulanmamış belge varsayımları.
> Kaynak: CLAUDE.md'nin 9 Kasım 2026 öncesi hali (sözcüğü sözcüğüne taşındı).

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
- Panel sınaması (`araclar/panel_sinama.sh`): 21 vadeli paritenin (BTC + `sinama.COINLER`) 15m / 1h
  için 1500, 1d için 1700 günlük verisinin `--prepend` (olmazsa `--erase`) ile inmesi, süresi ve
  diskte kapladığı yer; listedeki coinlerin hepsinin bugün Binance vadelide işlem görmesi; sunucudan
  `fapi.binance.com/fapi/v1/fundingRate`'e ulaşılması ve yanıt biçimi (`fundingTime`, `fundingRate`).
  Yalnız sahte `docker` ve kapalı ağla prova edildi (fonlama indirmesi burada 403 ile kaldı, betik
  sürdü ve raporu uyarıyla üretti).
- Stop sonrası izlemenin sunucudan Binance'in açık mum adreslerine (`api.binance.com/api/v3/klines`,
  `fapi.binance.com/fapi/v1/klines`) ulaşabilmesi ve yanıt biçimi; `kayitci` kapsayıcısının botların
  `db/*.sqlite` dosyalarını okuyup `kayit/stop_sonrasi.json` yazabilmesi. Yalnız sahte bir Binance
  sunucusuyla baştan sona denendi. Çalışmazsa Dersler ekranı "henüz izlenmiş stop yok" demeye devam eder
  ve `/gunluk` ile değil, `docker compose logs kayitci` ile görülür (sunucudaki Claude oturumu bakabilir).
- Yeni sonuç sayfası (11 Ekim 2026) yalnız buradaki Chromium'da, telefon ve masaüstü genişliğinde
  denendi: ekran geçişi, halkadaki dilime dokunma, yerinde tazeleme, bağlantı kopunca uyarı, betiksiz dosya
  hali. Ahmet'in telefonundaki tarayıcıda (Safari) ve Telegram'ın dosya görüntüleyicisinde denenmedi.
