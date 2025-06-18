from datetime import timedelta
from throttled.asyncio import Throttled, rate_limiter
from throttled import Throttled as ThrottledSync
from throttled import rate_limiter as rate_limiter_sync

from nexustrader.constants import (
    AccountType,
    OrderStatus,
    PositionSide,
    OrderSide,
    TimeInForce,
    OrderType,
    KlineInterval,
    RateLimiter,
    RateLimiterSync,
)
from enum import Enum
from nexustrader.error import KlineSupportedError


class BitgetAccountType(AccountType):
    LIVE = 0
    DEMO = 1
    SPOT_MOCK = 2
    LINEAR_MOCK = 3
    INVERSE_MOCK = 4

    @property
    def exchange_id(self):
        return "bitget"

    @property
    def testnet(self):
        return self == self.DEMO

    @property
    def stream_url(self):
        return "wss://ws.bitget.com/v2/ws"

    @property
    def is_mock(self):
        return self in (self.SPOT_MOCK, self.LINEAR_MOCK, self.INVERSE_MOCK)

    @property
    def is_linear_mock(self):
        return self == self.LINEAR_MOCK

    @property
    def is_inverse_mock(self):
        return self == self.INVERSE_MOCK

    @property
    def is_spot_mock(self):
        return self == self.SPOT_MOCK


class BitgetInstType(Enum):
    SPOT = "SPOT"
    USDT_FUTURES = "USDT-FUTURES"
    COIN_FUTURES = "COIN-FUTURES"


class BitgetKlineInterval(Enum):
    MINUTE_1 = "candle1m"
    MINUTE_5 = "candle5m"
    MINUTE_15 = "candle15m"
    MINUTE_30 = "candle30m"
    HOUR_1 = "candle1H"
    HOUR_4 = "candle4H"
    HOUR_6 = "candle6Hutc"
    HOUR_12 = "candle12Hutc"
    DAY_1 = "candle1Dutc"


class BitgetOrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class BitgetOrderStatus(Enum):
    NEW = "new"
    FILLED = "filled"
    CANCELED = "cancelled"
    PARTIALLY_FILLED = "partial-fill"
    FAILED = "failed"


class BitgetTimeInForce(Enum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class BitgetOrderType(Enum):
    LIMIT = "limit"
    MARKET = "market"


class BitgetPositionSide(Enum):
    LONG = "long"
    SHORT = "short"

    def parse_to_position_side(self) -> PositionSide:
        if self == self.LONG:
            return PositionSide.LONG
        elif self == self.SHORT:
            return PositionSide.SHORT
        else:
            return PositionSide.FLAT


class BitgetEnumParser:
    _kline_interval_map = {
        BitgetKlineInterval.MINUTE_1: KlineInterval.MINUTE_1,
        BitgetKlineInterval.MINUTE_5: KlineInterval.MINUTE_5,
        BitgetKlineInterval.MINUTE_15: KlineInterval.MINUTE_15,
        BitgetKlineInterval.MINUTE_30: KlineInterval.MINUTE_30,
        BitgetKlineInterval.HOUR_1: KlineInterval.HOUR_1,
        BitgetKlineInterval.HOUR_4: KlineInterval.HOUR_4,
        BitgetKlineInterval.HOUR_6: KlineInterval.HOUR_6,
        BitgetKlineInterval.HOUR_12: KlineInterval.HOUR_12,
        BitgetKlineInterval.DAY_1: KlineInterval.DAY_1,
    }

    _order_status_map = {
        BitgetOrderStatus.NEW: OrderStatus.ACCEPTED,
        BitgetOrderStatus.FILLED: OrderStatus.FILLED,
        BitgetOrderStatus.CANCELED: OrderStatus.CANCELED,
        BitgetOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
        BitgetOrderStatus.FAILED: OrderStatus.FAILED,
    }

    _order_side_map = {
        BitgetOrderSide.BUY: OrderSide.BUY,
        BitgetOrderSide.SELL: OrderSide.SELL,
    }

    _time_in_force_map = {
        BitgetTimeInForce.GTC: TimeInForce.GTC,
        BitgetTimeInForce.IOC: TimeInForce.IOC,
        BitgetTimeInForce.FOK: TimeInForce.FOK,
    }

    _order_type_map = {
        BitgetOrderType.LIMIT: OrderType.LIMIT,
        BitgetOrderType.MARKET: OrderType.MARKET,
    }

    @classmethod
    def parse_kline_interval(cls, interval: BitgetKlineInterval) -> KlineInterval:
        return cls._kline_interval_map[interval]

    @classmethod
    def parse_order_status(cls, status: BitgetOrderStatus) -> OrderStatus:
        return cls._order_status_map[status]

    @classmethod
    def parse_order_side(cls, side: BitgetOrderSide) -> OrderSide:
        return cls._order_side_map[side]

    @classmethod
    def parse_time_in_force(cls, tif: BitgetTimeInForce) -> TimeInForce:
        return cls._time_in_force_map[tif]

    @classmethod
    def parse_order_type(cls, order_type: BitgetOrderType) -> OrderType:
        return cls._order_type_map[order_type]


class BitgetRateLimiter(RateLimiter):
    def __init__(self):
        self._throttled: dict[str, Throttled] = {
            "public": Throttled(
                quota=rate_limiter.per_duration(timedelta(seconds=5), limit=600),
                timeout=5,
            ),
            "trade": Throttled(
                quota=rate_limiter.per_sec(20),
                timeout=1,
            ),
            "position": Throttled(
                quota=rate_limiter.per_sec(50),
                timeout=1,
            ),
            "account": Throttled(
                quota=rate_limiter.per_sec(50),
                timeout=1,
            ),
        }

    def __call__(self, rate_limit_type: str) -> Throttled:
        return self._throttled[rate_limit_type]


class BitgetRateLimiterSync(RateLimiterSync):
    def __init__(self):
        self._throttled: dict[str, ThrottledSync] = {
            "public": ThrottledSync(
                quota=rate_limiter_sync.per_duration(timedelta(seconds=5), limit=600),
                timeout=5,
            ),
            "trade": ThrottledSync(
                quota=rate_limiter_sync.per_sec(20),
                timeout=1,
            ),
            "position": ThrottledSync(
                quota=rate_limiter_sync.per_sec(50),
                timeout=1,
            ),
            "account": ThrottledSync(
                quota=rate_limiter_sync.per_sec(50),
                timeout=1,
            ),
        }

    def __call__(self, rate_limit_type: str) -> ThrottledSync:
        return self._throttled[rate_limit_type]
