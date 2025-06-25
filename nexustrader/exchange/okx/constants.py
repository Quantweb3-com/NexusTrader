from enum import Enum, unique
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
from nexustrader.error import KlineSupportedError


class OkxAcctLv(Enum):
    SPOT = "1"
    FUTURES = "2"
    MULTI_CURRENCY_MARGIN = "3"
    PORTFOLIO_MARGIN = "4"

    @property
    def is_spot(self):
        return self == self.SPOT

    @property
    def is_futures(self):
        return self == self.FUTURES

    @property
    def is_multi_currency_margin(self):
        return self == self.MULTI_CURRENCY_MARGIN

    @property
    def is_portfolio_margin(self):
        return self == self.PORTFOLIO_MARGIN


class OkxPositionMode(Enum):
    ONE_WAY_MODE = "net_mode"
    LONG_SHORT_MODE = "long_short_mode"

    @property
    def is_one_way_mode(self):
        return self == self.ONE_WAY_MODE

    @property
    def is_long_short_mode(self):
        return self == self.LONG_SHORT_MODE


class OkxSavingsPurchaseRedemptSide(Enum):
    PURCHASE = "purchase"
    REDEMPT = "redempt"


class OkxKlineInterval(Enum):
    SECOND_1 = "candle1s"
    MINUTE_1 = "candle1m"
    MINUTE_3 = "candle3m"
    MINUTE_5 = "candle5m"
    MINUTE_15 = "candle15m"
    MINUTE_30 = "candle30m"
    HOUR_1 = "candle1H"
    HOUR_4 = "candle4H"
    HOUR_6 = "candle6Hutc"
    HOUR_12 = "candle12Hutc"
    DAY_1 = "candle1Dutc"
    DAY_3 = "candle3Dutc"
    WEEK_1 = "candle1Wutc"
    MONTH_1 = "candle1Mutc"


class OkxInstrumentType(Enum):
    SPOT = "SPOT"
    MARGIN = "MARGIN"
    SWAP = "SWAP"
    FUTURES = "FUTURES"
    OPTION = "OPTION"
    ANY = "ANY"


class OkxInstrumentFamily(Enum):
    FUTURES = "FUTURES"
    SWAP = "SWAP"
    OPTION = "OPTION"


class OkxAccountType(AccountType):
    LIVE = "live"
    AWS = "aws"
    DEMO = "demo"
    LINEAR_MOCK = "linear_mock"
    INVERSE_MOCK = "inverse_mock"
    SPOT_MOCK = "spot_mock"

    @property
    def exchange_id(self):
        return "okx"

    @property
    def is_testnet(self):
        return self == OkxAccountType.DEMO

    @property
    def stream_url(self):
        return STREAM_URLS[self]

    @property
    def is_mock(self):
        return self in (self.LINEAR_MOCK, self.INVERSE_MOCK, self.SPOT_MOCK)

    @property
    def is_linear_mock(self):
        return self == self.LINEAR_MOCK

    @property
    def is_inverse_mock(self):
        return self == self.INVERSE_MOCK

    @property
    def is_spot_mock(self):
        return self == self.SPOT_MOCK


class OkxRestUrl(Enum):
    LIVE = "https://www.okx.com"
    AWS = "https://aws.okx.com"
    DEMO = "https://www.okx.com"


STREAM_URLS = {
    OkxAccountType.LIVE: "wss://ws.okx.com:8443/ws",
    OkxAccountType.AWS: "wss://wsaws.okx.com:8443/ws",
    OkxAccountType.DEMO: "wss://wspap.okx.com:8443/ws",
}

REST_URLS = {
    OkxAccountType.LIVE: "https://www.okx.com",
    OkxAccountType.AWS: "https://aws.okx.com",
    OkxAccountType.DEMO: "https://www.okx.com",
}


@unique
class OkxTdMode(Enum):
    CASH = "cash"  # 现货
    CROSS = "cross"  # 全仓
    ISOLATED = "isolated"  # 逐仓
    SPOT_ISOLATED = "spot_isolated"  # 现货逐仓

    @property
    def is_cash(self):
        return self == self.CASH

    @property
    def is_cross(self):
        return self == self.CROSS

    @property
    def is_isolated(self):
        return self == self.ISOLATED

    @property
    def is_spot_isolated(self):
        return self == self.SPOT_ISOLATED


@unique
class OkxPositionSide(Enum):
    LONG = "long"
    SHORT = "short"
    NET = "net"
    NONE = ""

    def parse_to_position_side(self) -> PositionSide:
        if self == self.NET:
            return PositionSide.FLAT
        elif self == self.LONG:
            return PositionSide.LONG
        elif self == self.SHORT:
            return PositionSide.SHORT
        raise RuntimeError(f"Invalid position side: {self}")


@unique
class OkxOrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OkxTimeInForce(Enum):
    IOC = "ioc"
    GTC = "gtc"
    FOK = "fok"


