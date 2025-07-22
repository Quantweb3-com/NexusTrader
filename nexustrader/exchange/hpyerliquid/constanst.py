from nexustrader.constants import (
    AccountType,
    OrderStatus,
    PositionSide,
    OrderSide,
    TimeInForce,
    OrderType,
    KlineInterval,
)
from enum import Enum
from nexustrader.error import KlineSupportedError


class HyperLiquidAccountType(AccountType):
    MAINNET = "mainnet"
    TESTNET = "testnet"

    @property
    def exchange_id(self):
        return "hyperliquid"

    @property
    def is_testnet(self):
        return self == self.TESTNET

    @property
    def ws_url(self):
        if self.is_testnet:
            return "wss://api.hyperliquid-testnet.xyz/ws"
        return "wss://api.hyperliquid.xyz/ws "


class HyperLiquidKlineInterval(Enum):
    MINUTE_1 = "1m"
    MINUTE_3 = "3m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_2 = "2h"
    HOUR_4 = "4h"
    HOUR_8 = "8h"
    HOUR_12 = "12h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"
