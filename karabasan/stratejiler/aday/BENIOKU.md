# Aday kurallar (panel sınaması)

Bu klasördeki kurallar canlı bot değildir. 12 Ekim 2026'daki uzman panelinin
önerdiği adaylar ve onların önceden yazılmış denemeleri, plasebolarıdır.
`karabasan/sinama.py` (panel sınaması) bunları 4 yıllık veride sınar; son yıl
ayrılmıştır ve bir kez açılır.

| Aile | Denemeler | Canlıya gidecek | Plasebo |
| --- | --- | --- | --- |
| ZSD: zorla satış dönüşü (alım, 15 dk) | ZSD, ZSDF (+ fonlama), ZSDT (+ günlük trend) | ZSD | ZSDP (BTC şartı yok) + rastgele giriş |
| TRG: günlük trend (alım, 1 s) | TRG14, TRG28, TRG56 | TRG28 | rastgele giriş |
| TRGK: günlük trend (açığa satış, 1 s) | TRGK14, TRGK28, TRGK56 | TRGK28 | rastgele giriş |
| ASYA / ASYAK: Asya seansı likidite avı (alım / açığa satış, 15 dk; 2. aşama) | ASYA / ASYAK (tek deneme) | ASYA / ASYAK | ASYAP1 / ASYAKP1 (12:00-18:59 aralığı), ASYAP2 / ASYAKP2 (saat şartı yok) + rastgele giriş |
| FON / FONK: fonlama sıkışması (alım / açığa satış, 1 s; 3. aşama, sayım 571 olay bulduğu için) | FON / FONK (tek deneme) | FON / FONK | FONP / FONKP (fonlama şartı yok) + rastgele giriş |
| AHMETOZEL / AHMETOZELK: Ahmet'in kendi stratejisi (alım / açığa satış, günlük; haftalık destek / direnç ve FVG, 13 Ekim 2026) | 1: hedef 2R, 30 gün; 2: hedef 3R, 30 gün; 3: hedef yok, günlük yapı ters dönünce (CHoCH) çık, 60 gün | AHMETOZEL / AHMETOZELK (1. deneme) | P1 (destek / direnç / FVG şartı yok; karar bunu kullanır), P2 (MACD şartı yok; yalnız bilgi) + rastgele giriş |

Kurallar dondurulmuştur: bir eşik değişirse o yeni bir denemedir ve deneme
defterine yazılır. Raporda her dosyanın özeti (SHA-256'nın ilk 12 hanesi) durur.
Bir bot ancak sınamayı ve ayrılmış yılı geçerse `botlar.BOTLAR`'a girer.

İlk sınama (PANEL_SURUMU=1, 12 Ekim 2026): ZSD, TRG ve TRGK kaldı (bkz. CLAUDE.md).
İkinci sınama (PANEL_SURUMU=2): ASYA ve ASYAK da kaldı; fonlama sayımı 571 olay (bkz. CLAUDE.md).
Üçüncü sınama (PANEL_SURUMU=4, 13 Ekim 2026): AHMETOZEL / AHMETOZELK eklendi; ölçüler R cinsinden
(işlem başına en az 0,15R, kural plasebosundan en az 0,15R iyi, ortalama kazanç / kayıp en az 1,5,
en büyük düşüş en çok 15 USDT; en az 60 işlem ve 40 ayrı gün, azsa HÜKÜM YOK).
