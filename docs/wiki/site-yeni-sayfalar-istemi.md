# Site: 5 trader + 5 görsel + 5 programcı ajanlı "yeni sayfalar" istemi

> 9 Kasım 2026, Ahmet'in isteği. Bu sayfa bir **istemdir** (prompt): yeni bir Claude oturumuna yapıştırılır.
> Kod yazılmadı; istem henüz çalıştırılmadı. Çalıştırılırsa sonucu günlüğe ve `sonuc-sayfasi.md`'ye yaz.

## İstem (olduğu gibi yapıştır)

Model: `claude-fable-5-2`. Çalışma yeri: bu depo (Karabasan). Önce `CLAUDE.md` ve `docs/wiki/README.md`, sonra
`sonuc-sayfasi.md`, `yapi.md` (yalnız sayfa / panel satırları) ve `internet-erisimi.md` dosyalarını oku. Başka büyük dosya okuma.

### Görev
Karabasan sonuç sitesine **beş yeni sayfa** ekle ve işi canlıya (main dalı) kadar götür. Mevcut ekranlar, sınıf adları,
veri akışı, test adları ve izin başlığı (CSP) mantığı **bozulmayacak**; yalnız eklenecek. Kullanıcı Ahmet kod bilmez,
yalnız telefon kullanır; her metin düz Türkçe olsun, teknik terim ilk geçtiği yerde açıklansın. Önceliği para kazanmak değil,
parayı kaybetmemektir.

### Değişmez sınırlar
1. Gerçek para yok: `dry_run` hep `true`, borsaya emir gönderen kod yazma; API anahtarı isteme.
2. Strateji ayarı, kural dosyaları (`stratejiler/`, `kural.py`, `gostergeler.py`, `botlar.py`, `user_data/strategies/`) ve
   `karne.py`'nin ölçütleri değişmez. Yeni sayfalar yalnız **okur**; bot ayarı yazmaz (sınav sürüyor, 3. kural).
3. Mimari: sayfa üretimi `karabasan/sayfa.py` (`EKRANLAR` listesi, `MENU_ACIKLAMA`, `GEZINTI_ADLARI`), sunucu `karabasan/panel.py`,
   veri `karabasan/sonuc.py`. Yeni ekran bu listeye eklenir; mevcut ekranların sırası ve içeriği aynı kalır. Her yeni ekran için
   "her ekran bir kez" testi geçmeli. Mantık `karabasan/` paketinde, testi `testler/` altında. Sayfada tek satır içi betik kuralı
   korunur (CSP özetinden üretilir); yeni betik ekleyeceksen aynı betiğe ekle, ikinci betik açma. Betiksiz de çalışmalı.
4. Yalnız standart kütüphane: sunucunun Python'unda numpy / pandas yok. Yeni kod bunlara dayanmasın (testler bunu denetler).
5. Geleceğe bakmak yasak: yeni bir gösterge ya da hesap eklersen sonradan gelen verinin geçmiş değeri değiştirmediğini sınayan test ekle.
6. Gizli bilgi, sunucu adresi, parola depoya girmez. Depo herkese açık.
7. Caddy yalnız GET / HEAD ve `POST /ayar/kayit`'e izin verir; yeni sayfalar yalnız GET kullansın, internet erişimine yeni kapı açma.
8. Sınanmamış şeyi sınanmış gibi anlatma. Burada Binance, Docker, Freqtrade yok; sunucuda ilk kez çalışacak kısımları açıkça yaz.
9. Rapor ile kod aynı şeyi söylesin: eşik / kural değişirse tasarım raporunu da güncelle.

