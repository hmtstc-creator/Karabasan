#!/usr/bin/env bash
# Karabasan Bot - sunucu kurulumu (Ubuntu 24.04, root olarak).
#
# Kimse başında beklemeden çalışır: soru sormaz, her adımı Telegram'a yazar.
# Yalnız sanal sınav için gerekenleri kurar; Binance API anahtarı istemez,
# borsaya emir gönderen hiçbir şeyi açmaz.
#
# Yeniden çalıştırmak güvenlidir. Hem ilk kurulumda (sunucu açılırken) hem de
# her güncellemede (araclar/oto_guncelle.sh) aynı betik çalışır; yapılmış
# adımları atlar.
#
# Telegram kodu /root/karabasan.env dosyasından okunur (TELEGRAM_TOKEN=...).
# Kayıt: user_data/logs/kurulum.txt (Telegram'da /kurulum yazınca gelir).

set -Eeuo pipefail

KLASOR="$(cd "$(dirname "$0")" && pwd)"
DURUM_KLASORU=/var/lib/karabasan
KILIT=/run/karabasan.kilit
ADIM="başlangıç"

bildir() { python3 -m karabasan.haberci gonder "$1" > /dev/null 2>&1 || true; }
belge() { python3 -m karabasan.haberci belge "$1" "$2" > /dev/null 2>&1 || true; }
adim() { ADIM="$1"; echo; echo "=== $1 === $(date -u '+%H:%M:%S UTC')"; }

dur() {
    trap - ERR
    echo
    echo "KURULUM DURDU: $1"
    git rev-parse HEAD > "$DURUM_KLASORU/son_deneme" 2> /dev/null || true
    bildir "Kurulum durdu: $1

Bir şey yapmana gerek yok, yalnız birazdan gelecek dosyayı Claude'a ilet. Claude düzeltmeyi gönderince sunucu 5 dakika içinde kendiliğinden yeniden dener."
    belge "$KLASOR/user_data/logs/kurulum.txt" "Kurulum kaydı. Bu dosyayı Claude'a ilet."
    exit 1
}

