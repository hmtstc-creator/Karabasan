"""Karabasan stratejilerini hazır motora (Freqtrade) bağlayan ince katman.

Burada işlem mantığı YOKTUR. Mantık karabasan/ paketindedir ve orada
test edilir; bu dosya yalnız o mantığı motorun beklediği biçime çevirir.

Her sanal bot için bir sınıf vardır (S1Spot, S1KVadeli, SMVadeli ...).
Sınıfın kâr hedefi, stopu, zaman dilimi ve yönü kural dosyasından gelir:
karabasan/stratejiler/<kod>.json

Bir kural günlük gibi büyük bir dilimi borsadan ayrıca istiyorsa
('borsa_dilimleri'), o mumları motor getirir; burada yalnız kural motoruna
aktarılır.
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy

# karabasan paketini bul: depo kökü ya da kapsayıcıda /freqtrade
_KOK = Path(__file__).resolve().parents[2]
if str(_KOK) not in sys.path:
    sys.path.insert(0, str(_KOK))

from karabasan import gostergeler as g  # noqa: E402
from karabasan.botlar import ayarlari_yukle, net_hedef_orani  # noqa: E402
from karabasan.kural import (  # noqa: E402
    borsa_dilimleri,
    gereken_mum,
    giris_sinyali,
    gosterge_ekle,
    kural_yukle,
)


logger = logging.getLogger(__name__)


class KarabasanTaban(IStrategy):
    """Kural dosyasından çalışan genel strateji. Doğrudan kullanılmaz."""

    INTERFACE_VERSION = 3

    kural_kodu = None  # alt sınıf belirler, örnek: "S1"
    piyasa = "spot"    # "spot" ya da "vadeli"
    kural = {}

    # Alt sınıflarda kural dosyasından doldurulur.
    timeframe = "5m"
    minimal_roi = {"0": 0.01}
    stoploss = -0.01
    can_short = False
    startup_candle_count = 200

    process_only_new_candles = True
    # custom_exit (süre aşımı) yalnız çıkış sinyalleri açıkken çağrılır.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    # Zararda ekleme (maliyet düşürme) kapalıdır.
    position_adjustment_enable = False
    use_custom_stoploss = False
    trailing_stop = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.kural_kodu:
            return
        kural = kural_yukle(cls.kural_kodu)
        ayar = ayarlari_yukle()
        komisyon = float(ayar["komisyon_yuzde"][cls.piyasa])
        cikis = kural["cikis"]
        cls.kural = kural
        cls.timeframe = kural["zaman_dilimi"]
        cls.can_short = kural["yon"] == "aciga_satis"
        cls.minimal_roi = {
            "0": net_hedef_orani(float(cikis["kar_hedefi_yuzde"]), komisyon, cls.can_short)
        }
        cls.stoploss = -float(cikis["zarar_durdur_yuzde"]) / 100.0
        cls.startup_candle_count = gereken_mum(kural)
        if cls.can_short and cls.piyasa != "vadeli":
            raise ValueError(f"{cls.__name__}: açığa satış yalnız vadeli piyasada yapılabilir.")

    @property
    def protections(self):
        """Stop sonrası aynı coine bekleme."""
        bekleme = int(self.kural.get("bekleme_dakika", 0))
        if bekleme <= 0:
            return []
        mum = max(1, bekleme // g.dilim_dakika(self.timeframe))
        return [
            {
                "method": "StoplossGuard",
                "lookback_period_candles": mum,
                "trade_limit": 1,
                "stop_duration_candles": mum,
                "only_per_pair": True,
            }
        ]

    def informative_pairs(self):
        """Kuralın borsadan ayrıca istediği dilimler (örnek: günlük mumlar).

        Motor burada sayılan (parite, dilim) çiftlerini kendisi indirir ve güncel tutar.
        """
        dilimler = borsa_dilimleri(self.kural)
        saglayici = getattr(self, "dp", None)
        if not dilimler or saglayici is None:
            return []
        try:
            pariteler = list(saglayici.current_whitelist())
        except Exception as hata:  # noqa: BLE001 - liste henüz hazır değilse bot durmasın
            logger.warning("%s: parite listesi okunamadı, %s mumları istenemedi: %s",
                           self.kural.get("kod"), ", ".join(dilimler), hata)
            return []
        return [(parite, dilim) for parite in pariteler for dilim in dilimler]

    def _ek_veri(self, parite: str) -> dict:
        """Borsadan gelen üst dilim mumları: {dilim: tablo}.

        Bir dilimin verisi alınamazsa yerine boş tablo konur: kural motoru o dilimi
        taban mumlardan toplamaya kalkmaz, göstergeleri boş kalır ve sinyal çıkmaz.
        Yani veri eksikliği işlem açtırmaz; yalnız o paritede o an işlem açılmaz.
        """
        ek = {}
        saglayici = getattr(self, "dp", None)
        for dilim in borsa_dilimleri(self.kural):
            tablo = None
            if saglayici is not None:
                try:
                    tablo = saglayici.get_pair_dataframe(pair=parite, timeframe=dilim)
                except Exception:  # noqa: BLE001 - veri yoksa sinyal de yok; bot durmasın
                    tablo = None
            if tablo is not None and len(tablo) > 0:
                ek[dilim] = tablo
            else:
                ek[dilim] = DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
                self._eksik_veri_bildir(parite, dilim)
        return ek

    def _eksik_veri_bildir(self, parite: str, dilim: str) -> None:
        """Alınamayan üst dilim verisini kayda bir kez yazar (uyum raporunda ve /gunluk'te görünür)."""
        bildirilen = self.__dict__.setdefault("_eksik_bildirilen", set())
        if (parite, dilim) not in bildirilen:
            bildirilen.add((parite, dilim))
            logger.warning("%s %s: %s mumları alınamadı; veri gelene kadar bu paritede sinyal üretilmez.",
                           self.kural.get("kod"), parite, dilim)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return gosterge_ekle(dataframe, self.kural, self._ek_veri(metadata["pair"]))

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        sinyal = giris_sinyali(dataframe, self.kural)
        sutun = "enter_short" if self.can_short else "enter_long"
        if self.can_short:
            dataframe["enter_short"] = 0
        dataframe.loc[sinyal, sutun] = 1
        dataframe.loc[sinyal, "enter_tag"] = self.kural["kod"]
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Çıkış yalnız kâr hedefi, stop ve süre aşımıyla olur; sinyalle çıkış yok.
        dataframe["exit_long"] = 0
        if self.can_short:
            dataframe["exit_short"] = 0
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs):
        sure = timedelta(minutes=int(self.kural["cikis"]["sure_asimi_dakika"]))
        if current_time - trade.open_date_utc >= sure:
            return "sure_asimi"
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag, side: str,
                 **kwargs) -> float:
        # Sınavda kaldıraç her zaman 1 kattır.
        return 1.0


class S1Spot(KarabasanTaban):
    kural_kodu, piyasa = "S1", "spot"


class S2Spot(KarabasanTaban):
    kural_kodu, piyasa = "S2", "spot"


class S3Spot(KarabasanTaban):
    kural_kodu, piyasa = "S3", "spot"


class S4Spot(KarabasanTaban):
    kural_kodu, piyasa = "S4", "spot"


class S1KVadeli(KarabasanTaban):
    kural_kodu, piyasa = "S1K", "vadeli"


class S2KVadeli(KarabasanTaban):
    kural_kodu, piyasa = "S2K", "vadeli"


class S5Vadeli(KarabasanTaban):
    kural_kodu, piyasa = "S5", "vadeli"


class S5KVadeli(KarabasanTaban):
    kural_kodu, piyasa = "S5K", "vadeli"


class S6Vadeli(KarabasanTaban):
    kural_kodu, piyasa = "S6", "vadeli"


class S6KVadeli(KarabasanTaban):
    kural_kodu, piyasa = "S6K", "vadeli"


class SMVadeli(KarabasanTaban):
    kural_kodu, piyasa = "SM", "vadeli"


class SMKVadeli(KarabasanTaban):
    kural_kodu, piyasa = "SMK", "vadeli"
