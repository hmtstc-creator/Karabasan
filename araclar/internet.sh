#!/usr/bin/env bash
# İnternetten erişim (Ahmet'in isteğiyle, 6 Kasım 2026): sonuç sayfasını kullanıcı adı ve
# parola arkasında, şifreli bağlantıyla (https) herkese açık bir adreste yayınlar.
#
#   Adres:    https://<sunucu-ip-tireli>.sslip.io  (ücretsiz; alan adı satın alınmadı)
#   Kullanıcı: ahmet   Parola: sunucuda üretilir, depoya girmez, Telegram'dan bir kez gelir
#   Araç:     Caddy (docker); sertifikayı kendisi alır ve yeniler
#
# Yalnız okuma: GET / HEAD dışındaki her istek 405 alır. Sayfa yalnız sanal sonuçları gösterir.
# Yeniden çalıştırmak güvenlidir (kur.sh her güncellemede çağırır). Çıkış kodu: 0 = yayında, 1 = değil.

set -uo pipefail
cd "$(dirname "$0")/.."

DURUM=/var/lib/karabasan
KLASOR="$DURUM/kapi"
KAP=karabasan-kapi
KULLANICI=ahmet
mkdir -p "$KLASOR"
chmod 700 "$KLASOR"

if [ -z "${TELEGRAM_TOKEN:-}" ] && [ -f telegram.env ]; then
    TELEGRAM_TOKEN="$(sed -n 's/^TELEGRAM_TOKEN=//p' telegram.env | head -1)"
    export TELEGRAM_TOKEN
fi
bildir() { python3 -m karabasan.haberci gonder "$1" > /dev/null 2>&1 || true; }
bir_kez() { # bir_kez <bayrak> <ileti>: aynı sorunu her 5 dakikada yeniden bildirme
    [ -f "$DURUM/internet_$1" ] && return 0
    bildir "$2"
    touch "$DURUM/internet_$1"
}

command -v docker > /dev/null 2>&1 || { echo "Docker yok."; exit 1; }

# 1) Genel IP adresi -> sslip.io adı (1.2.3.4 -> 1-2-3-4.sslip.io)
IP="$(curl -4fsS --max-time 10 https://api.ipify.org 2> /dev/null || true)"
if ! printf '%s' "$IP" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
    IP="$(curl -4fsS --max-time 10 https://ifconfig.me 2> /dev/null || true)"
fi
if ! printf '%s' "$IP" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
    echo "Genel IP adresi öğrenilemedi; internet yayını atlandı."
    exit 1
fi
ADRES="$(printf '%s' "$IP" | tr . -).sslip.io"

# 2) 80 ve 443 boş mu? (Kendi kapsayıcımız dinliyorsa sorun yok.)
if ! docker ps --format '{{.Names}}' 2> /dev/null | grep -qx "$KAP"; then
    if ss -H -tln 2> /dev/null | awk '{print $4}' | grep -Eq '[:.](80|443)$'; then
        echo "80 ya da 443 başka bir şey tarafından kullanılıyor; internet yayını atlandı."
        bir_kez kapi_dolu "İnternet yayını kurulamadı: sunucuda 80 ya da 443 numaralı kapıyı başka bir program kullanıyor. Botlar etkilenmedi. Bana haber ver, birlikte bakalım."
        exit 1
    fi
fi

# 3) Parola: bir kez üretilir, sonra aynı kalır. Düz hali yalnız root okuyabilen bir dosyada.
PAROLA_DOSYASI="$DURUM/internet_parola"
YENI_PAROLA=0
if [ ! -s "$PAROLA_DOSYASI" ]; then
    ( umask 077; openssl rand -hex 16 > "$PAROLA_DOSYASI" )
    rm -f "$KLASOR/parola_ozeti"
    YENI_PAROLA=1
fi
chmod 600 "$PAROLA_DOSYASI"
PAROLA="$(cat "$PAROLA_DOSYASI")"

# Parolanın bcrypt özeti (aynı parola için tuz değişmesin diye saklanır).
if [ ! -s "$KLASOR/parola_ozeti" ]; then
    OZET="$(docker run --rm caddy:2 caddy hash-password --plaintext "$PAROLA" 2> /dev/null | tail -1)"
    if [ -z "$OZET" ]; then
        echo "Parola özeti üretilemedi (caddy görüntüsü indirilemedi mi?)."
        bir_kez ozet_yok "İnternet yayını kurulamadı: Caddy görüntüsü indirilemedi. Botlar etkilenmedi; yeni bir sürümle yeniden denenecek."
        exit 1
    fi
    ( umask 077; printf '%s\n' "$OZET" > "$KLASOR/parola_ozeti" )
