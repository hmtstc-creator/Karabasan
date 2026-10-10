"""Haberci: Telegram üzerinden bildirim ve komutlar.

Ahmet sunucuyu yalnız telefondan yönetir. Bu modül üç iş yapar:

1. Kurulum ve güncelleme betiklerinin ilerlemeyi Telegram'a yazmasını sağlar.
2. Günde bir kez özet gönderir, bir bot susarsa haber verir.
3. Telefondan yazılan komutlara yanıt verir (/durum, /gunluk, /uyum ...).

Komutların hiçbiri borsaya emir göndermez, botların ayarını değiştirmez ve
sunucuda serbest komut çalıştırmaz. Yalnız kayıt sahibi olan sohbet dinlenir.

Tek istisna /claude komutudur: sunucudaki betiğe bir istek dosyası bırakır
(giriş bağlantısı iste, ya da tek kullanımlık giriş kodunu ilet). Dosyanın
içeriği komut olarak çalıştırılmaz; ayrıntı araclar/claude_sunucu.sh içinde.

Kullanım:

    python3 -m karabasan.haberci gonder "metin"     tek mesaj
    python3 -m karabasan.haberci belge DOSYA [not]  dosya gönder
    python3 -m karabasan.haberci bekle 600          sahibin /start yazmasını bekle
    python3 -m karabasan.haberci servis             sürekli çalışan servis

Kod (token) TELEGRAM_TOKEN ortam değişkeninden okunur ve hiçbir yere yazılmaz.
"gonder", "belge" ve "bekle" yalnız Python standart kütüphanesiyle çalışır;
böylece sunucunun kendi Python'u (pandas olmadan) yeterlidir.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.telegram.org"
MESAJ_SINIRI = 3900  # Telegram sınırı 4096 karakter
SAAT_DILIMI = "Europe/Bucharest"
OZET_SAATI = 9  # yerel saat
ISINMA_GUN = 7
SAYFA_ADRESI = "http://karabasan:8080"

gunluk = logging.getLogger("karabasan.haberci")


class TelegramHatasi(Exception):
    pass


def veri_klasoru() -> Path:
    ortam = os.environ.get("KARABASAN_VERI")
    if ortam:
        return Path(ortam)
    return Path(__file__).resolve().parent.parent / "user_data"


# --------------------------------------------------------------------------
# Telegram ile konuşma
# --------------------------------------------------------------------------


class Telegram:
    def __init__(self, token: str, taban: str | None = None, ac=None):
        if not token:
            raise TelegramHatasi("Telegram kodu (TELEGRAM_TOKEN) tanımlı değil.")
        self._token = token
        # Adres yalnız kurulum provasında (sahte Telegram ile) değiştirilir.
        self._taban = (taban or os.environ.get("KARABASAN_TELEGRAM_ADRESI") or API).rstrip("/")
        self._ac = ac or urllib.request.urlopen

    def _temizle(self, metin: str) -> str:
        """Hata metinlerinde kodun görünmesini önler."""
        return str(metin).replace(self._token, "***")

    def cagir(self, yontem: str, veri: dict | None = None, dosya: tuple | None = None,
              zaman_asimi: float = 20.0):
        """Telegram'ın bir yöntemini çağırır, 'result' alanını döndürür.

        dosya: (alan adı, dosya adı, içerik baytları)
        """
        adres = f"{self._taban}/bot{self._token}/{yontem}"
        veri = {k: v for k, v in (veri or {}).items() if v is not None}
        if dosya is None:
            govde = urllib.parse.urlencode(veri).encode("utf-8")
            baslik = {"Content-Type": "application/x-www-form-urlencoded"}
        else:
            sinir = uuid.uuid4().hex
            parcalar = []
            for ad, deger in veri.items():
                parcalar.append(
                    f'--{sinir}\r\nContent-Disposition: form-data; name="{ad}"\r\n\r\n{deger}\r\n'.encode("utf-8")
                )
            alan, dosya_adi, icerik = dosya
            parcalar.append(
                (
                    f'--{sinir}\r\nContent-Disposition: form-data; name="{alan}"; '
                    f'filename="{dosya_adi}"\r\nContent-Type: application/octet-stream\r\n\r\n'
                ).encode("utf-8")
                + icerik
                + b"\r\n"
            )
            parcalar.append(f"--{sinir}--\r\n".encode("utf-8"))
            govde = b"".join(parcalar)
            baslik = {"Content-Type": f"multipart/form-data; boundary={sinir}"}
        istek = urllib.request.Request(adres, data=govde, headers=baslik, method="POST")
        try:
            with self._ac(istek, timeout=zaman_asimi) as yanit:
                okunan = json.loads(yanit.read().decode("utf-8"))
        except urllib.error.HTTPError as hata:
            try:
                aciklama = json.loads(hata.read().decode("utf-8")).get("description", "")
            except Exception:  # noqa: BLE001
                aciklama = ""
            raise TelegramHatasi(self._temizle(f"Telegram {hata.code} yanıtı verdi. {aciklama}")) from None
        except (urllib.error.URLError, OSError, ValueError) as hata:
            raise TelegramHatasi(self._temizle(f"Telegram'a ulaşılamadı: {hata}")) from None
        if not okunan.get("ok"):
            raise TelegramHatasi(self._temizle(f"Telegram isteği reddetti: {okunan.get('description')}"))
        return okunan.get("result")

    def mesaj(self, sohbet: int, metin: str) -> None:
        for parca in parcala(metin):
            self.cagir(
                "sendMessage",
                {"chat_id": sohbet, "text": parca, "disable_web_page_preview": "true"},
            )

    def belge(self, sohbet: int, dosya_adi: str, icerik: bytes, aciklama: str = "") -> None:
        self.cagir(
            "sendDocument",
            {"chat_id": sohbet, "caption": aciklama[:1000] or None},
            dosya=("document", dosya_adi, icerik),
            zaman_asimi=60.0,
        )

    def guncellemeler(self, sira: int | None = None, bekle: int = 0) -> list:
        return self.cagir(
            "getUpdates",
            {"offset": sira, "timeout": bekle, "allowed_updates": '["message"]'},
            zaman_asimi=bekle + 15.0,
        ) or []


def parcala(metin: str, sinir: int = MESAJ_SINIRI) -> list[str]:
    """Uzun metni satır sonlarından bölerek Telegram sınırına sığdırır."""
    metin = metin.strip() or "(boş)"
    parcalar, kalan = [], metin
    while len(kalan) > sinir:
        kes = kalan.rfind("\n", 0, sinir)
        if kes < sinir // 2:
            kes = sinir
        parcalar.append(kalan[:kes])
        kalan = kalan[kes:].lstrip("\n")
    parcalar.append(kalan)
    return parcalar


# --------------------------------------------------------------------------
# Sahibin kaydı ve bekleyen mesajlar
# --------------------------------------------------------------------------


def sohbet_yolu(klasor: Path) -> Path:
    return klasor / "telegram_sohbet.txt"


def bekleyen_yolu(klasor: Path) -> Path:
    return klasor / "logs" / "bekleyen_mesajlar.txt"


def sohbet_oku(klasor: Path) -> int | None:
    try:
        return int(sohbet_yolu(klasor).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def sohbet_yaz(klasor: Path, sohbet: int) -> None:
    klasor.mkdir(parents=True, exist_ok=True)
    sohbet_yolu(klasor).write_text(f"{int(sohbet)}\n", encoding="utf-8")


def sahibi_bul(guncellemeler: list) -> int | None:
    """Bota özelden /start yazan ilk kişinin sohbet numarası."""
    for g in guncellemeler:
        mesaj = g.get("message") or {}
        sohbet = mesaj.get("chat") or {}
        if sohbet.get("type") == "private" and str(mesaj.get("text", "")).startswith("/start"):
            return int(sohbet["id"])
    return None


def sahibi_ogren(tg: Telegram, klasor: Path, bekle: int = 0) -> int | None:
    """Kayıtlı sohbeti döndürür; yoksa Telegram'a sorup /start yazanı kaydeder."""
    sohbet = sohbet_oku(klasor)
    if sohbet is not None:
        return sohbet
    sohbet = sahibi_bul(tg.guncellemeler(bekle=bekle))
    if sohbet is not None:
        sohbet_yaz(klasor, sohbet)
    return sohbet


