#!/usr/bin/env python3
"""Panel sınaması (bkz. karabasan/sinama.py).

Kapsayıcı içinde çalıştırılır; araclar/panel_sinama.sh önce 4 yıllık veriyi ve fonlama
geçmişini indirir:

    docker compose run --rm --entrypoint python3 arac /freqtrade/araclar/panel_sinama.py

Rapor ekrana yazılır (panel_sinama.sh onu user_data/logs/panel_sinama.txt'e koyar).
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "araclar"))

from karabasan import fonlama  # noqa: E402
from karabasan.sinama import sina  # noqa: E402
from karsilastir import mumlari_oku  # noqa: E402

FONLAMA_KLASORU = KOK / "user_data" / "data" / "fonlama"


def main() -> int:
    metin, _sonuc = sina(lambda coin, dilim: mumlari_oku(coin, dilim, "vadeli"),
                         lambda coin: fonlama.oku(coin, FONLAMA_KLASORU))
    print(metin, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
