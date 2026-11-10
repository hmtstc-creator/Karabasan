"""Coin listesi sayfası (sonuç sayfası /coinler).

Binance vadelideki (USDT sözleşmeli, sürekli) bütün coinleri listeler; stable coinleri
çıkarır, 24 saatlik USDT hacmi seçilen sınırı geçenleri gösterir. Yalnız okur: botların
işlem evrenini DEĞİŞTİRMEZ (botların kendi süzgeci `yapilandirma_uret.py`'dedir).
Yalnız standart kütüphane; Binance'in herkese açık, anahtarsız adreslerini kullanır.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from html import escape

TABAN = "https://fapi.binance.com"
VARSAYILAN_HACIM_MILYON = 5.0  # botlarla aynı: en az 5 milyon USDT
EN_FAZLA_HACIM_MILYON = 100_000.0
SECENEKLER = (1, 5, 10, 25, 50, 100, 250, 500)
ONBELLEK_SANIYE = 300

# Fiyatı 1 dolara bağlı ya da başka bir paraya bağlı coinler (taban varlık adı).
STABLE = frozenset({
    "USDT", "USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "EUR", "EURI", "AEUR", "USD1", "XUSD",
    "BFUSD", "USDE", "PYUSD", "RLUSD", "USDS", "USDD", "UST", "USTC", "GUSD", "LUSD", "FRAX",
    "SUSD", "CUSD", "HUSD", "USDX", "USDJ", "USDK", "TRYB", "GBPT", "BIDR", "IDRT", "UAH", "BRL",
    "USDG", "USDQ", "USDR", "USDY", "USDM", "USDB", "USDL", "USDT0", "USDF", "USDA", "USX",
})


def _adres(yol: str) -> str:
    return os.environ.get("KARABASAN_BINANCE_FAPI", TABAN).rstrip("/") + yol


def _getir(yol: str):
    istek = urllib.request.Request(_adres(yol), headers={"User-Agent": "karabasan-bot"})
    with urllib.request.urlopen(istek, timeout=15) as yanit:
        return json.loads(yanit.read().decode("utf-8"))


def stable_mi(taban: str) -> bool:
    return taban.upper() in STABLE


def birlestir(borsa_bilgisi: dict, tickerlar: list) -> list[dict]:
    """exchangeInfo + 24 saatlik ticker -> stable olmayan, işlemdeki USDT sözleşmeleri."""
    islemde = {}
    for s in borsa_bilgisi.get("symbols", []):
        if (s.get("status") == "TRADING" and s.get("contractType") == "PERPETUAL"
                and s.get("quoteAsset") == "USDT"):
            islemde[s["symbol"]] = s["baseAsset"]
    sonuc = []
    for t in tickerlar:
        taban = islemde.get(t.get("symbol"))
        if taban is None or stable_mi(taban):
            continue
        try:
            sonuc.append({"coin": taban, "hacim": float(t["quoteVolume"]), "fiyat": float(t["lastPrice"]),
                          "degisim": float(t["priceChangePercent"])})
        except (KeyError, TypeError, ValueError):
            continue
    return sonuc


def suz(coinler: list[dict], en_az_hacim: float) -> list[dict]:
    """Hacmi sınırı geçenler, en yüksek hacim önde."""
    gecen = [c for c in coinler if c["hacim"] >= en_az_hacim]
    return sorted(gecen, key=lambda c: (-c["hacim"], c["coin"]))


class Onbellek:
    def __init__(self):
        self._kilit = threading.Lock()
        self._veri: list[dict] | None = None
        self._zaman = 0.0

    def al(self) -> tuple[list[dict], float]:
        with self._kilit:
            simdi = time.time()
            if self._veri is None or simdi - self._zaman > ONBELLEK_SANIYE:
                try:
                    self._veri = birlestir(_getir("/fapi/v1/exchangeInfo"), _getir("/fapi/v1/ticker/24hr"))
                    self._zaman = simdi
                except Exception:  # noqa: BLE001 - eski liste varsa onu göster
                    if self._veri is None:
                        raise
            return self._veri, self._zaman


_ONBELLEK = Onbellek()


def hacim_oku(sorgu: dict) -> float:
    """?hacim=<milyon USDT>; bozuk ya da aşırı değerde varsayılan."""
    ham = (sorgu.get("hacim") or [""])[0].strip().replace(",", ".")
    try:
        d = float(ham)
    except ValueError:
        return VARSAYILAN_HACIM_MILYON
    if not 0 <= d <= EN_FAZLA_HACIM_MILYON or d != d:
        return VARSAYILAN_HACIM_MILYON
    return d


def _sayi(d: float, basamak: int = 2, isaret: bool = False) -> str:
    m = f"{d:{'+' if isaret else ''},.{basamak}f}"
    return m.replace(",", "_").replace(".", ",").replace("_", ".")


def _hacim_metni(d: float) -> str:
    if d >= 1e9:
        return f"{_sayi(d / 1e9, 2)} milyar"
    return f"{_sayi(d / 1e6, 1)} milyon"


def _fiyat_metni(f: float) -> str:
    return _sayi(f, 2 if f >= 1 else (4 if f >= 0.01 else 6))


BICIM = """
body{margin:0;background:#04070d;color:#e6edf5;font:15px/1.5 system-ui,sans-serif}
main{max-width:720px;margin:0 auto;padding:16px}
a{color:#7ab8ff}
h1{font-size:20px;margin:0 0 6px}
.soluk{color:#8fa0b5;font-size:13px}
.uyari{background:#3a2a10;border-radius:8px;padding:10px;margin:10px 0}
form{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0}
input[type=text]{width:90px;padding:8px;border-radius:8px;border:1px solid #2a3a50;background:#0b1320;color:#e6edf5;font-size:16px}
button,.sec{padding:8px 12px;border-radius:8px;border:1px solid #2a3a50;background:#12203a;color:#e6edf5;font-size:14px;text-decoration:none}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{padding:7px 6px;border-bottom:1px solid #1a2840;text-align:right}
th:nth-child(1),td:nth-child(1),th:nth-child(2),td:nth-child(2){text-align:left}
.arti{color:#4ade80}.eksi{color:#f87171}
"""


def guvenlik_basligi() -> str:
    return "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"


def sayfa_uret(sorgu: dict, onbellek: Onbellek | None = None) -> str:
    milyon = hacim_oku(sorgu)
    bas = ('<!doctype html><html lang="tr"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width, initial-scale=1">'
           '<meta name="robots" content="noindex"><title>Coin listesi</title>'
           f'<style>{BICIM}</style></head><body><main>')
    govde = ['<p><a href="/">&larr; Sonuç sayfası</a></p>', '<h1>Binance coin listesi</h1>',
             '<p class="soluk">Binance vadeli (USDT sözleşmeli) bütün coinler; stable coinler çıkarıldı. '
             'Yalnız son 24 saatte en az seçtiğin kadar USDT hacmi olanlar görünür. '
             'Bu sayfa yalnız bakmak içindir; botların işlem evrenini değiştirmez.</p>']
    govde.append('<form method="get" action="/coinler"><label for="h">En az 24 saatlik hacim (milyon USDT):</label>'
                 f'<input type="text" inputmode="decimal" id="h" name="hacim" value="{escape(_sayi(milyon, 2).rstrip("0").rstrip(","))}">'
                 '<button type="submit">Süz</button></form><p>'
                 + " ".join(f'<a class="sec" href="/coinler?hacim={s}">{s}</a>' for s in SECENEKLER) + "</p>")
    try:
        tum, zaman = (onbellek or _ONBELLEK).al()
    except Exception:  # noqa: BLE001
        govde.append('<div class="uyari">Binance\'e şu an ulaşılamadı. Biraz sonra yenile.</div>')
        return bas + "".join(govde) + "</main></body></html>"
    secilen = suz(tum, milyon * 1e6)
    govde.append(f'<p><b>{len(secilen)}</b> coin sınırı geçti (toplam {len(tum)} stable olmayan coin içinden). '
                 f'<span class="soluk">Veri {time.strftime("%H:%M:%S", time.gmtime(zaman))} UTC, 5 dakikada bir tazelenir.</span></p>')
    if secilen:
        satirlar = []
        for i, c in enumerate(secilen, 1):
            sinif = "arti" if c["degisim"] > 0 else ("eksi" if c["degisim"] < 0 else "")
            satirlar.append(f'<tr><td>{i}</td><td>{escape(c["coin"])}</td><td>{_hacim_metni(c["hacim"])}</td>'
                            f'<td>{_fiyat_metni(c["fiyat"])}</td>'
                            f'<td class="{sinif}">%{_sayi(c["degisim"], 2, True)}</td></tr>')
        govde.append("<table><tr><th>#</th><th>Coin</th><th>24s hacim (USDT)</th><th>Fiyat</th><th>24s değişim</th></tr>"
                     + "".join(satirlar) + "</table>")
    else:
        govde.append('<div class="uyari">Bu sınırı geçen coin yok. Sınırı düşür.</div>')
    return bas + "".join(govde) + "</main></body></html>"
