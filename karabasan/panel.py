"""Sonuç sayfası sunucusu.

Tek iş yapar: karabasan.sonuc özetini karabasan.sayfa ile HTML'e çevirip
sunar. Salt okunurdur; hiçbir ayarı değiştirmez, hiçbir botu yönetmez.

    python3 -m karabasan.panel

Adresler:
    /            Pano (karabasan.pano): Sonuçlar (bütün ekranlar), Uzay, ayar ve geçmiş test, ajan; /pano aynı
    /klasik      Türkçe sonuç sayfası tek başına; ?gomulu=1 panonun Sonuçlar sekmesindeki hali
    /s/, /api/   Panonun dosyaları ve veri adresleri (karabasan.pano)
    /veri.json   Aynı özetin ham hali
    /saglik      Sunucu ayakta mı (izleme için)
    /defter      Emir defteri denemesinin özeti (BTC/USDT vadeli, sanal)
    /islem       Tek bir işlemin fiyat grafiği (?bot=<bot adı>&id=<işlem kimliği>)
    /detay       Bot detayı: işlem listesi, oranlar, günlük bütçe kullanımı (?bot=<bot adı>)
    /sagla       Sağlama: kâr rakamını kayıt ve emirlerden baştan hesaplayıp denetler (?mum=1: Binance mumlarıyla da)
    /coinler     Binance coin listesi: stable olmayanlar, hacim sınırını geçenler (?hacim=<milyon USDT>)
    /ayar        Kriter ayar laboratuvarı: geçmişe sarıp kriter sayılarını denemek (kaydetmez)

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
import urllib.parse
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
        self._html: dict = {}
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

    def html(self, gomulu: bool = False) -> tuple[bytes, str]:
        """(sayfa baytları, ETag). Özet değişmedikçe aynı baytlar döner. gomulu: panonun Sonuçlar sekmesindeki hali."""
        self.ozet()
        with self._kilit:
            eldeki = self._html.get(gomulu)
            if eldeki is None or eldeki[0] != self._surum:
                govde = html_uret(self._ozet, yenile_saniye=YENILE_SANIYE, gomulu=gomulu).encode("utf-8")
                etiket = '"' + hashlib.sha256(govde).hexdigest()[:20] + '"'
                eldeki = self._html[gomulu] = (self._surum, govde, etiket)
            return eldeki[1], eldeki[2]


HATA_SAYFASI = """<!doctype html><html lang="tr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Karabasan</title><body style="font:16px/1.5 system-ui,sans-serif;max-width:40em;margin:2em auto;padding:0 16px">
<h1>Sayfa şu an hazırlanamadı</h1>
<p>Botlar bundan etkilenmez; yalnız bu sayfa özet çıkaramadı. Bir dakika sonra yeniden dene.
Sorun sürerse şu kimliği Claude'a gönder; ayrıntı sunucunun kaydındadır:</p>
<pre style="white-space:pre-wrap">{hata}</pre></body></html>"""


def isleyici_uret(onbellek: Onbellek, pano_ayari: dict | None = None):
    from . import islem_grafik
    from . import pano as _pano

    guvenlik = guvenlik_basligi()
    from . import ayar_kayit

    ayar_deposu = ayar_kayit.Depo(onbellek.klasor)
    pano_ayari = dict(pano_ayari or {})
    arka_plan = pano_ayari.pop("arka_plan", False)
    # Yeni pano açılamazsa (örneğin sunucuda beklenmeyen bir eksik) site kapanmaz: ana sayfa eski sayfaya döner.
    try:
        pano = _pano.Pano(onbellek, ayar_deposu, **pano_ayari)
        if arka_plan:
            pano.arka_planda_isit()
    except Exception:  # noqa: BLE001
        gunluk.exception("Yeni pano açılamadı; ana sayfada eski sayfa sunuluyor")
        pano = None
    mum_onbellegi = islem_grafik.MumOnbellegi()

    class Isleyici(BaseHTTPRequestHandler):
        server_version = "Karabasan"
        sys_version = ""

        def _yanit(self, kod: int, tur: str, govde: bytes, etiket: str | None = None,
                   izin: str | None = None, cerceve: bool = False) -> None:
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
            # cerceve: yalnız bu sitenin kendi panosu içinde (aynı köken) açılabilir.
            self.send_header("X-Frame-Options", "SAMEORIGIN" if cerceve else "DENY")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            izin = izin or guvenlik
            if cerceve:
                izin = izin.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
            self.send_header("Content-Security-Policy", izin)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(govde)

        def do_GET(self) -> None:  # noqa: N802 - http.server böyle adlandırır
            yol = self.path.split("?", 1)[0]
            try:
                # 10 Kasım 2026 akşamı (Ahmet: "eski ile yeni formatın hepsini bütün yap, yeni formatta"): ana sayfa
                # panodur ve ilk sekmesi "Sonuçlar" bütün eski ve yeni ekranları gösterir. Pano açılamazsa eski sayfa.
                if yol in ("/", "/index.html") and pano is None:
                    yol = "/klasik"
                if yol.startswith(("/s/", "/api/")) or yol in ("/", "/index.html", "/pano"):
                    sorgu = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "",
                                                  max_num_fields=20)
                    if pano is not None:
                        kod, tur, govde, etiket = pano.get(yol, sorgu)
                        self._yanit(kod, tur, govde, etiket, izin=_pano.GUVENLIK)
                        return
                    self._yanit(503, "text/plain; charset=utf-8", "Yeni pano şu an açılamadı.\n".encode("utf-8"))
                    return
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
                elif yol == "/islem":
                    sorgu = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                    bot = (sorgu.get("bot") or [""])[0]
                    kimlik = (sorgu.get("id") or [""])[0]
                    if islem_grafik.bot_bul(bot) is None or not kimlik.isdigit() or len(kimlik) > 12:
                        self._yanit(404, "text/plain; charset=utf-8", "Böyle bir işlem yok.\n".encode("utf-8"))
                    else:
                        govde = islem_grafik.islem_sayfasi(onbellek.klasor, bot, int(kimlik), mum_onbellegi)
                        self._yanit(200, "text/html; charset=utf-8", govde.encode("utf-8"))
                elif yol == "/detay":
                    from . import detay

                    sorgu = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                    bot = (sorgu.get("bot") or [""])[0][:40]
                    govde = detay.sayfa_uret(bot, onbellek.klasor)
                    self._yanit(200, "text/html; charset=utf-8", govde.encode("utf-8"))
                elif yol == "/sagla":
                    from . import saglama

                    sorgu = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "",
                                                  max_num_fields=5)
                    mum_fn = None
                    if (sorgu.get("mum") or [""])[0] == "1":
                        mum_fn = islem_grafik.mum_getir
                    ozet = onbellek.ozet()
                    uret = lambda: saglama.genel(onbellek.klasor, ozet, mum_fn)  # noqa: E731
                    sonuc = saglama.mum_sonucu_onbellekli(uret) if mum_fn else uret()
                    self._yanit(200, "text/html; charset=utf-8", saglama.sayfa_uret(sonuc).encode("utf-8"),
                                izin=saglama.guvenlik_basligi())
                elif yol == "/coinler":
                    from . import coinler

                    sorgu = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "",
                                                  max_num_fields=10)
                    self._yanit(200, "text/html; charset=utf-8", coinler.sayfa_uret(sorgu).encode("utf-8"),
                                izin=coinler.guvenlik_basligi())
                elif yol == "/ayar":
                    from . import ayar_sayfa

                    sorgu = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "",
                                                  max_num_fields=120)
                    istek = ayar_sayfa.sorgu_coz(sorgu)
                    if (sorgu.get("json") or [""])[0] == "1":
                        self._yanit(200, "application/json; charset=utf-8",
                                    ayar_sayfa.ayar_json(istek, depo=ayar_deposu).encode("utf-8"),
                                    izin=ayar_sayfa.guvenlik_basligi())
                    else:
                        govde = ayar_sayfa.ayar_sayfasi(istek, depo=ayar_deposu)
                        self._yanit(200, "text/html; charset=utf-8", govde.encode("utf-8"),
                                    izin=ayar_sayfa.guvenlik_basligi())
                elif yol == "/klasik":
                    gomulu = "gomulu=1" in (self.path.split("?", 1)[1] if "?" in self.path else "").split("&")
                    govde, etiket = onbellek.html(gomulu)
                    self._yanit(200, "text/html; charset=utf-8", govde, etiket, cerceve=gomulu)
                else:
                    self._yanit(404, "text/plain; charset=utf-8", "Böyle bir sayfa yok.\n".encode("utf-8"))
            except Exception:  # noqa: BLE001 - sayfa her durumda bir yanıt vermeli
                kimlik = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
                gunluk.exception("Sayfa hazırlanamadı (kimlik %s)", kimlik)
                govde = HATA_SAYFASI.format(hata=kimlik)
                self._yanit(500, "text/html; charset=utf-8", govde.encode("utf-8"))

        do_HEAD = do_GET  # noqa: N815

        def do_POST(self) -> None:  # noqa: N802
            """Yazma yolları: /ayar/kayit (eski ayar sayfasının kayıtları) ve panonun /api/ adresleri
            (geçmiş testi başlatma, kayıt, ajana soru, ajan anahtarı). Hiçbiri canlı bota dokunmaz."""
            yol = self.path.split("?", 1)[0]
            try:
                if yol.startswith("/api/") and pano is None:
                    self._yanit(503, "text/plain; charset=utf-8", "Yeni pano şu an açılamadı.\n".encode("utf-8"))
                    return
                if yol.startswith("/api/"):
                    if self.headers.get("X-Karabasan") != "1":
                        self._yanit(403, "text/plain; charset=utf-8", "İstek reddedildi.\n".encode("utf-8"))
                        return
                    try:
                        uzunluk = int(self.headers.get("Content-Length") or 0)
                    except ValueError:
                        uzunluk = -1
                    if not 0 < uzunluk <= _pano.EN_FAZLA_GOVDE:
                        self._yanit(413, "text/plain; charset=utf-8", "İstek çok büyük.\n".encode("utf-8"))
                        return
                    kod, tur, govde, etiket = pano.post(yol, self.rfile.read(uzunluk))
                    self._yanit(kod, tur, govde, etiket, izin=_pano.GUVENLIK)
                    return
                if yol != "/ayar/kayit":
                    self._yanit(405, "text/plain; charset=utf-8", "Bu adres yalnız okunur.\n".encode("utf-8"))
                    return
                # Başka bir sitenin formu bu başlığı gönderemez (tarayıcı önce izin sorar, sunucu vermez).
                if self.headers.get("X-Karabasan") != "1":
                    self._yanit(403, "text/plain; charset=utf-8", "İstek reddedildi.\n".encode("utf-8"))
                    return
                try:
                    uzunluk = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    uzunluk = -1
                if not 0 < uzunluk <= 8192:
                    self._yanit(413, "text/plain; charset=utf-8", "İstek çok büyük.\n".encode("utf-8"))
                    return
                from . import ayar_sayfa

                alanlar = urllib.parse.parse_qs(self.rfile.read(uzunluk).decode("utf-8", "replace"),
                                                max_num_fields=140)
                istek = ayar_sayfa.sorgu_coz(alanlar)
                tek = lambda ad: (alanlar.get(ad) or [""])[0]  # noqa: E731
                sonuc = ayar_sayfa.kayit_islemi(ayar_deposu, istek, tek("eylem")[:12], tek("kimlik")[:12], tek("ad")[:200])
                self._yanit(200, "application/json; charset=utf-8", json.dumps(sonuc, ensure_ascii=False).encode("utf-8"),
                            izin=ayar_sayfa.guvenlik_basligi())
            except Exception:  # noqa: BLE001
                gunluk.exception("Ayar kaydı işlenemedi")
                self._yanit(500, "text/plain; charset=utf-8", "Kayıt işlenemedi.\n".encode("utf-8"))

        def log_message(self, bicim, *degerler) -> None:
            gunluk.debug("%s %s", self.address_string(), bicim % degerler)

    return Isleyici


def sunucu_kur(klasor: Path, adres: str = "0.0.0.0", port: int = 8080, pano_ayari: dict | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((adres, port), isleyici_uret(Onbellek(klasor), pano_ayari))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    port = int(os.environ.get("KARABASAN_PANEL_PORT", "8080"))
    # Likidite ekranı: Binance'in herkese açık vadeli verisini yalnız panel süreci, arka planda çeker.
    try:
        from . import sonuc_likidite

        sonuc_likidite.ag_ac()
    except Exception:  # noqa: BLE001 - likidite açılamazsa sayfa yine çalışır
        gunluk.exception("Likidite verisi açılamadı")
    sunucu = sunucu_kur(veri_klasoru(), port=port, pano_ayari={"arka_plan": True})
    gunluk.info("Sonuç sayfası %s numaralı kapıda hazır.", port)
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
