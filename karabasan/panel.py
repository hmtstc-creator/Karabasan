"""Sonuç sayfası sunucusu.

Tek iş yapar: karabasan.sonuc özetini karabasan.sayfa ile HTML'e çevirip
sunar. Salt okunurdur; hiçbir ayarı değiştirmez, hiçbir botu yönetmez.

    python3 -m karabasan.panel

Adresler:
    /            Türkçe sonuç sayfası
    /veri.json   Aynı özetin ham hali
    /saglik      Sunucu ayakta mı (izleme için)
    /defter      Emir defteri denemesinin özeti (BTC/USDT vadeli, sanal)

Yalnız Python standart kütüphanesi ile karabasan paketini kullanır.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import logging
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .sayfa import betik, html_uret
from .sonuc import genel_ozet, json_icin

ONBELLEK_SANIYE = 20
YENIDEN_DENEME_SANIYE = 20
SIKISTIRMA_ESIGI = 1024
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
    """Özeti kısa süre saklar; sayfa sık yenilense de kayıt dosyaları sık okunmaz.

    Özet çıkarılamazsa son başarılı özet sunulmaya devam eder (sayfadaki "Son güncelleme"
    saati onun ne kadar eski olduğunu gösterir); yeniden deneme en erken 20 saniye sonradır.
    Üretilen HTML de aynı özete bağlı saklanır, böylece her istekte yeniden üretilmez.
    """

    def __init__(self, klasor: Path, sure: float = ONBELLEK_SANIYE):
        self.klasor = klasor
        self.sure = sure
        self._kilit = threading.Lock()
        self._ozet = None
        self._zaman = 0.0
        self._deneme = 0.0
        self.son_hata: str | None = None
        self._html: tuple[int, bytes, str] | None = None
        self._surum = 0

    def ozet(self) -> dict:
        with self._kilit:
            simdi = time.monotonic()
            taze = self._ozet is not None and simdi - self._zaman <= self.sure
            bekle = self._ozet is not None and self.son_hata and simdi - self._deneme < YENIDEN_DENEME_SANIYE
            if not taze and not bekle:
                self._deneme = simdi
                try:
                    self._ozet = genel_ozet(self.klasor)
                    self._zaman = simdi
                    self._surum += 1
                    self.son_hata = None
                except Exception as hata:  # noqa: BLE001 - eski özet varsa onu sun
                    self.son_hata = f"{type(hata).__name__}: {hata}"
                    if self._ozet is None:
                        raise
                    gunluk.exception("Özet çıkarılamadı; son başarılı özet sunuluyor")
            return self._ozet

    def yas_saniye(self) -> float | None:
        return None if self._ozet is None else time.monotonic() - self._zaman

    def html(self) -> tuple[bytes, str]:
        """(sayfa baytları, ETag). Özet değişmedikçe aynı baytlar döner."""
        self.ozet()
        with self._kilit:
            if self._html is None or self._html[0] != self._surum:
                govde = html_uret(self._ozet, yenile_saniye=YENILE_SANIYE).encode("utf-8")
                etiket = '"' + hashlib.sha256(govde).hexdigest()[:20] + '"'
                self._html = (self._surum, govde, etiket)
            return self._html[1], self._html[2]


HATA_SAYFASI = """<!doctype html><html lang="tr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Karabasan</title><body style="font:16px/1.5 system-ui,sans-serif;max-width:40em;margin:2em auto;padding:0 16px">
<h1>Sayfa şu an hazırlanamadı</h1>
<p>Botlar bundan etkilenmez; yalnız bu sayfa özet çıkaramadı. Bir dakika sonra yeniden dene.
Sorun sürerse şu kimliği Claude'a gönder; ayrıntı sunucunun kaydındadır:</p>
<pre style="white-space:pre-wrap">{hata}</pre></body></html>"""


def isleyici_uret(onbellek: Onbellek):
    guvenlik = guvenlik_basligi()

    class Isleyici(BaseHTTPRequestHandler):
        server_version = "Karabasan"
        sys_version = ""

        def _yanit(self, kod: int, tur: str, govde: bytes, etiket: str | None = None) -> None:
            if etiket and self.headers.get("If-None-Match") == etiket:
                kod, govde = 304, b""
            sikistir = (
                kod == 200 and len(govde) >= SIKISTIRMA_ESIGI
                and "gzip" in (self.headers.get("Accept-Encoding") or "")
            )
            if sikistir:
                govde = gzip.compress(govde, compresslevel=6)
            self.send_response(kod)
            if kod != 304:
                self.send_header("Content-Type", tur)
            self.send_header("Content-Length", str(len(govde)))
            if sikistir:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
            self.send_header("Cache-Control", "private, no-cache")
            if etiket:
                self.send_header("ETag", etiket)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Content-Security-Policy", guvenlik)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(govde)

        def do_GET(self) -> None:  # noqa: N802 - http.server böyle adlandırır
            yol = self.path.split("?", 1)[0]
            try:
                if yol == "/saglik":
                    yas = onbellek.yas_saniye()
                    if yas is None:
                        try:
                            onbellek.ozet()
                            yas = onbellek.yas_saniye()
                        except Exception:  # noqa: BLE001
                            self._yanit(503, "text/plain; charset=utf-8",
                                        "özet çıkarılamadı\n".encode("utf-8"))
                            return
                    metin = f"tamam\nözet {int(yas)} sn önce\n"
                    if onbellek.son_hata:
                        metin += "son deneme başarısız; eski özet sunuluyor\n"
                    self._yanit(200, "text/plain; charset=utf-8", metin.encode("utf-8"))
                elif yol == "/veri.json":
                    govde = json.dumps(json_icin(onbellek.ozet()), ensure_ascii=False, indent=1)
                    self._yanit(200, "application/json; charset=utf-8", govde.encode("utf-8"))
                elif yol == "/defter":
                    from . import defter_sayfa

                    ozet = defter_sayfa.ozet_cikar(onbellek.klasor / "kayit" / "defter.sqlite")
                    self._yanit(200, "text/html; charset=utf-8", defter_sayfa.html_uret(ozet).encode("utf-8"))
                elif yol in ("/", "/index.html"):
                    govde, etiket = onbellek.html()
                    self._yanit(200, "text/html; charset=utf-8", govde, etiket)
                else:
                    self._yanit(404, "text/plain; charset=utf-8", "Böyle bir sayfa yok.\n".encode("utf-8"))
            except Exception:  # noqa: BLE001 - sayfa her durumda bir yanıt vermeli
                kimlik = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
                gunluk.exception("Sayfa hazırlanamadı (kimlik %s)", kimlik)
                govde = HATA_SAYFASI.format(hata=kimlik)
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
