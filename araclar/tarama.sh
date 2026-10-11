#!/usr/bin/env bash
# Çıkış varyasyonu taraması: her botun girişleriyle 20 çıkış ayarını son bir yılda sınar.
# Veriyi 12 aylık test indirir (kur.sh bunu hemen ondan sonra çağırır). Hiçbir emir
# göndermez, botlara ve ayarlara dokunmaz. kur.sh, TARAMA_SURUMU değişince çağırır.
#
#   bash araclar/tarama.sh
#
# Sonuç: user_data/logs/tarama.txt (Telegram'da /tarama).
# Çıkış kodu: 0 rapor üretildi, 1 üretilemedi.

set -uo pipefail
cd "$(dirname "$0")/.."

RAPOR="user_data/logs/tarama.txt"
KAYIT="user_data/logs/tarama_kayit.txt"
GUN=365
mkdir -p user_data/logs
echo "Çıkış varyasyonu taraması - $(date -u '+%Y-%m-%d %H:%M UTC')" > "$KAYIT"

docker compose run --rm -T --entrypoint python3 arac /freqtrade/araclar/tarama.py "$GUN" \
    > "$RAPOR" 2>> "$KAYIT"
KOD=$?
echo "  (tarama çıkış kodu: $KOD)" >> "$KAYIT"

if [ "$KOD" -ne 0 ] || ! grep -q "^ÖZET" "$RAPOR"; then
    { echo; echo "TARAMA TAMAMLANAMADI. Kaydın son satırları:"; tail -40 "$KAYIT"; } >> "$RAPOR"
    exit 1
fi
exit 0