def gonder(tg: Telegram, klasor: Path, metin: str) -> bool:
    """Mesajı sahibine yollar. Sahip henüz /start yazmadıysa mesajı sıraya koyar."""
    try:
        sohbet = sahibi_ogren(tg, klasor)
    except TelegramHatasi as hata:
        gunluk.warning("%s", hata)
        sohbet = None
    kuyruk = bekleyen_yolu(klasor)
    if sohbet is None:
        kuyruk.parent.mkdir(parents=True, exist_ok=True)
        with kuyruk.open("a", encoding="utf-8") as dosya:
            dosya.write(metin.strip() + "\n\n")
        return False
    if kuyruk.exists():
        birikmis = kuyruk.read_text(encoding="utf-8").strip()
        kuyruk.unlink()
        if birikmis:
            metin = "Sen yokken olanlar:\n\n" + birikmis + "\n\n" + metin
    tg.mesaj(sohbet, metin)
    return True


def son_satirlar(yol: Path, adet: int) -> str:
    try:
        satirlar = yol.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(satirlar[-adet:])


# --------------------------------------------------------------------------
# Metinler
# --------------------------------------------------------------------------


def _sayi(deger: float, basamak: int = 2) -> str:
    metin = f"{abs(deger):,.{basamak}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if abs(deger) < 0.5 * 10 ** (-basamak):
        return metin
    return ("+" if deger > 0 else "−") + metin


