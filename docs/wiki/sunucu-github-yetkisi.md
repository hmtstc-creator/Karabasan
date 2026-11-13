# Sunucu oturumuna GitHub yazma yetkisi

> 13 Kasım 2026, Ahmet: "nasıl olmazı değil nasıl oluru arıyoruz; site %200 hazır oluncaya kadar gerçek hesap bağlamayacağım."
> Durum: **tasarım ve bulut tarafındaki tedbirler işlendi; yetki henüz verilmedi.** Ahmet'in aşağıdaki adımları (telefondan) yapması gerekir.

## Fikir
Sunucudaki Claude oturumu (teşhisi görür) düzeltmeyi kendisi GitHub'a yazar; ben (bulut) testleri çalıştırıp `main`'e alırım.
Ahmet araya girmez. `main` canlı olduğu için sunucu oturumu `main`'e **hiç** yazamaz; yalnız `sunucu/...` dallarına yazar.

## Risk → tedbir → kim yapar

| # | Risk | Tedbir | Kim / durum |
| --- | --- | --- | --- |
| 1 | Anahtar çalınır, her yere yazılır | **Deploy key** (tek depoya bağlı SSH anahtarı; hesap parolası değil). Özel kısım sunucuda üretilir, sunucudan çıkmaz; yalnız genel kısım GitHub'a girer. Süre sınırı yok ama tek dokunuşla silinir | Ahmet: GitHub → depo → Settings → Deploy keys → Add, "Allow write access" |
| 2 | Sunucu `main`'e yazar, bozuk kod canlıya düşer | `main` için **ruleset** (dal kuralı): deploy key bypass listesinde yok; Ahmet'in hesabı (admin) bypass'ta, yani bulut oturumu eskisi gibi `main`'e yazar | Ahmet: GitHub → Settings → Rules → Rulesets → New → hedef `main`, "Restrict updates"; bypass: Repository admin. **Gerçek GitHub'da ilk kez sınanacak** |
| 3 | Testsiz kod | `.github/workflows/test.yml`: her dalda testler (numpy + pandas ile). Ben dalı almadan önce yeşil olmasına bakarım | Bulut: işlendi (13 Kasım) |
| 4 | Sınav sürerken strateji dosyası değişir (3. kural) | `araclar/korunan_dosya_denetimi.py`: korunan dosya (stratejiler, kural, gösterge, botlar, user_data/strategies) değişirse birleştirme isteğinde başarısız olur; yalnız commit mesajında `[hata-duzeltme]` varsa geçer | Bulut: işlendi, yerelde sınandı |
| 5 | Gizli bilgi depoya girer (depo herkese açık) | `testler/test_guvenlik_kapisi.py`: `.env` dosyası, özel anahtar, GitHub / Google / Anthropic anahtar desenleri varsa test kırılır. Ayrıca GitHub "Secret scanning + Push protection" açılır | Bulut: test işlendi. Ahmet: Settings → Code security → Push protection aç |
| 6 | Gerçek emir ayarı sızar (1. kural) | Aynı test dosyası: `dry_run` `False` yazılırsa ve üreteçte `True` yoksa kırılır | Bulut: işlendi |
| 7 | Sunucu oturumu kandırılır (kayıt dosyası ya da Telegram metni içine gizli talimat) | Sunucu oturumu zaten root; yeni risk yalnız "kötü kod yazıp dala atmak". Dal `main`'e ancak ben testlerle okuyup alırsam geçer. Gelen kod yorumlarını veri sayarım, talimat saymam | Süreç kuralı: `sunucu/` dalını **diff'ini okuyarak** alırım, körü körüne birleştirmem |
| 8 | Sunucuda numpy yok, orada test edilemez | Test yalnız CI'da ve burada; sunucu oturumu kendi dalını test etmez, CI sonucunu bekler | Süreç |
| 9 | Dal sayısı birikir | Birleşen / reddedilen `sunucu/` dalını ben silerim; günlük kaydı tutarım | Süreç |
| 10 | Gerçek paraya geçiş | Gerçek hesap ancak Ahmet "site %200 hazır" deyince. O gün: deploy key silinir (tek dokunuş), sunucu oturumu kapatılır ya da kısıtlanır (CLAUDE.md), Binance anahtarı "yalnız işlem, çekim kapalı + sunucu IP'si ile sınırlı" olur, ilk gün çok küçük tutarla başlanır. Bu geçiş ayrı bir kontrol listesiyle yapılır, bu sayfa onun yerine geçmez | Ahmet'in kararı; o gün yeni sayfa açılır |