### Ekip: 5 üst düzey trader, her birinin yanında 1 görsel ve 1 programlama ajanı (15 ajan) + 1 başkoordinatör
Başkoordinatör sensin. Her ekip kendi sayfasının sahibidir; dosyalar çakışmasın diye her ekip kendi modülünü (`karabasan/sayfa_<ad>.py`
ve `karabasan/sonuc_<ad>.py` gibi) yazar, ortak dosyalara (`sayfa.py` `EKRANLAR`, `MENU_ACIKLAMA`, `GEZINTI_ADLARI`) yalnız en son,
sen tek tek eklersin. Trader ajanı **ne gösterileceğine ve neden** karar verir (gerçek piyasa bilgisi, hangi sayı kararı değiştirir);
görsel ajan telefonda (390 px) ve masaüstünde (1280 px) nasıl görüneceğini tasarlar; programlama ajanı yazar ve test eder.
Trader'ın "bu sayı karar için işe yaramaz" dediği şey sayfaya girmez.

1. **Sermaye Koruma / Risk Yöneticisi (sayfa: Risk).** Bir fon risk masası başkanı gibi düşün. Göster: toplam ve bot başına açık risk
   (stop fiyatına göre, komisyon hariç), tepeden düşüş ve düşüşten çıkış süresi, tek coin ve tek yönde yoğunlaşma, günlük bütçe
   kullanımı, "hepsi stopa giderse" senaryosu ve bunun sanal bütçeye oranı, 2 kat kaldıraçlı SMK2 / SMDK2'nin ek giriş sonrası
   gerçek riski. Her sayının yanında tek cümle: "bu sayı yükselirse ne yapmalıyım". Kırmızı çizgi: veri eksikse tahmin uydurma, "veri yok" yaz.
2. **Piyasa Ortamı / Makro Rejim Trader'ı (sayfa: Rejim).** Karabasan motorunun 0–100 puanını, dört durumunu ve veto kurallarını
   zaman içinde göster: şimdi hangi durumdayız, son 30 günde durum geçişleri, hangi veto ne kadar sürdü, bot o sırada işlem açtı mı.
   Puanın bileşenlerini (hangi parça puanı yukarı / aşağı çekiyor) görsel olarak ayır. Yalnız mevcut kayıttan oku; yeni hesap
   uydurma. Sonuçla ilişki kurarken az veriyi açıkça belirt ("Veri az").
3. **Vadeli Piyasa ve Likidite Trader'ı (sayfa: Likidite).** Açığa satış botları için kritik: fonlama oranı, açık faiz, emir defteri
   dengesizliği (`/defter` verisi varsa bağla, yoksa "yalnız defter servisi çalışırken"), spread ve coin başına hacim, tasfiye
   (liquidation) kümeleri varsa. Hangi coinde açığa satış sıkışması (short squeeze) riski yüksek, hangi coin ince? Herkese açık, anahtarsız
   Binance vadeli adreslerinden okuyan kod yalnız panel kapsayıcısında çalışır; ağ hatasında sayfa düşmesin, "alınamadı" yazsın.
4. **Kantitatif Doğrulama Trader'ı (sayfa: Güven).** Sonuçlara güvenebilir miyim? Gün bazında t değeri, işlem sayısı yeterliliği,
   şansa bağlı olma olasılığı, kazanma oranı için güven aralığı, en iyi / en kötü coin çıkarılırsa sonuç, 12 aylık testler ile sanal
   işlem arasındaki fark. Dürüst olmak şart: "henüz kanıt yok" demek serbest, süslemek yasak. Sınav gün sayacı ve karar için eksik kalan
   gün / işlem sayısı. Mevcut `guven_etiketi` ve `risk_olcumleri`'ni yeniden kullan, kopyalama.
5. **Yürütme ve Disiplin Trader'ı (sayfa: Disiplin).** İşlemlerin kalitesi: stopa giden işlemlerin ortak özelliği (saat, coin, durum),
   komisyon ve kayma payı ne kadar yiyor, ortalama süre, stop sonrası "ders" ekranıyla bağ (stop genişliği kararı), kuralı ihlal eden
   bir şey var mı (örn. bütçe aşımı). Sonunda "bugün dikkat edilecek 3 şey" kutusu: yalnız veriden türeyen, uydurma değil.

