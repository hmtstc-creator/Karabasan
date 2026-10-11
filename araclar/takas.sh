#!/usr/bin/env bash
# Takas alanı (swap): diskte 2 GB'lık bir dosya, bellek dolduğunda taşma yeri.
#
# Neden: 11 Ekim 2026 ölçümü, 12 bot açıkken 7,6 GB belleğin ~6,2 GB'ının
# dolu olduğunu, takas alanı olmadığını gösterdi. Uyum denemesi ve geçmiş
# ölçümü sırasında ek bir kapsayıcı (arac) daha çalışır; bellek o sırada
# biterse çekirdek bir botu öldürür. Takas alanı bunu yavaşlamaya çevirir.
#
# Yeniden çalıştırmak güvenlidir: kurulu olanı atlar. kur.sh her çalışmada
# çağırır; burada bir şey ters giderse yalnız uyarı yazılır, kurulum sürer.

set -uo pipefail

DOSYA="${TAKAS_DOSYASI:-/swapfile}"
FSTAB="${TAKAS_FSTAB:-/etc/fstab}"
SYSCTL="${TAKAS_SYSCTL:-/etc/sysctl.d/99-karabasan-takas.conf}"
BOYUT_MB=2048
# Bellek yetiyorken diske yazmasın; takas yalnız sıkışınca kullanılsın.
SWAPPINESS=10

uyar() { echo "UYARI (takas): $1"; }

etkin_mi() { swapon --show=NAME --noheadings 2> /dev/null | grep -qxF "$DOSYA"; }

if ! etkin_mi; then
    if [ ! -f "$DOSYA" ]; then
        BOS_MB=$(df --output=avail -m "$(dirname "$DOSYA")" 2> /dev/null | tail -1 | tr -d ' ')
        if [ -z "$BOS_MB" ] || [ "$BOS_MB" -lt $((BOYUT_MB + 4096)) ]; then
            uyar "diskte yeterli boş yer yok (${BOS_MB:-?} MB); takas alanı kurulmadı."
            exit 1
        fi
        # Önce geçici adla kurulur: yarıda kalırsa sonraki çalışmada bozuk dosya kalmaz.
        YENI="$DOSYA.yeni"
        rm -f "$YENI"
        if ! fallocate -l "${BOYUT_MB}M" "$YENI" 2> /dev/null; then
            dd if=/dev/zero of="$YENI" bs=1M count="$BOYUT_MB" status=none || { rm -f "$YENI"; uyar "dosya oluşturulamadı."; exit 1; }
        fi
        chmod 600 "$YENI"
        mkswap "$YENI" > /dev/null || { rm -f "$YENI"; uyar "mkswap başarısız."; exit 1; }
        mv -f "$YENI" "$DOSYA"
        echo "Takas dosyası oluşturuldu: $DOSYA (${BOYUT_MB} MB)."
    fi
    if ! swapon "$DOSYA"; then
        # Dosya var ama takas olarak açılmıyor: bozuk sayılır, bir sonraki çalışmada yeniden kurulur.
        rm -f "$DOSYA"
        uyar "$DOSYA açılamadı; silindi, bir sonraki güncellemede yeniden denenecek."
        exit 1
    fi
    echo "Takas alanı açıldı."
else
    echo "Takas alanı zaten açık, atlandı."
fi

# Yeniden açılışta da açılsın: /etc/fstab'a bir kez eklenir.
if ! awk -v d="$DOSYA" '$1 == d && $3 == "swap" { bulundu = 1 } END { exit !bulundu }' "$FSTAB" 2> /dev/null; then
    echo "$DOSYA none swap sw 0 0" >> "$FSTAB"
    echo "Takas alanı $FSTAB dosyasına eklendi."
fi

echo "vm.swappiness=$SWAPPINESS" > "$SYSCTL"
sysctl -q -w "vm.swappiness=$SWAPPINESS" > /dev/null 2>&1 || uyar "vm.swappiness ayarlanamadı."
exit 0
