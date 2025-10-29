from enum import Enum
from nexustrader.constants import AccountType
from throttled.asyncio import Throttled, rate_limiter, RateLimiterType
from throttled import Throttled as ThrottledSync
from throttled import rate_limiter as rate_limiter_sync

from nexustrader.constants import (
    OrderStatus,
    PositionSide,
    OrderSide,
    TimeInForce,
    OrderType,
    KlineInterval,
    RateLimiter,
    RateLimiterSync,
)
from nexustrader.error import KlineSupportedError


class BitgetAccountType(AccountType):
    UTA = "UTA"
    SPOT = "SPOT"
    FUTURE = "FUTURE"
    UTA_DEMO = "UTA_DEMO"
    SPOT_DEMO = "SPOT_DEMO"
    FUTURE_DEMO = "FUTURE_DEMO"
    SPOT_MOCK = "SPOT_MOCK"
    LINEAR_MOCK = "LINEAR_MOCK"
    INVERSE_MOCK = "INVERSE_MOCK"

    @property
    def exchange_id(self):
        return "bitget"

    @property
    def is_testnet(self):
        return self in (
            self.UTA_DEMO,
            self.SPOT_DEMO,
            self.FUTURE_DEMO,
        )

    @property
    def stream_url(self):
        version = "v3" if self.is_uta else "v2"
        if self.is_testnet:
            return f"wss://wspap.bitget.com/{version}/ws"
        else:
            return f"wss://ws.bitget.com/{version}/ws"

    @property
    def is_spot(self):
        return self in (self.SPOT, self.SPOT_DEMO, self.SPOT_MOCK)

    @property
    def is_future(self):
        return self in (
            self.FUTURE,
            self.FUTURE_DEMO,
            self.LINEAR_MOCK,
            self.INVERSE_MOCK,
        )

    @property
    def is_uta(self):
        return self in (self.UTA, self.UTA_DEMO)

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
    USDC_FUTURES = "USDC-FUTURES"
    # SUSDT_FUTURES = "SUSD-FUTURES" # deprecated
    # SUSDC_FUTURES = "SUSDC-FUTURES" # deprecated
    # SCOIN_FUTURES = "SCOIN-FUTURES" # deprecated

    @property
    def is_spot(self) -> bool:
        return self == BitgetInstType.SPOT

    @property
    def is_swap(self) -> bool:
        return not self.is_spot

    @property
    def is_linear(self) -> bool:
        return self in (BitgetInstType.USDT_FUTURES, BitgetInstType.USDC_FUTURES)

    @property
    def is_inverse(self) -> bool:
        return self == BitgetInstType.COIN_FUTURES

    @property
    def is_usdc_swap(self) -> bool:
        return self == BitgetInstType.USDC_FUTURES

    @property
    def is_usdt_swap(self) -> bool:
        return self == BitgetInstType.USDT_FUTURES


class BitgetUtaInstType(Enum):
    SPOT = "spot"
    USDT_FUTURES = "usdt-futures"
    COIN_FUTURES = "coin-futures"
    USDC_FUTURES = "usdc-futures"
    UTA = "UTA"

    @property
    def is_spot(self) -> bool:
        return self == BitgetInstType.SPOT

    @property
    def is_swap(self) -> bool:
        return not self.is_spot

    @property
    def is_linear(self) -> bool:
        return self in (BitgetInstType.USDT_FUTURES, BitgetInstType.USDC_FUTURES)

    @property
    def is_inverse(self) -> bool:
        return self == BitgetInstType.COIN_FUTURES

    @property
    def is_usdc_swap(self) -> bool:
        return self == BitgetInstType.USDC_FUTURES

    @property
    def is_usdt_swap(self) -> bool:
        return self == BitgetInstType.USDT_FUTURES


class BitgetKlineInterval(Enum):
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1H"
    HOUR_4 = "4H"
    HOUR_6 = "6H"
    HOUR_12 = "12H"
    DAY_1 = "1D"


class BitgetOrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class BitgetOrderStatus(Enum):
    LIVE = "live"
    NEW = "new"
    FILLED = "filled"
    CANCELED = "canceled"
    CANCELLED = "cancelled"  # Alias pointing to the same value
    PARTIALLY_FILLED = "partially_filled"


