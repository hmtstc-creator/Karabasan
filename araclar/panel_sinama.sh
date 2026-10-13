#!/usr/bin/env bash
# Panel sınaması: 4 yıllık vadeli veriyi ve fonlama geçmişini indirir, karabasan/sinama.py'yi
# çalıştırır. Hiçbir emir göndermez, botlara dokunmaz. kur.sh, PANEL_SURUMU değişince çağırır.
#
#   bash araclar/panel_sinama.sh
#
# Sonuç: user_data/logs/panel_sinama.txt (Telegram'da /panel).
# Çıkış kodu: 0 rapor üretildi, 1 üretilemedi.

set -uo pipefail
cd "$(dirname "$0")/.."

RAPOR="user_data/logs/panel_sinama.txt"
KAYIT="user_data/logs/panel_kayit.txt"
# 3 yıl geliştirme + 1 yıl ayrılmış + göstergelerin ısınması (günlük 50'lik ortalama).
GUN=1500
GUNLUK_GUN=2500
# karabasan/sinama.py: REFERANS + COINLER (testler bu listeyi denetler).
PARITELER="BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT XRP/USDT:USDT DOGE/USDT:USDT ADA/USDT:USDT BNB/USDT:USDT LINK/USDT:USDT AVAX/USDT:USDT DOT/USDT:USDT LTC/USDT:USDT BCH/USDT:USDT TRX/USDT:USDT ATOM/USDT:USDT ETC/USDT:USDT FIL/USDT:USDT NEAR/USDT:USDT UNI/USDT:USDT XLM/USDT:USDT AAVE/USDT:USDT ALGO/USDT:USDT"
FONLAMA_COINLERI="ETH SOL XRP DOGE ADA BNB LINK AVAX DOT LTC BCH TRX ATOM ETC FIL NEAR UNI XLM AAVE ALGO"
mkdir -p user_data/logs user_data/data/fonlama
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
indir() {  # indir GUN DILIMLER... : önce eldeki verinin başına ekle, olmazsa baştan indir; sonra sona ekle
    local KAC="$1"; shift
    indir_bir --prepend "$KAC" "$@" || indir_bir --erase "$KAC" "$@" || return 1
    # shellcheck disable=SC2086
    docker compose run --rm -T arac download-data --exchange binance --trading-mode futures \
        --pairs $PARITELER --timeframes "$@" --days 3 >> "$KAYIT" 2>&1 || true
}

echo "Panel sınaması - $(date -u '+%Y-%m-%d %H:%M UTC')" >> "$KAYIT"
VERI_TAMAM=1
indir "$GUN" 15m 1h || VERI_TAMAM=0
indir "$GUNLUK_GUN" 1d || VERI_TAMAM=0
# Fonlama geçmişi Binance'in herkese açık adresinden; yalnız standart kütüphane (sunucu Python'u).
# shellcheck disable=SC2086
python3 -m karabasan.fonlama user_data/data/fonlama "$GUN" $FONLAMA_COINLERI >> "$KAYIT" 2>&1 || VERI_TAMAM=0
chown -R 1000:1000 user_data 2> /dev/null || true

docker compose run --rm -T --entrypoint python3 arac /freqtrade/araclar/panel_sinama.py \
    > "$RAPOR" 2>> "$KAYIT"
KOD=$?
echo "  (sınama çıkış kodu: $KOD)" >> "$KAYIT"

if [ "$VERI_TAMAM" -eq 0 ]; then
    { echo; echo "UYARI: veri indirmenin bir kısmı hata verdi; sınama eldeki veriyle yapıldı."
      echo "Ayrıntı: user_data/logs/panel_kayit.txt"; } >> "$RAPOR"
fi
if [ "$KOD" -ne 0 ] || ! grep -q "^ÖZET" "$RAPOR"; then
    { echo; echo "SINAMA TAMAMLANAMADI. Kaydın son satırları:"; tail -40 "$KAYIT"; } >> "$RAPOR"
    exit 1
fi
exit 0