@unique
class OkxOrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    POST_ONLY = "post_only"  # limit only, requires "px" to be provided
    FOK = "fok"  # market order if "px" is not provided, otherwise limit order
    IOC = "ioc"  # market order if "px" is not provided, otherwise limit order
    OPTIMAL_LIMIT_IOC = (
        "optimal_limit_ioc"  # Market order with immediate-or-cancel order
    )
    MMP = "mmp"  # Market Maker Protection (only applicable to Option in Portfolio Margin mode)
    MMP_AND_POST_ONLY = "mmp_and_post_only"  # Market Maker Protection and Post-only order(only applicable to Option in Portfolio Margin mode)


@unique
class OkxOrderStatus(Enum):  # "state"
    CANCELED = "canceled"
    LIVE = "live"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    MMP_CANCELED = "mmp_canceled"


class OkxEnumParser:
    _okx_kline_interval_map = {
        OkxKlineInterval.SECOND_1: KlineInterval.SECOND_1,
        OkxKlineInterval.MINUTE_1: KlineInterval.MINUTE_1,
        OkxKlineInterval.MINUTE_3: KlineInterval.MINUTE_3,
        OkxKlineInterval.MINUTE_5: KlineInterval.MINUTE_5,
        OkxKlineInterval.MINUTE_15: KlineInterval.MINUTE_15,
        OkxKlineInterval.MINUTE_30: KlineInterval.MINUTE_30,
        OkxKlineInterval.HOUR_1: KlineInterval.HOUR_1,
        OkxKlineInterval.HOUR_4: KlineInterval.HOUR_4,
        OkxKlineInterval.HOUR_6: KlineInterval.HOUR_6,
        OkxKlineInterval.HOUR_12: KlineInterval.HOUR_12,
        OkxKlineInterval.DAY_1: KlineInterval.DAY_1,
        OkxKlineInterval.DAY_3: KlineInterval.DAY_3,
        OkxKlineInterval.WEEK_1: KlineInterval.WEEK_1,
        OkxKlineInterval.MONTH_1: KlineInterval.MONTH_1,
    }

    _okx_order_status_map = {
        OkxOrderStatus.LIVE: OrderStatus.ACCEPTED,
        OkxOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
        OkxOrderStatus.FILLED: OrderStatus.FILLED,
        OkxOrderStatus.CANCELED: OrderStatus.CANCELED,
    }

    _okx_position_side_map = {
        OkxPositionSide.NET: PositionSide.FLAT,
        OkxPositionSide.LONG: PositionSide.LONG,
        OkxPositionSide.SHORT: PositionSide.SHORT,
        OkxPositionSide.NONE: None,
    }

    _okx_order_side_map = {
        OkxOrderSide.BUY: OrderSide.BUY,
        OkxOrderSide.SELL: OrderSide.SELL,
    }

    # Add reverse mapping dictionaries
    _order_status_to_okx_map = {v: k for k, v in _okx_order_status_map.items()}
    _position_side_to_okx_map = {
        PositionSide.FLAT: OkxPositionSide.NET,
        PositionSide.LONG: OkxPositionSide.LONG,
        PositionSide.SHORT: OkxPositionSide.SHORT,
    }
    _order_side_to_okx_map = {v: k for k, v in _okx_order_side_map.items()}

    _kline_interval_to_okx_map = {v: k for k, v in _okx_kline_interval_map.items()}

    @classmethod
    def parse_kline_interval(cls, interval: OkxKlineInterval) -> KlineInterval:
        return cls._okx_kline_interval_map[interval]

    # Add reverse parsing methods
    @classmethod
    def parse_order_status(cls, status: OkxOrderStatus) -> OrderStatus:
        return cls._okx_order_status_map[status]

    @classmethod
    def parse_position_side(cls, side: OkxPositionSide) -> PositionSide:
        return cls._okx_position_side_map[side]

    @classmethod
    def parse_order_side(cls, side: OkxOrderSide) -> OrderSide:
        return cls._okx_order_side_map[side]

    @classmethod
    def parse_order_type(cls, ordType: OkxOrderType) -> OrderType:
        # TODO add parameters in future to enable parsing of all other nautilus OrderType's
        match ordType:
            case OkxOrderType.MARKET:
                return OrderType.MARKET
            case OkxOrderType.LIMIT:
                return OrderType.LIMIT
            case OkxOrderType.IOC:
                return OrderType.LIMIT
            case OkxOrderType.FOK:
                return OrderType.LIMIT
            case OkxOrderType.POST_ONLY:
                return OrderType.LIMIT
            case _:
                raise NotImplementedError(
                    f"Cannot parse OrderType from OKX order type {ordType}"
                )

    @classmethod
    def parse_time_in_force(cls, ordType: OkxOrderType) -> TimeInForce:
        match ordType:
            case OkxOrderType.MARKET:
                return TimeInForce.GTC
            case OkxOrderType.LIMIT:
                return TimeInForce.GTC
            case OkxOrderType.POST_ONLY:
                return TimeInForce.GTC
            case OkxOrderType.FOK:
                return TimeInForce.FOK
            case OkxOrderType.IOC:
                return TimeInForce.IOC
            case _:
                raise NotImplementedError(
                    f"Cannot parse TimeInForce from OKX order type {ordType}"
                )

    @classmethod
    def to_okx_order_status(cls, status: OrderStatus) -> OkxOrderStatus:
        return cls._order_status_to_okx_map[status]

    @classmethod
    def to_okx_position_side(cls, side: PositionSide) -> OkxPositionSide:
        return cls._position_side_to_okx_map[side]

    @classmethod
    def to_okx_order_side(cls, side: OrderSide) -> OkxOrderSide:
        return cls._order_side_to_okx_map[side]

    @classmethod
    def to_okx_order_type(
        cls, order_type: OrderType, time_in_force: TimeInForce
    ) -> OkxOrderType:
        if order_type == OrderType.MARKET:
            return OkxOrderType.MARKET

        match time_in_force:
            case TimeInForce.GTC:
                return OkxOrderType.LIMIT  # OKX limit orders are GTC by default
            case TimeInForce.FOK:
                return OkxOrderType.FOK
            case TimeInForce.IOC:
                return OkxOrderType.IOC
            case _:
                raise RuntimeError(
                    f"Could not determine OKX order type from order_type {order_type} and time_in_force {time_in_force}, valid OKX order types are: {list(OkxOrderType)}",
                )

    @classmethod
    def to_okx_kline_interval(cls, interval: KlineInterval) -> OkxKlineInterval:
        if interval not in cls._kline_interval_to_okx_map:
            raise KlineSupportedError(
                f"Kline interval {interval} is not supported by OKX"
            )
        return cls._kline_interval_to_okx_map[interval]


