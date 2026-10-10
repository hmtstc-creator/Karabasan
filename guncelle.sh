#!/usr/bin/env bash
# Karabasan Bot - güncellemeyi elle tetikler. Normalde gerekmez: sunucu
# 5 dakikada bir kendisi denetler (araclar/oto_guncelle.sh).
#
#   bash /opt/karabasan-bot/guncelle.sh

exec bash "$(dirname "$0")/araclar/oto_guncelle.sh"
