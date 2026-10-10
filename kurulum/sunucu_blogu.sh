#!/bin/bash
# Karabasan sunucu kurulumu.
# Yalnız alttaki BURAYA_TELEGRAM_KODU yazısını sil ve yerine BotFather'ın
# verdiği kodu yapıştır. Başka hiçbir şeye dokunma.
umask 077
cat > /root/karabasan.env <<'SON'
TELEGRAM_TOKEN=BURAYA_TELEGRAM_KODU
SON
chmod 600 /root/karabasan.env
umask 022
exec >> /var/log/karabasan-baslat.log 2>&1
export HOME=/root DEBIAN_FRONTEND=noninteractive
for deneme in 1 2 3 4 5 6 7 8 9 10; do
  apt-get -o DPkg::Lock::Timeout=300 update -y && apt-get -o DPkg::Lock::Timeout=300 install -y git curl ca-certificates python3 && break
  sleep 30
done
for deneme in 1 2 3 4 5 6 7 8 9 10; do
  [ -d /opt/karabasan-bot/.git ] && break
  rm -rf /opt/karabasan-bot
  git clone https://github.com/hmtstc-creator/Karabasan.git /opt/karabasan-bot && break
  sleep 30
done
exec bash /opt/karabasan-bot/kur.sh