Görsel ajanların ortak ödevi: mevcut "Premium katman" görünümüne (koyu lacivert, şampanya altını, cam kartlar) uy; ayrı uyarı rengi
(`--uyari`) kuralını koru; renk körlüğüne dayanıklı ol (renge ek olarak simge / etiket); grafikler satır içi SVG ve `<title>` ipuçlu;
dokunma hedefi en az 44 px; telefonda yatay kaydırma yok; alt çubuk telefonda zaten 5 sekme: yeni sayfalar **Menü**'de açılır, alt çubuğu
şişirme. Programlama ajanlarının ortak ödevi: hata olursa sayfa düşmesin (son başarılı özet), ETag / 304 mantığını bozma, her yeni
sayı için birim test, yeni ekran için "betiksiz render" testi.

### Çalışma sırası
1. Keşif: her trader ajan kendi sayfasının veri ihtiyacını yazar ve **elde olmayan veriyi** işaretler (uydurma yok). Sen çakışmaları çözersin.
2. Tasarım: görsel ajanlar 390 ve 1280 px için düzen çizimi (kısa metin) verir; sen onaylarsın.
3. Yapım: programlama ajanları kendi modüllerini ve testlerini yazar. Paralel çalışsınlar, ortak dosyaya dokunmasınlar.
4. Birleştirme: sen `EKRANLAR` / menü / gezinti kayıtlarını eklersin; tam test: `python3 -m unittest discover -s testler -t .`
   Tek test bile kırmızıysa işleme, önce düzelt.
5. Görsel denetim: buradaki Chromium ile her yeni sayfanın 390 ve 1280 px ekran görüntüsünü al, betikli ve betiksiz; bozukluk varsa düzelt.
6. Dokümantasyon: `docs/wiki/sonuc-sayfasi.md` (yeni ekranlar), `yapi.md` (yeni dosyalar), `gunluk.md` (bir satır) ve gerekirse tasarım raporu.
7. Canlıya alma: testler geçince **doğrudan `main`'e işle ve it** (Ahmet'in kuralı: birleştirme isteği, onay yok). Sunucu 5 dakikada bir
   `main`'i alıp `kur.sh`'ı çalıştırır; yeni sayfa kısa sürede canlıdır. `kur.sh`'a dokunuyorsan her adım yeniden çalıştırılabilir olsun.
   Not: `sayfa.py` / `panel.py` değişince yalnız panel kapsayıcısı yenilenmeli; bot kapsayıcılarını (strateji dosyaları) hiç etkileme,
   çünkü bir saatten uzun kesinti o günü sınavdan düşürür. İşlemeden önce hangi dosyaların botları yeniden başlatacağını denetle ve yaz.

### Bitiş ölçütü (bunlar sağlanmadan "bitti" deme)
- Beş yeni sayfa menüde, her biri telefonda düzgün; eski ekranlar birebir aynı çalışıyor; tüm testler yeşil.
- Hiçbir bot dosyası, kural, karne ölçütü değişmedi (değişen dosya listesini göster).
- Ahmet'e telefonda okunacak tek mesaj: neyin eklendiği, hangi sayfada ne göreceği, **neyin yalnız sunucuda ilk kez çalışacağı**
  ("gerçek sunucuda ilk kez" listesi), sayfaya nasıl gidileceği. Terminal ya da SSH isteme.
- Sonunda sunucu oturumuna (`send_message`, yalnız Read aracıyla okuma iste) canlıya geçtiğini doğrulat: panel `/saglik` cevabı ve yeni
  sayfaların açılışı. Doğrulanamazsa "canlıya gitti ama doğrulanmadı" de.

## Sınanan / sınanmayan
Hiçbiri: bu yalnız bir metindir. İstemin kendisi test edilmedi; "15 ajan" paralel çalıştırma maliyeti yüksektir, istenirse trader
sayısı 3'e indirilebilir.
