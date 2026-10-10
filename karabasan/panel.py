"""Sonuç sayfası sunucusu.

Tek iş yapar: karabasan.sonuc özetini karabasan.sayfa ile HTML'e çevirip
sunar. Salt okunurdur; hiçbir ayarı değiştirmez, hiçbir botu yönetmez.

    python3 -m karabasan.panel

Adresler:
    /            Türkçe sonuç sayfası
    /veri.json   Aynı özetin ham hali
    /saglik      Sunucu ayakta mı (izleme için)

Yalnız Python standart kütüphanesi ile karabasan paketini kullanır.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .sayfa import betik, html_uret
from .sonuc import genel_ozet, json_icin

ONBELLEK_SANIYE = 20
YENILE_SANIYE = 60


def guvenlik_basligi(yenile_saniye: int = YENILE_SANIYE) -> str:
    """Tarayıcıya neye izin verildiğini söyler (Content-Security-Policy).

    Sayfa yalnız kendi içindeki biçimi ve tek bir betiği kullanabilir; betik
    metninin özeti (sha256) burada yazdığı için başka hiçbir betik çalışmaz.
    Betik yalnız bu sunucudan veri çekebilir. Dış kaynak, çerçeve ve form yok.
    """
    ozet = base64.b64encode(hashlib.sha256(betik(yenile_saniye).encode("utf-8")).digest()).decode("ascii")
    return (
        "default-src 'none'; style-src 'unsafe-inline'; "
        f"script-src 'sha256-{ozet}'; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )

gunluk = logging.getLogger("karabasan.panel")


def veri_klasoru() -> Path:
    ortam = os.environ.get("KARABASAN_VERI")
    if ortam:
        return Path(ortam)
    return Path(__file__).resolve().parent.parent / "user_data"


class Onbellek:
    """Özeti kısa süre saklar; sayfa sık yenilense de kayıt dosyaları sık okunmaz."""

    def __init__(self, klasor: Path, sure: float = ONBELLEK_SANIYE):
        self.klasor = klasor
        self.sure = sure
        self._kilit = threading.Lock()
        self._ozet = None
        self._zaman = 0.0

    def ozet(self) -> dict:
        with self._kilit:
            if self._ozet is None or time.monotonic() - self._zaman > self.sure:
                self._ozet = genel_ozet(self.klasor)
                self._zaman = time.monotonic()
            return self._ozet


HATA_SAYFASI = """<!doctype html><html lang="tr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Karabasan</title><body style="font:16px/1.5 system-ui,sans-serif;max-width:40em;margin:2em auto;padding:0 16px">
<h1>Sayfa şu an hazırlanamadı</h1>
<p>Botlar bundan etkilenmez; yalnız bu sayfa özet çıkaramadı. Bir dakika sonra yeniden dene.
Sorun sürerse şu satırı Claude'a gönder:</p><pre style="white-space:pre-wrap">{hata}</pre></body></html>"""


def isleyici_uret(onbellek: Onbellek):
    guvenlik = guvenlik_basligi()

    class Isleyici(BaseHTTPRequestHandler):
        server_version = "Karabasan"
        sys_version = ""

        def _yanit(self, kod: int, tur: str, govde: bytes) -> None:
            self.send_response(kod)
            self.send_header("Content-Type", tur)
            self.send_header("Content-Length", str(len(govde)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", guvenlik)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(govde)

        def do_GET(self) -> None:  # noqa: N802 - http.server böyle adlandırır
            yol = self.path.split("?", 1)[0]
            try:
                if yol == "/saglik":
                    self._yanit(200, "text/plain; charset=utf-8", b"tamam\n")
                elif yol == "/veri.json":
                    govde = json.dumps(json_icin(onbellek.ozet()), ensure_ascii=False, indent=1)
                    self._yanit(200, "application/json; charset=utf-8", govde.encode("utf-8"))
                elif yol in ("/", "/index.html"):
                    self._yanit(
                        200, "text/html; charset=utf-8",
                        html_uret(onbellek.ozet(), yenile_saniye=YENILE_SANIYE).encode("utf-8"),
                    )
                else:
                    self._yanit(404, "text/plain; charset=utf-8", "Böyle bir sayfa yok.\n".encode("utf-8"))
            except Exception as hata:  # noqa: BLE001 - sayfa her durumda bir yanıt vermeli
                gunluk.exception("Sayfa hazırlanamadı")
                from html import escape

                govde = HATA_SAYFASI.format(hata=escape(f"{type(hata).__name__}: {hata}"))
                self._yanit(500, "text/html; charset=utf-8", govde.encode("utf-8"))

        do_HEAD = do_GET  # noqa: N815

        def log_message(self, bicim, *degerler) -> None:
            gunluk.debug("%s %s", self.address_string(), bicim % degerler)

    return Isleyici


def sunucu_kur(klasor: Path, adres: str = "0.0.0.0", port: int = 8080) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((adres, port), isleyici_uret(Onbellek(klasor)))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    port = int(os.environ.get("KARABASAN_PANEL_PORT", "8080"))
    sunucu = sunucu_kur(veri_klasoru(), port=port)
    gunluk.info("Sonuç sayfası %s numaralı kapıda hazır.", port)
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
