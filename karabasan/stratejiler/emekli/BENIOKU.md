# Emekli stratejiler

Artık hiçbir sanal botun çalıştırmadığı kural dosyaları. Kayıt ve karşılaştırma
için saklanır; `kural.tum_kurallar()` bu klasörü okumaz.

| Kod | Ad | Neden çıkarıldı |
| --- | --- | --- |
| S2K | Dip kırılımını sat | 12 Ekim 2026: 30 günlük gerçek veride en çok kaybeden iki stratejiden biri (bağımsız benzetim 189 işlem, %31 kazanma, −17,61 USDT). Yerine S7K geldi. |
| S6 | Likidite avı sonrası alım | 12 Ekim 2026: aynı ölçümde en çok kaybeden ikinci strateji (hazır motor 211 işlem, −18,11 USDT; BTC hariç). Yerine S7 geldi. |

| S1, S1K, S2, S3, S4, S5, S5K, S6K, S7, S7K | 12 Ekim 2026 (Ahmet'in isteği): 12 aylık geçmiş testinde (11.10.2025–11.10.2026, hedef %0,8, stop %3) hepsi ekside, hiçbiri dört çeyreğin üçünde artıda değil. İşlem başına net −%0,08 ile −%0,14; komisyon öncesi sıfıra yakın. Yalnız Smartmoney (SM, SMK) kaldı. |

Dosyalar çıkarıldıkları andaki ayarlarıyla durur (hedef ve stop o günkü değerler).