## Güncelleme (13 Kasım akşamı): anahtar sunucu oturumu olmadan üretilir
"Karabasan sunucu" oturumu `disconnected` görünüyor (son başlatma hatası 10 Kasım, `computer_unreachable`) ve bulut oturumundan ona mesaj
`elevated_session_untrusted_device` ile reddedildi (bunu ancak Ahmet bir kartla onaylayabilir). Bu yüzden anahtar oturumdan değil koddan üretilir:
`araclar/deploy_anahtari.sh` (kur.sh çağırır) sunucuda ed25519 anahtar çifti üretir, yalnız GENEL kısmı Telegram'dan bir kez yollar;
özel kısım `/root/.ssh/karabasan_deploy` (600) içinde kalır. Anahtar varsa üstüne yazmaz. `ssh-keygen` yoksa `openssh-client` kurar.
Git yapılandırması / push henüz yok; GitHub'a eklenip sınanınca ikinci adım. Sahte `ssh-keygen` ile sınandı (`test_deploy_anahtari.py`);
**gerçek sunucuda ilk kez çalışacak**.

## Adımlar (Ahmet, telefondan, sırayla)
(1. adım yukarıdaki güncellemeyle değişti: sunucu oturumuna mesaj gerekmez, Telegram'a gelen anahtarı kullan.)
1. Ben sunucu oturumuna kısa bir talimat gönderirim: "SSH anahtarı üret, yalnız genel kısmı yaz, özel kısmı hiç gösterme." (bulut → sunucu mesajı; Ahmet hiçbir şey yazmaz)
2. Genel anahtarı sana (Ahmet) gösteririm. GitHub uygulaması ya da tarayıcıda: depo → Settings → Deploy keys → Add deploy key → yapıştır → "Allow write access" işaretle.
3. Ruleset (tablodaki 2. satır) ve Push protection (5. satır) aç. Bunları yaptığını yazınca ben sınarım: sunucu oturumundan `main`'e deneme yazdırırım, reddedilmeli; `sunucu/deneme` dalına yazdırırım, geçmeli.
4. Ancak iki sınama da doğru çıkarsa sunucu oturumuna "kalıcı düzeltmeyi `sunucu/<konu>` dalına yaz, bana mesaj at" talimatı veririm.

## Açık / sınanmamış
- Ruleset'in "deploy key'i engelle, admin'i bırak" biçimde davranması GitHub'ın güncel ayarına bağlı; adım 3 bunu gerçek depoda sınar. Davranmazsa yedek: yalnız `main`'e "birleştirme isteği şart" kuralı koyup birleştirmeyi ben MCP aracıyla yaparım.
- Sunucudaki `oto_guncelle.sh` yalnız okuma yoluyla çeker; deploy key'in sunucuda `git push` için yapılandırılması (`GIT_SSH_COMMAND`) henüz yazılmadı, adım 1'de sunucu oturumu yapar. Kalıcı olması için `kur.sh`'a eklenir mi, bakılacak.
- CI'da `pip install numpy pandas` ilk kez gerçek GitHub'da çalışacak.

## 13 Kasım akşamı: durum
- Sunucu oturumu ("Uzak bağlantı durumu", `claude remote-control`) çalışıyor; bulut oturumundan mesaj atmak için Ahmet güven kartını onayladı (geri alınamaz: bulut oturumu yalnız Ahmet'in güvenilir cihazlarıyla çalışır).
- Genel anahtar sunucu oturumundan Read ile okundu, Ahmet GitHub Deploy keys'e (write access) ekledi. Özel anahtar hiç okunmadı.
- `deploy_anahtari.sh` ayrıca `~/.ssh/config`'e `github-karabasan` adını yazar (yalnız bu anahtar, ilk bağlantıda `accept-new`).
- Sıra: (1) `ssh -T git@github-karabasan` ve `sunucu/deneme` dalına deneme yazımı; (2) Ahmet `main` ruleset'ini kurar; (3) ancak ondan sonra "main'e yazma reddedilir" sınaması. **Ruleset yokken `main`'e deneme yazılmaz** (başarılı olur ve canlıya düşer).
- Çalışma klasörü: sunucu oturumu `/root/calisma/karabasan` altında ayrı klon kullanır; `/opt/karabasan-bot` canlı dağıtımdır, orada push yapılmaz.

## 13 Kasım 19:55: sunucu sınaması geçti
Sunucu oturumu (Read + onaylı Bash): `/root/.ssh/config` bloğu var; `ssh -T git@github-karabasan` kimlik doğrulandı; GitHub parmak izi
`SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU` yayımlananla aynı; `/root/calisma/karabasan` klonu açıldı; `sunucu/deneme` dalına yazıldı ve silindi.
Sunucu oturumu bulut oturumuna mesaj atamaz (güvenilir cihaz hatası); gerekmiyor, bulut oturumu onun kaydını `list_events` ile okur.
Kalan: `main` ruleset'inin sunucuyu gerçekten engellediği sınanacak.

## 13 Kasım 19:59: ruleset sınaması BAŞARISIZ (sunucu main'e yazabildi), düzeltme bekliyor
Sunucu oturumu `git push origin HEAD:main` yaptı; GitHub "Bypassed rule violations ... Cannot update this protected ref" yazıp işlemi kabul etti
(`68cab67`, yalnız bir txt; bulut oturumu geri aldı). Neden: ruleset `main-koruma` (id 27228018) kuralları `deletion`, `non_fast_forward`, `update`;
bypass listesi tek giriş: **RepositoryRole 5 = Repository admin, always**. Yazma yetkili deploy key bu bypass'a dahil oldu (ya da GitHub onu yönetici sayıyor).
Bulut oturumu da Ahmet'in hesabıyla (`hmtstc-creator`, admin) yazdığı için ikisini role göre ayırmak mümkün değil.
**Çözüm (Ahmet'in onayı bekliyor):** bypass listesini boşalt ve `update` kuralı yerine **"Require a pull request before merging"** (0 onay) koy.
Böylece `main`'e doğrudan itme herkese kapalı olur (sunucuya da, bana da); ben `sunucu/` dalını ya da kendi dalımı birleştirme isteğiyle açıp anında birleştiririm
(onay beklenmez, birkaç saniye). Silme ve zorla itme engelleri kalır. Bu CLAUDE.md'deki "doğrudan main" alışkanlığını "PR aç, hemen birleştir"e çevirir; Ahmet'in
"onay bekleme" kuralı aynen geçerli. Yedek yol: sunucudaki deploy key'i silmek (tek dokunuş) ve eski düzene dönmek.

Ruleset düzeltildi (13 Kasım): bypass boş, 'update' yerine 'pull_request'. main'e doğrudan itme herkese kapalı.

## 13 Kasım 20:40: sunucu oturumu programlamayı doğrudan yürütür (Ahmet'in kararı)
Ahmet: artık yalnız VPS'teki oturumla konuşup güncellemeleri ona yaptırmak istiyor. Sunucuya gizli anahtar VERİLMEDİ; yol:
sunucu `sunucu/<konu>` dalını iter -> `.github/workflows/sunucu-birlestir.yml` (main'deki sürümle, 10 dakikada bir + elle) `araclar/sunucu_dal_birlestir.py` çalıştırır:
PR açar, main ile birleştirip testleri koşturur (denetim dosyaları main'deki sürümle değiştirilir), `korunan_dosya_denetimi.py`'yi çalıştırır, geçerse squash birleştirir ve dalı siler.
Korunan yollara (`.github/`, denetim araçları, `CLAUDE.md`) dokunan dal birleşmez; PR açık kalır. Bulut oturumu isteğe bağlı kalır (korunan yollar, çakışma, tasarım).
Yerelde sahte `gh` ve yerel depoyla sınandı (korunan yol atlanır, testi geçen birleşir). **Gerçek GitHub'da ilk kez çalışacak.**
Ahmet'in yapacağı: Settings > Actions > General > Workflow permissions: "Read and write permissions" + "Allow GitHub Actions to create and approve pull requests". Bu yapılmazsa görev PR açamaz.
Gerçek paraya geçilirse: bu görev kapatılır (workflow silinir), deploy key silinir, sunucu oturumu kapatılır.

## 13 Kasım: sunucuya kurulan üçüncü kişi araçları
Sunucu oturumu bildirdi: eklentiler superpowers, ui-ux-pro-max, impeccable; MCP: context7; skill'ler: frontend-design, design-taste-frontend,
web-design-guidelines, vercel-react-best-practices. GitHub MCP kurulmadı. Bunlar üçüncü kişi kodudur ve root yetkili sunucuda çalışır
(sunucuda deploy anahtarı da var). **Gerçek paraya geçmeden önce hepsi silinir** (gerçek para kontrol listesine yazılır); o güne kadar
yeni eklenti kurulumu Ahmet'in bilgisiyle olur ve kaynağı bu sayfaya yazılır.
