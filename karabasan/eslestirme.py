"""Hazır motorun geçmiş testi ile bağımsız benzetimi işlem işlem eşleştirir.

Uyum denemesi iki hesabın yalnız toplamlarını karşılaştırıyordu. Toplamlar
tutmadığında (11 Ekim 2026: açığa satış botlarında motor her coinde yaklaşık
%10 fazla işlem saydı, alım botlarında birebir tuttu) farkın nedenini görmek
için işlemleri tek tek yan yana koymak gerekir. Bu modül bunu yapar:

- Her iki taraftaki işlemleri (coin, giriş zamanı) ile eşleştirir.
- Eşleşen işlemlerde çıkış nedeni ya da çıkış mumu farklıysa sayar.
- Eşleşen işlemlerde iki tarafın komisyon dahil net sonucunu toplar; iz süren
  stopla kapananlarda benzetimin kaç işlemi daha geç ya da erken kapattığını
  sayar (motor stopu mumun tepesiyle aynı mumda taşır, benzetim bir sonraki
  mumdan; 16. uyum denemesinde 33 iz süren stopun 31'i başka mumda kapandı).
- Yalnız bir tarafta olan işlemlerin ilk birkaçını, o sırada öbür tarafta
  açık olan işlemle birlikte yazar. Fark çoğu zaman şöyle görünür: "motor
  bu işlemi açtı, çünkü benzetimdeki önceki işlem motorda daha erken kapandı".

Hiçbir ayarı değiştirmez; yalnız okur ve rapor yazar.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd

# Motorun çıkış nedenlerini benzetimin adlarına çevirir.
MOTOR_NEDENLERI = {
    "roi": "kar_hedefi",
    "stop_loss": "zarar_durdur",
    "stoploss_on_exchange": "zarar_durdur",
    "trailing_stop_loss": "iz_suren_stop",
    "exit_signal": "cikis_sinyali",
    "liquidation": "tasfiye",
    "sure_asimi": "sure_asimi",
    "force_exit": "zorla_kapatma",
}


def _zaman(deger) -> pd.Timestamp:
    z = pd.Timestamp(deger)
    return z.tz_localize("UTC") if z.tzinfo is None else z.tz_convert("UTC")


def _sonuc_icerigi(dosya: Path) -> dict | None:
    """Bir sonuç dosyasından {strateji: {...}} sözlüğünü çıkarır; yoksa None."""
    adaylar = []
    try:
        if dosya.suffix == ".zip":
            with zipfile.ZipFile(dosya) as z:
                for ad in z.namelist():
                    if ad.endswith(".json"):
                        adaylar.append(z.read(ad))
        elif dosya.suffix == ".json":
            adaylar.append(dosya.read_bytes())
    except (OSError, zipfile.BadZipFile):
        return None
    for ham in adaylar:
        try:
            veri = json.loads(ham)
        except ValueError:
            continue
        strateji = veri.get("strategy") if isinstance(veri, dict) else None
        if isinstance(strateji, dict) and any(
            isinstance(v, dict) and "trades" in v for v in strateji.values()
        ):
            return strateji
    return None


def motor_sonuclari_oku(klasor: Path) -> dict[str, list[dict]]:
    """Klasördeki geçmiş testi sonuçlarını okur: {strateji sınıfı: işlem listesi}.

    Aynı strateji birden çok dosyada varsa en yeni dosya kazanır.
    """
    sonuc: dict[str, tuple[float, list[dict]]] = {}
    if not klasor.is_dir():
        return {}
    for dosya in klasor.iterdir():
        if dosya.name.startswith(".") or dosya.name.endswith(".meta.json"):
            continue
        icerik = _sonuc_icerigi(dosya)
        if not icerik:
            continue
        zaman = dosya.stat().st_mtime
        for ad, ozet in icerik.items():
            if not isinstance(ozet, dict) or "trades" not in ozet:
                continue
            if ad not in sonuc or sonuc[ad][0] < zaman:
                sonuc[ad] = (zaman, list(ozet["trades"]))
    return {ad: islemler for ad, (_z, islemler) in sonuc.items()}


def motor_islemleri(ham: list[dict]) -> list[dict]:
    """Motorun işlem kayıtlarını ortak biçime çevirir.

    cikis_mumu: işlemin kapandığı mumun açılış zamanı. Motor kâr hedefi ve
    stopta o mumun zamanını yazar; süre aşımında bir sonraki mumun açılışında
    kapatır, yani o mumu yazar.
    """
    sonuc = []
    for t in ham:
        cift = str(t.get("pair", ""))
        neden_ham = str(t.get("exit_reason") or t.get("sell_reason") or "")
        sonuc.append(
            {
                "coin": cift.split("/")[0],
                "giris": _zaman(t["open_date"]),
                "cikis_mumu": _zaman(t["close_date"]),
                "neden": MOTOR_NEDENLERI.get(neden_ham, neden_ham),
                "aciga_satis": bool(t.get("is_short", False)),
                "net": _yuzde(t.get("profit_ratio"), 100.0),
            }
        )
    return sonuc


def benzetim_islemleri(islemler: list[dict], coin: str, mum: pd.Timedelta) -> list[dict]:
    """Benzetimin işlemlerini motorla aynı biçime çevirir.

    Benzetim çıkış zamanı olarak çıkış mumunun kapanışını yazar. Kâr hedefi ve
    stop o mumun içinde olur, motor o mumun açılış zamanını yazar; süre aşımı
    mumun kapanışında olur, motor bir sonraki mumun açılışını yazar.
    """
    sonuc = []
    for i in islemler:
        cikis = i["cikis_zamani"]
        if i["neden"] != "sure_asimi":
            cikis = cikis - mum
        sonuc.append(
            {
                "coin": coin,
                "giris": _zaman(i["giris_zamani"]),
                "cikis_mumu": _zaman(cikis),
                "neden": i["neden"],
                "aciga_satis": i.get("yon") == "aciga_satis",
                "net": _yuzde(i.get("net_yuzde"), 1.0),
            }
        )
    return sonuc


def _yuzde(deger, kat: float) -> float | None:
    """İşlemin komisyon dahil net sonucu, yüzde; kayıtta yoksa None."""
    try:
        return None if deger is None else float(deger) * kat
    except (TypeError, ValueError):
        return None


def _net_ozeti(ciftler: list[tuple[dict, dict]]) -> dict:
    """Eşleşen işlemlerde iki tarafın net sonucu (yalnız ikisinde de net yazılıysa)."""
    netli = [(m, b) for m, b in ciftler if m.get("net") is not None and b.get("net") is not None]
    iz = [(m, b) for m, b in netli if m["neden"] == b["neden"] == "iz_suren_stop"]
    return {
        "sayi": len(netli),
        "motor": sum(m["net"] for m, _ in netli),
        "benzetim": sum(b["net"] for _, b in netli),
        "iz_sayi": len(iz),
        "iz_motor": sum(m["net"] for m, _ in iz),
        "iz_benzetim": sum(b["net"] for _, b in iz),
        "iz_gec": sum(1 for m, b in iz if b["cikis_mumu"] > m["cikis_mumu"]),
        "iz_erken": sum(1 for m, b in iz if b["cikis_mumu"] < m["cikis_mumu"]),
    }


def _acik_olan(islemler: list[dict], coin: str, an: pd.Timestamp) -> dict | None:
    """Verilen anda aynı coinde açık olan (ya da o mumda kapanan) işlem."""
    for t in islemler:
        if t["coin"] == coin and t["giris"] <= an <= t["cikis_mumu"]:
            return t
    return None


def eslestir(motor: list[dict], benzetim: list[dict]) -> dict:
    """İki işlem listesini (coin, giriş zamanı) ile eşleştirir."""
    m_anahtar = {(t["coin"], t["giris"]): t for t in motor}
    b_anahtar = {(t["coin"], t["giris"]): t for t in benzetim}
    ortak = sorted(set(m_anahtar) & set(b_anahtar))
    neden_farki: dict[tuple[str, str], int] = {}
    yalniz_mum_farki = 0
    for k in ortak:
        m, b = m_anahtar[k], b_anahtar[k]
        if m["neden"] != b["neden"]:
            cift = (m["neden"], b["neden"])
            neden_farki[cift] = neden_farki.get(cift, 0) + 1
        elif m["cikis_mumu"] != b["cikis_mumu"]:
            yalniz_mum_farki += 1
    yalniz_motor = sorted(
        (m_anahtar[k] for k in set(m_anahtar) - set(b_anahtar)), key=lambda t: (t["giris"], t["coin"])
    )
    yalniz_benzetim = sorted(
        (b_anahtar[k] for k in set(b_anahtar) - set(m_anahtar)), key=lambda t: (t["giris"], t["coin"])
    )
    return {
        "motor": len(motor),
        "benzetim": len(benzetim),
        "eslesen": len(ortak),
        "neden_farki": neden_farki,
        "cikis_mumu_farki": yalniz_mum_farki,
        "yalniz_motor": yalniz_motor,
        "yalniz_benzetim": yalniz_benzetim,
        "motor_nedenleri": _say(motor),
        "benzetim_nedenleri": _say(benzetim),
        "net": _net_ozeti([(m_anahtar[k], b_anahtar[k]) for k in ortak]),
    }


def _say(islemler: list[dict]) -> dict[str, int]:
    sayac: dict[str, int] = {}
    for t in islemler:
        sayac[t["neden"]] = sayac.get(t["neden"], 0) + 1
    return dict(sorted(sayac.items()))


def _kisa(t: dict | None) -> str:
    if t is None:
        return "açık işlem yok"
    return (f"{t['giris']:%m-%d %H:%M} → {t['cikis_mumu']:%m-%d %H:%M} {t['neden']}")


def _isaretli(x: float) -> str:
    return f"{x:+.2f}".replace(".", ",")


def rapor_satirlari(bot: str, motor: list[dict], benzetim: list[dict], ornek: int = 4,
                    tutar: float | None = None) -> list[str]:
    """Bir bot için okunur rapor satırları üretir. tutar: işlem başına USDT (verilirse USDT de yazılır)."""
    s = eslestir(motor, benzetim)
    satirlar = [
        f"{bot}: motor {s['motor']}, benzetim {s['benzetim']}, eşleşen {s['eslesen']}, "
        f"yalnız motor {len(s['yalniz_motor'])}, yalnız benzetim {len(s['yalniz_benzetim'])}",
        f"    çıkış nedenleri  motor: {_nedenler(s['motor_nedenleri'])}",
        f"                benzetim: {_nedenler(s['benzetim_nedenleri'])}",
    ]
    if s["neden_farki"]:
        farklar = ", ".join(f"motor {m} / benzetim {b}: {n}" for (m, b), n in sorted(s["neden_farki"].items()))
        satirlar.append(f"    eşleşip farklı nedenle kapanan: {farklar}")
    if s["cikis_mumu_farki"]:
        satirlar.append(f"    eşleşip aynı nedenle ama başka mumda kapanan: {s['cikis_mumu_farki']}")
    n = s["net"]
    if n["sayi"]:
        def kac(toplam):
            usdt = f" = {_isaretli(toplam * tutar / 100.0)} USDT" if tutar else ""
            return f"%{_isaretli(toplam)}{usdt}"

        satirlar.append(f"    eşleşen {n['sayi']} işlemin net toplamı (komisyon dahil): "
                        f"motor {kac(n['motor'])}, benzetim {kac(n['benzetim'])}")
    if n["iz_sayi"]:
        satirlar.append(
            f"    iki tarafta da iz süren stopla kapanan {n['iz_sayi']}: benzetim {n['iz_gec']} tanesini daha geç, "
            f"{n['iz_erken']} tanesini daha erken kapattı; işlem başına ortalama net motor "
            f"%{_isaretli(n['iz_motor'] / n['iz_sayi'])}, benzetim %{_isaretli(n['iz_benzetim'] / n['iz_sayi'])}")
    for t in s["yalniz_motor"][:ornek]:
        satirlar.append(
            f"    yalnız motor  {t['coin']:<5} {_kisa(t)}  | benzetimde o an: {_kisa(_acik_olan(benzetim, t['coin'], t['giris']))}"
        )
    for t in s["yalniz_benzetim"][:ornek]:
        satirlar.append(
            f"    yalnız benz.  {t['coin']:<5} {_kisa(t)}  | motorda o an: {_kisa(_acik_olan(motor, t['coin'], t['giris']))}"
        )
    return satirlar


def _nedenler(sayac: dict[str, int]) -> str:
    return ", ".join(f"{k} {v}" for k, v in sayac.items()) or "-"
