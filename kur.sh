#!/usr/bin/env bash
# Karabasan Bot - sunucu kurulumu (Ubuntu 24.04, root olarak).
#
# Bu betik sanal sınav için gerekenleri kurar. Binance API anahtarı istemez,
# borsaya emir gönderen hiçbir şeyi açmaz. Yeniden çalıştırmak güvenlidir.
#
#   bash /opt/karabasan-bot/kur.sh
#
# Tüm çıktı /var/log/karabasan-kurulum.log dosyasına da yazılır.

set -euo pipefail

KLASOR="$(cd "$(dirname "$0")" && pwd)"
GUNLUK=/var/log/karabasan-kurulum.log
exec > >(tee -a "$GUNLUK") 2>&1

adim() { echo; echo "=== $1 ==="; }
dur() { echo; echo "KURULUM DURDU: $1"; echo "Şu dosyayı Claude'a gönder: $GUNLUK"; exit 1; }
trap 'dur "beklenmeyen hata (satır $LINENO)"' ERR

[ "$(id -u)" -eq 0 ] || dur "Bu betik root olarak çalıştırılmalı."
cd "$KLASOR"
export DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------- 1
adim "1/9 Sistem güncelleniyor"
apt-get update -y
apt-get install -y ca-certificates curl git python3 openssl ufw fail2ban unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades || true

# ---------------------------------------------------------------- 2
adim "2/9 Sunucu girişi sıkılaştırılıyor"
if [ -s /root/.ssh/authorized_keys ]; then
    cat > /etc/ssh/sshd_config.d/99-karabasan.conf <<'SSH'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
SSH
    if sshd -t; then
        systemctl reload ssh || systemctl reload sshd || true
        echo "Parolayla giriş kapatıldı; yalnız anahtarla girilir."
    else
        rm -f /etc/ssh/sshd_config.d/99-karabasan.conf
        echo "UYARI: SSH ayarı doğrulanamadı, değişiklik geri alındı."
    fi
else
    echo "UYARI: Kayıtlı giriş anahtarı bulunamadı; kilitlenmemen için parolayla giriş açık bırakıldı."
fi
ufw allow 22/tcp > /dev/null
ufw allow in on tailscale0 > /dev/null 2>&1 || true
ufw --force enable > /dev/null
echo "Güvenlik duvarı açık: dışarıdan yalnız SSH (22)."

# ---------------------------------------------------------------- 3
adim "3/9 Docker kuruluyor"
if ! command -v docker > /dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
fi
docker compose version > /dev/null || dur "Docker Compose bulunamadı."
systemctl enable --now docker > /dev/null

# ---------------------------------------------------------------- 4
adim "4/9 Özel ağ (Tailscale) kuruluyor"
if ! command -v tailscale > /dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi
if ! tailscale status > /dev/null 2>&1; then
    echo "Aşağıda çıkan bağlantıyı tarayıcında aç ve Tailscale hesabınla onayla."
    tailscale up --hostname karabasan
fi
TS_IP="$(tailscale ip -4 2> /dev/null | head -1 || true)"
[ -n "$TS_IP" ] || dur "Tailscale adresi alınamadı. 'tailscale up' komutunu çalıştırıp bağlantıyı onayla, sonra betiği yeniden başlat."
echo "Özel ağ adresi: $TS_IP"

# ---------------------------------------------------------------- 5
adim "5/9 Gizli anahtarlar üretiliyor"
if [ ! -f .env ]; then
    umask 077
    cat > .env <<ENV
FREQTRADE__API_SERVER__USERNAME=karabasan
FREQTRADE__API_SERVER__PASSWORD=$(openssl rand -hex 12)
FREQTRADE__API_SERVER__JWT_SECRET_KEY=$(openssl rand -hex 32)
FREQTRADE__API_SERVER__WS_TOKEN=$(openssl rand -hex 16)
ENV
    chmod 600 .env
    echo ".env oluşturuldu (yalnız root okuyabilir)."
else
    echo ".env zaten var, dokunulmadı."
fi

# ---------------------------------------------------------------- 6
adim "6/9 Bot yapılandırmaları üretiliyor"
mkdir -p user_data
python3 - "$TS_IP" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from karabasan.botlar import BOTLAR, ILK_PORT, VARSAYILAN_AYARLAR
yol = Path("user_data/ayarlar.json")
ayar = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else json.loads(json.dumps(VARSAYILAN_AYARLAR))
adresler = []
for sira in range(len(BOTLAR)):
    for ad in ("karabasan", sys.argv[1]):
        adresler.append(f"http://{ad}:{ILK_PORT + sira}")
ayar["panel_adresleri"] = adresler
yol.write_text(json.dumps(ayar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
python3 araclar/yapilandirma_uret.py
# Kapsayıcıdaki kullanıcı (1000) kayıt ve veritabanı yazabilsin.
chown -R 1000:1000 user_data

# ---------------------------------------------------------------- 7
adim "7/9 Hazır motor indiriliyor"
docker compose --profile arac pull -q

# ---------------------------------------------------------------- 8
adim "8/9 Uyum denemesi (yaklaşık 10-20 dakika)"
trap - ERR
if ! bash araclar/uyum_denemesi.sh; then
    chown -R 1000:1000 user_data
    echo
    echo "Uyum denemesi geçmedi; sanal botlar başlatılmadı."
    echo "Şu dosyayı Claude'a gönder: $KLASOR/user_data/logs/uyum_denemesi.txt"
    exit 1
fi
trap 'dur "beklenmeyen hata (satır $LINENO)"' ERR
chown -R 1000:1000 user_data

# ---------------------------------------------------------------- 9
adim "9/9 Sanal botlar başlatılıyor"
docker compose up -d
[ -f user_data/sinav_baslangici.txt ] || date -u '+%Y-%m-%dT%H:%M:%SZ' > user_data/sinav_baslangici.txt

# Bot ekranlarını yalnız özel ağdan erişilir kıl.
PORTLAR=$(python3 -c "
import sys; sys.path.insert(0, '.')
from karabasan.botlar import BOTLAR, ILK_PORT
print(' '.join(str(ILK_PORT + i) for i in range(len(BOTLAR))))")
ERISIM=1
for PORT in $PORTLAR; do
    tailscale serve --bg --tcp "$PORT" "tcp://127.0.0.1:$PORT" > /dev/null 2>&1 || ERISIM=0
done

echo
echo "============================================================"
echo "KURULUM TAMAM. On sanal bot çalışıyor; hiçbir emir borsaya gitmez."
echo "Sınav başlangıcı: $(cat user_data/sinav_baslangici.txt)"
echo
if [ "$ERISIM" -eq 1 ]; then
    echo "Bot ekranları (Tailscale açıkken tarayıcıdan):"
    echo "  http://karabasan:8081  ...  http://karabasan:8090"
else
    echo "UYARI: Özel ağ yönlendirmesi kurulamadı; bot ekranlarına şimdilik erişilemez."
    echo "Botlar çalışıyor. Bu satırı Claude'a ilet."
fi
echo "Kullanıcı adı: karabasan"
echo "Parola: şu komutla görürsün ->  grep PASSWORD $KLASOR/.env"
echo "Uyum denemesi raporu: $KLASOR/user_data/logs/uyum_denemesi.txt"
echo "============================================================"
