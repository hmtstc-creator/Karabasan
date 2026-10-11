#!/usr/bin/env python3
"""12 aylık geçmiş testi (bkz. karabasan/yillik.py).

Kapsayıcı içinde çalıştırılır; araclar/yillik_test.sh önce bir yıllık veriyi indirir:

    docker compose run --rm --entrypoint python3 arac /freqtrade/araclar/yillik_test.py 365

Rapor ekrana yazılır (yillik_test.sh onu user_data/logs/yillik_test.txt'e koyar);
bot başına işlem başına net sonuç user_data/gecmis_test.json'a yazılır.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "araclar"))

from karabasan.yillik import rapor_uret  # noqa: E402
from karsilastir import mumlari_oku  # noqa: E402

JSON_YOLU = KOK / "user_data" / "gecmis_test.json"


def main() -> int:
    gun = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    metin, sonuc, eksik = rapor_uret(mumlari_oku, gun)
    print(metin, end="")
    gecici = JSON_YOLU.with_suffix(".json.yeni")
    gecici.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
    gecici.replace(JSON_YOLU)
    if eksik:
        print(f"UYARI: {eksik} veri dosyası bulunamadı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
