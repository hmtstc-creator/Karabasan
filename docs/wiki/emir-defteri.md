# Emir defteri denemesi

> BTC vadeli defter servisi ve /defter sayfası.
> Kaynak: CLAUDE.md'nin 9 Kasım 2026 öncesi hali (sözcüğü sözcüğüne taşındı).

**Emir defteri denemesi (12 Ekim 2026, Ahmet'in isteğiyle).** Ahmet "yalnız
BTC vadeli, alım ve satış; her saniye emir defterine bakıp 5 ve 15 dakika sonra
fiyatın ne olacağını hacim, RSI, destek / direnç ile kestir, kazanç görürsen
pozisyon aç; geçmişe dönük değil ileriye dönük test et; mevcut sayfaları bozmadan
ayrı bir özet sayfası yap" dedi. Yapılan: `defter` servisi ve `/defter` sayfası
(Yapı tablosunda). Mevcut botlara, sayfaya ve ayarlara dokunulmadı.
- Tahmin için önceden yazılmış bir formül yok; model servisin kendi kaydından
  öğrenir ve yalnız sonucu belli olmuş anlardan öğrenir (5. kural testleri
  `test_defter.py`'de). Sabit eğilim terimi yok (yoksa son saatlerin ortalama
  hareketini geleceğe taşıyordu; yapay piyasada bu yüzden "değişmez"den kötü çıktı).
- Yapay piyasada (defterde gerçekten ipucu olan) model yeterli kayıttan sonra
  "değişmez" tahmininden iyi çıkıyor; bu yalnız düzeneğin çalıştığını gösterir.
  Gerçek BTC defterinde 5-15 dakikalık bir ipucu olup olmadığı bilinmiyor;
  Ahmet'e "kendi başına kazandıracağının bir garantisi yok" dendi. Sayfadaki
  ölçüt: tahmin hatası "değişmez" hatasından küçük ve yön isabeti %50'den
  belirgin büyük mü? Değilse işlemlerin sonucu şanstır.
- Sunucuda doğrulanacak: `fapi.binance.com/fapi/v1/depth`'e saniyede bir
  ulaşılabilmesi (ağırlık 5, dakikada 300; sınır 2.400), kapsayıcının
  `kayit/defter.sqlite` yazabilmesi, panel ve habercinin aynı dosyayı salt
  okunur açabilmesi (WAL). Sorun olursa `docker compose logs defter`.
- Sonuç sayfası sunucusu yalnız Tailscale ile açılır ve Ahmet henüz onaylamadı;
  bu yüzden Telegram `/defter` hem kısa özeti hem sayfayı dosya olarak yollar.
