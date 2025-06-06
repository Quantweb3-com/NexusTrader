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


class BinanceErrorCode(Enum):
    """
    Represents a Binance error code (covers futures).
    """

    UNKNOWN = -1000
    DISCONNECTED = -1001
    UNAUTHORIZED = -1002
    TOO_MANY_REQUESTS = -1003
    DUPLICATE_IP = -1004
    NO_SUCH_IP = -1005
    UNEXPECTED_RESP = -1006
    TIMEOUT = -1007
    SERVER_BUSY = -1008
    ERROR_MSG_RECEIVED = -1010
    NON_WHITE_LIST = -1011
    INVALID_MESSAGE = -1013
    UNKNOWN_ORDER_COMPOSITION = -1014
    TOO_MANY_ORDERS = -1015
    SERVICE_SHUTTING_DOWN = -1016
    UNSUPPORTED_OPERATION = -1020
    INVALID_TIMESTAMP = -1021
    INVALID_SIGNATURE = -1022
    START_TIME_GREATER_THAN_END_TIME = -1023
    NOT_FOUND = -1099
    ILLEGAL_CHARS = -1100
    TOO_MANY_PARAMETERS = -1101
    MANDATORY_PARAM_EMPTY_OR_MALFORMED = -1102
    UNKNOWN_PARAM = -1103
    UNREAD_PARAMETERS = -1104
    PARAM_EMPTY = -1105
    PARAM_NOT_REQUIRED = -1106
    BAD_ASSET = -1108
    BAD_ACCOUNT = -1109
    BAD_INSTRUMENT_TYPE = -1110
    BAD_PRECISION = -1111
    NO_DEPTH = -1112
    WITHDRAW_NOT_NEGATIVE = -1113
    TIF_NOT_REQUIRED = -1114
    INVALID_TIF = -1115
    INVALID_ORDER_TYPE = -1116
    INVALID_SIDE = -1117
    EMPTY_NEW_CL_ORD_ID = -1118
    EMPTY_ORG_CL_ORD_ID = -1119
    BAD_INTERVAL = -1120
    BAD_SYMBOL = -1121
    INVALID_SYMBOL_STATUS = -1122
    INVALID_LISTEN_KEY = -1125
    ASSET_NOT_SUPPORTED = -1126
    MORE_THAN_XX_HOURS = -1127
    OPTIONAL_PARAMS_BAD_COMBO = -1128
    INVALID_PARAMETER = -1130
    INVALID_NEW_ORDER_RESP_TYPE = -1136

    INVALID_CALLBACK_RATE = -2007
    NEW_ORDER_REJECTED = -2010
    CANCEL_REJECTED = -2011
    CANCEL_ALL_FAIL = -2012
    NO_SUCH_ORDER = -2013
    BAD_API_KEY_FMT = -2014
    REJECTED_MBX_KEY = -2015
    NO_TRADING_WINDOW = -2016
    API_KEYS_LOCKED = -2017
    BALANCE_NOT_SUFFICIENT = -2018
    MARGIN_NOT_SUFFICIENT = -2019
    UNABLE_TO_FILL = -2020
    ORDER_WOULD_IMMEDIATELY_TRIGGER = -2021
    REDUCE_ONLY_REJECT = -2022
    USER_IN_LIQUIDATION = -2023
    POSITION_NOT_SUFFICIENT = -2024
    MAX_OPEN_ORDER_EXCEEDED = -2025
    REDUCE_ONLY_ORDER_TYPE_NOT_SUPPORTED = -2026
    MAX_LEVERAGE_RATIO = -2027
    MIN_LEVERAGE_RATIO = -2028

    INVALID_ORDER_STATUS = -4000
    PRICE_LESS_THAN_ZERO = -4001
    PRICE_GREATER_THAN_MAX_PRICE = -4002
    QTY_LESS_THAN_ZERO = -4003
    QTY_LESS_THAN_MIN_QTY = -4004
    QTY_GREATER_THAN_MAX_QTY = -4005
    STOP_PRICE_LESS_THAN_ZERO = -4006
    STOP_PRICE_GREATER_THAN_MAX_PRICE = -4007
    TICK_SIZE_LESS_THAN_ZERO = -4008
    MAX_PRICE_LESS_THAN_MIN_PRICE = -4009
    MAX_QTY_LESS_THAN_MIN_QTY = -4010
    STEP_SIZE_LESS_THAN_ZERO = -4011
    MAX_NUM_ORDERS_LESS_THAN_ZERO = -4012
    PRICE_LESS_THAN_MIN_PRICE = -4013
    PRICE_NOT_INCREASED_BY_TICK_SIZE = -4014
    INVALID_CL_ORD_ID_LEN = -4015
    PRICE_HIGHTER_THAN_MULTIPLIER_UP = -4016
    MULTIPLIER_UP_LESS_THAN_ZERO = -4017
    MULTIPLIER_DOWN_LESS_THAN_ZERO = -4018
    COMPOSITE_SCALE_OVERFLOW = -4019
    TARGET_STRATEGY_INVALID = -4020
    INVALID_DEPTH_LIMIT = -4021
    WRONG_MARKET_STATUS = -4022
    QTY_NOT_INCREASED_BY_STEP_SIZE = -4023
    PRICE_LOWER_THAN_MULTIPLIER_DOWN = -4024
    MULTIPLIER_DECIMAL_LESS_THAN_ZERO = -4025
    COMMISSION_INVALID = -4026
    INVALID_ACCOUNT_TYPE = -4027
    INVALID_LEVERAGE = -4028
    INVALID_TICK_SIZE_PRECISION = -4029
    INVALID_STEP_SIZE_PRECISION = -4030
    INVALID_WORKING_TYPE = -4031
    EXCEED_MAX_CANCEL_ORDER_SIZE = -4032
    INSURANCE_ACCOUNT_NOT_FOUND = -4033
    INVALID_BALANCE_TYPE = -4044
    MAX_STOP_ORDER_EXCEEDED = -4045
    NO_NEED_TO_CHANGE_MARGIN_TYPE = -4046
    THERE_EXISTS_OPEN_ORDERS = -4047
    THERE_EXISTS_QUANTITY = -4048
    ADD_ISOLATED_MARGIN_REJECT = -4049
    CROSS_BALANCE_INSUFFICIENT = -4050
    ISOLATED_BALANCE_INSUFFICIENT = -4051
    NO_NEED_TO_CHANGE_AUTO_ADD_MARGIN = -4052
    AUTO_ADD_CROSSED_MARGIN_REJECT = -4053
    ADD_ISOLATED_MARGIN_NO_POSITION_REJECT = -4054
    AMOUNT_MUST_BE_POSITIVE = -4055
    INVALID_API_KEY_TYPE = -4056
    INVALID_RSA_PUBLIC_KEY = -4057
    MAX_PRICE_TOO_LARGE = -4058
    NO_NEED_TO_CHANGE_POSITION_SIDE = -4059
    INVALID_POSITION_SIDE = -4060
    POSITION_SIDE_NOT_MATCH = -4061
    REDUCE_ONLY_CONFLICT = -4062
    INVALID_OPTIONS_REQUEST_TYPE = -4063
    INVALID_OPTIONS_TIME_FRAME = -4064
    INVALID_OPTIONS_AMOUNT = -4065
    INVALID_OPTIONS_EVENT_TYPE = -4066
    POSITION_SIDE_CHANGE_EXISTS_OPEN_ORDERS = -4067
    POSITION_SIDE_CHANGE_EXISTS_QUANTITY = -4068
    INVALID_OPTIONS_PREMIUM_FEE = -4069
    INVALID_CL_OPTIONS_ID_LEN = -4070
    INVALID_OPTIONS_DIRECTION = -4071
    OPTIONS_PREMIUM_NOT_UPDATE = -4072
    OPTIONS_PREMIUM_INPUT_LESS_THAN_ZERO = -4073
    OPTIONS_AMOUNT_BIGGER_THAN_UPPER = -4074
    OPTIONS_PREMIUM_OUTPUT_ZERO = -4075
    OPTIONS_PREMIUM_TOO_DIFF = -4076
    OPTIONS_PREMIUM_REACH_LIMIT = -4077
    OPTIONS_COMMON_ERROR = -4078
    INVALID_OPTIONS_ID = -4079
    OPTIONS_USER_NOT_FOUND = -4080
    OPTIONS_NOT_FOUND = -4081
    INVALID_BATCH_PLACE_ORDER_SIZE = -4082
    PLACE_BATCH_ORDERS_FAIL = -4083
    UPCOMING_METHOD = -4084
    INVALID_NOTIONAL_LIMIT_COEF = -4085
    INVALID_PRICE_SPREAD_THRESHOLD = -4086
    REDUCE_ONLY_ORDER_PERMISSION = -4087
    NO_PLACE_ORDER_PERMISSION = -4088
    INVALID_CONTRACT_TYPE = -4104
    INVALID_CLIENT_TRAN_ID_LEN = -4114
    DUPLICATED_CLIENT_TRAN_ID = -4115
    REDUCE_ONLY_MARGIN_CHECK_FAILED = -4118
    MARKET_ORDER_REJECT = -4131
    INVALID_ACTIVATION_PRICE = -4135
    QUANTITY_EXISTS_WITH_CLOSE_POSITION = -4137
    REDUCE_ONLY_MUST_BE_TRUE = -4138
    ORDER_TYPE_CANNOT_BE_MKT = -4139
    INVALID_OPENING_POSITION_STATUS = -4140
    SYMBOL_ALREADY_CLOSED = -4141
    STRATEGY_INVALID_TRIGGER_PRICE = -4142
    INVALID_PAIR = -4144
    ISOLATED_LEVERAGE_REJECT_WITH_POSITION = -4161
    MIN_NOTIONAL = -4164
    INVALID_TIME_INTERVAL = -4165
    ISOLATED_REJECT_WITH_JOINT_MARGIN = -4167
    JOINT_MARGIN_REJECT_WITH_ISOLATED = -4168
    JOINT_MARGIN_REJECT_WITH_MB = -4169
    JOINT_MARGIN_REJECT_WITH_OPEN_ORDER = -4170
    NO_NEED_TO_CHANGE_JOINT_MARGIN = -4171
    JOINT_MARGIN_REJECT_WITH_NEGATIVE_BALANCE = -4172
    ISOLATED_REJECT_WITH_JOINT_MARGIN_2 = -4183
    PRICE_LOWER_THAN_STOP_MULTIPLIER_DOWN = -4184
    COOLING_OFF_PERIOD = -4192
    ADJUST_LEVERAGE_KYC_FAILED = -4202
    ADJUST_LEVERAGE_ONE_MONTH_FAILED = -4203
    ADJUST_LEVERAGE_X_DAYS_FAILED = -4205
    ADJUST_LEVERAGE_KYC_LIMIT = -4206
    ADJUST_LEVERAGE_ACCOUNT_SYMBOL_FAILED = -4208
    ADJUST_LEVERAGE_SYMBOL_FAILED = -4209
    STOP_PRICE_HIGHER_THAN_PRICE_MULTIPLIER_LIMIT = -4210
    STOP_PRICE_LOWER_THAN_PRICE_MULTIPLIER_LIMIT = -4211
    TRADING_QUANTITATIVE_RULE = -4400
    COMPLIANCE_RESTRICTION = -4401
    COMPLIANCE_BLACK_SYMBOL_RESTRICTION = -4402
    ADJUST_LEVERAGE_COMPLIANCE_FAILED = -4403

    FOK_ORDER_REJECT = -5021
    GTX_ORDER_REJECT = -5022
    MOVE_ORDER_NOT_ALLOWED_SYMBOL_REASON = -5024
    LIMIT_ORDER_ONLY = 5025
    EXCEED_MAXIMUM_MODIFY_ORDER_LIMIT = -5026
    SAME_ORDER = -5027
    ME_RECVWINDOW_REJECT = -5028
    INVALID_GOOD_TILL_DATE = -5040


