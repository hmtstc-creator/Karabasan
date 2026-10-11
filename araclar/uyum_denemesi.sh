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

GECICI="$(mktemp)"
trap 'rm -f "$GECICI"' EXIT

yaz() { echo "$@" | tee -a "$RAPOR"; }

# Hazır motor bazı hatalarda (örneğin ayar hatası) çıkış koduyla haber vermeyebilir.
# Bu yüzden bir adım ancak hem çıkış kodu temizse hem de çıktısında hata satırı
# yoksa geçmiş sayılır. İlk kurulumda bu denetim yoktu ve on geçmiş testi ayar
# hatasıyla durduğu halde "geçti" yazıldı.
HATA_DESENI='CRITICAL|Configuration error|Traceback \(most recent call last\)|Fatal exception'

# calistir KOMUT...: hazır motoru çalıştırır, çıktıyı rapora ve $GECICI dosyasına yazar.
# Dönüş: 0 temiz, 1 çıkış kodu hatalı, 2 çıktıda hata satırı var.
calistir() {
    docker compose run --rm -T arac "$@" > "$GECICI" 2>&1
    local KOD=$?
    cat "$GECICI" >> "$RAPOR"
    echo "  (çıkış kodu: $KOD)" >> "$RAPOR"
    if [ "$KOD" -ne 0 ]; then return 1; fi
    if grep -Eq "$HATA_DESENI" "$GECICI"; then return 2; fi
    return 0
}
hata_satiri() { grep -E "$HATA_DESENI|ERROR" "$GECICI" | head -1 | cut -c1-200; }

# Bot listesi tek yerden gelir: karabasan/botlar.py ("bot:sınıf:piyasa").
BOTLAR="$(python3 -c "
import sys; sys.path.insert(0, '.')
from karabasan.botlar import BOTLAR
print(' '.join(f'{b}:{s}:{p}' for b, s, _k, p in BOTLAR))" 2> /dev/null)"
if [ -z "$BOTLAR" ]; then
    yaz "Bot listesi okunamadı (karabasan/botlar.py)."
    yaz "SONUÇ: 1 adım kaldı."
    exit 1
fi
BOT_SAYISI=$(echo "$BOTLAR" | wc -w)

HATA=0
gecti() { yaz "  [GEÇTİ] $1"; }
kaldi() { yaz "  [KALDI] $1"; HATA=$((HATA + 1)); }

yaz "Karabasan uyum denemesi - $(date -u '+%Y-%m-%d %H:%M UTC')"
yaz "Motor sürümü: $(docker compose run --rm -T arac --version 2>/dev/null | tail -1)"
yaz ""

