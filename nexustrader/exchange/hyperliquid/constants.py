from datetime import timedelta
from typing import Dict, TypedDict, NotRequired
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
from throttled import Throttled, rate_limiter


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


class HyperLiquidTimeInForce(Enum):
    GTC = "Gtc"
    IOC = "Ioc"
    ALO = "Alo"  # Post Only


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


class HyperLiquidRateLimiter:
    """Rate limiter for Hyperliquid API"""

    def __init__(self, enable_rate_limit: bool = True):
        self._throttled: Dict[str, Throttled] = {
            "/exchange": Throttled(
                quota=rate_limiter.per_duration(timedelta(seconds=60), limit=1200),
                timeout=60 if enable_rate_limit else -1,
            ),
        }

    def __call__(self, endpoint: str) -> Throttled:
        return self._throttled[endpoint]


class HyperLiquidRateLimiterSync:
    """Synchronous rate limiter for Hyperliquid API"""

    def __init__(self, enable_rate_limit: bool = True):
        self._throttled: Dict[str, Throttled] = {
            "/info": Throttled(
                quota=rate_limiter.per_duration(timedelta(seconds=60), limit=1200),
                timeout=60 if enable_rate_limit else -1,
            ),
        }

    def __call__(self, endpoint: str) -> Throttled:
        return self._throttled[endpoint]


class HyperLiquidOrderLimitTypeRequest(TypedDict):
    tif: str  # "Alo" other exchange called post only | Ioc (Immediate or Cancel) | Gtc (Good Till Cancel)


class HyperLiquidOrderTriggerTypeRequest(TypedDict):
    isMarket: bool  # True for market order, False for limit order
    triggerPx: str  # Trigger price for stop orders, empty for limit orders
    tpsl: str  # tp | sl


class HyperLiquidOrderTypeRequest(TypedDict):
    limit: NotRequired[HyperLiquidOrderLimitTypeRequest]  # Limit order type
    trigger: NotRequired[HyperLiquidOrderTriggerTypeRequest]


class HyperLiquidOrderRequest(TypedDict):
    """
    HyperLiquid order request schema


    a: int  asset
    b: bool isBuy
    p: str  price
    s: str  size
    r: bool  reduceOnly
    t: HyperLiquidOrderTypeRequest
    c: NotRequired[str]  clientOrderId
    """

    a: int  # asset
    b: bool  # isBuy
    p: str  # price
    s: str  # size
    r: bool  # reduceOnly
    t: HyperLiquidOrderTypeRequest
    c: NotRequired[str]  # clientOrderId


class HyperLiquidOrderCancelRequest(TypedDict):
    a: int  # asset
    o: int  # oid  # orderId


class HyperLiquidEnumParser:
    _hyperliquid_kline_interval_map = {
        HyperLiquidKlineInterval.MINUTE_1: KlineInterval.MINUTE_1,
        HyperLiquidKlineInterval.MINUTE_3: KlineInterval.MINUTE_3,
        HyperLiquidKlineInterval.MINUTE_5: KlineInterval.MINUTE_5,
        HyperLiquidKlineInterval.MINUTE_15: KlineInterval.MINUTE_15,
        HyperLiquidKlineInterval.MINUTE_30: KlineInterval.MINUTE_30,
        HyperLiquidKlineInterval.HOUR_1: KlineInterval.HOUR_1,
        HyperLiquidKlineInterval.HOUR_2: KlineInterval.HOUR_2,
        HyperLiquidKlineInterval.HOUR_4: KlineInterval.HOUR_4,
        HyperLiquidKlineInterval.HOUR_8: KlineInterval.HOUR_8,
        HyperLiquidKlineInterval.HOUR_12: KlineInterval.HOUR_12,
        HyperLiquidKlineInterval.DAY_1: KlineInterval.DAY_1,
        HyperLiquidKlineInterval.WEEK_1: KlineInterval.WEEK_1,
        HyperLiquidKlineInterval.MONTH_1: KlineInterval.MONTH_1,
    }

    _kline_interval_to_hyperliquid_map = {
        v: k for k, v in _hyperliquid_kline_interval_map.items()
    }

    _hyperliquid_time_in_force_map = {
        HyperLiquidTimeInForce.GTC: TimeInForce.GTC,
        HyperLiquidTimeInForce.IOC: TimeInForce.IOC,
    }

    _time_in_force_to_hyperliquid_map = {
        v: k for k, v in _hyperliquid_time_in_force_map.items()
    }

    @classmethod
    def parse_kline_interval(cls, interval: HyperLiquidKlineInterval) -> KlineInterval:
        """Convert KlineInterval to HyperLiquidKlineInterval"""
        return cls._hyperliquid_kline_interval_map[interval]

    @classmethod
    def to_hyperliquid_kline_interval(
        cls, interval: KlineInterval
    ) -> HyperLiquidKlineInterval:
        """Convert KlineInterval to HyperLiquidKlineInterval"""
        if interval not in cls._kline_interval_to_hyperliquid_map:
            raise KlineSupportedError(
                f"Unsupported kline interval: {interval}. Supported intervals: {list(cls._kline_interval_to_hyperliquid_map.keys())}"
            )
        return cls._kline_interval_to_hyperliquid_map[interval]

    @classmethod
    def parse_time_in_force(cls, time_in_force: HyperLiquidTimeInForce) -> TimeInForce:
        """Convert HyperLiquidTimeInForce to TimeInForce"""
        return cls._hyperliquid_time_in_force_map[time_in_force]

    @classmethod
    def to_hyperliquid_time_in_force(
        cls, time_in_force: TimeInForce
    ) -> HyperLiquidTimeInForce:
        """Convert TimeInForce to HyperLiquidTimeInForce"""
        return cls._time_in_force_to_hyperliquid_map[time_in_force]