BINANCE_RETRY_ERRORS: set[BinanceErrorCode] = {
    BinanceErrorCode.DISCONNECTED,
    BinanceErrorCode.TOO_MANY_REQUESTS,  # Short retry delays may result in bans
    BinanceErrorCode.TIMEOUT,
    BinanceErrorCode.SERVER_BUSY,
    BinanceErrorCode.INVALID_TIMESTAMP,
    BinanceErrorCode.CANCEL_REJECTED,
    BinanceErrorCode.ME_RECVWINDOW_REJECT,
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
    def parse_futures_order_type(cls, order_type: BinanceOrderType) -> OrderType:
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
    def __init__(self):
        self._throttled: dict[
            BinanceAccountType, dict[BinanceRateLimitType, Throttled]
        ] = {
            BinanceAccountType.SPOT: {
                BinanceRateLimitType.ORDERS: Throttled(
                    quota=rate_limiter.per_duration(timedelta(seconds=10), limit=50),
                    timeout=10,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: Throttled(
                    quota=rate_limiter.per_min(6000),
                    timeout=60,
                ),
            },
            BinanceAccountType.USD_M_FUTURE: {
                BinanceRateLimitType.ORDERS: Throttled(
                    quota=rate_limiter.per_duration(timedelta(seconds=10), limit=300),
                    timeout=10,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: Throttled(
                    quota=rate_limiter.per_min(6000),
                    timeout=60,
                ),
            },
            BinanceAccountType.COIN_M_FUTURE: {
                BinanceRateLimitType.ORDERS: Throttled(
                    quota=rate_limiter.per_min(6000),
                    timeout=60,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: Throttled(
                    quota=rate_limiter.per_min(6000),
                    timeout=60,
                ),
            },
            BinanceAccountType.PORTFOLIO_MARGIN: {
                BinanceRateLimitType.ORDERS: Throttled(
                    quota=rate_limiter.per_min(1200),
                    timeout=60,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: Throttled(
                    quota=rate_limiter.per_min(6000),
                    timeout=60,
                ),
            },
        }

    def __call__(
        self, account_type: BinanceAccountType, rate_limit_type: BinanceRateLimitType
    ) -> Throttled:
        return self._throttled[account_type][rate_limit_type]


class BinanceRateLimiterSync(RateLimiterSync):
    def __init__(self):
        self._throttled: dict[
            BinanceAccountType, dict[BinanceRateLimitType, ThrottledSync]
        ] = {
            BinanceAccountType.SPOT: {
                BinanceRateLimitType.ORDERS: ThrottledSync(
                    quota=rate_limiter_sync.per_duration(
                        timedelta(seconds=10), limit=50
                    ),
                    timeout=10,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: ThrottledSync(
                    quota=rate_limiter_sync.per_min(6000),
                    timeout=60,
                ),
            },
            BinanceAccountType.USD_M_FUTURE: {
                BinanceRateLimitType.ORDERS: ThrottledSync(
                    quota=rate_limiter_sync.per_duration(
                        timedelta(seconds=10), limit=300
                    ),
                    timeout=10,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: ThrottledSync(
                    quota=rate_limiter_sync.per_min(6000),
                    timeout=60,
                ),
            },
            BinanceAccountType.COIN_M_FUTURE: {
                BinanceRateLimitType.ORDERS: ThrottledSync(
                    quota=rate_limiter_sync.per_min(6000),
                    timeout=60,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: ThrottledSync(
                    quota=rate_limiter_sync.per_min(6000),
                    timeout=60,
                ),
            },
            BinanceAccountType.PORTFOLIO_MARGIN: {
                BinanceRateLimitType.ORDERS: ThrottledSync(
                    quota=rate_limiter_sync.per_min(1200),
                    timeout=60,
                ),
                BinanceRateLimitType.REQUEST_WEIGHT: ThrottledSync(
                    quota=rate_limiter_sync.per_min(6000),
                    timeout=60,
                ),
            },
        }

    def __call__(
        self, account_type: BinanceAccountType, rate_limit_type: BinanceRateLimitType
    ) -> ThrottledSync:
        return self._throttled[account_type][rate_limit_type]