def _donem_satiri(ozet: dict) -> str:
    donem, gun = ozet["donem"], ozet["gun"]
    if donem == "kurulmadi":
        return "Botlar henüz başlamadı."
    if donem == "isinma":
        return f"Isınma dönemi, {gun}. gün. Bu işlemler sınava sayılmıyor."
    if donem == "sinav":
        return f"Sınavın {gun}. günü, {ozet['sinav_gun'] - gun} gün kaldı."
    gecen = [b["bot"] for b in ozet["botlar"] if b.get("karar") == "gecti"]
    if gecen:
        return "Sınav bitti. Yedi ölçütün hepsini geçenler: " + ", ".join(gecen) + "."
    return "Sınav bitti. Hiçbir bot yedi ölçütün hepsini geçemedi."


def durum_metni(ozet: dict, baslik: str = "Karabasan durumu") -> str:
    t = ozet["toplam"]
    satirlar = [
        baslik,
        _donem_satiri(ozet),
        "",
        f"Çalışan bot: {t['calisan_bot']} / {t['bot_sayisi']}",
        f"Kapanan işlem: {t['islem_sayisi']} (son 24 saatte {t['son_24s_islem']})",
        f"Açık pozisyon: {t['acik_pozisyon']}",
        f"Toplam sanal sonuç: {_sayi(t['net_tutar'])} USDT"
        f" (son 24 saatte {_sayi(t['son_24s_net_tutar'])})",
    ]
    islemli = [b for b in ozet["botlar"] if b["islem_sayisi"] > 0]
    if islemli:
        en_iyi = max(islemli, key=lambda b: b["net_tutar"])
        en_kotu = min(islemli, key=lambda b: b["net_tutar"])
        satirlar += ["", f"En iyi: {en_iyi['bot']} {_sayi(en_iyi['net_tutar'])} USDT"]
        if en_kotu is not en_iyi:
            satirlar.append(f"En kötü: {en_kotu['bot']} {_sayi(en_kotu['net_tutar'])} USDT")
    sessiz = [b["bot"] for b in ozet["botlar"] if not b["calisiyor"]]
    if sessiz and ozet["donem"] != "kurulmadi":
        satirlar += ["", "Ses vermeyen botlar: " + ", ".join(sessiz)]
    satirlar += ["", "Hiçbir emir borsaya gitmiyor; hepsi sanal.", f"Ayrıntı: {SAYFA_ADRESI} (Tailscale açıkken) ya da /sayfa"]
    return "\n".join(satirlar)


def botlar_metni(ozet: dict) -> str:
    satirlar = ["Botlar (işlem sayısı, kazanma oranı, net sonuç)", ""]
    for b in ozet["botlar"]:
        if b["islem_sayisi"]:
            oran = f"%{b['kazanma_orani']:.0f}"
            sonuc = f"{b['islem_sayisi']} işlem, {oran} kazanma, {_sayi(b['net_tutar'])} USDT"
        else:
            sonuc = "henüz kapanan işlem yok"
        durum = "" if b["calisiyor"] else " (ses yok)"
        satirlar.append(f"{b['bot']}{durum}: {sonuc}")
    return "\n".join(satirlar)


