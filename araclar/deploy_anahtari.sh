#!/usr/bin/env bash
# Sunucunun GitHub'a yazma anahtarı (deploy key) - docs/wiki/sunucu-github-yetkisi.md
#
# Yapılan: anahtar çiftini sunucuda üretir (yoksa), GENEL kısmı bir kez Ahmet'e Telegram'dan yollar.
# Özel kısım /root/.ssh/karabasan_deploy dosyasında kalır (600); hiçbir yere gönderilmez, yazılmaz.
# Yapılmayan: git yapılandırması, uzak adres, push. Anahtar GitHub'a eklenip sınanmadan bunlara dokunulmaz.
# Her çalıştırmada güvenle tekrarlanabilir: anahtar varsa üstüne yazılmaz, bildirim bir kez gider.
set -u

SSH_KLASORU="${KARABASAN_SSH_KLASORU:-/root/.ssh}"
DURUM_KLASORU="${KARABASAN_DURUM_KLASORU:-/var/lib/karabasan}"
ANAHTAR="$SSH_KLASORU/karabasan_deploy"
ISARET="$DURUM_KLASORU/deploy_anahtari_bildirildi"

bildir() { python3 -m karabasan.haberci gonder "$1" > /dev/null 2>&1 || true; }

if ! command -v ssh-keygen > /dev/null 2>&1; then
    # Paket listesi ilk kurulumda sabitlendi; ssh istemcisi eksikse burada tek başına kurulur.
    apt-get -o DPkg::Lock::Timeout=600 install -y openssh-client > /dev/null 2>&1 || true
fi
command -v ssh-keygen > /dev/null 2>&1 || { echo "ssh-keygen yok; deploy anahtarı atlandı."; exit 0; }

mkdir -p "$SSH_KLASORU" "$DURUM_KLASORU"
chmod 700 "$SSH_KLASORU"

if [ ! -f "$ANAHTAR" ]; then
    ssh-keygen -q -t ed25519 -N "" -C "karabasan-sunucu-deploy" -f "$ANAHTAR" || { echo "Anahtar üretilemedi."; exit 0; }
    echo "Deploy anahtarı üretildi."
else
    echo "Deploy anahtarı zaten var, dokunulmadı."
fi
chmod 600 "$ANAHTAR"
chmod 644 "$ANAHTAR.pub" 2> /dev/null || true

if [ ! -f "$ISARET" ] && [ -s "$ANAHTAR.pub" ]; then
    bildir "Sunucunun GitHub anahtarı hazır. Bunu GitHub'a ekle (telefondan):
1. GitHub uygulaması ya da tarayıcı: Karabasan deposu > Settings > Deploy keys > Add deploy key
2. Title: karabasan-sunucu
3. Key: aşağıdaki satırın tamamını kopyalayıp yapıştır
4. 'Allow write access' kutusunu işaretle > Add key

$(cat "$ANAHTAR.pub")

Bu anahtar yalnız bu depoya yazabilir ve tek dokunuşla silinir. Eklediğinde Claude'a 'anahtarı ekledim' yaz; ben sınarım. Henüz hiçbir şey yazma yetkisi kullanılmıyor."
    date -u '+%Y-%m-%dT%H:%M:%SZ' > "$ISARET"
fi
exit 0
