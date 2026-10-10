#!/usr/bin/env bash
# Uyum denemesi: hazır motorun (Freqtrade) Karabasan stratejileriyle doğru
# çalıştığını sunucuda sınar. Hiçbir emir göndermez, API anahtarı istemez.
#
#   bash araclar/uyum_denemesi.sh
#
# Sonuç ekrana ve user_data/logs/uyum_denemesi.txt dosyasına yazılır.
# Bir adım kalırsa bu dosyayı Claude'a göndermen yeterlidir.

set -uo pipefail
cd "$(dirname "$0")/.."

RAPOR="user_data/logs/uyum_denemesi.txt"
GUN=30
INDIRILECEK_GUN=45
mkdir -p user_data/logs
: > "$RAPOR"

yaz() { echo "$@" | tee -a "$RAPOR"; }
calistir() { docker compose run --rm -T arac "$@" 2>&1 | tee -a "$RAPOR"; return "${PIPESTATUS[0]}"; }

HATA=0
gecti() { yaz "  [GEÇTİ] $1"; }
kaldi() { yaz "  [KALDI] $1"; HATA=$((HATA + 1)); }

yaz "Karabasan uyum denemesi - $(date -u '+%Y-%m-%d %H:%M UTC')"
yaz "Motor sürümü: $(docker compose run --rm -T arac --version 2>/dev/null | tail -1)"
yaz ""

# ---------------------------------------------------------------- 1
yaz "1/5 Strateji sınıfları yükleniyor"
CIKTI=$(docker compose run --rm -T arac list-strategies --strategy-path /freqtrade/user_data/strategies 2>&1)
echo "$CIKTI" >> "$RAPOR"
EKSIK=""
for SINIF in S1Spot S2Spot S3Spot S4Spot S1Vadeli S2Vadeli S3Vadeli S4Vadeli S1KVadeli S2KVadeli; do
    echo "$CIKTI" | grep -q "$SINIF" || EKSIK="$EKSIK $SINIF"
done
if [ -n "$EKSIK" ]; then
    kaldi "Bulunamayan sınıflar:$EKSIK"
elif echo "$CIKTI" | grep -q "LOAD FAILED"; then
    kaldi "Bazı strateji dosyaları yüklenemedi (ayrıntı raporda)"
else
    gecti "On strateji sınıfı bulundu ve yüklendi"
fi

# ---------------------------------------------------------------- 2
yaz ""
yaz "2/5 Spot geçmiş verisi indiriliyor ($INDIRILECEK_GUN gün, 5 parite)"
if calistir download-data --exchange binance --trading-mode spot \
        --pairs BTC/USDT ETH/USDT SOL/USDT XRP/USDT DOGE/USDT \
        --timeframes 5m 15m --days "$INDIRILECEK_GUN" > /dev/null; then
    gecti "Spot verisi indirildi"
else
    kaldi "Spot verisi indirilemedi"
fi

# ---------------------------------------------------------------- 3
yaz ""
yaz "3/5 Vadeli geçmiş verisi indiriliyor ($INDIRILECEK_GUN gün, 5 parite)"
if calistir download-data --exchange binance --trading-mode futures \
        --pairs BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT XRP/USDT:USDT DOGE/USDT:USDT \
        --timeframes 5m 15m --days "$INDIRILECEK_GUN" > /dev/null; then
    gecti "Vadeli verisi indirildi"
else
    kaldi "Vadeli verisi indirilemedi"
fi

# ---------------------------------------------------------------- 4
yaz ""
yaz "4/5 Her bot için $GUN günlük geçmiş testi (hazır motor)"
BASLANGIC=$(date -u -d "$GUN days ago" +%Y%m%d)
BOTLAR="s1-spot:S1Spot:spot s2-spot:S2Spot:spot s3-spot:S3Spot:spot s4-spot:S4Spot:spot \
s1-vadeli:S1Vadeli:vadeli s2-vadeli:S2Vadeli:vadeli s3-vadeli:S3Vadeli:vadeli s4-vadeli:S4Vadeli:vadeli \
s1k-vadeli:S1KVadeli:vadeli s2k-vadeli:S2KVadeli:vadeli"
for SATIR in $BOTLAR; do
    BOT=${SATIR%%:*}; KALAN=${SATIR#*:}; SINIF=${KALAN%%:*}; PIYASA=${KALAN#*:}
    yaz ""
    yaz "--- $BOT ($SINIF) ---"
    if calistir backtesting \
            --config "/freqtrade/user_data/config/$BOT.json" \
            --config "/freqtrade/user_data/config/geri_test_$PIYASA.json" \
            --strategy "$SINIF" --timerange "$BASLANGIC-" \
            --enable-protections --export none > /dev/null; then
        gecti "$BOT geçmiş testi tamamlandı"
    else
        kaldi "$BOT geçmiş testi hata verdi"
    fi
done

# ---------------------------------------------------------------- 5
yaz ""
yaz "5/5 Bağımsız karşılaştırma (aynı veride kendi benzetimimiz)"
docker compose run --rm -T --entrypoint python3 arac /freqtrade/araclar/karsilastir.py "$GUN" 2>&1 | tee -a "$RAPOR"
if [ "${PIPESTATUS[0]}" -eq 0 ]; then
    gecti "Bağımsız benzetim çalıştı"
else
    # Bu adım yalnız bir çapraz kontroldür; botların başlamasını engellemez.
    yaz "  [UYARI] Bağımsız benzetim çalışmadı; karşılaştırma yapılamadı."
fi

yaz ""
if [ "$HATA" -eq 0 ]; then
    yaz "SONUÇ: Tüm adımlar geçti."
    yaz "Not: 4. ve 5. adımdaki işlem sayıları ve sonuçlar birbirine yakın olmalı."
    yaz "Raporu Claude'a gönderirsen karşılaştırmayı o yapar: $RAPOR"
    exit 0
fi
yaz "SONUÇ: $HATA adım kaldı. Sanal botlar BAŞLATILMADI."
yaz "Şu dosyayı Claude'a gönder: $RAPOR"
exit 1
