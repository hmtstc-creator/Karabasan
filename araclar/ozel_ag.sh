#!/usr/bin/env bash
# Özel ağ (Tailscale): sunucuyu Ahmet'in özel ağına bağlar ve sonuç sayfası ile
# bot ekranlarını YALNIZ o ağdan erişilir kılar. İnternete hiçbir kapı açmaz.
#
#   bash araclar/ozel_ag.sh              durumu denetle, gerekeni yap, hemen dön
#   bash araclar/ozel_ag.sh --bekle 600  onay bağlantısını gönder, onayı bekle
#
# Yeniden çalıştırmak güvenlidir; güncelleme zamanlayıcısı 5 dakikada bir çağırır.
# Çıkış kodu: 0 = ağ bağlı, 1 = henüz bağlı değil.

set -uo pipefail
cd "$(dirname "$0")/.."

DURUM_KLASORU=/var/lib/karabasan
BEKLE=0
if [ "${1:-}" = "--bekle" ]; then BEKLE="${2:-600}"; fi
mkdir -p "$DURUM_KLASORU"

if [ -z "${TELEGRAM_TOKEN:-}" ] && [ -f telegram.env ]; then
    TELEGRAM_TOKEN="$(sed -n 's/^TELEGRAM_TOKEN=//p' telegram.env | head -1)"
    export TELEGRAM_TOKEN
fi
bildir() { python3 -m karabasan.haberci gonder "$1" > /dev/null 2>&1 || true; }

command -v tailscale > /dev/null 2>&1 || { echo "Tailscale kurulu değil."; exit 1; }

# Tailscale'in durumundan tek bir alanı okur (BackendState, AuthURL).
alan() {
    tailscale status --json 2> /dev/null | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get(sys.argv[1]) or "")
except Exception:
    print("")' "$1"
}

bagli_mi() { [ "$(alan BackendState)" = "Running" ]; }

yonlendir() {
    # Sonuç sayfası (8080) ve bot ekranları sunucunun içinde yalnız 127.0.0.1'i
    # dinler. Buradaki küçük köprüler (socat) aynı kapıları sunucunun özel ağ
    # adresinde de dinler; internete bakan adreste hiçbir şey dinlemez.
    local IP="$1" PORTLAR PORT
    [ -n "$IP" ] || return 1
    if ! command -v socat > /dev/null 2>&1; then
        DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y socat > /dev/null 2>&1 || return 1
    fi
    PORTLAR="8080 $(python3 -c "
import sys; sys.path.insert(0, '.')
from karabasan.botlar import BOTLAR, ILK_PORT
print(' '.join(str(ILK_PORT + i) for i in range(len(BOTLAR))))")"
    ufw allow in on tailscale0 > /dev/null 2>&1 || true
    local BIRIM=/etc/systemd/system/karabasan-kopru@.service YENI_BIRIM
    YENI_BIRIM='[Unit]
Description=Karabasan: %i numarali kapiyi ozel aga tasir
After=tailscaled.service docker.service

[Service]
EnvironmentFile=/etc/karabasan-ozel-ag.env
ExecStart=/usr/bin/socat TCP4-LISTEN:%i,bind=${OZEL_AG_IP},reuseaddr,fork TCP4:127.0.0.1:%i
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target'
    local DEGISTI=0
    if [ "$(cat /etc/karabasan-ozel-ag.env 2> /dev/null)" != "OZEL_AG_IP=$IP" ] \
            || [ "$(cat "$BIRIM" 2> /dev/null)" != "$YENI_BIRIM" ]; then
        echo "OZEL_AG_IP=$IP" > /etc/karabasan-ozel-ag.env
        printf '%s\n' "$YENI_BIRIM" > "$BIRIM"
        systemctl daemon-reload
        DEGISTI=1
    fi
    for PORT in $PORTLAR; do
        # Adres ya da köprü tanımı değiştiyse hepsi yeniden başlar; değişmediyse yalnız
        # çalışmayan köprüler açılır (örneğin sonradan eklenen bir botun kapısı).
        if [ "$DEGISTI" -eq 1 ] || ! systemctl is-active --quiet karabasan-kopru@"$PORT".service; then
            systemctl enable karabasan-kopru@"$PORT".service > /dev/null 2>&1 || true
            systemctl restart karabasan-kopru@"$PORT".service || true
        fi
    done
    # Denetim: sonuç sayfası özel ağ adresinden yanıt veriyor mu?
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        if curl -fsS --max-time 5 "http://$IP:8080/saglik" > /dev/null 2>&1; then return 0; fi
        sleep 3
    done
    return 1
}