# ---------------------------------------------------------------- 1
yaz "1/5 Strateji sınıfları yükleniyor"
calistir list-strategies
LISTE=$?
EKSIK=""
for SATIR in $BOTLAR; do
    KALAN=${SATIR#*:}; SINIF=${KALAN%%:*}
    grep -qw "$SINIF" "$GECICI" || EKSIK="$EKSIK $SINIF"
done
if [ "$LISTE" -ne 0 ]; then
    kaldi "Strateji listesi alınamadı: $(hata_satiri)"
elif [ -n "$EKSIK" ]; then
    kaldi "Bulunamayan sınıflar:$EKSIK"
elif grep -q "LOAD FAILED" "$GECICI"; then
    kaldi "Bazı strateji dosyaları yüklenemedi (ayrıntı raporda)"
else
    gecti "$BOT_SAYISI strateji sınıfı bulundu ve yüklendi"
fi

# ---------------------------------------------------------------- 2
yaz ""
yaz "2/5 Spot geçmiş verisi indiriliyor ($INDIRILECEK_GUN gün, 5 parite)"
if calistir download-data --exchange binance --trading-mode spot \
        --pairs BTC/USDT ETH/USDT SOL/USDT XRP/USDT DOGE/USDT \
        --timeframes 5m 15m --days "$INDIRILECEK_GUN"; then
    gecti "Spot verisi indirildi"
else
    kaldi "Spot verisi indirilemedi: $(hata_satiri)"
fi

# ---------------------------------------------------------------- 3
yaz ""
yaz "3/5 Vadeli geçmiş verisi indiriliyor ($INDIRILECEK_GUN gün, 5 parite)"
if calistir download-data --exchange binance --trading-mode futures \
        --pairs BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT XRP/USDT:USDT DOGE/USDT:USDT \
        --timeframes 5m 15m --days "$INDIRILECEK_GUN"; then
    gecti "Vadeli verisi indirildi"
else
    kaldi "Vadeli verisi indirilemedi: $(hata_satiri)"
fi

# ---------------------------------------------------------------- 4
yaz ""
yaz "4/5 Her bot için $GUN günlük geçmiş testi (hazır motor)"
BASLANGIC=$(date -u -d "$GUN days ago" +%Y%m%d)
# Motorun işlem listeleri 5. adımda benzetimle tek tek eşleştirilir. Klasör
# yalnız bu deneme içindir; eski sonuçlar karışmasın diye boşaltılır.
mkdir -p user_data/backtest_results
rm -f user_data/backtest_results/backtest-result-* user_data/backtest_results/.last_result.json
chown 1000:1000 user_data/backtest_results 2> /dev/null || true
for SATIR in $BOTLAR; do
    BOT=${SATIR%%:*}; KALAN=${SATIR#*:}; SINIF=${KALAN%%:*}; PIYASA=${KALAN#*:}
    yaz ""
    yaz "--- $BOT ($SINIF) ---"
    calistir backtesting \
        --config "/freqtrade/user_data/config/$BOT.json" \
        --config "/freqtrade/user_data/config/geri_test_$PIYASA.json" \
        --strategy "$SINIF" --timerange "$BASLANGIC-" \
        --enable-protections --export trades
    SONUC=$?
    if [ "$SONUC" -ne 0 ]; then
        kaldi "$BOT geçmiş testi hata verdi: $(hata_satiri)"
    elif grep -q "BACKTESTING REPORT" "$GECICI"; then
        gecti "$BOT geçmiş testi tamamlandı"
        # Karşılaştırmayı kolaylaştıran satırlar (bulunursa).
        grep -E "TOTAL|Total/Daily Avg Trades|Absolute profit|Total profit %" "$GECICI" \
            | head -6 | sed 's/^/    > /' >> "$RAPOR"
    elif grep -q "No trades made" "$GECICI"; then
        gecti "$BOT geçmiş testi tamamlandı, ama hiç işlem açmadı"
    else
        # Hata satırı yok ama sonuç tablosu da yok: geçti sayılmaz.
        kaldi "$BOT geçmiş testinin sonuç tablosu çıktıda bulunamadı"
    fi
done

# ---------------------------------------------------------------- 5
yaz ""
yaz "5/5 Bağımsız karşılaştırma (aynı veride kendi benzetimimiz)"
docker compose run --rm -T --entrypoint python3 arac /freqtrade/araclar/karsilastir.py "$GUN" > "$GECICI" 2>&1
KOD=$?
cat "$GECICI" | tee -a "$RAPOR"
if [ "$KOD" -eq 0 ] && ! grep -q "Traceback (most recent call last)" "$GECICI"; then
    gecti "Bağımsız benzetim çalıştı"
else
    # Bu adım yalnız bir çapraz kontroldür; botların başlamasını engellemez.
    yaz "  [UYARI] Bağımsız benzetim çalışmadı; karşılaştırma yapılamadı."
fi

# İşlem işlem eşleştirme: toplamlar tutmadığında farkın nedenini gösterir.
# Yalnız bilgi içindir; sonucu denemenin geçip kalmasını etkilemez.
yaz ""
yaz "İşlem işlem eşleştirme"
docker compose run --rm -T --entrypoint python3 arac /freqtrade/araclar/islem_eslestir.py "$BASLANGIC" > "$GECICI" 2>&1 \
    || yaz "  [UYARI] Eşleştirme tamamlanamadı (aşağıdaki çıktıya bak)."
cat "$GECICI" >> "$RAPOR"

yaz ""
if [ "$HATA" -eq 0 ]; then
    yaz "SONUÇ: Tüm adımlar geçti."
    yaz "Not: 4. ve 5. adımdaki işlem sayıları ve sonuçlar birbirine yakın olmalı."
    yaz "Raporu Claude'a gönderirsen karşılaştırmayı o yapar: $RAPOR"
    exit 0
fi
yaz "SONUÇ: $HATA adım kaldı."
yaz "Şu dosyayı Claude'a gönder: $RAPOR"
exit 1
