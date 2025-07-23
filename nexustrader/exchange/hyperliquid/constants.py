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
        return "wss://api.hyperliquid.xyz/ws"

    @property
    def rest_url(self):
        if self.is_testnet:
            return "https://api.hyperliquid-testnet.xyz"
        return "https://api.hyperliquid.xyz"


class HyperLiquidOrderType(Enum):
    LIMIT = "Limit"
    MARKET = "Market"
    POST_ONLY = "PostOnly"


class HyperLiquidTimeInForce(Enum):
    GTC = "Gtc"
    IOC = "Ioc"
    FOK = "Fok"


class HyperLiquidOrderSide(Enum):
    BUY = "B"
    SELL = "A"
