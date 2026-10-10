#!/usr/bin/env bash
# Karabasan Bot - güncelleme. Yeni kodu çeker ve botları yeniden başlatır.
# Sanal işlem kayıtları (user_data/db) silinmez.
#
#   bash /opt/karabasan-bot/guncelle.sh

set -euo pipefail
cd "$(dirname "$0")"

echo "Yeni kod çekiliyor..."
git pull --ff-only
python3 araclar/yapilandirma_uret.py
chown -R 1000:1000 user_data
docker compose --profile arac pull -q
docker compose up -d
echo "Güncelleme tamam."
docker compose ps --format 'table {{.Name}}\t{{.Status}}'