class BitgetTimeInForce(Enum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    POST_ONLY = "post_only"

    @property
    def is_gtc(self) -> bool:
        return self == BitgetTimeInForce.GTC

    @property
    def is_ioc(self) -> bool:
        return self == BitgetTimeInForce.IOC

    @property
    def is_fok(self) -> bool:
        return self == BitgetTimeInForce.FOK

    @property
    def is_post_only(self) -> bool:
        return self == BitgetTimeInForce.POST_ONLY


class BitgetOrderType(Enum):
    LIMIT = "limit"
    MARKET = "market"

    @property
    def is_limit(self) -> bool:
        return self == BitgetOrderType.LIMIT

    @property
    def is_market(self) -> bool:
        return self == BitgetOrderType.MARKET


class BitgetPositionSide(Enum):
    LONG = "long"
    SHORT = "short"
    NET = "net"  # one-way mode position

    @property
    def is_long(self) -> bool:
        return self == BitgetPositionSide.LONG

    @property
    def is_short(self) -> bool:
        return self == BitgetPositionSide.SHORT

    @property
    def is_net(self) -> bool:
        return self == BitgetPositionSide.NET

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
        BitgetOrderStatus.LIVE: OrderStatus.ACCEPTED,
        BitgetOrderStatus.FILLED: OrderStatus.FILLED,
        BitgetOrderStatus.CANCELED: OrderStatus.CANCELED,
        BitgetOrderStatus.CANCELLED: OrderStatus.CANCELED,  # Alias pointing to the same value
        BitgetOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
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

    _kline_interval_to_bitget_map = {v: k for k, v in _kline_interval_map.items()}
    _order_side_to_bitget_map = {v: k for k, v in _order_side_map.items()}
    _time_in_force_to_bitget_map = {v: k for k, v in _time_in_force_map.items()}

    @classmethod
    def parse_kline_interval(cls, interval: BitgetKlineInterval) -> KlineInterval:
        return cls._kline_interval_map[interval]

    @classmethod
    def to_bitget_kline_interval(cls, interval: KlineInterval) -> BitgetKlineInterval:
        interval = cls._kline_interval_to_bitget_map.get(interval)
        if not interval:
            raise KlineSupportedError(
                f"Unsupported KlineInterval: {interval}. Supported intervals: {list(cls._kline_interval_to_bitget_map.keys())}"
            )
        return interval

    @classmethod
    def parse_order_status(cls, status: BitgetOrderStatus) -> OrderStatus:
        # we do not care the UTA account NEW order status, so we ignore it
        # ref: https://www.bitget.com/zh-CN/api-doc/uta/websocket/private/Order-Channel
        return cls._order_status_map.get(status, None)

    @classmethod
    def parse_order_side(cls, side: BitgetOrderSide) -> OrderSide:
        return cls._order_side_map[side]

    @classmethod
    def to_bitget_order_side(cls, side: OrderSide) -> BitgetOrderSide:
        return cls._order_side_to_bitget_map[side]

    @classmethod
    def parse_time_in_force(cls, tif: BitgetTimeInForce) -> TimeInForce:
        return cls._time_in_force_map[tif]

    @classmethod
    def to_bitget_time_in_force(cls, tif: TimeInForce) -> BitgetTimeInForce:
        return cls._time_in_force_to_bitget_map[tif]

    @classmethod
    def parse_order_type(cls, order_type: BitgetOrderType) -> OrderType:
        return cls._order_type_map[order_type]


class BitgetRateLimiter(RateLimiter):
    def __init__(self, enable_rate_limit: bool = True):
        self._throttled: dict[str, Throttled] = {
            "/api/v2/mix/order/place-order": Throttled(
                quota=rate_limiter.per_sec(10),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
            "/api/v2/spot/trade/place-order": Throttled(
                quota=rate_limiter.per_sec(10),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
            "/api/v2/mix/order/cancel-order": Throttled(
                quota=rate_limiter.per_sec(10),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
            "/api/v2/spot/trade/cancel-order": Throttled(
                quota=rate_limiter.per_sec(10),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
            "/api/v3/trade/place-order": Throttled(
                quota=rate_limiter.per_sec(10),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
            "/api/v3/trade/cancel-order": Throttled(
                quota=rate_limiter.per_sec(10),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
            "/api/v3/trade/cancel-symbol-order": Throttled(
                quota=rate_limiter.per_sec(5),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
        }

    def __call__(self, rate_limit_type: str) -> Throttled:
        return self._throttled[rate_limit_type]


class BitgetRateLimiterSync(RateLimiterSync):
    def __init__(self, enable_rate_limit: bool = True):
        self._throttled: dict[str, ThrottledSync] = {
            "/api/v2/mix/order/place-order": ThrottledSync(
                quota=rate_limiter_sync.per_sec(10),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
            "/api/v2/spot/trade/place-order": ThrottledSync(
                quota=rate_limiter_sync.per_sec(10),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
            "/api/v2/mix/position/all-position": ThrottledSync(
                quota=rate_limiter_sync.per_sec(10),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
            "/api/v3/market/tickers": ThrottledSync(
                quota=rate_limiter_sync.per_sec(20),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
            "/api/v3/position/current-position": ThrottledSync(
                quota=rate_limiter_sync.per_sec(20),
                timeout=60 if enable_rate_limit else -1,
                using=RateLimiterType.GCRA.value,
            ),
        }

    def __call__(self, rate_limit_type: str) -> ThrottledSync:
        return self._throttled[rate_limit_type]
