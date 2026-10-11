#!/usr/bin/env python3
"""Çıkış varyasyonu taraması (bkz. karabasan/tarama.py).

Kapsayıcı içinde çalıştırılır; veriyi 12 aylık test (araclar/yillik_test.sh) indirir:

    docker compose run --rm --entrypoint python3 arac /freqtrade/araclar/tarama.py 365

Rapor ekrana yazılır; araclar/tarama.sh onu user_data/logs/tarama.txt'e koyar.
Hiçbir ayarı değiştirmez.
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "araclar"))

from karabasan.tarama import tara  # noqa: E402
from karsilastir import mumlari_oku  # noqa: E402


def main() -> int:
    gun = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    metin, _satirlar, eksik = tara(mumlari_oku, gun)
    print(metin, end="")
    if eksik:
        print(f"UYARI: {eksik} veri dosyası bulunamadı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
