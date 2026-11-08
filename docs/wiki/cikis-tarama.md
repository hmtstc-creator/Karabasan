# İz süren stop ve 20 varyasyonluk çıkış taraması

> İz süren stopun eklenmesi, tarama sonucu.
> Kaynak: CLAUDE.md'nin 9 Kasım 2026 öncesi hali (sözcüğü sözcüğüne taşındı).

**İz süren stop, %3 stop, süre sınırı yok + 20 varyasyonluk tarama (12 Ekim 2026,
Ahmet'in isteği).** Ahmet: "Sniper'daki limitli girişi izleyelim. Belki kâr hedefini
2 yapsak yakalıyorduk, belki çok erken çıkıyoruz; trailing stop ekle, 1,2'de tetiklensin
0,9'a düşünce kapatsın, stop %3, saat limiti koyma; botları böyle güncelle. Ayrıca 20
farklı varyasyonla bir senelik test yapıp en kazançlıyı bul." Yapılan:
- Çıkış alanları: `kar_hedefi_yuzde` ve `sure_asimi_dakika` artık isteğe bağlı; yeni
  `iz_suren_stop` (`tetik_yuzde` 0,1–20, `mesafe_yuzde` 0,05–10, mesafe < tetik).
  Stoptan başka en az bir çıkış yolu zorunlu. `cikis_metni` düz Türkçe anlatır.
  `basabas_orani` sabit hedef yoksa None.
- Beş canlı kuralın çıkışı: `{"zarar_durdur_yuzde": 3.0, "iz_suren_stop": {"tetik_yuzde":
  1.2, "mesafe_yuzde": 0.3}}`. Tetik komisyon sonrası kârdır (motorun
  `trailing_stop_positive_offset`'i gibi); seviye en iyi fiyatın %0,3 gerisi
  (`trailing_stop_positive`). İlk anda çıkış ≈ fiyat %1,3 → ×0,997 ≈ %1,0 brüt, %0,9 net.
  Motor: `trailing_stop = True`, `trailing_only_offset_is_reached = True`,
  `minimal_roi = {"0": 100}` (hedef fiilen kapalı), `custom_exit` süre yoksa None.
- Benzetim: etkin stop = sabit stop ile iz seviyesinin yakını; önceki mumların en iyi
  fiyatından; mum stopun ötesinde açılırsa açılıştan kapanır (neden `iz_suren_stop`).
  Limitli girişte dolduğu mumun tepesi en iyi fiyata katılmaz. Motorun geçmiş testi
  mum içinde daha iyimser olabilir; 16. uyum denemesinde eşleştirmede görülür
  (`trailing_stop_loss` → `iz_suren_stop`, `exit_signal` → `cikis_sinyali`).
- 12 aylık testin "stop = hedef" sütunu sabit hedef / süre olmayan kuralları atlar. Stop sonrası
  izleme 13 Ekim 2026'dan beri (Ahmet "stop dersi bütün botlarda görülmeli" dedi) iz süren stoplu,
  süresiz botları da izler: geniş stoplu hal botun kendi iz süren stop kuralıyla (benzetimdeki gibi,
  tepe stopu sonraki mumdan taşır) yeniden oynatılır; izleme girişten 72 saat, stoptan en az 24 saat
  sürer (`IZLEME_SURESIZ`, `IZLEME_STOP_SONRASI`), o anda açık kalan seçenek son fiyattan "açık"
  sayılır; "hedefi gördü" yerine "tetiğe ulaştı" (`esik` = "iz"). Dersler ekranı her bota kart
  gösterir. Yalnız çıkış sinyalli ya da işlem başına stoplu (ATR / R) kurallar atlanır (canlıda yok).
  Gerçek Binance mumlarıyla sunucuda ilk kez çalışacak (5 dakikalık mum, 72 saat ≈ 864 mum).
- Tarama: `karabasan/tarama.py` (Yapı tablosunda). Varyasyonlar: iz süren stop tetik
  {0,8; 1,2; 2} × mesafe {0,3; 0,6} × stop {1,5; 3} süresiz (12), V01 ile aynı iz /
  stop + 4 s ve 24 s süre (2), sabit hedef: 0,8/3/4 s (eski SM), 1,2/1,5/3 s (eski
  Sniper), 2/3/süresiz (Ahmet'in "hedef 2"si), 2/2/24 s, 1/1/4 s, 3/1,5/24 s (6).
  5 bot × 20 = 100 deneme; yapay veride ~110 sn. Rapor: her bot için 20 satır (yıl,
  ilk 9 ay, son 3 ay, en büyük düşüş), seçim dönemine göre en iyisi ve doğrulaması,
  yıl boyu en iyisi ("ezbere açık"), kaç denemenin artıda olduğu. Rastgele veride 100
  denemenin hiçbiri artıda değil (beklenen).
- `UYUM_SURUMU=16`, `YILLIK_SURUMU=5`, `TARAMA_SURUMU=1`. Süresiz işlemler yüzünden
  botlar daha az ve daha uzun işlem açar; 20 pozisyon sınırı dolabilir.
- **Gerçek motorda ilk kez:** iz süren stopun bu motorda canlı ve geçmiş testinde nasıl
  uygulandığı, `minimal_roi = {"0": 100}`, süresiz `custom_exit`.

**Çıkış taramasının ilk sonucu (11 Ekim 2026 20:54 UTC, Ahmet iletti; 11.10.2025–
11.10.2026, seçim 12.07.2026'ya kadar).** 100 denemenin 25'i yıl sonunda artıda; hem
ilk 9 ayda hem son 3 ayda artıda yalnız 2 (SMD V07 +5,41 / +1,23; SM V20 +1,62 /
+3,82): şanstan ayırt edilemez. Dürüst seçim (SMK V10) son 3 ayda −18,83.
- Tutarlı ders: beş botta da iz süren stoplu ayarlar sabit küçük hedeflerin (V15 eski
  SM, V16 eski Sniper, V19) belirgin önünde; eski ayarlar her botta en kötüler arasında.
  Şimdiki V01 yıl sonunda SM −9,88, SMK +14,16, SMD −0,37, SMDK +17,84, Sniper
  −18,19 (toplam ≈ +3,6); aynı girişler eski çıkışlarla ≈ −166. Yani "erken çıkıyoruz"
  gözlemi doğru çıktı; ama kenar yaratmadı, kaybı sıfıra çekti.
- Açığa satış botlarının (SMK, SMDK) artısı tamamen ilk 9 aydan; son 3 ayda 20
  varyasyonun 20'si de ekside. Piyasa yönü (düşüş dönemi) gibi görünüyor, beceri değil.
- Son 3 ayda V01 beş botta da ekside (toplam ≈ −59,9).
- Ahmet'e öneri: ayar değiştirme (en iyi görünenler doğrulamada kaybediyor); V01'de
  kal, canlı sonucu izle. Ayar değişikliği yalnız Ahmet isterse.