baglandi() {
    local IP
    IP="$(tailscale ip -4 2> /dev/null | head -1)"
    if yonlendir "$IP"; then
        if [ ! -f "$DURUM_KLASORU/ozel_ag_bildirildi" ]; then
            echo "Özel ağ bağlı: $IP"
            bildir "Özel ağ bağlandı. Telefonunda Tailscale açıkken sonuç sayfası:
http://karabasan:8080

Bu ad açılmazsa şunu dene: http://$IP:8080
İkisi de açılmazsa bana haber ver; o sırada /sayfa komutu aynı sayfayı dosya olarak yollar."
            touch "$DURUM_KLASORU/ozel_ag_bildirildi"
        fi
    elif [ ! -f "$DURUM_KLASORU/ozel_ag_sorun_bildirildi" ]; then
        echo "UYARI: sonuç sayfası özel ağ adresinden ($IP) yanıt vermiyor."
        systemctl --no-pager status karabasan-kopru@8080.service 2>&1 | tail -8 || true
        bildir "Özel ağ bağlandı ama sonuç sayfası ağa açılamadı. Botlar bundan etkilenmez. /kurulum yazıp gelen dosyayı Claude'a ilet; o sırada /sayfa komutu sayfayı dosya olarak yollar."
        touch "$DURUM_KLASORU/ozel_ag_sorun_bildirildi"
    fi
}

if bagli_mi; then
    baglandi
    exit 0
fi

# Henüz bağlı değil: giriş sürecini başlat (zaten sürüyorsa yenisini başlatma).
systemctl enable --now tailscaled > /dev/null 2>&1 || true
if ! pgrep -f "tailscale up" > /dev/null 2>&1; then
    # 9>&- : kurulum kilidini bu arka plan süreci devralmasın.
    nohup setsid tailscale up --hostname=karabasan > /run/karabasan-tailscale.txt 2>&1 < /dev/null 9>&- &
fi

# Onay bağlantısının çıkmasını bekle (en fazla 60 saniye).
ADRES=""
for _ in $(seq 1 30); do
    ADRES="$(alan AuthURL)"
    if [ -z "$ADRES" ]; then
        ADRES="$(grep -Eo 'https://login\.tailscale\.com/[A-Za-z0-9/_-]+' /run/karabasan-tailscale.txt 2> /dev/null | head -1 || true)"
    fi
    if [ -n "$ADRES" ] || bagli_mi; then break; fi
    sleep 2
done

if [ -n "$ADRES" ] && [ "$(cat "$DURUM_KLASORU/ozel_ag_adresi" 2> /dev/null)" != "$ADRES" ]; then
    echo "Tailscale onay bağlantısı gönderiliyor."
    bildir "Senden istediğim tek şey bu:

1. Telefonunda Tailscale uygulaması kurulu ve giriş yapılmış olsun.
2. Şu bağlantıya dokun, aynı hesapla giriş yap ve \"Connect\" düğmesine bas:
$ADRES

Bu, sunucuyu yalnız senin telefonunun görebildiği özel ağa ekler. Onaylamasan da kurulum devam eder; bağlantı sonra da geçerlidir."
    echo "$ADRES" > "$DURUM_KLASORU/ozel_ag_adresi"
elif [ -z "$ADRES" ]; then
    echo "Tailscale onay bağlantısı alınamadı."
    tail -5 /run/karabasan-tailscale.txt 2> /dev/null || true
fi

BITIS=$(( $(date +%s) + BEKLE ))
while [ "$(date +%s)" -lt "$BITIS" ]; do
    if bagli_mi; then break; fi
    sleep 5
done

if bagli_mi; then
    baglandi
    exit 0
fi
exit 1
