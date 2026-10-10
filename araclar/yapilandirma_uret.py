#!/usr/bin/env python3
"""On sanal botun yapılandırma dosyalarını ve docker-compose.yml'i üretir.

Kullanım (depo kökünde):

    python3 araclar/yapilandirma_uret.py

Yalnız Python standart kütüphanesini kullanır; sunucuda ek kurulum istemez.
Üretilen dosyalar:

    user_data/ayarlar.json            (yoksa başlangıç değerleriyle oluşturulur)
    user_data/config/<bot>.json       (her bot için)
    user_data/config/geri_test.json   (geçmiş testi için sabit parite listesi)
    docker-compose.yml
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from karabasan.botlar import (  # noqa: E402
    BOTLAR,
    ILK_PORT,
    VARSAYILAN_AYARLAR,
    ayarlari_yukle,
)
from karabasan.kural import kural_yukle  # noqa: E402

GORUNTU = "freqtradeorg/freqtrade:stable"

# 1. katman (uygunluk): alım satımı anlamsız ya da riskli olanlar.
SABIT_COINLER = (
    "USDC|FDUSD|TUSD|USDP|DAI|BUSD|EUR|EURI|AEUR|USD1|XUSD|BFUSD|USDE|PYUSD|RLUSD|USDS|USDD"
)
SARILI_COINLER = "WBTC|WBETH|WETH|BNSOL|WBNB|WSOL"
# BNB komisyon için tutulur; bot alıp satmamalı. PAXG altına bağlıdır.
DIGER_HARIC = "BNB|PAXG"
# Vadelide kripto olmayan sözleşmeler (altın, gümüş vb.) işlem evreninde yer almaz.
KRIPTO_OLMAYAN = "XAU|XAG|XPT|XPD"

# Geçmiş testi ve uyum denemesi için sabit, yüksek hacimli pariteler.
GERI_TEST_COINLERI = ["BTC", "ETH", "SOL", "XRP", "DOGE"]


# Kapsayıcı günlükleri diski doldurmasın.
GUNLUK_SINIRI = [
    "    logging:",
    "      driver: json-file",
    "      options:",
    "        max-size: \"10m\"",
    "        max-file: \"3\"",
]


def kara_liste(piyasa: str) -> list[str]:
    desenler = [f"({SABIT_COINLER})/.*", f"({SARILI_COINLER})/.*", f"({DIGER_HARIC})/.*"]
    if piyasa == "vadeli":
        desenler.append(f"({KRIPTO_OLMAYAN})/.*")
    return desenler


def parite_listeleri(piyasa: str, ayar: dict) -> list[dict]:
    liste = [
        {
            "method": "VolumePairList",
            "number_assets": int(ayar["parite_sayisi"]),
            "sort_key": "quoteVolume",
            "min_value": float(ayar["en_az_hacim_24s"]),
            "refresh_period": 1800,
        },
        {"method": "AgeFilter", "min_days_listed": int(ayar["en_az_listelenme_gun"])},
    ]
    if piyasa == "spot":
        # Vadelide borsa alış-satış fiyatını toplu vermediği için bu süzgeç yalnız spot'ta var.
        liste.append(
            {"method": "SpreadFilter", "max_spread_ratio": float(ayar["en_fazla_fark_yuzde"]) / 100.0}
        )
    return liste


def bot_yapilandirmasi(bot: str, kural_kodu: str, piyasa: str, ayar: dict) -> dict:
    kural_yukle(kural_kodu)  # kural dosyası bozuksa burada, üretim sırasında dursun
    yapi = {
        "bot_name": bot,
        "dry_run": True,
        "dry_run_wallet": float(ayar["sanal_bakiye"]),
        "stake_currency": "USDT",
        "stake_amount": float(ayar["islem_tutari"]),
        "max_open_trades": int(ayar["en_fazla_pozisyon"]),
        "tradable_balance_ratio": 1.0,
        "trading_mode": "futures" if piyasa == "vadeli" else "spot",
        "fee": float(ayar["komisyon_yuzde"][piyasa]) / 100.0,
        "cancel_open_orders_on_exit": False,
        "force_entry_enable": False,
        "initial_state": "running",
        "unfilledtimeout": {"entry": 10, "exit": 10, "exit_timeout_count": 0, "unit": "minutes"},
        # Tüm emirler piyasa emridir ve karşı taraftan fiyatlanır: kötümser varsayım.
        "entry_pricing": {
            "price_side": "other",
            "use_order_book": True,
            "order_book_top": 1,
            "price_last_balance": 0.0,
            "check_depth_of_market": {"enabled": False, "bids_to_ask_delta": 1},
        },
        "exit_pricing": {"price_side": "other", "use_order_book": True, "order_book_top": 1},
        "order_types": {
            "entry": "market",
            "exit": "market",
            "emergency_exit": "market",
            "force_entry": "market",
            "force_exit": "market",
            "stoploss": "market",
            "stoploss_on_exchange": False,
            "stoploss_on_exchange_interval": 60,
        },
        "exchange": {
            "name": "binance",
            # Sanal sınavda API anahtarı kullanılmaz.
            "key": "",
            "secret": "",
            "ccxt_config": {},
            "ccxt_async_config": {},
            "pair_whitelist": [],
            "pair_blacklist": kara_liste(piyasa),
        },
        "pairlists": parite_listeleri(piyasa, ayar),
        "telegram": {"enabled": False, "token": "", "chat_id": ""},
        "api_server": {
            "enabled": True,
            "listen_ip_address": "0.0.0.0",
            "listen_port": 8080,
            "verbosity": "error",
            "enable_openapi": False,
            # Gerçek değerler .env dosyasından ortam değişkeniyle gelir.
            "jwt_secret_key": "ENV_DOSYASINDAN_GELIR",
            "ws_token": "ENV_DOSYASINDAN_GELIR",
            # Paneli tarayıcıda açtığın adresler; kurulum betiği doldurur.
            "CORS_origins": list(ayar.get("panel_adresleri", [])),
            "username": "karabasan",
            "password": "ENV_DOSYASINDAN_GELIR",
        },
        "internals": {"process_throttle_secs": 5},
    }
    if piyasa == "vadeli":
        yapi["margin_mode"] = "isolated"
    return yapi


def geri_test_yapilandirmasi(piyasa: str) -> dict:
    """Geçmiş testinde hacim sıralaması kullanılamaz; sabit liste gerekir."""
    ek = ":USDT" if piyasa == "vadeli" else ""
    return {
        "exchange": {"pair_whitelist": [f"{c}/USDT{ek}" for c in GERI_TEST_COINLERI]},
        "pairlists": [{"method": "StaticPairList"}],
        "api_server": {"enabled": False},
    }


def compose_metni() -> str:
    satirlar = [
        "# Bu dosya araclar/yapilandirma_uret.py tarafından üretilir. Elle düzenleme.",
        "services:",
        # Tek seferlik komutlar için (veri indirme, geçmiş testi): docker compose run --rm arac ...
        "  arac:",
        f"    image: {GORUNTU}",
        "    profiles: [\"arac\"]",
        "    volumes:",
        "      - ./user_data:/freqtrade/user_data",
        "      - ./karabasan:/freqtrade/karabasan:ro",
        "      - ./araclar:/freqtrade/araclar:ro",
        "",
    ]
    # BTC dominansı ve TOTAL2'yi 10 dakikada bir kaydeder.
    satirlar += [
        "  kayitci:",
        f"    image: {GORUNTU}",
        "    container_name: kb-kayitci",
        "    restart: unless-stopped",
        "    volumes:",
        "      - ./user_data:/freqtrade/user_data",
        "      - ./karabasan:/freqtrade/karabasan:ro",
        "    entrypoint: [\"python3\", \"-m\", \"karabasan.kayitci\"]",
        *GUNLUK_SINIRI,
        "",
    ]
    for sira, (bot, sinif, _kural, _piyasa) in enumerate(BOTLAR):
        port = ILK_PORT + sira
        # Botlar borsaya aynı anda yüklenmesin diye sırayla, 45 saniye arayla açılır.
        gecikme = sira * 45
        komut = (
            f"sleep {gecikme} && exec freqtrade trade"
            f" --logfile /freqtrade/user_data/logs/{bot}.log"
            f" --db-url sqlite:////freqtrade/user_data/db/{bot}.sqlite"
            f" --config /freqtrade/user_data/config/{bot}.json"
            f" --strategy {sinif}"
        )
        satirlar += [
            f"  {bot}:",
            f"    image: {GORUNTU}",
            f"    container_name: kb-{bot}",
            "    restart: unless-stopped",
            "    env_file: .env",
            "    volumes:",
            "      - ./user_data:/freqtrade/user_data",
            "      - ./karabasan:/freqtrade/karabasan:ro",
            "    ports:",
            # Yalnız sunucunun kendisinden erişilir; dışarıya özel ağ (Tailscale) taşır.
            f"      - \"127.0.0.1:{port}:8080\"",
            "    entrypoint: [\"/bin/sh\", \"-c\"]",
            f"    command: [\"{komut}\"]",
            *GUNLUK_SINIRI,
            "",
        ]
    return "\n".join(satirlar)


def yaz(yol: Path, icerik: str) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(icerik, encoding="utf-8")


def main() -> int:
    veri = KOK / "user_data"
    ayar_dosyasi = veri / "ayarlar.json"
    if not ayar_dosyasi.exists():
        yaz(ayar_dosyasi, json.dumps(VARSAYILAN_AYARLAR, ensure_ascii=False, indent=2) + "\n")
        print(f"Oluşturuldu: {ayar_dosyasi.relative_to(KOK)} (başlangıç değerleriyle)")
    ayar = ayarlari_yukle(ayar_dosyasi)

    for klasor in ("config", "db", "logs", "data", "kayit"):
        (veri / klasor).mkdir(parents=True, exist_ok=True)

    for bot, _sinif, kural_kodu, piyasa in BOTLAR:
        yapi = bot_yapilandirmasi(bot, kural_kodu, piyasa, ayar)
        yaz(veri / "config" / f"{bot}.json", json.dumps(yapi, ensure_ascii=False, indent=2) + "\n")
    for piyasa in ("spot", "vadeli"):
        yaz(
            veri / "config" / f"geri_test_{piyasa}.json",
            json.dumps(geri_test_yapilandirmasi(piyasa), ensure_ascii=False, indent=2) + "\n",
        )
    yaz(KOK / "docker-compose.yml", compose_metni() + "\n")

    print(f"{len(BOTLAR)} bot yapılandırması ve docker-compose.yml üretildi.")
    print(
        "Komisyon: spot %{spot:g}, vadeli %{vadeli:g} (taraf başına). "
        "Değiştirmek için user_data/ayarlar.json dosyasını düzenle ve bu komutu yeniden çalıştır.".format(
            **ayar["komisyon_yuzde"]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
