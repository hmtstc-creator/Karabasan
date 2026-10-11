#!/usr/bin/env bash
# 12 aylık geçmiş testi: bir yıllık vadeli veriyi indirir, karabasan/yillik.py'yi çalıştırır.
# Hiçbir emir göndermez, botlara dokunmaz. kur.sh, YILLIK_SURUMU değişince çağırır.
#
#   bash araclar/yillik_test.sh
#
# Sonuç: user_data/logs/yillik_test.txt (Telegram'da /yillik) ve user_data/gecmis_test.json.
# Çıkış kodu: 0 rapor üretildi, 1 üretilemedi.

set -uo pipefail
cd "$(dirname "$0")/.."

RAPOR="user_data/logs/yillik_test.txt"
KAYIT="user_data/logs/yillik_kayit.txt"
GUN=365
# Göstergelerin ısınması için yılın başından önce pay bırakılır.
INDIRILECEK_GUN=400
# Günlük mum isteyen kurallar (Smartmoney) için daha uzun geçmiş.
EK_GUN=1100
PARITELER="ETH/USDT:USDT SOL/USDT:USDT XRP/USDT:USDT DOGE/USDT:USDT"
mkdir -p user_data/logs
: > "$KAYIT"

HATA_DESENI='CRITICAL|Configuration error|Traceback \(most recent call last\)|Fatal exception'
GECICI="$(mktemp)"
trap 'rm -f "$GECICI"' EXIT

indir_bir() {  # indir_bir BAYRAK GUN DILIMLER...
    local BAYRAK="$1" KAC="$2"; shift 2
    # shellcheck disable=SC2086
    docker compose run --rm -T arac download-data --exchange binance --trading-mode futures \
        --pairs $PARITELER --timeframes "$@" --days "$KAC" "$BAYRAK" > "$GECICI" 2>&1
    local KOD=$?
    cat "$GECICI" >> "$KAYIT"
    echo "  (veri indirme, $*, $BAYRAK, çıkış kodu: $KOD)" >> "$KAYIT"
    [ "$KOD" -eq 0 ] && ! grep -Eq "$HATA_DESENI|unrecognized arguments" "$GECICI"
}
indir() {  # indir GUN DILIMLER... : önce eldeki verinin başına ekle, olmazsa baştan indir
    local KAC="$1"; shift
    indir_bir --prepend "$KAC" "$@" || indir_bir --erase "$KAC" "$@"
}
ek_dilimler() {
    python3 -c "
import sys; sys.path.insert(0, '.')
from karabasan.botlar import ek_dilimler
print(' '.join(ek_dilimler('vadeli')))" 2> /dev/null
}

echo "12 aylık geçmiş testi - $(date -u '+%Y-%m-%d %H:%M UTC')" >> "$KAYIT"
VERI_TAMAM=1
indir "$INDIRILECEK_GUN" 5m 15m || VERI_TAMAM=0
EK="$(ek_dilimler)"
if [ -n "$EK" ]; then
    # shellcheck disable=SC2086
    indir "$EK_GUN" $EK || VERI_TAMAM=0
fi
chown -R 1000:1000 user_data 2> /dev/null || true

docker compose run --rm -T --entrypoint python3 arac /freqtrade/araclar/yillik_test.py "$GUN" \
    > "$RAPOR" 2>> "$KAYIT"
KOD=$?
echo "  (test çıkış kodu: $KOD)" >> "$KAYIT"

if [ "$VERI_TAMAM" -eq 0 ]; then
    { echo; echo "UYARI: veri indirme adımı hata verdi; test eldeki veriyle yapıldı."
      echo "Ayrıntı: user_data/logs/yillik_kayit.txt"; } >> "$RAPOR"
fi
if [ "$KOD" -ne 0 ] || ! grep -q "^ÖZET" "$RAPOR"; then
    { echo; echo "TEST TAMAMLANAMADI. Kaydın son satırları:"; tail -40 "$KAYIT"; } >> "$RAPOR"
    exit 1
fi
exit 0
