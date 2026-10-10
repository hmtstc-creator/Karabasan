#!/usr/bin/env bash
# Analiz: sunucudaki geçmiş veride Karabasan geçmiş ölçümünü çalıştırır.
# Hiçbir emir göndermez, botlara dokunmaz. kur.sh, ANALIZ_SURUMU değişince çağırır.
#
#   bash araclar/analiz.sh
#
# Sonuç: user_data/logs/karabasan_gecmis.txt (Telegram'dan dosya olarak gider).
# Çıkış kodu: 0 rapor üretildi, 1 üretilemedi.

set -uo pipefail
cd "$(dirname "$0")/.."

RAPOR="user_data/logs/karabasan_gecmis.txt"
KAYIT="user_data/logs/analiz.txt"
GUN=30
# Karabasan puanı için ölçülen dönemden önce yaklaşık 35 günlük geçmiş gerekir
# (200 tane 4 saatlik mum); pay bırakılır.
INDIRILECEK_GUN=80
mkdir -p user_data/logs
: > "$KAYIT"

HATA_DESENI='CRITICAL|Configuration error|Traceback \(most recent call last\)|Fatal exception'
GECICI="$(mktemp)"
trap 'rm -f "$GECICI"' EXIT

indir_bir() {  # indir_bir BAYRAK spot|futures PARITELER...
    local BAYRAK="$1" MOD="$2"; shift 2
    docker compose run --rm -T arac download-data --exchange binance --trading-mode "$MOD" \
        --pairs "$@" --timeframes 5m 15m --days "$INDIRILECEK_GUN" "$BAYRAK" > "$GECICI" 2>&1
    local KOD=$?
    cat "$GECICI" >> "$KAYIT"
    echo "  ($MOD veri indirme, $BAYRAK, çıkış kodu: $KOD)" >> "$KAYIT"
    [ "$KOD" -eq 0 ] && ! grep -Eq "$HATA_DESENI|unrecognized arguments" "$GECICI"
}
indir() {
    # Önce eldeki verinin başına ekle; olmazsa silip baştan indir.
    indir_bir --prepend "$@" || indir_bir --erase "$@"
}

echo "Analiz - $(date -u '+%Y-%m-%d %H:%M UTC')" >> "$KAYIT"
VERI_TAMAM=1
indir spot BTC/USDT ETH/USDT SOL/USDT XRP/USDT DOGE/USDT || VERI_TAMAM=0
indir futures BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT XRP/USDT:USDT DOGE/USDT:USDT || VERI_TAMAM=0

docker compose run --rm -T --entrypoint python3 arac /freqtrade/araclar/karabasan_gecmis.py "$GUN" \
    > "$RAPOR" 2>> "$KAYIT"
KOD=$?
echo "  (ölçüm çıkış kodu: $KOD)" >> "$KAYIT"

if [ "$VERI_TAMAM" -eq 0 ]; then
    { echo; echo "UYARI: veri indirme adımı hata verdi; ölçüm eldeki veriyle yapıldı."
      echo "Ayrıntı: user_data/logs/analiz.txt"; } >> "$RAPOR"
fi
if ! grep -q "Karabasan geçmiş ölçümü:" "$RAPOR"; then
    # Rapor üretilemedi: nedenini görebilmek için kaydın sonunu ekle.
    { echo; echo "ÖLÇÜM ÜRETİLEMEDİ. Kaydın son satırları:"; tail -40 "$KAYIT"; } >> "$RAPOR"
    exit 1
fi
exit 0
