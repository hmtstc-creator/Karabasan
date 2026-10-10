#!/usr/bin/env bash
# Kendiliğinden güncelleme. Zamanlayıcı (karabasan-guncelle.timer) 5 dakikada
# bir çalıştırır:
#
#   1. GitHub'daki ana dalda yeni kod var mı bakar, varsa alır.
#   2. Yeni kod geldiyse kur.sh'ı çalıştırır (yapılmış adımları atlar, yalnız
#      değişenle ilgili servisleri yeniden başlatır).
#   3. Kurulum yarım kaldıysa ve yeni kod geldiyse yeniden dener.
#   4. Özel ağ bağlantısını denetler.
#
# Ahmet'in bir şey yapması gerekmez; sonucu Telegram'dan öğrenir.
# Sanal işlem kayıtları (user_data/db) hiçbir zaman silinmez.

set -uo pipefail

main() {
    cd "$(dirname "$0")/.." || exit 1
    export HOME=/root
    export PATH="${PATH:+$PATH:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    local DURUM_KLASORU=/var/lib/karabasan
    mkdir -p "$DURUM_KLASORU"

    # Kurulum ya da başka bir güncelleme sürüyorsa bekleme, çık.
    exec 9> /run/karabasan.kilit
    flock -n 9 || exit 0

    if [ -f telegram.env ]; then
        TELEGRAM_TOKEN="$(sed -n 's/^TELEGRAM_TOKEN=//p' telegram.env | head -1)"
        export TELEGRAM_TOKEN
    fi
    bildir() { python3 -m karabasan.haberci gonder "$1" > /dev/null 2>&1 || true; }

    local ONCEKI YENI DENENEN
    ONCEKI="$(git rev-parse HEAD)"
    if git fetch -q origin main; then
        YENI="$(git rev-parse origin/main)"
    else
        echo "Yeni kod denetlenemedi (GitHub'a ulaşılamadı)."
        YENI="$ONCEKI"
    fi

    if [ "$YENI" != "$ONCEKI" ]; then
        echo "Yeni kod alınıyor: ${ONCEKI:0:7} -> ${YENI:0:7}"
        # Sunucuda elle değişiklik yapılmaz; depo her zaman ana dalın aynısıdır.
        # Üretilen dosyalar ve kayıtlar (.gitignore'da) bundan etkilenmez.
        git reset -q --hard origin/main || { echo "Yeni kod alınamadı."; exit 1; }
    fi

    local CALISTIR=0
    if [ ! -f user_data/kurulum_tamam ]; then
        # Kurulum yarım. Aynı kodla hata verdiyse yeni kod gelene kadar yeniden deneme.
        DENENEN="$(cat "$DURUM_KLASORU/son_deneme" 2> /dev/null || true)"
        if [ "$YENI" != "$DENENEN" ]; then CALISTIR=1; fi
    elif [ "$YENI" != "$ONCEKI" ]; then
        CALISTIR=1
    fi

    if [ "$CALISTIR" -eq 1 ]; then
        local BASLIKLAR=""
        if [ "$YENI" != "$ONCEKI" ]; then
            BASLIKLAR="$(git log --format='- %s' "$ONCEKI..$YENI" 2> /dev/null | head -5)"
        fi
        if KARABASAN_KILIT_BENDE=1 ONCEKI_SURUM="$ONCEKI" bash kur.sh; then
            if [ -n "$BASLIKLAR" ]; then
                bildir "Güncelleme alındı ve uygulandı:
$BASLIKLAR"
            fi
        fi
        # kur.sh hata verdiyse kendisi bildirir.
    else
        bash araclar/ozel_ag.sh > /dev/null 2>&1 || true
    fi
}

main "$@"
exit $?
