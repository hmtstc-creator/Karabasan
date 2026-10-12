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

Kurallar dondurulmuştur: bir eşik değişirse o yeni bir denemedir ve deneme
defterine yazılır. Raporda her dosyanın özeti (SHA-256'nın ilk 12 hanesi) durur.
Bir bot ancak sınamayı ve ayrılmış yılı geçerse `botlar.BOTLAR`'a girer.