main() {
    [ "$(id -u)" -eq 0 ] || { echo "Bu betik root olarak çalıştırılmalı."; exit 1; }
    cd "$KLASOR"
    export HOME=/root DEBIAN_FRONTEND=noninteractive
    export PATH="${PATH:+$PATH:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    mkdir -p user_data/logs "$DURUM_KLASORU"

    # Aynı anda tek kurulum çalışsın (güncelleme zamanlayıcısı ile çakışmasın).
    if [ "${KARABASAN_KILIT_BENDE:-0}" != "1" ]; then
        exec 9> "$KILIT"
        flock -n 9 || { echo "Başka bir kurulum zaten çalışıyor."; exit 0; }
    fi

    exec > >(tee -a "$KLASOR/user_data/logs/kurulum.txt") 2>&1
    trap 'dur "beklenmeyen hata (adım: $ADIM, satır $LINENO)"' ERR
    echo
    echo "##### Karabasan kurulumu $(date -u '+%Y-%m-%d %H:%M UTC') sürüm $(git rev-parse --short HEAD 2> /dev/null || echo '?') #####"

    # Telegram kodu: yalnız biçimi doğruysa kullanılır.
    TELEGRAM_TOKEN=""
    if [ -f /root/karabasan.env ]; then
        TELEGRAM_TOKEN="$(sed -n 's/^[[:space:]]*TELEGRAM_TOKEN=//p' /root/karabasan.env | head -1 | tr -d ' \r"'"'")"
    fi
    if ! printf '%s' "$TELEGRAM_TOKEN" | grep -Eq '^[0-9]+:[A-Za-z0-9_-]{30,}$'; then
        [ -z "$TELEGRAM_TOKEN" ] || echo "UYARI: Telegram kodu beklenen biçimde değil; bildirimler kapalı."
        TELEGRAM_TOKEN=""
    fi
    export TELEGRAM_TOKEN

    local ILK=1
    if [ -f user_data/kurulum_tamam ]; then ILK=0; fi

    # ------------------------------------------------------------ 1
    adim "1/10 Kendiliğinden güncelleme kuruluyor"
    # En başta kurulur: sonraki adımlardan biri takılırsa, Claude'un gönderdiği
    # düzeltme sunucuya kendiliğinden ulaşır.
    cat > /etc/systemd/system/karabasan-guncelle.service <<UNIT
[Unit]
Description=Karabasan: yeni kodu al, gerekeni yeniden baslat
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
Environment=HOME=/root
ExecStart=/bin/bash $KLASOR/araclar/oto_guncelle.sh
UNIT
    cat > /etc/systemd/system/karabasan-guncelle.timer <<'UNIT'
[Unit]
Description=Karabasan: 5 dakikada bir guncelleme denetimi

[Timer]
OnBootSec=3min
OnUnitActiveSec=5min
RandomizedDelaySec=20

[Install]
WantedBy=timers.target
UNIT
    systemctl daemon-reload
    systemctl enable --now karabasan-guncelle.timer > /dev/null 2>&1
    if [ "$ILK" -eq 1 ]; then
        bildir "Sunucu açıldı, kurulum başladı. Yaklaşık 30-40 dakika sürer; her adımı buraya yazacağım.

Senden tek bir şey isteyeceğim: birazdan göndereceğim Tailscale bağlantısına dokunup onaylaman."
    fi

    # ------------------------------------------------------------ 2
    adim "2/10 Sistem paketleri"
    if [ ! -f "$DURUM_KLASORU/paketler_tamam" ]; then
        apt-get -o DPkg::Lock::Timeout=600 update -y
        apt-get -o DPkg::Lock::Timeout=600 install -y \
            ca-certificates curl git python3 openssl ufw fail2ban unattended-upgrades tzdata socat
        dpkg-reconfigure -f noninteractive unattended-upgrades || true
        touch "$DURUM_KLASORU/paketler_tamam"
    else
        echo "Paketler kurulu, atlandı."
    fi

    # ------------------------------------------------------------ 3
    adim "3/10 Güvenlik duvarı"
    ufw default deny incoming > /dev/null
    ufw default allow outgoing > /dev/null
    ufw allow in on tailscale0 > /dev/null 2>&1 || true
    if [ -s /root/.ssh/authorized_keys ]; then
        # Giriş anahtarı tanımlıysa SSH açık kalır, ama yalnız anahtarla girilir.
        cat > /etc/ssh/sshd_config.d/99-karabasan.conf <<'SSH'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
SSH
        if sshd -t; then
            systemctl reload ssh || systemctl reload sshd || true
        else
            rm -f /etc/ssh/sshd_config.d/99-karabasan.conf
            echo "UYARI: SSH ayarı doğrulanamadı, değişiklik geri alındı."
        fi
        ufw allow 22/tcp > /dev/null
        echo "Dışarıdan yalnız anahtarla SSH (22) açık."
    else
        # Giriş anahtarı yok: parolayla SSH internete açık bırakılmaz.
        # Sunucuya gerekirse sağlayıcının web konsolundan ya da özel ağdan girilir.
        ufw delete allow 22/tcp > /dev/null 2>&1 || true
        echo "Dışarıdan hiçbir kapı açık değil (SSH dahil)."
    fi
    ufw --force enable > /dev/null

    # ------------------------------------------------------------ 4
    adim "4/10 Docker"
    if ! command -v docker > /dev/null 2>&1; then
        curl -fsSL https://get.docker.com -o /tmp/docker-kur.sh
        sh /tmp/docker-kur.sh
        rm -f /tmp/docker-kur.sh
    fi
    docker compose version > /dev/null || dur "Docker Compose bulunamadı."
    systemctl enable --now docker > /dev/null 2>&1
    if [ "$ILK" -eq 1 ]; then
        bildir "Adım 4/10 tamam: sistem güncellendi, güvenlik duvarı açıldı, Docker kuruldu."
    fi

    # ------------------------------------------------------------ 5
    adim "5/10 Gizli dosyalar"
    umask 077
    if [ ! -f .env ]; then
        cat > .env <<ENV
FREQTRADE__API_SERVER__USERNAME=karabasan
FREQTRADE__API_SERVER__PASSWORD=$(openssl rand -hex 12)
FREQTRADE__API_SERVER__JWT_SECRET_KEY=$(openssl rand -hex 32)
FREQTRADE__API_SERVER__WS_TOKEN=$(openssl rand -hex 16)
ENV
        echo ".env oluşturuldu (yalnız root okuyabilir)."
    else
        echo ".env zaten var, dokunulmadı."
    fi
    # Telegram kodunu yalnız haberci servisi görür.
    printf 'TELEGRAM_TOKEN=%s\n' "$TELEGRAM_TOKEN" > telegram.env
    chmod 600 .env telegram.env
    umask 022

    # ------------------------------------------------------------ 6
    adim "6/10 Bot yapılandırmaları"
    local TS_IP=""
    TS_IP="$(tailscale ip -4 2> /dev/null | head -1 || true)"
    python3 - "$TS_IP" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from karabasan.botlar import BOTLAR, ILK_PORT
# Bu dosya yalnız sunucuya özel değerleri taşır; gerisi depodaki başlangıç değerleridir.
yol = Path("user_data/ayarlar.json")
ayar = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}
adlar = ["karabasan"] + ([sys.argv[1]] if sys.argv[1] else [])
ayar["panel_adresleri"] = [
    f"http://{ad}:{ILK_PORT + sira}" for sira in range(len(BOTLAR)) for ad in adlar
]
yol.write_text(json.dumps(ayar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
    python3 araclar/yapilandirma_uret.py
    # Kapsayıcıdaki kullanıcı (1000) kayıt ve veritabanı yazabilsin.
    chown -R 1000:1000 user_data

    # ------------------------------------------------------------ 7
    adim "7/10 Hazır motor indiriliyor"
    # Motor yalnız ilk kurulumda indirilir. Sonraki güncellemelerde kendiliğinden
    # yenilenmez: sınav sürerken motorun sürümü değişmemeli.
    local GORUNTU
    GORUNTU="$(sed -n 's/^GORUNTU = "\(.*\)"$/\1/p' araclar/yapilandirma_uret.py | head -1)"
    if ! docker image inspect "$GORUNTU" > /dev/null 2>&1; then
        docker compose --profile arac pull -q
    else
        echo "Motor zaten indirilmiş ($GORUNTU), atlandı."
    fi
    # Sonuç sayfası botlardan önce açılır.
    docker compose up -d kayitci panel

    # ------------------------------------------------------------ 8
    adim "8/10 Özel ağ (Tailscale)"
    if ! command -v tailscale > /dev/null 2>&1; then
        curl -fsSL https://tailscale.com/install.sh -o /tmp/tailscale-kur.sh
        sh /tmp/tailscale-kur.sh
        rm -f /tmp/tailscale-kur.sh
    fi
    if [ "$ILK" -eq 1 ]; then
        # Bağlantıyı gönderebilmek için sahibin Telegram'da "Başlat"a basmış olması gerekir.
        if python3 -m karabasan.haberci bekle 600; then
            bildir "Seni tanıdım. Bundan sonra yalnız seni dinlerim."
        else
            echo "Telegram'da henüz Başlat'a basılmadı; beklemeden devam."
        fi
    fi
    # Haberci servisi sahibi beklemeyi bitirdikten sonra açılır; ikisi aynı anda
    # Telegram'ı dinlerse birbirinin isteğini keser.
    docker compose up -d haberci
    if [ "$ILK" -eq 1 ]; then
        bash araclar/ozel_ag.sh --bekle 600 || echo "Özel ağ henüz onaylanmadı; kurulum beklemeden devam ediyor."
    else
        bash araclar/ozel_ag.sh || true
    fi

    # ------------------------------------------------------------ 9
    adim "9/10 Uyum denemesi"
    local SURUM
    SURUM="$(git rev-parse HEAD 2> /dev/null || echo bilinmiyor)"
    if [ ! -f user_data/logs/uyum_gecti ]; then
        bildir "Adım 9/10: uyum denemesi başladı. Hazır motorun stratejilerimizle doğru çalıştığını gerçek Binance verisinde sınıyor. 10-20 dakika sürer; bitince raporu yollarım."
        trap - ERR
        local UYUM=0
        bash araclar/uyum_denemesi.sh || UYUM=$?
        trap 'dur "beklenmeyen hata (adım: $ADIM, satır $LINENO)"' ERR
        chown -R 1000:1000 user_data
        if [ "$UYUM" -ne 0 ]; then
            echo "$SURUM" > "$DURUM_KLASORU/son_deneme"
            bildir "Uyum denemesi geçmedi; sanal botlar başlatılmadı. Bu beklenen bir olasılıktı: kod ilk kez gerçek motorla buluşuyor.

Birazdan gelecek raporu Claude'a ilet. Claude düzeltmeyi gönderince sunucu 5 dakika içinde kendiliğinden yeniden dener."
            belge "$KLASOR/user_data/logs/uyum_denemesi.txt" "Uyum denemesi raporu (geçmedi). Bu dosyayı Claude'a ilet."
            exit 1
        fi
        echo "$SURUM" > user_data/logs/uyum_gecti
        belge "$KLASOR/user_data/logs/uyum_denemesi.txt" "Uyum denemesi geçti. Sayıları karşılaştırması için bu dosyayı Claude'a ilet."
    else
        echo "Uyum denemesi daha önce geçti, atlandı."
    fi

    # ------------------------------------------------------------ 10
    adim "10/10 Sanal botlar"
    docker compose up -d --remove-orphans
    if [ -n "${ONCEKI_SURUM:-}" ]; then
        local DEGISEN
        DEGISEN="$(git diff --name-only "$ONCEKI_SURUM" HEAD 2> /dev/null || true)"
        # Sayfa ve haberci kodu değiştiyse yalnız onlar yeniden başlar.
        if echo "$DEGISEN" | grep -Eq '^karabasan/'; then
            docker compose restart kayitci panel haberci
        fi
        # Botlar yalnız kendilerini ilgilendiren bir dosya değiştiyse yeniden başlar.
        if echo "$DEGISEN" | grep -Eq '^(karabasan/(stratejiler/|kural\.py|gostergeler\.py|botlar\.py)|user_data/strategies/)'; then
            local BOT_ADLARI
            BOT_ADLARI="$(python3 -c "
import sys; sys.path.insert(0, '.')
from karabasan.botlar import BOTLAR
print(' '.join(b[0] for b in BOTLAR))")"
            # shellcheck disable=SC2086
            docker compose restart $BOT_ADLARI
            echo "Botlar yeniden başlatıldı."
        fi
    fi
    # Bu tarih ısınma döneminin başlangıcıdır. 30 günlük sınavın saati ayrıca,
    # Telegram'dan /sinav_baslat ile başlatılır.
    [ -f user_data/isinma_baslangici.txt ] || date -u '+%Y-%m-%dT%H:%M:%SZ' > user_data/isinma_baslangici.txt
    chown -R 1000:1000 user_data
    bash araclar/ozel_ag.sh || true

    rm -f "$DURUM_KLASORU/son_deneme"
    if [ "$ILK" -eq 1 ]; then
        date -u '+%Y-%m-%dT%H:%M:%SZ' > user_data/kurulum_tamam
        bildir "Kurulum tamam. On sanal bot çalışıyor; hiçbir emir borsaya gitmiyor.

Şimdi ısınma haftasındayız: botlar sanal işlem yapıyor ama 30 günlük sınavın saati henüz başlamadı.

Sonuçları üç yerden görürsün:
1. Buradan: /durum yaz.
2. Sonuç sayfası: telefonunda Tailscale açıkken http://karabasan:8080
3. Her sabah 09:00'da buraya kısa bir özet gelir.

Tüm komutlar için /yardim yaz."
    fi
    echo
    echo "KURULUM TAMAM $(date -u '+%Y-%m-%d %H:%M UTC')"
}

main "$@"
exit $?
