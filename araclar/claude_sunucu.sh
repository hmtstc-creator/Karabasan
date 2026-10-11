#!/usr/bin/env bash
# Sunucudaki Claude: Claude Code'u sunucuya kurar ve Ahmet'in telefonundaki
# Claude uygulamasından yönetilebilir kılar (Remote Control).
#
#   bash araclar/claude_sunucu.sh kur      kur, servisleri tanımla (kur.sh çağırır)
#   bash araclar/claude_sunucu.sh giris    giriş akışı (karabasan-claude-giris.service)
#   bash araclar/claude_sunucu.sh oturum   uzaktan yönetim oturumu (karabasan-claude.service)
#   bash araclar/claude_sunucu.sh istek    Telegram'dan gelen istekleri işle (.path birimi)
#   bash araclar/claude_sunucu.sh durum    durum dosyasını tazele
#
# Giriş telefondan yapılır, terminal gerekmez:
#   1. Sunucu "claude auth login" başlatır, çıkan bağlantıyı Telegram'dan yollar.
#   2. Ahmet bağlantıya dokunur, Claude hesabıyla girer, ekrandaki kodu bota
#      "/claude KOD" diye yazar.
#   3. Haberci kodu user_data/claude_kod.istek dosyasına bırakır; buradaki
#      "istek" işi onu bekleyen giriş ekranına yapıştırır.
#
# Kod tek kullanımlıktır ve yalnız o an bekleyen giriş ekranına yazılır; ekran
# yoksa hiçbir yere yazılmaz. Bu betik Telegram'dan gelen hiçbir metni komut
# olarak çalıştırmaz.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

KLASOR="$(pwd)"
VERI="$KLASOR/user_data"
DURUM_KLASORU=/var/lib/karabasan
GUNLUK="$VERI/logs/claude.txt"
OTURUM_ADI="Karabasan sunucu"
export HOME=/root
export PATH="/root/.local/bin:${PATH:+$PATH:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
mkdir -p "$VERI/logs" "$DURUM_KLASORU"

if [ -z "${TELEGRAM_TOKEN:-}" ] && [ -f telegram.env ]; then
    TELEGRAM_TOKEN="$(sed -n 's/^TELEGRAM_TOKEN=//p' telegram.env | head -1)"
    export TELEGRAM_TOKEN
fi
bildir() { python3 -m karabasan.haberci gonder "$1" > /dev/null 2>&1 || true; }
yaz() { echo "$(date -u '+%Y-%m-%d %H:%M:%S') $*" >> "$GUNLUK"; }

giris_tmux() { tmux -L kb-giris "$@"; }
oturum_tmux() { tmux -L kb-claude "$@"; }
giris_ekrani() { giris_tmux capture-pane -p -J -t giris -S -200 2> /dev/null; }
oturum_ekrani() { oturum_tmux capture-pane -p -J -t claude -S -200 2> /dev/null; }

giris_var_mi() {
    command -v claude > /dev/null 2>&1 || return 1
    claude auth status 2> /dev/null | python3 -c '
import json, sys
try:
    sys.exit(0 if json.load(sys.stdin).get("loggedIn") else 1)
except Exception:
    sys.exit(1)'
}

