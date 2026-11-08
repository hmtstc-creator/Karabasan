"""Kriter ayar laboratuvarının kayıtları (9 Kasım 2026, Ahmet'in isteği).

Her kayıt bir botun o andaki bütün sayılarını, hangi şartların / parçaların pasif olduğunu ve
bir adı taşır; ad sonradan değiştirilebilir. Kayıtlar yalnız bu sayfadaki denemelerdir:
canlı kural dosyaları ve botlar değişmez (3. kural). Güzel görünen bir kayıt yalnız öneridir.

Dosya: user_data/kayit/ayar_kayitlari.json (yalnız standart kütüphane; atomik yazılır).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import botlar as _botlar

DOSYA = Path("kayit") / "ayar_kayitlari.json"
EN_FAZLA_AD = 60
EN_FAZLA_KAYIT_BOT_BASINA = 200
EN_FAZLA_SAYI = 80
_YOL = re.compile(r"^[A-Za-z0-9_.]{1,80}$")
_ANAHTAR = re.compile(r"^[A-Za-z0-9_]{1,40}$")
_KIMLIK = re.compile(r"^[0-9a-f]{8}$")


class KayitHatasi(ValueError):
    """Kullanıcıya olduğu gibi gösterilebilen düz Türkçe hata."""


def ad_temizle(ad: str) -> str:
    ad = " ".join(str(ad or "").split())
    ad = "".join(c for c in ad if c.isprintable())[:EN_FAZLA_AD].strip()
    if not ad:
        raise KayitHatasi("Kayda bir ad ver.")
    return ad


class Depo:
    def __init__(self, klasor: Path):
        self.yol = Path(klasor) / DOSYA
        self._kilit = threading.Lock()

    # -- okuma / yazma -----------------------------------------------------
    def _oku(self) -> list[dict]:
        try:
            veri = json.loads(self.yol.read_text(encoding="utf-8"))
            kayitlar = veri.get("kayitlar", [])
            return [k for k in kayitlar if isinstance(k, dict) and _KIMLIK.match(str(k.get("id", "")))]
        except FileNotFoundError:
            return []
        except (OSError, ValueError, AttributeError):
            # Bozuk dosya: üstüne yazmadan önce yanına alınır, kayıtlar kaybolmasın.
            try:
                os.replace(self.yol, self.yol.with_suffix(".bozuk"))
            except OSError:
                pass
            return []

    def _yaz(self, kayitlar: list[dict]) -> None:
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        govde = json.dumps({"surum": 1, "kayitlar": kayitlar}, ensure_ascii=False, indent=1)
        gecici = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.yol.parent, delete=False,
                                             prefix=".ayar_kayit_", suffix=".tmp")
        try:
            with gecici:
                gecici.write(govde)
            os.replace(gecici.name, self.yol)
        except OSError:
            try:
                os.unlink(gecici.name)
            except OSError:
                pass
            raise KayitHatasi("Kayıt dosyasına yazılamadı. Biraz sonra yeniden dene.") from None

    # -- işlemler ----------------------------------------------------------
    def listele(self, bot: str) -> list[dict]:
        with self._kilit:
            return sorted((k for k in self._oku() if k.get("bot") == bot),
                          key=lambda k: k.get("guncelleme", ""), reverse=True)

    def getir(self, kimlik: str) -> dict | None:
        if not _KIMLIK.match(str(kimlik or "")):
            return None
        with self._kilit:
            for k in self._oku():
                if k["id"] == kimlik:
                    return k
        return None

    def kaydet(self, bot: str, ad: str, degerler: dict, pasif, bakis: dict | None = None,
               kimlik: str | None = None, simdi: datetime | None = None) -> dict:
        """Yeni kayıt açar; `kimlik` verilirse o kaydın değerlerini günceller (adı yalnız ad verilmişse değişir)."""
        if bot not in {b[0] for b in _botlar.BOTLAR}:
            raise KayitHatasi("Böyle bir bot yok.")
        temiz = {}
        for yol, deger in dict(degerler).items():
            if not _YOL.match(str(yol)) or len(temiz) >= EN_FAZLA_SAYI:
                continue
            try:
                temiz[str(yol)] = float(deger) if not float(deger).is_integer() else int(float(deger))
            except (TypeError, ValueError, OverflowError):
                raise KayitHatasi("Kaydedilecek sayılardan biri geçersiz.") from None
        pasif = sorted({str(p) for p in pasif if _ANAHTAR.match(str(p))})[:40]
        bakis = {k: bakis[k] for k in ("coin", "gun", "once") if bakis and k in bakis}
        an = (simdi or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._kilit:
            kayitlar = self._oku()
            if kimlik:
                for k in kayitlar:
                    if k["id"] == kimlik and k.get("bot") == bot:
                        k.update(degerler=temiz, pasif=pasif, bakis=bakis, guncelleme=an)
                        if ad:
                            k["ad"] = ad_temizle(ad)
                        self._yaz(kayitlar)
                        return k
                raise KayitHatasi("Üstüne yazılacak kayıt bulunamadı.")
            if sum(1 for k in kayitlar if k.get("bot") == bot) >= EN_FAZLA_KAYIT_BOT_BASINA:
                raise KayitHatasi(f"Bir bot için en çok {EN_FAZLA_KAYIT_BOT_BASINA} kayıt tutulur; eskileri sil.")
            kayit = {"id": secrets.token_hex(4), "bot": bot, "ad": ad_temizle(ad), "olusturma": an,
                     "guncelleme": an, "degerler": temiz, "pasif": pasif, "bakis": bakis}
            kayitlar.append(kayit)
            self._yaz(kayitlar)
            return kayit

    def adlandir(self, kimlik: str, ad: str) -> dict:
        ad = ad_temizle(ad)
        with self._kilit:
            kayitlar = self._oku()
            for k in kayitlar:
                if k["id"] == kimlik:
                    k["ad"] = ad
                    self._yaz(kayitlar)
                    return k
        raise KayitHatasi("Kayıt bulunamadı.")

    def sil(self, kimlik: str) -> None:
        with self._kilit:
            kayitlar = self._oku()
            kalan = [k for k in kayitlar if k["id"] != kimlik]
            if len(kalan) == len(kayitlar):
                raise KayitHatasi("Kayıt bulunamadı.")
            self._yaz(kalan)
