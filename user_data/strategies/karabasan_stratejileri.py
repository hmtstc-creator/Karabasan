"""Karabasan stratejilerini hazır motora (Freqtrade) bağlayan ince katman.

Burada işlem mantığı YOKTUR. Mantık karabasan/ paketindedir ve orada
test edilir; bu dosya yalnız o mantığı motorun beklediği biçime çevirir.

Her sanal bot için bir sınıf vardır (SMKVadeli, SMDKVadeli, SMK2Vadeli, SMDK2Vadeli).
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
    cikis_sinyali,
    ekleme_gerekli,
    gereken_mum,
    giris_limit_yuzde,
    giris_sinyali,
    gosterge_ekle,
    kaldirac,
    kural_yukle,
    limit_fiyati,
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
    # Zararda ekleme (maliyet düşürme) kapalıdır; yalnız kuralı 'zararda_ekleme' isteyen
    # sanal botta açılır (22 Ekim 2026, Ahmet'in isteği), o zaman da işlem başına bir kez.
    position_adjustment_enable = False
    max_entry_position_adjustment = 0
    kaldirac_kat = 1.0
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
        # Motor oranları teminata göre ölçer: kaldıraçlı işlemde stop, hedef ve iz süren stop
        # oranları kaldıraçla çarpılır ki fiyattaki uzaklık kural dosyasındaki gibi kalsın.
        kat = kaldirac(kural)
        cls.kaldirac_kat = kat
        cls.kural = kural
        cls.timeframe = kural["zaman_dilimi"]
        cls.can_short = kural["yon"] == "aciga_satis"
        if cikis.get("kar_hedefi_yuzde") is not None:
            cls.minimal_roi = {
                "0": net_hedef_orani(float(cikis["kar_hedefi_yuzde"]), komisyon, cls.can_short) * kat
            }
        else:
            # Sabit kâr hedefi yok: motorun hedef çıkışı fiilen kapalı (%10.000).
            cls.minimal_roi = {"0": 100.0}
        cls.stoploss = -float(cikis["zarar_durdur_yuzde"]) / 100.0 * kat
        iz = cikis.get("iz_suren_stop")
        # İz süren stop: kâr (komisyon sonrası) tetiğe ulaşınca devreye girer, stop en iyi
        # fiyatın mesafe kadar gerisine çekilir. Motorun kendi ayarlarıyla birebir.
        cls.trailing_stop = bool(iz)
        if iz:
            cls.trailing_stop_positive = float(iz["mesafe_yuzde"]) / 100.0 * kat
            cls.trailing_stop_positive_offset = float(iz["tetik_yuzde"]) / 100.0 * kat
            cls.trailing_only_offset_is_reached = True
        cls.position_adjustment_enable = bool(kural.get("zararda_ekleme"))
        cls.max_entry_position_adjustment = 1 if cls.position_adjustment_enable else 0
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
        dataframe["giris_limit_yuzde"] = giris_limit_yuzde(dataframe, self.kural)
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Çıkış kâr hedefi, stop ve süre aşımıyla olur; kural 'cikis > sinyal' tanımlıyorsa
        # (Sniper) o sinyalle de. Sinyal mumun kapanışında, çıkış bir sonraki mumda.
        dataframe["exit_long"] = 0
        if self.can_short:
            dataframe["exit_short"] = 0
        sinyal = cikis_sinyali(dataframe, self.kural)
        dataframe.loc[sinyal, "exit_short" if self.can_short else "exit_long"] = 1
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag, side: str,
                            **kwargs) -> bool:
        """Kural 'defter_onayi' istiyorsa girişten hemen önce emir defterine bakar.

        Karar karabasan.defter.defter_onayi'dedir. Yalnız canlı ve sanal modda çalışır:
        geçmiş testinde geçmişin emir defteri yoktur, o yüzden orada bu adım atlanır.
        Defter okunamazsa işlem açılmaz.
        """
        ayar = self.kural.get("defter_onayi")
        saglayici = getattr(self, "dp", None)
        if not ayar or saglayici is None:
            return True
        kip = getattr(getattr(saglayici, "runmode", None), "value", "")
        if kip not in ("live", "dry_run"):
            return True
        from karabasan.defter import defter_onayi

        try:
            kitap = saglayici.orderbook(pair, 100)
            onay, aciklama = defter_onayi("alim" if side == "long" else "satis", kitap["bids"], kitap["asks"],
                                          float(ayar["en_az_dengesizlik"]))
        except Exception as hata:  # noqa: BLE001 - defter yoksa girme, bot durmasın
            logger.warning("%s %s: emir defteri okunamadı, işlem açılmadı: %s", self.kural.get("kod"), pair, hata)
            return False
        logger.info("%s %s: %s", self.kural.get("kod"), pair, aciklama)
        return onay

    def custom_entry_price(self, pair: str, trade, current_time: datetime, proposed_rate: float,
                           entry_tag, side: str, **kwargs) -> float:
        """Kural 'giris_limiti' istiyorsa limit emrin fiyatı: sinyalden sonra daha iyi fiyat.

        Uzaklık kural motorunda, sinyal mumunun satırında hesaplanır (giris_limit_yuzde).
        O satır bulunamazsa en küçük uzaklık kullanılır; emir yine de piyasadan iyi fiyattır.
        """
        limit = self.kural.get("giris_limiti")
        if not limit or trade is not None:
            # Zararda ek giriş (trade açık) önerilen fiyattan, beklemeden.
            return proposed_rate
        uzaklik = float(limit["en_az_yuzde"])
        saglayici = getattr(self, "dp", None)
        try:
            tablo, _ = saglayici.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
            # Sinyal mumu: girişin yapıldığı mumdan bir önceki. Canlıda son kapanmış mum,
            # geçmiş testinde de aynısı; daha yenisi (giriş mumunun kendisi) kullanılmaz.
            mum = timedelta(minutes=g.dilim_dakika(self.timeframe))
            simdi = current_time.timestamp() // mum.total_seconds() * mum.total_seconds()
            sinir = datetime.fromtimestamp(simdi, tz=current_time.tzinfo) - mum
            uygun = tablo[tablo["date"] <= sinir]
            if len(uygun) and uygun["giris_limit_yuzde"].iloc[-1] == uygun["giris_limit_yuzde"].iloc[-1]:
                uzaklik = float(uygun["giris_limit_yuzde"].iloc[-1])
        except Exception as hata:  # noqa: BLE001 - tablo yoksa en küçük uzaklık; bot durmasın
            logger.warning("%s %s: limit uzaklığı okunamadı, en küçüğü kullanıldı: %s",
                           self.kural.get("kod"), pair, hata)
        return limit_fiyati(proposed_rate, uzaklik, side == "long")

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs):
        dakika = self.kural["cikis"].get("sure_asimi_dakika")
        if dakika is None:
            return None     # süre sınırı yok
        if current_time - trade.open_date_utc >= timedelta(minutes=int(dakika)):
            return "sure_asimi"
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag, side: str,
                 **kwargs) -> float:
        # Kaldıraç 1 kattır; kuralı 'kaldirac' isteyen sanal bot (22 Ekim 2026) dışında.
        return min(self.kaldirac_kat, max_leverage)

    def adjust_trade_position(self, trade: Trade, current_time: datetime, current_rate: float,
                              current_profit: float, min_stake, max_stake: float, **kwargs):
        """Zararda ek giriş: fiyat ilk girişten stopa 'stopa_kala_yuzde' kalana kadar aleyhe
        gidince ilk tutarın 'kat' katı kadar, işlem başına bir kez. Karar karabasan.kural'dadır
        (ekleme_gerekli); burada yalnız motora çevrilir. Stop fiyatı ilk girişe göre kalır
        (motor ek girişte stopu yeniden kurmaz); hedef ve iz süren stop ortalama girişten.
        """
        ekleme = self.kural.get("zararda_ekleme")
        if not ekleme or trade.nr_of_successful_entries != 1 or getattr(trade, "has_open_orders", False):
            return None
        if not ekleme_gerekli(self.kural, float(trade.open_rate), float(current_rate)):
            return None
        tutar = float(trade.stake_amount) * float(ekleme["kat"])
        tutar = min(tutar, float(max_stake))
        if min_stake is not None and tutar < float(min_stake):
            logger.warning("%s %s: zararda ek giriş tutarı (%.2f) borsanın en küçük tutarından az; eklenmedi.",
                           self.kural.get("kod"), trade.pair, tutar)
            return None
        logger.info("%s %s: fiyat ekleme seviyesine geldi, %.2f USDT ek giriş.", self.kural.get("kod"),
                    trade.pair, tutar)
        return tutar


class SMKVadeli(KarabasanTaban):
    kural_kodu, piyasa = "SMK", "vadeli"


class SMDKVadeli(KarabasanTaban):
    kural_kodu, piyasa = "SMDK", "vadeli"


# 22 Ekim 2026 (Ahmet'in isteği): SMK / SMDK'nın aynısı, 2 kat kaldıraç ve zararda bir kez ek giriş.
class SMK2Vadeli(KarabasanTaban):
    kural_kodu, piyasa = "SMK2", "vadeli"


class SMDK2Vadeli(KarabasanTaban):
    kural_kodu, piyasa = "SMDK2", "vadeli"