class OkxRateLimiter(RateLimiter):
    def __init__(self):
        self._throttled: dict[str, Throttled] = {
            "/api/v5/account/balance": Throttled(
                quota=rate_limiter.per_sec(5),
                timeout=1,
            ),
            "/api/v5/account/positions": Throttled(
                quota=rate_limiter.per_sec(5),
                timeout=1,
            ),
            "/api/v5/trade/order": Throttled(
                quota=rate_limiter.per_sec(30),
                timeout=1,
            ),
            "/api/v5/trade/cancel-order": Throttled(
                quota=rate_limiter.per_sec(30),
                timeout=1,
            ),
            "/api/v5/market/candles": Throttled(
                quota=rate_limiter.per_sec(20),
                timeout=1,
            ),
            "/api/v5/market/history-candles": Throttled(
                quota=rate_limiter.per_sec(10),
                timeout=1,
            ),
            "/api/v5/trade/amend-order": Throttled(
                quota=rate_limiter.per_sec(30),
                timeout=1,
            ),
            "/api/v5/account/config": Throttled(
                quota=rate_limiter.per_sec(2),
                timeout=1,
            ),
            "/api/v5/market/history-index-candles": Throttled(
                quota=rate_limiter.per_sec(4),
                timeout=1,
            ),
            "/api/v5/trade/batch-orders": Throttled(
                quota=rate_limiter.per_sec(150),
                timeout=1,
            ),
        }

    def __call__(self, endpoint: str) -> Throttled:
        return self._throttled[endpoint]


class OkxRateLimiterSync(RateLimiterSync):
    def __init__(self):
        self._throttled: dict[str, ThrottledSync] = {
            "/api/v5/account/balance": ThrottledSync(
                quota=rate_limiter_sync.per_sec(5),
                timeout=1,
            ),
            "/api/v5/account/positions": ThrottledSync(
                quota=rate_limiter_sync.per_sec(5),
                timeout=1,
            ),
            "/api/v5/trade/order": ThrottledSync(
                quota=rate_limiter_sync.per_sec(30),
                timeout=1,
            ),
            "/api/v5/trade/cancel-order": ThrottledSync(
                quota=rate_limiter_sync.per_sec(30),
                timeout=1,
            ),
            "/api/v5/market/candles": ThrottledSync(
                quota=rate_limiter_sync.per_sec(20),
                timeout=1,
            ),
            "/api/v5/market/history-candles": ThrottledSync(
                quota=rate_limiter_sync.per_sec(10),
                timeout=1,
            ),
            "/api/v5/trade/amend-order": ThrottledSync(
                quota=rate_limiter_sync.per_sec(30),
                timeout=1,
            ),
            "/api/v5/account/config": ThrottledSync(
                quota=rate_limiter_sync.per_sec(2),
                timeout=1,
            ),
            "/api/v5/market/history-index-candles": ThrottledSync(
                quota=rate_limiter_sync.per_sec(4),
                timeout=1,
            ),
            "/api/v5/trade/batch-orders": ThrottledSync(
                quota=rate_limiter_sync.per_sec(150),
                timeout=1,
            ),
        }

    def __call__(self, endpoint: str) -> ThrottledSync:
        return self._throttled[endpoint]
