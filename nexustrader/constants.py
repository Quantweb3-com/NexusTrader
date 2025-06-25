import os
import sys
from abc import abstractmethod
from typing import Literal, Dict, List
from enum import Enum
from dynaconf import Dynaconf
from throttled import Throttled as ThrottledSync
from throttled.asyncio import Throttled
from nautilus_trader.core.nautilus_pyo3 import LogColor  # noqa


def is_sphinx_build():
    return "sphinx" in sys.modules


if not os.path.exists(".keys/"):
    os.makedirs(".keys/")
if not os.path.exists(".keys/.secrets.toml") and not is_sphinx_build():
    raise FileNotFoundError(
        "Config file not found, please create a config file at .keys/.secrets.toml"
    )


settings = Dynaconf(
    envvar_prefix="NEXUS",
    settings_files=[".keys/settings.toml", ".keys/.secrets.toml"],
    load_dotenv=True,
)


def get_postgresql_config():
    """Get PostgreSQL configuration from environment variables or settings files."""
    return {
        "host": settings.get("PG_HOST", "localhost"),
        "port": settings.get("PG_PORT", 5432),
        "user": settings.get("PG_USER", "postgres"),
        "password": settings.get("PG_PASSWORD", ""),
        "database": settings.get("PG_DATABASE", "postgres"),
    }


def get_redis_config(in_docker: bool = False):
    try:
        if in_docker:
            return {
                "host": "redis",
                "db": settings.REDIS_DB,
                "password": settings.REDIS_PASSWORD,
            }

        return {
            "host": settings.REDIS_HOST,
            "port": settings.REDIS_PORT,
            "db": settings.REDIS_DB,
            "password": settings.REDIS_PASSWORD,
        }
    except Exception as e:
        raise ValueError(f"Failed to get Redis password: {e}")


IntervalType = Literal[
    "1s",
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
]


class BookLevel(Enum):
    L5 = "5"
    L10 = "10"
    L20 = "20"
    L50 = "50"


class KlineInterval(Enum):
    SECOND_1 = "1s"
    MINUTE_1 = "1m"
    MINUTE_3 = "3m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_2 = "2h"
    HOUR_4 = "4h"
    HOUR_6 = "6h"
    HOUR_8 = "8h"
    HOUR_12 = "12h"
    DAY_1 = "1d"
    DAY_3 = "3d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"

    @property
    def seconds(self) -> int:
        return {
            KlineInterval.SECOND_1: 1,
            KlineInterval.MINUTE_1: 60,
            KlineInterval.MINUTE_3: 180,
            KlineInterval.MINUTE_5: 300,
            KlineInterval.MINUTE_15: 900,
            KlineInterval.MINUTE_30: 1800,
            KlineInterval.HOUR_1: 3600,
            KlineInterval.HOUR_2: 7200,
            KlineInterval.HOUR_4: 14400,
            KlineInterval.HOUR_6: 21600,
            KlineInterval.HOUR_8: 28800,
            KlineInterval.HOUR_12: 43200,
            KlineInterval.DAY_1: 86400,
            KlineInterval.DAY_3: 259200,
            KlineInterval.WEEK_1: 604800,
            KlineInterval.MONTH_1: 2592000,
        }[self]

    @property
    def microseconds(self) -> int:
        return self.seconds * 1000


class SubmitType(Enum):
    CREATE = 0
    CANCEL = 1
    TWAP = 2
    CANCEL_TWAP = 3
    VWAP = 4
    CANCEL_VWAP = 5
    STOP_LOSS = 6
    TAKE_PROFIT = 7
    MODIFY = 8
    CANCEL_ALL = 9
    BATCH = 10


class EventType(Enum):
    BOOKL1 = 0
    TRADE = 1
    KLINE = 2
    MARK_PRICE = 3
    FUNDING_RATE = 4
    INDEX_PRICE = 5


class AlgoOrderStatus(Enum):
    RUNNING = "RUNNING"
    CANCELING = "CANCELING"
    FINISHED = "FINISHED"
    CANCELED = "CANCELED"
    FAILED = "FAILED"


class OrderStatus(Enum):
    # LOCAL
    INITIALIZED = "INITIALIZED"
    FAILED = "FAILED"
    CANCEL_FAILED = "CANCEL_FAILED"

    # IN-FLOW
    PENDING = "PENDING"
    CANCELING = "CANCELING"

    # OPEN
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"

    # CLOSED
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"