YARDIM = """Karabasan komutları

/durum  Genel durum: kaç bot çalışıyor, kaç işlem, toplam sonuç
/botlar  Her botun sonucu
/sayfa  Sonuç sayfasını dosya olarak gönderir
/gunluk  Botların son kayıt satırları (sorun olursa Claude'a iletmek için)
/gunluk s1-spot  Tek bir botun kayıtları
/uyum  Uyum denemesi raporu
/kurulum  Kurulum kaydı
/sinav_baslat  30 günlük sınavın saatini başlatır
/claude  Sunucudaki Claude'un durumu; giriş yapılmadıysa giriş bağlantısı ister
/yardim  Bu liste

Hiçbir komut borsaya emir göndermez, botların ayarını değiştirmez."""

HOSGELDIN = """Merhaba, ben Karabasan sunucusuyum. Seni sahibim olarak kaydettim; bundan sonra yalnız seni dinlerim.

Her sabah 09:00'da kısa bir özet yollarım. Bir bot susarsa haber veririm.

Komutları görmek için /yardim yaz."""


# --------------------------------------------------------------------------
# Servis
# --------------------------------------------------------------------------


def yerel_saat(simdi: datetime) -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return simdi.astimezone(ZoneInfo(SAAT_DILIMI))
    except Exception:  # noqa: BLE001 - saat dilimi verisi yoksa UTC+3 varsay
        return simdi.astimezone(timezone(timedelta(hours=3)))


