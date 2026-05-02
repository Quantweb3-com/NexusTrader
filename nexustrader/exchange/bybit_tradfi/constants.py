"""
Constants and enumerations for the Bybit TradeFi (MT5) connector.
"""

from __future__ import annotations


from nexustrader.constants import AccountType, KlineInterval


class BybitTradeFiAccountType(AccountType):
    """
    Account types for Bybit TradeFi via MetaTrader5.

    Credentials mapping (using ``BasicConfig`` fields):
        api_key   → MT5 account login number (integer as string)
        secret    → MT5 account password
        passphrase→ MT5 broker server name  (e.g. "BybitBroker-Demo")
        testnet   → True for demo account
    """

    LIVE = "LIVE"
    DEMO = "DEMO"

    @property
    def exchange_id(self) -> str:
        return "bybit_tradfi"

    @property
    def is_testnet(self) -> bool:
        return self == BybitTradeFiAccountType.DEMO

    @property
    def is_live(self) -> bool:
        return self == BybitTradeFiAccountType.LIVE

    @property
    def is_demo(self) -> bool:
        return self == BybitTradeFiAccountType.DEMO

    # The MT5 connector never uses mock connectors
    @property
    def is_mock(self) -> bool:
        return False

    @property
    def is_linear_mock(self) -> bool:
        return False

    @property
    def is_inverse_mock(self) -> bool:
        return False

    @property
    def is_spot_mock(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# MT5 timeframe mapping
# ---------------------------------------------------------------------------
# Values match mt5.TIMEFRAME_* constants.  We store them as plain ints to
# avoid importing MetaTrader5 at module level (lazy import principle).

_KLINE_TO_MT5_TF: dict[KlineInterval, int] = {
    KlineInterval.MINUTE_1: 1,
    KlineInterval.MINUTE_3: 3,
    KlineInterval.MINUTE_5: 5,
    KlineInterval.MINUTE_15: 15,
    KlineInterval.MINUTE_30: 30,
    KlineInterval.HOUR_1: 16385,  # mt5.TIMEFRAME_H1
    KlineInterval.HOUR_2: 16386,  # mt5.TIMEFRAME_H2
    KlineInterval.HOUR_4: 16388,  # mt5.TIMEFRAME_H4
    KlineInterval.HOUR_6: 16390,  # mt5.TIMEFRAME_H6
    KlineInterval.HOUR_8: 16392,  # mt5.TIMEFRAME_H8
    KlineInterval.HOUR_12: 16396,  # mt5.TIMEFRAME_H12
    KlineInterval.DAY_1: 16408,  # mt5.TIMEFRAME_D1
    KlineInterval.WEEK_1: 32769,  # mt5.TIMEFRAME_W1
    KlineInterval.MONTH_1: 49153,  # mt5.TIMEFRAME_MN1
}


def kline_interval_to_mt5_timeframe(interval: KlineInterval) -> int:
    """Convert NexusTrader KlineInterval to the corresponding MT5 timeframe constant."""
    tf = _KLINE_TO_MT5_TF.get(interval)
    if tf is None:
        raise ValueError(
            f"KlineInterval.{interval.name} is not supported by MetaTrader5."
        )
    return tf