fi
OZET="$(cat "$KLASOR/parola_ozeti")"

# 4) Caddy ayarı. Parolanın özeti burada olduğu için dosya depoda değil, yalnız sunucuda durur.
YENI_AYAR="{
	admin off
}

$ADRES {
	encode zstd gzip
	@yazma not method GET HEAD
	respond @yazma 405
	header {
		Strict-Transport-Security \"max-age=31536000\"
		X-Content-Type-Options nosniff
		X-Frame-Options DENY
		Referrer-Policy no-referrer
		-Server
	}
	basic_auth {
		$KULLANICI $OZET
	}
	reverse_proxy 127.0.0.1:8080
}"
AYAR="$KLASOR/Caddyfile"
DEGISTI=0
if [ "$(cat "$AYAR" 2> /dev/null)" != "$YENI_AYAR" ]; then
    ( umask 077; printf '%s\n' "$YENI_AYAR" > "$AYAR" )
    DEGISTI=1
fi

# 5) Güvenlik duvarı: yalnız 80 (sertifika doğrulaması ve https'e yönlendirme) ve 443.
ufw allow 80/tcp > /dev/null 2>&1 || true
ufw allow 443/tcp > /dev/null 2>&1 || true

# 6) Kapsayıcı. Ana makinenin ağını kullanır; böylece 127.0.0.1:8080'deki sayfaya ulaşır.
if docker ps -a --format '{{.Names}}' | grep -qx "$KAP"; then
    if ! docker ps --format '{{.Names}}' | grep -qx "$KAP"; then
        docker start "$KAP" > /dev/null 2>&1 || true
    elif [ "$DEGISTI" -eq 1 ]; then
        docker restart "$KAP" > /dev/null 2>&1 || true
    fi
else
    docker run -d --name "$KAP" --restart unless-stopped --network host \
        -v "$AYAR":/etc/caddy/Caddyfile:ro -v karabasan-kapi-veri:/data caddy:2 > /dev/null 2>&1 || {
        echo "Caddy başlatılamadı."
        bir_kez baslamadi "İnternet yayını kurulamadı: Caddy kapsayıcısı başlamadı. Botlar etkilenmedi."
        exit 1
    }
fi

# 7) Denetim: sertifika alınıp sayfa parolayla açılıyor mu? (en çok ~2 dakika)
YETKI="$(printf '%s:%s' "$KULLANICI" "$PAROLA" | base64 | tr -d '\n')"
TAMAM=0
for _ in $(seq 1 24); do
    if curl -fsS --max-time 10 -H "Authorization: Basic $YETKI" "https://$ADRES/saglik" > /dev/null 2>&1; then
        TAMAM=1
        break
    fi
    sleep 5
done

if [ "$TAMAM" -eq 1 ]; then
    echo "İnternet yayını hazır: https://$ADRES"
    if [ ! -f "$DURUM/internet_bildirildi" ] || [ "$YENI_PAROLA" -eq 1 ]; then
        bildir "Sonuç sayfası internete açıldı (şifreli bağlantı, parolalı).

Adres: https://$ADRES
Kullanıcı: $KULLANICI
Parola: $PAROLA

Bu mesajı kimseyle paylaşma. Parolayı değiştirmek ya da yayını kapatmak istersen bana söyle. Sayfa yalnız sanal sonuçları gösterir; hiçbir ayarı değiştirmez."
        touch "$DURUM/internet_bildirildi"
    fi
    exit 0
fi

echo "UYARI: https://$ADRES parolayla açılmadı."
docker logs --tail 15 "$KAP" 2>&1 | sed 's/^/  /' || true
bir_kez acilmadi "İnternet yayını kuruldu ama adres henüz açılmıyor (sertifika alınamamış olabilir; ücretsiz sertifika servisleri bazen sınır koyar). Botlar etkilenmedi. 'docker logs karabasan-kapi' çıktısını sunucudaki Claude'a okutabilirsin; birkaç saat sonra kendiliğinden yeniden denenir."
exit 1