class Servis:
    def __init__(self, tg: Telegram, klasor: Path, simdi=None, ozet_al=None):
        self.tg = tg
        self.klasor = klasor
        self._simdi = simdi or (lambda: datetime.now(timezone.utc))
        self._ozet_al = ozet_al
        self.durum = {"sira": None, "son_ozet_gunu": None, "sessiz": []}
        self._durum_oku()

    # --- kalıcı durum ---
    def _durum_yolu(self) -> Path:
        return self.klasor / "haberci.json"

    def _durum_oku(self) -> None:
        try:
            self.durum.update(json.loads(self._durum_yolu().read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def _durum_yaz(self) -> None:
        try:
            self._durum_yolu().write_text(json.dumps(self.durum, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as hata:
            gunluk.warning("Durum dosyası yazılamadı: %s", hata)

    def ozet(self) -> dict:
        if self._ozet_al is not None:
            return self._ozet_al()
        from .sonuc import genel_ozet  # pandas ister; yalnız serviste gerekir

        return genel_ozet(self.klasor, self._simdi())

    # --- komutlar ---
    def komut(self, metin: str) -> list[tuple]:
        """Bir komutu işler. Dönen liste: ("mesaj", metin) ya da ("belge", ad, bayt, not)."""
        parcalar = metin.strip().split()
        ad = parcalar[0].split("@")[0].lower() if parcalar else ""
        ek = parcalar[1:] if parcalar else []
        if ad in ("/start", "/yardim", "/help"):
            return [("mesaj", YARDIM)]
        if ad == "/durum":
            return [("mesaj", durum_metni(self.ozet()))]
        if ad == "/botlar":
            return [("mesaj", botlar_metni(self.ozet()))]
        if ad == "/sayfa":
            from .sayfa import html_uret

            sayfa = html_uret(self.ozet(), yenile_saniye=0).encode("utf-8")
            return [("belge", "karabasan-sonuc.html", sayfa,
                     "Sonuç sayfası. Dosyaya dokun, tarayıcıda aç.")]
        if ad == "/gunluk":
            return self._gunluk(ek)
        if ad == "/uyum":
            return self._dosya("uyum_denemesi.txt", "Uyum denemesi raporu", 2000,
                               "Uyum denemesi henüz çalışmadı.")
        if ad == "/kurulum":
            return self._dosya("kurulum.txt", "Kurulum kaydı (son satırlar)", 400,
                               "Kurulum kaydı bulunamadı.")
        if ad == "/sinav_baslat":
            return [("mesaj", self._sinav_baslat(ek))]
        if ad == "/claude":
            return [("mesaj", self._claude(ek))]
        return [("mesaj", "Bu komutu tanımıyorum. Liste için /yardim yaz.")]

    def _dosya(self, ad: str, aciklama: str, satir: int, yoksa: str) -> list[tuple]:
        icerik = son_satirlar(self.klasor / "logs" / ad, satir)
        if not icerik:
            return [("mesaj", yoksa)]
        return [("belge", ad, icerik.encode("utf-8"), aciklama + ". Bu dosyayı Claude'a iletebilirsin.")]

    def _gunluk(self, ek: list[str]) -> list[tuple]:
        from .botlar import BOTLAR

        adlar = [b[0] for b in BOTLAR]
        if ek and ek[0].lower() == "claude":
            # Sunucudaki Claude'un kaydı ve oturum ekranının son hali.
            bolumler = []
            for ad in ("claude.txt", "claude_ekrani.txt"):
                icerik = son_satirlar(self.klasor / "logs" / ad, 150)
                bolumler.append(f"===== {ad} =====\n{icerik or '(kayıt yok)'}")
            return [("belge", "claude-kaydi.txt", "\n\n".join(bolumler).encode("utf-8"),
                     "Sunucudaki Claude'un kaydı. Bu dosyayı Claude'a iletebilirsin.")]
        if ek:
            bot = ek[0].lower()
            if bot not in adlar:
                return [("mesaj", "Böyle bir bot yok. Botlar: " + ", ".join(adlar))]
            icerik = son_satirlar(self.klasor / "logs" / f"{bot}.log", 300)
            if not icerik:
                return [("mesaj", f"{bot} henüz kayıt yazmamış.")]
            return [("belge", f"{bot}.txt", icerik.encode("utf-8"), f"{bot} botunun son kayıtları.")]
        bolumler = []
        for bot in adlar:
            icerik = son_satirlar(self.klasor / "logs" / f"{bot}.log", 40)
            bolumler.append(f"===== {bot} =====\n{icerik or '(kayıt yok)'}")
        return [("belge", "bot-kayitlari.txt", "\n\n".join(bolumler).encode("utf-8"),
                 "On botun son kayıtları. Bu dosyayı Claude'a iletebilirsin.")]

    def _sinav_baslat(self, ek: list[str]) -> str:
        from .sonuc import zaman_dosyasi_oku

        sinav = zaman_dosyasi_oku(self.klasor / "sinav_baslangici.txt")
        if sinav is not None:
            return f"Sınav zaten başladı: {yerel_saat(sinav):%d.%m.%Y %H:%M}. Saat yeniden başlatılamaz."
        isinma = zaman_dosyasi_oku(self.klasor / "isinma_baslangici.txt")
        if isinma is None:
            return "Botlar henüz başlamadı; önce kurulum bitmeli."
        simdi = self._simdi()
        gun = (simdi - isinma) / timedelta(days=1)
        if not ek or ek[0].lower() != "evet":
            uyari = (
                f"Isınma döneminin {int(gun) + 1}. günündeyiz; önerilen süre {ISINMA_GUN} gün. "
                if gun < ISINMA_GUN
                else ""
            )
            return (
                f"{uyari}Sınav başlayınca 30 gün boyunca strateji ayarları değişmez ve saat geri alınamaz.\n\n"
                "Eminsen şunu yaz: /sinav_baslat evet"
            )
        try:
            (self.klasor / "sinav_baslangici.txt").write_text(
                simdi.strftime("%Y-%m-%dT%H:%M:%SZ\n"), encoding="utf-8"
            )
        except OSError as hata:
            return f"Sınav başlatılamadı, dosya yazılamadı: {hata}"
        bitis = yerel_saat(simdi + timedelta(days=30))
        return (
            "30 günlük sınav başladı. Bundan sonraki sanal işlemler sınava sayılır.\n"
            f"Bitiş: {bitis:%d.%m.%Y %H:%M}. O gün karar raporunu yollarım."
        )

    def _istek_birak(self, ad: str, icerik: str = "") -> bool:
        """Sunucudaki betiğe (araclar/claude_sunucu.sh) bir istek dosyası bırakır.

        Haberci sunucuda komut çalıştırmaz; yalnız bu dosyayı yazar. Dosyayı
        sunucudaki izleyici okur ve ne yapacağına kendisi karar verir.
        """
        try:
            yol = self.klasor / ad
            yol.write_text(icerik, encoding="utf-8")
            yol.chmod(0o600)
            return True
        except OSError as hata:
            gunluk.warning("İstek dosyası yazılamadı: %s", hata)
            return False

    def _claude(self, ek: list[str]) -> str:
        """Sunucudaki Claude: durum, giriş bağlantısı isteği ya da giriş kodu."""
        if ek:
            kod = ek[0].strip()
            if not re.fullmatch(r"[A-Za-z0-9_#.~-]{8,512}", kod):
                return ("Bu bir giriş koduna benzemiyor. Kodu giriş sayfasından olduğu gibi "
                        "kopyalayıp şöyle yaz: /claude KOD")
            if not self._istek_birak("claude_kod.istek", kod + "\n"):
                return "Kodu sunucuya iletemedim. /kurulum yazıp gelen dosyayı Claude'a ilet."
            return "Kodu aldım, giriş ekranına yazıyorum. Sonucu bir dakika içinde bildiririm."
        try:
            durum = json.loads((self.klasor / "claude_durum.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ("Claude sunucuya henüz kurulmadı. Kurulum bittiğinde giriş bağlantısı "
                    "kendiliğinden gelir.")
        if not durum.get("kurulu"):
            return "Claude sunucuya kurulamadı. /kurulum yazıp gelen dosyayı Claude'a ilet."
        if not durum.get("giris"):
            if not self._istek_birak("claude_giris.istek"):
                return "Giriş isteğini sunucuya iletemedim. /kurulum yazıp gelen dosyayı Claude'a ilet."
            return "Claude sunucuda kurulu ama giriş yapılmamış. Giriş bağlantısını birazdan yolluyorum."
        if durum.get("oturum"):
            adres = durum.get("adres") or ""
            return (
                "Claude sunucuda çalışıyor. Telefonundaki Claude uygulamasında Code bölümünü aç; "
                "\"Karabasan sunucu\" adlı oturumu göreceksin."
                + (f"\nDoğrudan bağlantı: {adres}" if adres else "")
            )
        if not self._istek_birak("claude_giris.istek"):
            return "Oturumu açma isteğini sunucuya iletemedim. /kurulum yazıp gelen dosyayı Claude'a ilet."
        return "Giriş yapılmış ama oturum kapalı. Yeniden açıyorum; hazır olunca yazarım."

    # --- gelen mesajlar ---
    def guncelleme_isle(self, g: dict) -> None:
        mesaj = g.get("message") or {}
        sohbet = mesaj.get("chat") or {}
        metin = str(mesaj.get("text") or "")
        sahip = sohbet_oku(self.klasor)
        if sahip is None:
            if sohbet.get("type") == "private" and metin.startswith("/start"):
                sohbet_yaz(self.klasor, int(sohbet["id"]))
                gonder(self.tg, self.klasor, HOSGELDIN)
            return
        if sohbet.get("id") != sahip or not metin.startswith("/"):
            return  # başkasından gelen ya da komut olmayan mesaj: yanıt yok
        try:
            yanitlar = self.komut(metin)
        except Exception as hata:  # noqa: BLE001 - servis tek komut yüzünden düşmemeli
            gunluk.exception("Komut işlenemedi: %s", metin.split()[0])
            yanitlar = [("mesaj", f"Bu komut şu an yanıt veremedi. Şu satırı Claude'a ilet:\n{type(hata).__name__}: {hata}")]
        for yanit in yanitlar:
            if yanit[0] == "mesaj":
                self.tg.mesaj(sahip, yanit[1])
            else:
                self.tg.belge(sahip, yanit[1], yanit[2], yanit[3])

    # --- zamanlı işler ---
    def zamanli_isler(self) -> None:
        sahip = sohbet_oku(self.klasor)
        if sahip is None:
            return
        simdi = self._simdi()
        ozet = self.ozet()
        self._saglik(sahip, ozet, simdi)
        yerel = yerel_saat(simdi)
        bugun = yerel.strftime("%Y-%m-%d")
        if yerel.hour >= OZET_SAATI and self.durum.get("son_ozet_gunu") != bugun:
            if self.durum.get("son_ozet_gunu") is not None and ozet["donem"] != "kurulmadi":
                ek = ""
                if ozet["donem"] == "isinma" and ozet["gun"] > ISINMA_GUN:
                    ek = ("\n\nIsınma haftası doldu. Claude ile konuşup bir sorun görmediyseniz "
                          "sınavı /sinav_baslat ile başlatabilirsin.")
                self.tg.mesaj(sahip, durum_metni(ozet, "Günlük özet") + ek)
            self.durum["son_ozet_gunu"] = bugun
            self._durum_yaz()

    def _saglik(self, sahip: int, ozet: dict, simdi: datetime) -> None:
        """Bir bot susarsa bir kez, geri gelince bir kez haber verir."""
        if ozet["donem"] == "kurulmadi":
            return
        baslangic = ozet["baslangic"]
        if ozet["donem"] == "isinma" and baslangic and simdi - baslangic < timedelta(minutes=30):
            return  # botlar sırayla açılıyor
        sessiz = sorted(b["bot"] for b in ozet["botlar"] if not b["calisiyor"])
        onceki = sorted(self.durum.get("sessiz") or [])
        if sessiz == onceki:
            return
        yeni = [b for b in sessiz if b not in onceki]
        donen = [b for b in onceki if b not in sessiz]
        satirlar = []
        if yeni:
            satirlar.append("Ses vermeyen bot var: " + ", ".join(yeni) + ".")
            satirlar.append("15 dakikadan uzun süredir kayıt yazmıyor. /gunluk yazıp gelen dosyayı Claude'a ilet.")
        if donen:
            satirlar.append("Yeniden çalışıyor: " + ", ".join(donen) + ".")
        self.durum["sessiz"] = sessiz
        self._durum_yaz()
        self.tg.mesaj(sahip, "\n".join(satirlar))

    def calis(self) -> None:
        son_kontrol = 0.0
        while True:
            try:
                for g in self.tg.guncellemeler(self.durum.get("sira"), bekle=25):
                    self.durum["sira"] = int(g["update_id"]) + 1
                    self._durum_yaz()
                    self.guncelleme_isle(g)
            except TelegramHatasi as hata:
                gunluk.warning("%s", hata)
                time.sleep(15)
            except Exception:  # noqa: BLE001
                gunluk.exception("Beklenmeyen hata")
                time.sleep(15)
            if time.monotonic() - son_kontrol >= 60:
                son_kontrol = time.monotonic()
                try:
                    self.zamanli_isler()
                except Exception:  # noqa: BLE001
                    gunluk.exception("Zamanlı işler çalışamadı")


# --------------------------------------------------------------------------
# Komut satırı
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    is_adi, ek = argv[0], argv[1:]
    klasor = veri_klasoru()
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()

    if is_adi == "servis":
        while not token:
            gunluk.warning("Telegram kodu tanımlı değil; haberci bekliyor.")
            time.sleep(3600)
        Servis(Telegram(token), klasor).calis()
        return 0

    # Aşağıdakiler kurulum betiğinden çağrılır; Telegram'a ulaşılamaması kurulumu durdurmamalı.
    if not token:
        print("Telegram kodu tanımlı değil; mesaj gönderilmedi.", file=sys.stderr)
        return 0
    try:
        tg = Telegram(token)
        if is_adi == "gonder":
            gonder(tg, klasor, " ".join(ek))
        elif is_adi == "belge":
            sohbet = sahibi_ogren(tg, klasor)
            yol = Path(ek[0])
            if sohbet is not None and yol.exists():
                icerik = son_satirlar(yol, 2000).encode("utf-8")
                tg.belge(sohbet, yol.name, icerik, " ".join(ek[1:]))
        elif is_adi == "bekle":
            bitis = time.monotonic() + float(ek[0] if ek else 600)
            while True:
                try:
                    if sahibi_ogren(tg, klasor, bekle=20) is not None:
                        return 0
                except TelegramHatasi as hata:
                    print(hata, file=sys.stderr)
                    time.sleep(10)
                if time.monotonic() >= bitis:
                    return 1
        else:
            print(f"Bilinmeyen iş: {is_adi}", file=sys.stderr)
            return 2
    except TelegramHatasi as hata:
        print(hata, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
