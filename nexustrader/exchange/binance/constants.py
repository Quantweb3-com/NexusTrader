from enum import Enum
from datetime import timedelta
from nexustrader.constants import (
    KlineInterval,
    AccountType,
    OrderStatus,
    OrderType,
    PositionSide,
    OrderSide,
    TimeInForce,
    TriggerType,
    RateLimiter,
    RateLimiterSync,
)
from nexustrader.error import KlineSupportedError
from throttled.asyncio import Throttled, rate_limiter
from throttled import Throttled as ThrottledSync
from throttled import rate_limiter as rate_limiter_sync


class BinancePriceMatch(Enum):
    """
    NONE (No price match)
    OPPONENT (counterparty best price)
    OPPONENT_5 (the 5th best price from the counterparty)
    OPPONENT_10 (the 10th best price from the counterparty)
    OPPONENT_20 (the 20th best price from the counterparty)
    QUEUE (the best price on the same side of the order book)
    QUEUE_5 (the 5th best price on the same side of the order book)
    QUEUE_10 (the 10th best price on the same side of the order book)
    QUEUE_20 (the 20th best price on the same side of the order book)
    """

    NONE = "NONE"
    OPPONENT = "OPPONENT"
    OPPONENT_5 = "OPPONENT_5"
    OPPONENT_10 = "OPPONENT_10"
    OPPONENT_20 = "OPPONENT_20"
    QUEUE = "QUEUE"
    QUEUE_5 = "QUEUE_5"
    QUEUE_10 = "QUEUE_10"
    QUEUE_20 = "QUEUE_20"


class BinanceTriggerType(Enum):
    MARK_PRICE = "MARK_PRICE"
    CONTRACT_PRICE = "CONTRACT_PRICE"