class ExchangeType(Enum):
    BINANCE = "binance"
    OKX = "okx"
    BYBIT = "bybit"
    HYPERLIQUID = "hyperliquid"
    BITGET = "bitget"


class BinanceAccountType(Enum):
    SPOT = "SPOT"
    MARGIN = "MARGIN"
    ISOLATED_MARGIN = "ISOLATED_MARGIN"
    USD_M_FUTURE = "USD_M_FUTURE"
    COIN_M_FUTURE = "COIN_M_FUTURE"
    PORTFOLIO_MARGIN = "PORTFOLIO_MARGIN"
    SPOT_TESTNET = "SPOT_TESTNET"
    USD_M_FUTURE_TESTNET = "USD_M_FUTURE_TESTNET"
    COIN_M_FUTURE_TESTNET = "COIN_M_FUTURE_TESTNET"


class AccountType(Enum):
    pass


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"

    @property
    def is_take_profit(self) -> bool:
        return self in (OrderType.TAKE_PROFIT_MARKET, OrderType.TAKE_PROFIT_LIMIT)

    @property
    def is_stop_loss(self) -> bool:
        return self in (OrderType.STOP_LOSS_MARKET, OrderType.STOP_LOSS_LIMIT)

    @property
    def is_market(self) -> bool:
        return self in (
            OrderType.MARKET,
            OrderType.TAKE_PROFIT_MARKET,
            OrderType.STOP_LOSS_MARKET,
        )

    @property
    def is_limit(self) -> bool:
        return self in (
            OrderType.LIMIT,
            OrderType.TAKE_PROFIT_LIMIT,
            OrderType.STOP_LOSS_LIMIT,
        )


class TriggerType(Enum):
    LAST_PRICE = "LAST_PRICE"
    MARK_PRICE = "MARK_PRICE"
    INDEX_PRICE = "INDEX_PRICE"


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def is_buy(self) -> bool:
        return self == OrderSide.BUY

    @property
    def is_sell(self) -> bool:
        return self == OrderSide.SELL


class TimeInForce(Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class PositionSide(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"

    @property
    def is_long(self) -> bool:
        return self == PositionSide.LONG

    @property
    def is_short(self) -> bool:
        return self == PositionSide.SHORT

    @property
    def is_flat(self) -> bool:
        return self == PositionSide.FLAT


class InstrumentType(Enum):
    SPOT = "spot"
    MARGIN = "margin"
    FUTURE = "future"
    OPTION = "option"
    SWAP = "swap"
    LINEAR = "linear"
    INVERSE = "inverse"


class OptionType(Enum):
    CALL = "call"
    PUT = "put"


STATUS_TRANSITIONS: Dict[OrderStatus, List[OrderStatus]] = {
    OrderStatus.PENDING: [
        OrderStatus.PENDING,
        OrderStatus.CANCELED,
        OrderStatus.CANCELING,
        OrderStatus.ACCEPTED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCEL_FAILED,
    ],
    OrderStatus.CANCELING: [
        OrderStatus.CANCELED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
    ],
    OrderStatus.ACCEPTED: [
        OrderStatus.ACCEPTED,  # for modify order, pending -> accepted -> accepted -> (not allowed) -> pending
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELING,
        OrderStatus.CANCELED,
        OrderStatus.EXPIRED,
        OrderStatus.CANCEL_FAILED,
    ],
    OrderStatus.PARTIALLY_FILLED: [
        OrderStatus.ACCEPTED,  # for modify order, accepted -> partially filled -> accepted -> (not allowed) -> pending
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELING,
        OrderStatus.CANCELED,
        OrderStatus.EXPIRED,
        OrderStatus.CANCEL_FAILED,
    ],
    OrderStatus.FILLED: [],
    OrderStatus.CANCELED: [],
    OrderStatus.EXPIRED: [],
    OrderStatus.FAILED: [],
}


class DataType(Enum):
    BOOKL1 = "bookl1"
    BOOKL2 = "bookl2"
    TRADE = "trade"
    KLINE = "kline"
    MARK_PRICE = "mark_price"
    FUNDING_RATE = "funding_rate"
    INDEX_PRICE = "index_price"


class StorageType(Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class RateLimiter:
    @abstractmethod
    def __call__(self, endpoint: str) -> Throttled: ...


class RateLimiterSync:
    @abstractmethod
    def __call__(self, endpoint: str) -> ThrottledSync: ...
