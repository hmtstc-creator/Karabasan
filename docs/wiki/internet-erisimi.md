# İnternetten parolalı erişim

> Caddy, sslip.io, parola.
> Kaynak: CLAUDE.md'nin 9 Kasım 2026 öncesi hali (sözcüğü sözcüğüne taşındı).

**İnternetten parolalı erişim (6 Kasım 2026, Ahmet'in açık isteği; önceki "internete kapı açılmaz" kuralının tek istisnası).**
`araclar/internet.sh` (kur.sh çağırır): Caddy kapsayıcısı (`karabasan-kapi`, ana makine ağı) sonuç sayfasını
(127.0.0.1:8080) `https://<ip-tireli>.sslip.io` adresinde yayınlar (ücretsiz ad; Ahmet alan adı almadı). Kullanıcı `ahmet`;
parola sunucuda üretilir (`/var/lib/karabasan/internet_parola`, root 600), depoya girmez, Ahmet'e Telegram'dan bir kez gelir.
Yalnız GET / HEAD, geri kalanı 405. ufw 80 ve 443 açılır. Yanlış parola denemesi sınırlanmaz (uzun rastgele parola, 128 bit);
istenirse fail2ban eklenebilir. Sertifika sslip.io'nun ortak sınırına takılabilir (Caddy ZeroSSL'e düşer). Yalnız sahte
`docker` / `curl` / `ufw` ile prova edildi; **gerçek sunucuda ilk kez çalışacak**: sertifika alımı, 80 / 443'ün boş olması
(PlanningExpert'in Tailscale kapsayıcısı ana makine kapılarını tutmamalı), Hetzner bulut güvenlik duvarının bu kapıları
engellememesi. Kapatmak için `internet.sh`'ı `kur.sh`'tan çıkar ve sunucuda kapsayıcıyı durdur.
