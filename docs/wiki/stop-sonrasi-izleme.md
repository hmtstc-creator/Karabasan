# Stop sonrası izleme

> Stop olan işlemin izlenmesi, dersler, karar ölçütleri.
> Kaynak: CLAUDE.md'nin 9 Kasım 2026 öncesi hali (sözcüğü sözcüğüne taşındı).

**Stop sonrası izleme (11 Ekim 2026, Ahmet'in isteğiyle).** Ahmet "stop
olunca fiyatı izlemeye devam et; stopu esnetsem belki kazandırırdı, bunu
derslerine al ve kararlarını güncelle" dedi. Yapılan: `stop_sonrasi.py` canlı
stopları izler, sayfada Dersler ekranı ve Telegram'da `/dersler` gösterir,
geçmiş ölçüm raporu stop genişliğini yeniden benzetimle sınar. **Sistem stopu
kendi kendine değiştirmez** ve değiştirmemeli: karar yalnız öneridir, geniş
stoplu hal ayrı bir sanal botla denenir (3. kural ve tasarım raporundaki
"öneri ve onay" ilkesi). "Stop dar" demek bilerek zordur: en az 30 izlenmiş
stop, ortalama farkın standart hatasının en az 2 katı olması, stop başına en
az %0,15 iyileşme ve iyileşmenin en az dörtte birinin dönemin her iki
yarısından gelmesi. Neden: rastgele üretilmiş veride bile bazı seçenekler iyi
görünüyordu (ilk kural S3'e yapay veride "dar" dedi; kural bunun üzerine
sıkılaştırıldı). On bot × üç seçenek sınandığı için yine de arada bir şans eseri
"dar" çıkabilir; bu yüzden sonuç ayar değil, yeni bir sanal bot önerisidir.
Ahmet'e söylendi.

Ahmet 11 Ekim'de Tailscale bağlantısını henüz onaylamamıştı. **Sunucudaki
Claude oturumu çalışıyor (11 Ekim 2026, doğrulandı).** `claude remote-control`
gerçek sunucuda açıldı; `--spawn=same-dir` ile üçüncü soru ("Choose [1/2]")
çıkmadı. O oturum arşivdeki raporları kendisi okuyup özetini Ahmet üzerinden
bu oturuma iletiyor.
