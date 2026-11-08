# Stratejiler: S1–S7, Smartmoney, SMD, Sniper, RSI (Ekim 2026)

> İlk dönem botları, ayarları, 12 aylık test sonuçları ve neden durdurulduklarının kaydı.
> Kaynak: CLAUDE.md'nin 9 Kasım 2026 öncesi hali (sözcüğü sözcüğüne taşındı).

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


**RSI botları (13 Ekim 2026, Ahmet'in isteği: "yalnız RSI, 5 / 15 dk / 1 saat; RSI önceki bardan
artışa geçtiyse ve aşırı satıştaysa long, tersi short; hedef %1,5, süre yok, stop %3, trailing 0,3;
30 gün takip").** İki bot (motor her botu tek yönde çalıştırır): `rsi-vadeli` (8086, `RSI.json`) ve
`rsik-vadeli` (8087, `RSIK.json`). Alım: 5 dk RSI(14) önceki mumda ≤ 30, önceki mumda düşüyordu,
bu mumda yükseldi; 15 dk RSI ≤ 40; 1 s RSI ≤ 50. Açığa satış aynası (≥ 70, 15 dk ≥ 60, 1 s ≥ 50).
Eşikler Claude'un (Ahmet yalnız "aşırı satış" dedi). Çıkış: hedef %1,5 + iz süren stop tetik %1,2
(diğer botlarla aynı) / mesafe %0,3 + stop %3, süre yok; piyasa emri. `UYUM_SURUMU=18`,
`YILLIK_SURUMU=6` (12 aylık test RSI dahil yeniden). Yapay veride kendiliğinden kâr yok (60 günde RSI
59 işlem −%9, RSIK 99 işlem −%35; rastgele yürüyüşte beklenen). 7 bot ≈ 3,1 GB bellek.
- **On sekizinci uyum denemesi geçti (13 Ekim 20:10 UTC; sunucudaki oturumdan okundu).** 7 sınıf yüklendi.
  RSI motorla tutuyor: RSI motor 109 / benzetim 106 / eşleşen 105; RSIK 105 / 105 / 105. Son 30 gün motor:
  RSI 118 işlem %67,8 kazanma −9,94 USDT; RSIK 106 / %66,0 / −12,59 (başa baş ~%71). Benzetim (BTC dahil):
  RSI 130 / %70,0 / −5,56; RSIK 114 / %65,8 / −14,81. Eşleşen işlemlerde net fark küçük (RSI −12,67 /
  −12,00). Motor, benzetimin hedefle kapattığı 8-9 işlemi iz süren stopla kapatıyor (aynı mumda hedef / iz
  önceliği farkı olabilir; doğrulanmadı, sonuca etkisi küçük).
- **Limitli giriş (13 Ekim 2026 akşamı, Ahmet'in isteği: "sinyal anındaki fiyatın long için %1 altına,
  short için %1 üstüne emir").** RSI / RSIK'ta `giris_limiti` {atr_kat 0, en_az = en_fazla %1,
  sure_dakika 60}: uzaklık her zaman %1, emir 60 dk (12 mum) bekler, dolmazsa iptal. Bekleme süresini
  Ahmet söylemedi, Claude seçti (Ahmet'e söylendi). 30 günlük takip bu ayarla yeniden başlar (rapor
  hatırlatmaları 20 Ekim ve 12 Kasım'da duruyor; ilk saatin piyasa emirli birkaç işlemi kayıtta kalır).
  Yapay veride işlem sayısı ~yarıya iner. `UYUM_SURUMU=19`, `YILLIK_SURUMU=7`.
- **Limitli girişin ilk sonucu (uyum 19, 13 Ekim 20:28 UTC; 12 aylık test 7, 20:37 UTC; sunucudaki
  oturumdan okundu).** Son 30 gün motor (BTC hariç; piyasa emri → %1 limit): RSI 118 / %67,8 / −9,94 →
  32 / %71,9 / −0,24; RSIK 106 / %66,0 / −12,59 → 31 / %71,0 / −0,60. Benzetim (BTC dahil): RSI +0,51
  (32 işlem), RSIK −2,54 (34). Eşleşme: RSI 28 / 28 / 27, RSIK 31 / 31 / 31. İşlem dörtte bire indi,
  kayıp neredeyse sıfıra (tek ay). 12 aylık test (13.10.2025–13.10.2026, benzetim): RSI 507 işlem %71,6
  (başa baş %68,9) −5,40 USDT, işlem başına −%0,021, çeyrekler +10,75 / −21,46 / −6,50 / +11,81 (2 / 4);
  RSIK 387 / %63,3 / −69,22, işlem başına −%0,358, 1 / 4 çeyrek. Yani RSI sıfıra yakın (kenar yok),
  RSIK belirgin kaybettiriyor. Motor bazı işlemleri benzetimin hedefle kapattığı yerde iz süren stopla
  kapatıyor (RSI 2, RSIK 5); RSIK'ta eşleşen netin işaretini çeviriyor (motor −0,67, benzetim +0,05):
  benzetim RSIK'ı biraz iyimser gösterebilir. Ahmet'e söylendi; ayar değişmedi, canlı 30 gün sürüyor.
- **RSI 7 + momentum 14 (14 Ekim 2026, Ahmet'in isteği: "14 gün süremiz uzun, RSI 7'ye düşür; momentum
  kriteri ekle, 14 günlük bak").** Aynı iki botta yerinde değişti (yeni bot yok): üç dilimde RSI(14) →
  RSI(7) (göstergeler `rsi7`, `rsi7_15`, `rsi7_1s`; eşikler aynı); yeni `mom14` = 5 dk kapanışın 14 mum
  öncesine göre yüzde değişimi (`degisim_yuzde`). Alım: önceki mumda momentum < 0, önceki mumda düşüyordu,
  bu mumda yükseldi (RSI ile aynı "dönüş" mantığı); açığa satış aynası. Momentum şartının biçimi Claude'un
  (Ahmet yalnız "momentum, 14" dedi). Not: periyotlar gün değil mumdur (5 dk RSI 14 = 70 dk); dolmayan
  emirlerin nedeni RSI periyodu değil, %1 uzaklık ve 60 dk beklemedir; Ahmet'e söylendi. Limit giriş ve
  çıkış aynı. Yapay veride (60 gün) sinyal ~%35-55, işlem ~%65-85 arttı. 30 günlük takip yine baştan.
  `UYUM_SURUMU=20`, `YILLIK_SURUMU=8`.
- **RSI 7 + momentum 14'ün ilk sonucu (uyum 20, 14 Ekim 12:29 UTC; 12 aylık test 8, 12:39 UTC; sunucudaki
  oturumdan okundu).** Eşleşme birebir: RSI 36 / 36 / 36, RSIK 54 / 54 / 54 (eşleşen net motor / benzetim
  RSI −8,68 / −8,16, RSIK −8,85 / −8,47). Son 30 gün motor (RSI 14 limitli → RSI 7 + momentum): RSI 32 / %71,9
  / −0,24 → 36 / %61,1 / −8,66; RSIK 31 / %71,0 / −0,60 → 55 / %65,5 / −8,24. 12 ay (14.10.2025–14.10.2026,
  benzetim): RSI 507 / −5,40 / 2 çeyrek → 715 / %72,2 / −0,14 / 1 çeyrek (işlem başına %0,000); RSIK
  387 / −69,22 / 1 → 562 / %63,7 / −99,85 / 1 (işlem başına −%0,355). Kenar yok: RSI sıfır, RSIK iki
  sürümde de belirgin kaybettiriyor. Ahmet'e söylendi; ayar değişmedi.

**Sniper, RSI ve RSIK durduruldu (15 Ekim 2026, Ahmet'in isteği: "SNIPER ve RSI olanları durdur ve sil,
4 bot kalsın").** `BOTLAR` dört bot: SM, SMK, SMD, SMDK. Üç kural dosyası `stratejiler/emekli/`'ye
taşındı (silinmedi; `kural_yukle` koduyla bulur, testleri emekli sınıfla çalışır: `emekli_sinifi`).
Motor sınıfları (`SniperVadeli`, `RSIVadeli`, `RSIKVadeli`) bağlantı katmanından çıktı. Sunucuda
`up --remove-orphans` üç kapsayıcıyı kaldırır; SQLite kayıtları `user_data/db/`'de kalır, okunmaz.
8085–8087 Tailscale köprüleri boşa dinleyebilir, zararsız. RSI rapor hatırlatmaları (20 Ekim, 12 Kasım)
silindi. `UYUM_SURUMU=21`, `YILLIK_SURUMU=9`.
- **Aynı gün SM ve SMD de durduruldu (Ahmet: "aynı şekilde sm ve smd'yi de sil, sadece 2 bot kalsın").**
  `BOTLAR`: `smk-vadeli` (8081), `smdk-vadeli` (8082); ikisi de açığa satış, hiç alım botu yok. SM / SMD
  `emekli/`'de; testler SM'yi emekli sınıfla sınar. Kapılar sıradan verildiği için SMK 8082 → 8081, SMDK
  8084 → 8082 (kayıtlar bot adıyla tutulur, etkilenmez; `ozel_ag.sh` köprüleri kapı listesinden kurar).
  12 aylık testte SMK +16,73 ve SMDK +20,33 tek artıdaki botlardı; çeyreklerin üçünde artı değiller ve
  çıkış taramasında artıları ilk 9 aydan (düşüş dönemi) geliyordu. `UYUM_SURUMU=22`, `YILLIK_SURUMU=10`.