durum_yaz() {
    # Haberci (/claude komutu) bu dosyayı okur.
    local KURULU=false GIRIS=false OTURUM=false ADRES=""
    if command -v claude > /dev/null 2>&1; then KURULU=true; fi
    if giris_var_mi; then GIRIS=true; fi
    if oturum_tmux has-session -t claude 2> /dev/null; then OTURUM=true; fi
    ADRES="$(cat "$DURUM_KLASORU/claude_adresi" 2> /dev/null || true)"
    python3 - "$KURULU" "$GIRIS" "$OTURUM" "$ADRES" > "$VERI/claude_durum.json.yeni" << 'PY'
import json, sys, time
kurulu, giris, oturum, adres = sys.argv[1:5]
print(json.dumps({"kurulu": kurulu == "true", "giris": giris == "true",
                  "oturum": oturum == "true", "adres": adres if oturum == "true" else "",
                  "zaman": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
PY
    mv -f "$VERI/claude_durum.json.yeni" "$VERI/claude_durum.json"
    chmod 644 "$VERI/claude_durum.json"
}

# ------------------------------------------------------------------ kur
kur() {
    if ! command -v tmux > /dev/null 2>&1; then
        DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y tmux > /dev/null
    fi
    if ! command -v claude > /dev/null 2>&1; then
        echo "Claude Code kuruluyor."
        curl -fsSL https://claude.ai/install.sh -o /tmp/claude-kur.sh
        bash /tmp/claude-kur.sh
        rm -f /tmp/claude-kur.sh
    fi
    command -v claude > /dev/null 2>&1 || { echo "Claude Code kurulamadı."; return 1; }
    echo "Claude Code: $(claude --version 2> /dev/null | head -1)"

    local DEGISTI=0
    birim() {  # birim ADI İÇERİK : yalnız içerik değiştiyse yazar
        local YOL="/etc/systemd/system/$1"
        if [ "$(cat "$YOL" 2> /dev/null)" != "$2" ]; then
            printf '%s\n' "$2" > "$YOL"
            DEGISTI=1
        fi
    }
    birim karabasan-claude.service "[Unit]
Description=Karabasan: Claude uzaktan yonetim oturumu
After=network-online.target
Wants=network-online.target

[Service]
Environment=HOME=/root
Environment=LANG=C.UTF-8
WorkingDirectory=$KLASOR
ExecStart=/bin/bash $KLASOR/araclar/claude_sunucu.sh oturum
ExecStopPost=-/usr/bin/tmux -L kb-claude kill-server
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target"
    birim karabasan-claude-giris.service "[Unit]
Description=Karabasan: Claude giris akisi
After=network-online.target

[Service]
Environment=HOME=/root
Environment=LANG=C.UTF-8
WorkingDirectory=$KLASOR
ExecStart=/bin/bash $KLASOR/araclar/claude_sunucu.sh giris
ExecStopPost=-/usr/bin/tmux -L kb-giris kill-server
TimeoutStartSec=infinity"
    birim karabasan-claude-istek.service "[Unit]
Description=Karabasan: Telegram'dan gelen Claude isteklerini isle

[Service]
Type=oneshot
Environment=HOME=/root
Environment=LANG=C.UTF-8
ExecStart=/bin/bash $KLASOR/araclar/claude_sunucu.sh istek"
    birim karabasan-claude-istek.path "[Unit]
Description=Karabasan: Claude istek dosyalarini izle

[Path]
PathExistsGlob=$VERI/claude_*.istek

[Install]
WantedBy=multi-user.target"
    if [ "$DEGISTI" -eq 1 ]; then systemctl daemon-reload; fi
    systemctl enable --now karabasan-claude-istek.path > /dev/null 2>&1 || true

    if giris_var_mi; then
        systemctl enable karabasan-claude.service > /dev/null 2>&1 || true
        # Oturum adresi yoksa oturum açılamamış ya da açılışta takılmış demektir:
        # servis "çalışıyor" görünse de yeniden başlat ki bu betiğin yeni hali denensin
        # ve sonuç (hazır ya da takıldı) Telegram'a yeniden yazılsın.
        if [ "$DEGISTI" -eq 1 ] || ! systemctl is-active --quiet karabasan-claude.service \
                || [ ! -s "$DURUM_KLASORU/claude_adresi" ]; then
            rm -f "$DURUM_KLASORU/claude_bildirilen"
            systemctl restart --no-block karabasan-claude.service || true
        fi
    elif [ ! -f "$DURUM_KLASORU/claude_giris_istendi" ]; then
        # Giriş bağlantısı ilk kurulumda bir kez kendiliğinden gönderilir;
        # sonrası için Ahmet Telegram'da /claude yazar.
        touch "$DURUM_KLASORU/claude_giris_istendi"
        systemctl restart --no-block karabasan-claude-giris.service || true
    fi
    durum_yaz
}

# ------------------------------------------------------------------ giris
giris() {
    if giris_var_mi; then
        yaz "Giriş zaten yapılmış."
        systemctl enable --now karabasan-claude.service > /dev/null 2>&1 || true
        durum_yaz
        return 0
    fi
    giris_tmux kill-server 2> /dev/null || true
    giris_tmux new-session -d -s giris -x 600 -y 50 "claude auth login --claudeai"
    local ADRES="" EKRAN=""
    for _ in $(seq 1 60); do
        EKRAN="$(giris_ekrani)"
        ADRES="$(printf '%s\n' "$EKRAN" | grep -Eo 'https://[A-Za-z0-9./_-]*oauth/authorize\?[^[:space:]]+' | head -1 || true)"
        if [ -n "$ADRES" ]; then break; fi
        giris_tmux has-session -t giris 2> /dev/null || break
        sleep 1
    done
    if [ -z "$ADRES" ]; then
        yaz "Giriş bağlantısı alınamadı. Ekran: $EKRAN"
        bildir "Claude giriş bağlantısı alınamadı. /kurulum yazıp gelen dosyayı Claude'a ilet."
        giris_tmux kill-server 2> /dev/null || true
        return 1
    fi
    yaz "Giriş bağlantısı gönderildi."
    bildir "Claude'u sunucuya bağlamak için bir kerelik giriş gerekiyor:

1. Şu bağlantıya dokun ve Claude hesabınla giriş yap, izin isteyince onayla:
$ADRES

2. Ekranda bir kod çıkacak. Kodu kopyala ve bana şöyle yaz:
/claude KOD

Bağlantı 30 dakika bekler. Süre dolarsa /claude yazıp yenisini iste."

    # Kod gelene (ya da süre dolana) kadar bekle; kodu 'istek' işi yapıştırır.
    local BITIS=$(( $(date +%s) + 1800 )) TUR=0
    while [ "$(date +%s)" -lt "$BITIS" ]; do
        giris_tmux has-session -t giris 2> /dev/null || break
        EKRAN="$(giris_ekrani)"
        # Giriş programı kod kabul edildikten sonra bir tuş bekleyip açık kalabilir;
        # giriş gerçekleştiyse beklemeyi bırak.
        TUR=$((TUR + 1))
        if [ $((TUR % 5)) -eq 0 ] && giris_var_mi; then break; fi
        sleep 2
    done
    giris_tmux kill-server 2> /dev/null || true

    if giris_var_mi; then
        yaz "Giriş başarılı."
        bildir "Giriş tamam. Uzaktan yönetim oturumunu açıyorum; hazır olunca yazacağım."
        systemctl enable karabasan-claude.service > /dev/null 2>&1 || true
        systemctl restart --no-block karabasan-claude.service || true
    else
        yaz "Giriş tamamlanmadı. Son ekran: $(printf '%s' "$EKRAN" | tail -5 | cut -c1-300)"
        bildir "Claude girişi tamamlanmadı (süre doldu ya da kod kabul edilmedi). Yeniden denemek için /claude yaz."
    fi
    durum_yaz
}

# ------------------------------------------------------------------ istek
istek() {
    local DOSYA KOD
    DOSYA="$VERI/claude_giris.istek"
    if [ -e "$DOSYA" ]; then
        rm -f "$DOSYA"
        if giris_var_mi; then
            systemctl enable karabasan-claude.service > /dev/null 2>&1 || true
            systemctl restart --no-block karabasan-claude.service || true
        else
            systemctl restart --no-block karabasan-claude-giris.service || true
        fi
    fi
    DOSYA="$VERI/claude_kod.istek"
    if [ -e "$DOSYA" ]; then
        KOD="$(head -c 600 "$DOSYA" | tr -d ' \r\n\t')"
        rm -f "$DOSYA"
        if ! printf '%s' "$KOD" | grep -Eq '^[A-Za-z0-9_#.~-]{8,512}$'; then
            bildir "Bu bir giriş koduna benzemiyor. Kodu sayfadan olduğu gibi kopyalayıp /claude KOD diye yaz."
        elif giris_tmux has-session -t giris 2> /dev/null; then
            # -l: metin tuş adı olarak yorumlanmaz, harfi harfine yazılır.
            giris_tmux send-keys -t giris -l -- "$KOD"
            giris_tmux send-keys -t giris Enter
            yaz "Giriş kodu yapıştırıldı."
        else
            bildir "Bekleyen bir giriş yok. /claude yazıp yeni bağlantı iste."
        fi
    fi
    # İşlenmeyen başka istek dosyası kalmasın; yoksa izleyici sürekli tetiklenir.
    rm -f "$VERI"/claude_*.istek
    durum_yaz
}

# ------------------------------------------------------------------ oturum
oturum() {
    if ! giris_var_mi; then
        yaz "Giriş yok; oturum açılmadı."
        durum_yaz
        # Giriş yapılana kadar servis boşuna dönmesin.
        systemctl disable karabasan-claude.service > /dev/null 2>&1 || true
        sleep 3600
        return 0
    fi
    oturum_tmux kill-server 2> /dev/null || true
    rm -f "$DURUM_KLASORU/claude_adresi"
    # --spawn=same-dir: verilmezse program "Choose [1/2] (default: 1):" diye sorar.
    # 10 Ekim'deki ilk açılış bu soruda takılı kalmıştı (kayıt: /gunluk claude).
    oturum_tmux new-session -d -s claude -x 250 -y 50 -c "$KLASOR" \
        "claude remote-control --name '$OTURUM_ADI' --spawn=same-dir"
    yaz "Oturum başlatıldı."
    local EKRAN="" ADRES="" ESKI_ADRES="" SON_YANIT=0 SIMDI SAYAC=0 YANIT_SAYISI=0 SON_SATIRLAR SORU
    local BASLANGIC TAKILDI_YAZILDI=0
    BASLANGIC="$(date +%s)"
    while oturum_tmux has-session -t claude 2> /dev/null; do
        EKRAN="$(oturum_ekrani)"
        printf '%s\n' "$EKRAN" > "$VERI/logs/claude_ekrani.txt"
        SIMDI="$(date +%s)"
        # İlk açılıştaki sorular: bu klasöre güven, özelliği aç, oturumlar aynı klasörde
        # açılsın (sonuncusu --spawn ile zaten verildi; yine sorarsa diye). Soru ekranın
        # son satırlarındaysa yanıtlanır (altında bir ipucu satırı olabilir). Oturum adresi
        # görüldükten sonra hiçbir tuş gönderilmez; açılışta da en fazla altı kez.
        SON_SATIRLAR="$(printf '%s\n' "$EKRAN" | grep -v '^[[:space:]]*$' | tail -6)"
        SORU="$(printf '%s\n' "$SON_SATIRLAR" \
            | grep -E 'Enable Remote Control\? *\(y/n\)|Trust .*\[y/N\]|Choose \[1/2\] \(default: 1\)' | tail -1 || true)"
        if [ -z "$ESKI_ADRES" ] && [ -n "$SORU" ] && [ "$YANIT_SAYISI" -lt 6 ] \
                && [ $((SIMDI - SON_YANIT)) -ge 10 ]; then
            if printf '%s' "$SORU" | grep -q 'Choose \[1/2\]'; then
                oturum_tmux send-keys -t claude 1     # same-dir: oturumlar bu klasörde çalışır
            else
                oturum_tmux send-keys -t claude y
            fi
            oturum_tmux send-keys -t claude Enter
            SON_YANIT="$SIMDI"
            YANIT_SAYISI=$((YANIT_SAYISI + 1))
            yaz "Açılış sorusu yanıtlandı: $(printf '%s' "$SORU" | cut -c1-80)"
        fi
        # Adres iki dakikada gelmediyse açılış takılmıştır: son ekranı bir kez bildir
        # (kendi kendine teşhis), beş dakikada gelmediyse kapatıp baştan dene.
        if [ -z "$ESKI_ADRES" ] && [ $((SIMDI - BASLANGIC)) -ge "${CLAUDE_TAKILMA_SANIYE:-120}" ] \
                && [ "$TAKILDI_YAZILDI" -eq 0 ]; then
            TAKILDI_YAZILDI=1
            yaz "Açılış takıldı. Son ekran: $(printf '%s' "$SON_SATIRLAR" | cut -c1-200 | tr '\n' '|')"
            if [ "$(cat "$DURUM_KLASORU/claude_bildirilen" 2> /dev/null)" != "takildi" ]; then
                echo takildi > "$DURUM_KLASORU/claude_bildirilen"
                bildir "Claude'un sunucudaki oturumu açılışta bekliyor; iki dakikadır oturum adresi gelmedi. Ekranın son satırları (bunu Claude'a ilet):

$(printf '%s' "$SON_SATIRLAR" | cut -c1-200)"
            fi
        fi
        if [ -z "$ESKI_ADRES" ] && [ $((SIMDI - BASLANGIC)) -ge "${CLAUDE_VAZGECME_SANIYE:-300}" ]; then
            yaz "Beş dakikada açılmadı; oturum kapatılıp yeniden denenecek."
            oturum_tmux kill-server 2> /dev/null || true
            break
        fi
        ADRES="$(printf '%s\n' "$EKRAN" | grep -Eo 'https://claude\.ai/code[^[:space:]]*' | tail -1 || true)"
        if [ -n "$ADRES" ] && [ "$ADRES" != "$ESKI_ADRES" ]; then
            ESKI_ADRES="$ADRES"
            echo "$ADRES" > "$DURUM_KLASORU/claude_adresi"
            durum_yaz
            yaz "Oturum hazır."
            if [ "$(cat "$DURUM_KLASORU/claude_bildirilen" 2> /dev/null)" != "hazir" ]; then
                echo hazir > "$DURUM_KLASORU/claude_bildirilen"
                bildir "Claude sunucuda hazır. Telefonundaki Claude uygulamasında Code bölümünü aç; \"$OTURUM_ADI\" adlı oturumu göreceksin. Doğrudan bağlantı:
$ADRES

Orada yazdıkların sunucunun içinde çalışır. Sunucuda bir şeyi değiştirecek komutlardan önce senden onay ister."
            fi
        fi
        SAYAC=$((SAYAC + 1))
        if [ $((SAYAC % 20)) -eq 0 ]; then durum_yaz; fi
        sleep 3
    done
    yaz "Oturum kapandı. Son ekran: $(printf '%s' "$EKRAN" | grep -v '^[[:space:]]*$' | tail -6 | cut -c1-300)"
    rm -f "$DURUM_KLASORU/claude_adresi"
    durum_yaz
    case "$(cat "$DURUM_KLASORU/claude_bildirilen" 2> /dev/null)" in
        sorun | takildi) ;;  # zaten bildirildi; sessizce yeniden dene
        *)
            if [ -z "$ESKI_ADRES" ]; then
                # Hiç açılamadı: nedenini (son ekranı) bir kez yaz, sonra sessizce yeniden dene.
                echo sorun > "$DURUM_KLASORU/claude_bildirilen"
                bildir "Claude'un sunucudaki oturumu açılamadı. Ekranın son satırları (bunu Claude'a ilet):

$(printf '%s' "$EKRAN" | grep -v '^[[:space:]]*$' | tail -8 | cut -c1-200)"
            fi
            ;;
    esac
    return 1
}

case "${1:-}" in
    kur) kur ;;
    giris) giris ;;
    oturum) oturum ;;
    istek) istek ;;
    durum) durum_yaz ;;
    *) echo "Kullanım: $0 kur|giris|oturum|istek|durum"; exit 2 ;;
esac
