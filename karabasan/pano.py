"""Yeni pano ("Karabasan Uzayı"): sayfa dosyaları ve /api/ adresleri (10 Kasım 2026, Ahmet'in isteği).

Sayfanın kendisi karabasan/statik/ altındaki durağan dosyalardır (pano.html, pano.css, pano.js, three.min.js,
yazı tipi). Tarayıcı yalnız bu sunucudan betik ve biçim yükleyebilir (izin başlığı aşağıda); dış kaynak yoktur.

Okuma adresleri (GET):
    /                  pano
    /s/<dosya>         durağan dosyalar
    /api/ozet          canlı botların kısa özeti (bot tablosu, gün gün, açık işlemler)
    /api/bot           bir botun bütün ayarlanabilir sayıları, şartları, kayıtları, test seçenekleri
    /api/uzay          coinlerin girişe uzaklığı (istenirse denenen ayarla)
    /api/test          bir geçmiş testin durumu / sonucu
    /api/ajan          bir sorunun durumu / yanıtı;  /api/ajan/durum, /api/ajan/gecmis, /api/ajan/arsiv
Yazma adresleri (POST, JSON, "X-Karabasan: 1" başlığı zorunlu):
    /api/test          geçmiş testi başlatır (yalnız hesap; hiçbir şeyi değiştirmez)
    /api/kayit         ayar laboratuvarının adlı kayıtları (canlı botu değiştirmez)
    /api/ajan          ajana soru
    /api/ajan/anahtar  ajanın Anthropic anahtarını kaydeder / siler (yalnız sunucudaki gizli dosyaya)

Hiçbir adres canlı botların ayarını, kural dosyalarını ya da borsayı etkilemez.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from . import ajan as _ajan
from .sonuc import json_icin

STATIK = Path(__file__).resolve().parent / "statik"
TURLER = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
          ".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8"}
GUVENLIK = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
EN_FAZLA_GOVDE = 32768
JSON_TURU = "application/json; charset=utf-8"


class IstekHatasi(ValueError):
    def __init__(self, ileti: str, kod: int = 400):
        super().__init__(ileti)
        self.kod = kod


def _json(veri, kod: int = 200):
    return kod, JSON_TURU, json.dumps(veri, ensure_ascii=False, default=str).encode("utf-8"), None


class Pano:
    def __init__(self, onbellek, ayar_deposu, getir=None, saat=None, cagir=None, oku=None):
        from . import gecmis_test, uzay

        self.onbellek = onbellek
        self.kayitlar = ayar_deposu
        self.uzay = uzay.UzayServisi(getir, saat)
        self.testler = gecmis_test.TestYoneticisi(onbellek.klasor, getir, oku)
        ek = {"cagir": cagir} if cagir else {}
        self.ajan = _ajan.Ajan(onbellek.klasor, ozet_al=lambda: json_icin(onbellek.ozet()), testler=self.testler,
                               uzay=self.uzay, kayitlar=ayar_deposu, saat=saat, **ek)
        self._dosyalar: dict[str, tuple[float, bytes, str]] = {}
        self._kilit = threading.Lock()

    def arka_planda_isit(self) -> None:
        threading.Thread(target=self.uzay.isit, daemon=True, name="uzay-isit").start()

    # -- durağan dosyalar -----------------------------------------------------
    def _dosya(self, ad: str):
        yol = STATIK / ad
        if "/" in ad or "\\" in ad or ad.startswith(".") or yol.suffix not in TURLER or not yol.is_file():
            return None
        damga = yol.stat().st_mtime
        with self._kilit:
            eldeki = self._dosyalar.get(ad)
            if not eldeki or eldeki[0] != damga:
                govde = yol.read_bytes()
                eldeki = (damga, govde, '"' + hashlib.sha256(govde).hexdigest()[:20] + '"')
                self._dosyalar[ad] = eldeki
        return 200, TURLER[yol.suffix], eldeki[1], eldeki[2]

    # -- GET -------------------------------------------------------------------
    def get(self, yol: str, sorgu: dict):
        """(kod, tür, gövde, etiket) ya da bu sınıfın bilmediği adres için None."""
        tek = lambda ad, sinir=64: (sorgu.get(ad) or [""])[0][:sinir]  # noqa: E731
        if yol in ("/", "/index.html", "/pano"):
            return self._dosya("pano.html")
        if yol.startswith("/s/"):
            return self._dosya(yol[3:]) or (404, "text/plain; charset=utf-8", "Böyle bir dosya yok.\n".encode("utf-8"), None)
        if not yol.startswith("/api/"):
            return None
        try:
            return self._api_get(yol, tek, sorgu)
        except IstekHatasi as hata:
            return _json({"hata": str(hata)}, hata.kod)
        except Exception as hata:  # noqa: BLE001
            from . import ayar, gecmis_test

            if isinstance(hata, (ayar.AyarHatasi, gecmis_test.TestHatasi, _ajan.AjanHatasi)):
                return _json({"hata": str(hata)}, 400)
            raise

    def _api_get(self, yol: str, tek, sorgu: dict):
        from . import gecmis_test, uzay

        if yol == "/api/ozet":
            ozet = json_icin(self.onbellek.ozet())
            kisa = _ajan.canli_ozeti(ozet)
            kisa["gunluk"] = [{k: g.get(k) for k in ("gun", "islem", "kazanan", "net_tutar")} for g in ozet.get("gunluk_toplam", [])[-35:]]
            kisa["uretildi"] = ozet.get("uretildi")
            return _json(kisa)
        if yol == "/api/bot":
            bot = tek("bot")
            if bot not in uzay.bot_adlari():
                raise IstekHatasi("Böyle bir bot yok.", 404)
            sema = uzay.bot_semasi(bot)
            sema.update(botlar=uzay.bot_adlari(), kayitlar=self.kayitlar.listele(bot),
                        hazir_coinler=self.testler.hazir_coinler(), uzay_coinleri=uzay.COINLER,
                        donemler=list(gecmis_test.GUNLER), indirme_siniri=gecmis_test.INDIRME_SINIRI_GUN)
            return _json(sema)
        if yol == "/api/uzay":
            ayar = self._ayar_coz((sorgu.get("ayar") or [""])[0][:6000])
            return _json(self.uzay.al(tek("bot"), ayar.get("degerler"), ayar.get("pasif")))
        if yol == "/api/test":
            durum = self.testler.durum(tek("id", 24))
            if durum is None:
                raise IstekHatasi("Böyle bir test yok (sayfa yenilenmiş olabilir); yeniden çalıştır.", 404)
            return _json(durum)
        if yol == "/api/ajan":
            durum = self.ajan.is_durumu(tek("id", 24))
            if durum is None:
                raise IstekHatasi("Böyle bir soru yok.", 404)
            return _json(durum)
        if yol == "/api/ajan/durum":
            return _json(self.ajan.durum())
        if yol == "/api/ajan/gecmis":
            return _json({"mesajlar": self.ajan.arsiv.mesajlar(60)})
        if yol == "/api/ajan/arsiv":
            gun = tek("gun", 12)
            if gun:
                metin = self.ajan.arsiv.gun_oku(gun)
                if metin is None:
                    raise IstekHatasi("O güne ait kayıt yok.", 404)
                return _json({"gun": gun, "metin": metin})
            return _json({"gunler": self.ajan.arsiv.gunler(), "dersler": self.ajan.arsiv.dersler()})
        raise IstekHatasi("Böyle bir adres yok.", 404)

    @staticmethod
    def _ayar_coz(metin: str) -> dict:
        if not metin:
            return {}
        try:
            veri = json.loads(metin)
        except ValueError:
            raise IstekHatasi("Ayar okunamadı.") from None
        if not isinstance(veri, dict):
            raise IstekHatasi("Ayar okunamadı.")
        degerler = veri.get("degerler") if isinstance(veri.get("degerler"), dict) else {}
        pasif = veri.get("pasif") if isinstance(veri.get("pasif"), list) else []
        return {"degerler": {str(k)[:80]: v for k, v in list(degerler.items())[:80] if isinstance(v, (int, float, str))},
                "pasif": [str(p)[:40] for p in pasif[:40]]}

    # -- POST ------------------------------------------------------------------
    def post(self, yol: str, ham: bytes):
        """(kod, tür, gövde, etiket) ya da bilinmeyen adres için None."""
        if not yol.startswith("/api/"):
            return None
        from . import ayar, ayar_kayit, gecmis_test

        try:
            try:
                veri = json.loads(ham.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise IstekHatasi("İstek okunamadı.") from None
            if not isinstance(veri, dict):
                raise IstekHatasi("İstek okunamadı.")
            a = self._ayar_coz(json.dumps(veri))
            bot = str(veri.get("bot", ""))[:64]
            if yol == "/api/test":
                kimlik = self.testler.baslat(bot, a.get("degerler"), a.get("pasif"), veri.get("coinler") if isinstance(veri.get("coinler"), list) else [],
                                             veri.get("gun"))
                return _json({"id": kimlik})
            if yol == "/api/kayit":
                return _json(self._kayit(veri, bot, a))
            if yol == "/api/ajan":
                baglam = veri.get("baglam") if isinstance(veri.get("baglam"), dict) else {}
                return _json({"id": self.ajan.sor(veri.get("mesaj", ""), baglam)})
            if yol == "/api/ajan/anahtar":
                if veri.get("sil") is True:
                    _ajan.anahtar_sil(self.onbellek.klasor)
                else:
                    _ajan.anahtar_yaz(self.onbellek.klasor, veri.get("anahtar", ""))
                return _json(self.ajan.durum())
            raise IstekHatasi("Bu adres yalnız okunur.", 405)
        except IstekHatasi as hata:
            return _json({"hata": str(hata)}, hata.kod)
        except (ayar.AyarHatasi, ayar_kayit.KayitHatasi, gecmis_test.TestHatasi, _ajan.AjanHatasi) as hata:
            return _json({"hata": str(hata)}, 400)

    def _kayit(self, veri: dict, bot: str, a: dict) -> dict:
        from . import ayar_kayit, uzay

        if bot not in uzay.bot_adlari():
            raise IstekHatasi("Böyle bir bot yok.", 404)
        eylem = str(veri.get("eylem", ""))
        kimlik = str(veri.get("kimlik", ""))[:12]
        ad = str(veri.get("ad", ""))[:200]
        if eylem in ("kaydet", "ustune"):
            _canli, _kural, temiz = uzay.kural_kur(bot, a.get("degerler"), a.get("pasif"))   # geçersiz ayar kaydedilmez
            kayit = self.kayitlar.kaydet(bot, ad, temiz["degerler"], temiz["pasif"], kimlik=kimlik if eylem == "ustune" else None)
        elif eylem == "adlandir":
            kayit = self.kayitlar.adlandir(kimlik, ad)
        elif eylem == "sil":
            self.kayitlar.sil(kimlik)
            kayit = None
        else:
            raise ayar_kayit.KayitHatasi("Bilinmeyen işlem.")
        return {"kayit": kayit, "kayitlar": self.kayitlar.listele(bot)}