class BinanceAccountEventReasonType(Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    ORDER = "ORDER"
    FUNDING_FEE = "FUNDING_FEE"
    WITHDRAW_REJECT = "WITHDRAW_REJECT"
    ADJUSTMENT = "ADJUSTMENT"
    INSURANCE_CLEAR = "INSURANCE_CLEAR"
    ADMIN_DEPOSIT = "ADMIN_DEPOSIT"
    ADMIN_WITHDRAW = "ADMIN_WITHDRAW"
    MARGIN_TRANSFER = "MARGIN_TRANSFER"
    MARGIN_TYPE_CHANGE = "MARGIN_TYPE_CHANGE"
    ASSET_TRANSFER = "ASSET_TRANSFER"
    OPTIONS_PREMIUM_FEE = "OPTIONS_PREMIUM_FEE"
    OPTIONS_SETTLE_PROFIT = "OPTIONS_SETTLE_PROFIT"
    AUTO_EXCHANGE = "AUTO_EXCHANGE"
    COIN_SWAP_DEPOSIT = "COIN_SWAP_DEPOSIT"
    COIN_SWAP_WITHDRAW = "COIN_SWAP_WITHDRAW"


class BinanceBusinessUnit(Enum):
    """
    Represents a Binance business unit.
    """

    UM = "UM"
    CM = "CM"


class BinanceFuturesWorkingType(Enum):
    """
    Represents a Binance Futures working type.
    """

    MARK_PRICE = "MARK_PRICE"
    CONTRACT_PRICE = "CONTRACT_PRICE"


class BinanceTimeInForce(Enum):
    """
    Represents a Binance order time in force.
    """

    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    GTX = "GTX"  # FUTURES only, Good-Till-Crossing (Post Only)
    GTD = "GTD"  # FUTURES only
    GTE_GTC = "GTE_GTC"  # Undocumented


class BinanceOrderSide(Enum):
    """
    Represents a Binance order side.
    """

    BUY = "BUY"
    SELL = "SELL"


class BinanceKlineInterval(Enum):
    """
    Represents a Binance kline chart interval.
    """

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


class BinanceWsEventType(Enum):
    TRADE = "trade"
    AGG_TRADE = "aggTrade"
    BOOK_TICKER = "bookTicker"
    KLINE = "kline"
    MARK_PRICE_UPDATE = "markPriceUpdate"
    DEPTH_UPDATE = "depthUpdate"


class BinanceUserDataStreamWsEventType(Enum):
    TRADE_LITE = "TRADE_LITE"
    MARGIN_CALL = "MARGIN_CALL"
    ACCOUNT_UPDATE = "ACCOUNT_UPDATE"
    ORDER_TRADE_UPDATE = "ORDER_TRADE_UPDATE"
    ACCOUNT_CONFIG_UPDATE = "ACCOUNT_CONFIG_UPDATE"
    STRATEGY_UPDATE = "STRATEGY_UPDATE"
    GRID_UPDATE = "GRID_UPDATE"
    CONDITIONAL_ORDER_TIGGER_REJECT = "CONDITIONAL_ORDER_TIGGER_REJECT"
    OUT_BOUND_ACCOUNT_POSITION = "outboundAccountPosition"
    BALANCE_UPDATE = "balanceUpdate"
    EXECUTION_REPORT = "executionReport"
    LISTING_STATUS = "listingStatus"
    LISTEN_KEY_EXPIRED = "listenKeyExpired"
    OPEN_ORDER_LOSS = "openOrderLoss"
    LIABILITY_CHANGE = "liabilityChange"
    RISK_LEVEL_CHANGE = "RISK_LEVEL_CHANGE"
    CONDITIONAL_ORDER_TRADE_UPDATE = "CONDITIONAL_ORDER_TRADE_UPDATE"


class BinanceOrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"

    STOP = "STOP"  # futures only
    TAKE_PROFIT = "TAKE_PROFIT"  # futures/spot in spot it is MARKET order in futures it is LIMIT order
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"  # futures only
    STOP_MARKET = "STOP_MARKET"  # futures only

    STOP_LOSS = "STOP_LOSS"  # spot only
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"  # spot only
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"  # spot only

    LIMIT_MAKER = "LIMIT_MAKER"  # spot only
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"

    @property
    def is_market(self):
        return self in (
            self.STOP_MARKET,
            self.TAKE_PROFIT_MARKET,
            self.STOP_LOSS,
            self.TAKE_PROFIT,
            self.MARKET,
        )

    @property
    def is_limit(self):
        return self in (
            self.TAKE_PROFIT_LIMIT,
            self.STOP_LOSS_LIMIT,
            self.STOP,
            self.TAKE_PROFIT,
            self.LIMIT,
        )


class BinanceExecutionType(Enum):
    NEW = "NEW"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    TRADE = "TRADE"
    EXPIRED = "EXPIRED"
    CALCULATED = "CALCULATED"
    TRADE_PREVENTION = "TRADE_PREVENTION"
    AMENDMENT = "AMENDMENT"


class BinanceOrderStatus(Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    EXPIRED_IN_MATCH = "EXPIRED_IN_MATCH"


class BinancePositionSide(Enum):
    BOTH = "BOTH"
    LONG = "LONG"
    SHORT = "SHORT"

    def parse_to_position_side(self) -> PositionSide:
        if self == self.BOTH:
            return PositionSide.FLAT
        elif self == self.LONG:
            return PositionSide.LONG
        elif self == self.SHORT:
            return PositionSide.SHORT
        raise RuntimeError(f"Invalid position side: {self}")


class BinanceAccountType(AccountType):
    SPOT = "SPOT"
    MARGIN = "MARGIN"
    ISOLATED_MARGIN = "ISOLATED_MARGIN"
    USD_M_FUTURE = "USD_M_FUTURE"
    COIN_M_FUTURE = "COIN_M_FUTURE"
    PORTFOLIO_MARGIN = "PORTFOLIO_MARGIN"
    SPOT_TESTNET = "SPOT_TESTNET"
    USD_M_FUTURE_TESTNET = "USD_M_FUTURE_TESTNET"
    COIN_M_FUTURE_TESTNET = "COIN_M_FUTURE_TESTNET"
    LINEAR_MOCK = "LINEAR_MOCK"  # for mock linear connector
    INVERSE_MOCK = "INVERSE_MOCK"  # for mock inverse connector
    SPOT_MOCK = "SPOT_MOCK"  # for mock spot connector

    @property
    def exchange_id(self):
        return "binance"

    @property
    def is_spot(self):
        return self in (self.SPOT, self.SPOT_TESTNET)

    @property
    def is_margin(self):
        return self in (self.MARGIN,)

    @property
    def is_isolated_margin(self):
        return self in (self.ISOLATED_MARGIN,)

    @property
    def is_isolated_margin_or_margin(self):
        return self in (self.MARGIN, self.ISOLATED_MARGIN)

    @property
    def is_spot_or_margin(self):
        return self in (self.SPOT, self.MARGIN, self.ISOLATED_MARGIN, self.SPOT_TESTNET)

    @property
    def is_future(self):
        return self in (
            self.USD_M_FUTURE,
            self.COIN_M_FUTURE,
            self.USD_M_FUTURE_TESTNET,
            self.COIN_M_FUTURE_TESTNET,
        )

    @property
    def is_linear(self):
        return self in (self.USD_M_FUTURE, self.USD_M_FUTURE_TESTNET)

    @property
    def is_inverse(self):
        return self in (self.COIN_M_FUTURE, self.COIN_M_FUTURE_TESTNET)

    @property
    def is_portfolio_margin(self):
        return self in (self.PORTFOLIO_MARGIN,)

    @property
    def is_testnet(self):
        return self in (
            self.SPOT_TESTNET,
            self.USD_M_FUTURE_TESTNET,
            self.COIN_M_FUTURE_TESTNET,
        )

    @property
    def base_url(self):
        return BASE_URLS[self]

    @property
    def ws_url(self):
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


class EndpointsType(Enum):
    USER_DATA_STREAM = "USER_DATA_STREAM"
    ACCOUNT = "ACCOUNT"
    TRADING = "TRADING"
    MARKET = "MARKET"
    GENERAL = "GENERAL"


BASE_URLS = {
    BinanceAccountType.SPOT: "https://api.binance.com",
    BinanceAccountType.MARGIN: "https://api.binance.com",
    BinanceAccountType.ISOLATED_MARGIN: "https://api.binance.com",
    BinanceAccountType.USD_M_FUTURE: "https://fapi.binance.com",
    BinanceAccountType.COIN_M_FUTURE: "https://dapi.binance.com",
    BinanceAccountType.PORTFOLIO_MARGIN: "https://papi.binance.com",
    BinanceAccountType.SPOT_TESTNET: "https://testnet.binance.vision",
    BinanceAccountType.USD_M_FUTURE_TESTNET: "https://testnet.binancefuture.com",
    BinanceAccountType.COIN_M_FUTURE_TESTNET: "https://testnet.binancefuture.com",
}

STREAM_URLS = {
    BinanceAccountType.SPOT: "wss://stream.binance.com:9443",
    BinanceAccountType.MARGIN: "wss://stream.binance.com:9443",
    BinanceAccountType.ISOLATED_MARGIN: "wss://stream.binance.com:9443",
    BinanceAccountType.USD_M_FUTURE: "wss://fstream.binance.com",
    BinanceAccountType.COIN_M_FUTURE: "wss://dstream.binance.com",
    BinanceAccountType.PORTFOLIO_MARGIN: "wss://fstream.binance.com/pm",
    BinanceAccountType.SPOT_TESTNET: "wss://testnet.binance.vision",
    BinanceAccountType.USD_M_FUTURE_TESTNET: "wss://stream.binancefuture.com",
    BinanceAccountType.COIN_M_FUTURE_TESTNET: "wss://dstream.binancefuture.com",
}

ENDPOINTS = {
    EndpointsType.USER_DATA_STREAM: {
        BinanceAccountType.SPOT: "/api/v3/userDataStream",
        BinanceAccountType.MARGIN: "/sapi/v1/userDataStream",
        BinanceAccountType.ISOLATED_MARGIN: "/sapi/v1/userDataStream/isolated",
        BinanceAccountType.USD_M_FUTURE: "/fapi/v1/listenKey",
        BinanceAccountType.COIN_M_FUTURE: "/dapi/v1/listenKey",
        BinanceAccountType.PORTFOLIO_MARGIN: "/papi/v1/listenKey",
        BinanceAccountType.SPOT_TESTNET: "/api/v3/userDataStream",
        BinanceAccountType.USD_M_FUTURE_TESTNET: "/fapi/v1/listenKey",
        BinanceAccountType.COIN_M_FUTURE_TESTNET: "/dapi/v1/listenKey",
    },
    EndpointsType.TRADING: {
        BinanceAccountType.SPOT: "/api/v3",
        BinanceAccountType.MARGIN: "/sapi/v1",
        BinanceAccountType.ISOLATED_MARGIN: "/sapi/v1",
        BinanceAccountType.USD_M_FUTURE: "/fapi/v1",
        BinanceAccountType.COIN_M_FUTURE: "/dapi/v1",
        BinanceAccountType.PORTFOLIO_MARGIN: "/papi/v1",
        BinanceAccountType.SPOT_TESTNET: "/api/v3",
        BinanceAccountType.USD_M_FUTURE_TESTNET: "/fapi/v1",
        BinanceAccountType.COIN_M_FUTURE_TESTNET: "/dapi/v1",
    },
}


class BinanceEnumParser:
    _binance_trigger_type_map = {
        BinanceTriggerType.MARK_PRICE: TriggerType.MARK_PRICE,
        BinanceTriggerType.CONTRACT_PRICE: TriggerType.LAST_PRICE,
    }

    _binance_kline_interval_map = {
        BinanceKlineInterval.SECOND_1: KlineInterval.SECOND_1,
        BinanceKlineInterval.MINUTE_1: KlineInterval.MINUTE_1,
        BinanceKlineInterval.MINUTE_3: KlineInterval.MINUTE_3,
        BinanceKlineInterval.MINUTE_5: KlineInterval.MINUTE_5,
        BinanceKlineInterval.MINUTE_15: KlineInterval.MINUTE_15,
        BinanceKlineInterval.MINUTE_30: KlineInterval.MINUTE_30,
        BinanceKlineInterval.HOUR_1: KlineInterval.HOUR_1,
        BinanceKlineInterval.HOUR_2: KlineInterval.HOUR_2,
        BinanceKlineInterval.HOUR_4: KlineInterval.HOUR_4,
        BinanceKlineInterval.HOUR_6: KlineInterval.HOUR_6,
        BinanceKlineInterval.HOUR_8: KlineInterval.HOUR_8,
        BinanceKlineInterval.HOUR_12: KlineInterval.HOUR_12,
        BinanceKlineInterval.DAY_1: KlineInterval.DAY_1,
        BinanceKlineInterval.DAY_3: KlineInterval.DAY_3,
        BinanceKlineInterval.WEEK_1: KlineInterval.WEEK_1,
        BinanceKlineInterval.MONTH_1: KlineInterval.MONTH_1,
    }

    _binance_order_status_map = {
        BinanceOrderStatus.NEW: OrderStatus.ACCEPTED,
        BinanceOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
        BinanceOrderStatus.FILLED: OrderStatus.FILLED,
        BinanceOrderStatus.CANCELED: OrderStatus.CANCELED,
        BinanceOrderStatus.EXPIRED: OrderStatus.EXPIRED,
        BinanceOrderStatus.EXPIRED_IN_MATCH: OrderStatus.EXPIRED,
    }

    _binance_position_side_map = {
        BinancePositionSide.LONG: PositionSide.LONG,
        BinancePositionSide.SHORT: PositionSide.SHORT,
        BinancePositionSide.BOTH: PositionSide.FLAT,
    }

    _binance_order_side_map = {
        BinanceOrderSide.BUY: OrderSide.BUY,
        BinanceOrderSide.SELL: OrderSide.SELL,
    }

    _binance_order_time_in_force_map = {
        BinanceTimeInForce.IOC: TimeInForce.IOC,
        BinanceTimeInForce.GTC: TimeInForce.GTC,
        BinanceTimeInForce.FOK: TimeInForce.FOK,
        BinanceTimeInForce.GTX: TimeInForce.GTC,  # FUTURES only
    }

    _binance_order_type_map = {
        BinanceOrderType.LIMIT: OrderType.LIMIT,
        BinanceOrderType.MARKET: OrderType.MARKET,
    }

    # ref1: https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api
    # ref2: https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/trade
    _binance_futures_order_type_map = {
        BinanceOrderType.LIMIT: OrderType.LIMIT,
        BinanceOrderType.MARKET: OrderType.MARKET,
        BinanceOrderType.STOP: OrderType.STOP_LOSS_LIMIT,
        BinanceOrderType.TAKE_PROFIT: OrderType.TAKE_PROFIT_LIMIT,
        BinanceOrderType.STOP_MARKET: OrderType.STOP_LOSS_MARKET,
        BinanceOrderType.TAKE_PROFIT_MARKET: OrderType.TAKE_PROFIT_MARKET,
    }

    # ref: https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/rest-api/trading-endpoints
    _binance_spot_order_type_map = {
        BinanceOrderType.LIMIT: OrderType.LIMIT,
        BinanceOrderType.MARKET: OrderType.MARKET,
        BinanceOrderType.STOP_LOSS: OrderType.STOP_LOSS_MARKET,
        BinanceOrderType.STOP_LOSS_LIMIT: OrderType.STOP_LOSS_LIMIT,
        BinanceOrderType.TAKE_PROFIT: OrderType.TAKE_PROFIT_MARKET,
        BinanceOrderType.TAKE_PROFIT_LIMIT: OrderType.TAKE_PROFIT_LIMIT,
        BinanceOrderType.LIMIT_MAKER: OrderType.POST_ONLY,
    }

    _order_status_to_binance_map = {v: k for k, v in _binance_order_status_map.items()}
    _order_status_to_binance_map[OrderStatus.EXPIRED] = BinanceOrderStatus.EXPIRED
    _position_side_to_binance_map = {
        v: k for k, v in _binance_position_side_map.items()
    }
    _order_side_to_binance_map = {v: k for k, v in _binance_order_side_map.items()}
    _time_in_force_to_binance_map = {
        v: k for k, v in _binance_order_time_in_force_map.items()
    }
    _time_in_force_to_binance_map[TimeInForce.GTC] = BinanceTimeInForce.GTC
    _order_type_to_binance_map = {v: k for k, v in _binance_order_type_map.items()}
    _kline_interval_to_binance_map = {
        v: k for k, v in _binance_kline_interval_map.items()
    }

    _futures_order_type_to_binance_map = {
        v: k for k, v in _binance_futures_order_type_map.items()
    }
    _spot_order_type_to_binance_map = {
        v: k for k, v in _binance_spot_order_type_map.items()
    }
    _trigger_type_to_binance_map = {v: k for k, v in _binance_trigger_type_map.items()}

    @classmethod
    def parse_kline_interval(cls, interval: BinanceKlineInterval) -> KlineInterval:
        return cls._binance_kline_interval_map[interval]

    @classmethod
    def parse_order_status(cls, status: BinanceOrderStatus) -> OrderStatus:
        return cls._binance_order_status_map[status]

    @classmethod
    def parse_futures_order_type(
        cls,
        order_type: BinanceOrderType,
        time_in_force: BinanceTimeInForce | None = None,
    ) -> OrderType:
        if time_in_force == BinanceTimeInForce.GTX:
            # GTX is a special case for futures, it is a post-only order
            return OrderType.POST_ONLY
        return cls._binance_futures_order_type_map[order_type]

    @classmethod
    def parse_spot_order_type(cls, order_type: BinanceOrderType) -> OrderType:
        return cls._binance_spot_order_type_map[order_type]

    @classmethod
    def parse_trigger_type(cls, trigger_type: BinanceTriggerType) -> TriggerType:
        return cls._binance_trigger_type_map[trigger_type]

    @classmethod
    def parse_position_side(cls, side: BinancePositionSide) -> PositionSide:
        return cls._binance_position_side_map[side]

    @classmethod
    def parse_order_side(cls, side: BinanceOrderSide) -> OrderSide:
        return cls._binance_order_side_map[side]

    @classmethod
    def parse_time_in_force(cls, tif: BinanceTimeInForce) -> TimeInForce:
        return cls._binance_order_time_in_force_map[tif]

    @classmethod
    def parse_order_type(cls, order_type: BinanceOrderType) -> OrderType:
        return cls._binance_order_type_map[order_type]

    @classmethod
    def to_binance_order_status(cls, status: OrderStatus) -> BinanceOrderStatus:
        return cls._order_status_to_binance_map[status]

    @classmethod
    def to_binance_position_side(cls, side: PositionSide) -> BinancePositionSide:
        return cls._position_side_to_binance_map[side]

    @classmethod
    def to_binance_order_side(cls, side: OrderSide) -> BinanceOrderSide:
        return cls._order_side_to_binance_map[side]

    @classmethod
    def to_binance_time_in_force(cls, tif: TimeInForce) -> BinanceTimeInForce:
        return cls._time_in_force_to_binance_map[tif]

    @classmethod
    def to_binance_order_type(cls, order_type: OrderType) -> BinanceOrderType:
        return cls._order_type_to_binance_map[order_type]

    @classmethod
    def to_binance_futures_order_type(cls, order_type: OrderType) -> BinanceOrderType:
        return cls._futures_order_type_to_binance_map[order_type]

    @classmethod
    def to_binance_spot_order_type(cls, order_type: OrderType) -> BinanceOrderType:
        return cls._spot_order_type_to_binance_map[order_type]

    @classmethod
    def to_binance_trigger_type(cls, trigger_type: TriggerType) -> BinanceTriggerType:
        return cls._trigger_type_to_binance_map[trigger_type]

    @classmethod
    def to_binance_kline_interval(cls, interval: KlineInterval) -> BinanceKlineInterval:
        if interval not in cls._kline_interval_to_binance_map:
            raise KlineSupportedError(
                f"Kline interval {interval} is not supported by Binance"
            )
        return cls._kline_interval_to_binance_map[interval]


class BinanceRateLimitType(Enum):
    ORDERS = "ORDERS"
    REQUEST_WEIGHT = "REQUEST_WEIGHT"


class BinanceRateLimiter(RateLimiter):
    def __init__(self, enable_rate_limit: bool = True):
        self._throttled: dict[
            BinanceAccountType, dict[BinanceRateLimitType, Throttled]
        ] = {
            BinanceAccountType.SPOT: {
                BinanceRateLimitType.ORDERS: Throttled(
                    quota=rate_limiter.per_duration(timedelta(seconds=10), limit=50),
                    timeout=10 if enable_rate_limit else -1,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: Throttled(
                    quota=rate_limiter.per_min(6000),
                    timeout=60 if enable_rate_limit else -1,
                ),
            },
            BinanceAccountType.USD_M_FUTURE: {
                BinanceRateLimitType.ORDERS: Throttled(
                    quota=rate_limiter.per_duration(timedelta(seconds=10), limit=300),
                    timeout=10 if enable_rate_limit else -1,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: Throttled(
                    quota=rate_limiter.per_min(6000),
                    timeout=60 if enable_rate_limit else -1,
                ),
            },
            BinanceAccountType.COIN_M_FUTURE: {
                BinanceRateLimitType.ORDERS: Throttled(
                    quota=rate_limiter.per_min(6000),
                    timeout=60 if enable_rate_limit else -1,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: Throttled(
                    quota=rate_limiter.per_min(6000),
                    timeout=60 if enable_rate_limit else -1,
                ),
            },
            BinanceAccountType.PORTFOLIO_MARGIN: {
                BinanceRateLimitType.ORDERS: Throttled(
                    quota=rate_limiter.per_min(1200),
                    timeout=60 if enable_rate_limit else -1,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: Throttled(
                    quota=rate_limiter.per_min(6000),
                    timeout=60 if enable_rate_limit else -1,
                ),
            },
        }

    def __call__(
        self, account_type: BinanceAccountType, rate_limit_type: BinanceRateLimitType
    ) -> Throttled:
        return self._throttled[account_type][rate_limit_type]


class BinanceRateLimiterSync(RateLimiterSync):
    def __init__(self, enable_rate_limit: bool = True):
        self._throttled: dict[
            BinanceAccountType, dict[BinanceRateLimitType, ThrottledSync]
        ] = {
            BinanceAccountType.SPOT: {
                BinanceRateLimitType.ORDERS: ThrottledSync(
                    quota=rate_limiter_sync.per_duration(
                        timedelta(seconds=10), limit=50
                    ),
                    timeout=10 if enable_rate_limit else -1,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: ThrottledSync(
                    quota=rate_limiter_sync.per_min(6000),
                    timeout=60 if enable_rate_limit else -1,
                ),
            },
            BinanceAccountType.USD_M_FUTURE: {
                BinanceRateLimitType.ORDERS: ThrottledSync(
                    quota=rate_limiter_sync.per_duration(
                        timedelta(seconds=10), limit=300
                    ),
                    timeout=10 if enable_rate_limit else -1,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: ThrottledSync(
                    quota=rate_limiter_sync.per_min(6000),
                    timeout=60 if enable_rate_limit else -1,
                ),
            },
            BinanceAccountType.COIN_M_FUTURE: {
                BinanceRateLimitType.ORDERS: ThrottledSync(
                    quota=rate_limiter_sync.per_min(6000),
                    timeout=60 if enable_rate_limit else -1,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: ThrottledSync(
                    quota=rate_limiter_sync.per_min(6000),
                    timeout=60 if enable_rate_limit else -1,
                ),
            },
            BinanceAccountType.PORTFOLIO_MARGIN: {
                BinanceRateLimitType.ORDERS: ThrottledSync(
                    quota=rate_limiter_sync.per_min(1200),
                    timeout=60 if enable_rate_limit else -1,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: ThrottledSync(
                    quota=rate_limiter_sync.per_min(6000),
                    timeout=60 if enable_rate_limit else -1,
                ),
            },
        }

    def __call__(
        self, account_type: BinanceAccountType, rate_limit_type: BinanceRateLimitType
    ) -> ThrottledSync:
        return self._throttled[account_type][rate_limit_type]
