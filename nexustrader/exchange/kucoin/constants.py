from enum import Enum
from nexustrader.constants import AccountType
from throttled.asyncio import Throttled, rate_limiter, RateLimiterType
from throttled import Throttled as ThrottledSync
from throttled import rate_limiter as rate_limiter_sync
import time
import threading
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


class KucoinAccountType(AccountType):
    SPOT = "spot"
    MARGIN = "margin"
    FUTURES = "futures"
    SPOT_MOCK = "SPOT_MOCK"
    LINEAR_MOCK = "LINEAR_MOCK"
    INVERSE_MOCK = "INVERSE_MOCK"

    @property
    def exchange_id(self) -> str:
        return "kucoin"

    @property
    def base_url(self) -> str:
        if self == KucoinAccountType.SPOT or self == KucoinAccountType.MARGIN:
            return "https://api.kucoin.com"
        elif self == KucoinAccountType.FUTURES:
            return "https://api-futures.kucoin.com"
        else:
            raise ValueError(f"Unsupported Kucoin account type: {self}")
    
    @property
    def stream_url(self) -> str:
        if self == KucoinAccountType.SPOT or self == KucoinAccountType.MARGIN:
            return "wss://ws-api-spot.kucoin.com"
        elif self == KucoinAccountType.FUTURES:
            return "wss://ws-api-futures.kucoin.com"
        else:
            raise ValueError(f"Unsupported Kucoin account type: {self}")

    @property
    def is_spot(self):
        return self in (self.SPOT, self.SPOT_MOCK)

    @property
    def is_future(self):
        return self in (
            self.LINEAR_MOCK,
            self.INVERSE_MOCK,
        )

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

class KucoinRateLimitType(Enum):
    ORDERS = "ORDERS"
    REQUEST_WEIGHT = "REQUEST_WEIGHT"

class KucoinKlineInterval(Enum):
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

class KucoinEnumParser:
    _kucoin_kline_interval_map = {
        KucoinKlineInterval.SECOND_1: KlineInterval.SECOND_1,
        KucoinKlineInterval.MINUTE_1: KlineInterval.MINUTE_1,
        KucoinKlineInterval.MINUTE_3: KlineInterval.MINUTE_3,
        KucoinKlineInterval.MINUTE_5: KlineInterval.MINUTE_5,
        KucoinKlineInterval.MINUTE_15: KlineInterval.MINUTE_15,
        KucoinKlineInterval.MINUTE_30: KlineInterval.MINUTE_30,
        KucoinKlineInterval.HOUR_1: KlineInterval.HOUR_1,
        KucoinKlineInterval.HOUR_2: KlineInterval.HOUR_2,
        KucoinKlineInterval.HOUR_4: KlineInterval.HOUR_4,
        KucoinKlineInterval.HOUR_6: KlineInterval.HOUR_6,
        KucoinKlineInterval.HOUR_8: KlineInterval.HOUR_8,
        KucoinKlineInterval.HOUR_12: KlineInterval.HOUR_12,
        KucoinKlineInterval.DAY_1: KlineInterval.DAY_1,
        KucoinKlineInterval.DAY_3: KlineInterval.DAY_3,
        KucoinKlineInterval.WEEK_1: KlineInterval.WEEK_1,
        KucoinKlineInterval.MONTH_1: KlineInterval.MONTH_1,
    }

    @staticmethod
    def ws_interval_str(interval: KlineInterval) -> str:
        """Convert `KlineInterval` to KuCoin WS interval string.

        Supported values: 1min, 3min, 5min, 15min, 30min, 1hour, 2hour, 4hour, 6hour, 8hour, 12hour, 1day, 1week.
        """
        mapping = {
            KlineInterval.MINUTE_1: "1min",
            KlineInterval.MINUTE_3: "3min",
            KlineInterval.MINUTE_5: "5min",
            KlineInterval.MINUTE_15: "15min",
            KlineInterval.MINUTE_30: "30min",
            KlineInterval.HOUR_1: "1hour",
            KlineInterval.HOUR_2: "2hour",
            KlineInterval.HOUR_4: "4hour",
            KlineInterval.HOUR_6: "6hour",
            KlineInterval.HOUR_8: "8hour",
            KlineInterval.HOUR_12: "12hour",
            KlineInterval.DAY_1: "1day",
            KlineInterval.WEEK_1: "1week",
        }
        val = mapping.get(interval)
        if not val:
            raise ValueError(f"Unsupported interval {interval} for KuCoin WS kline")
        return val

    @staticmethod
    def spot_interval_str(interval: KlineInterval) -> str:
        """Convert `KlineInterval` to KuCoin REST spot interval string.

        Supported: 1min, 3min, 5min, 15min, 30min, 1hour, 2hour, 4hour, 6hour, 8hour, 12hour, 1day, 1week, 1month.
        """
        mapping = {
            KlineInterval.MINUTE_1: "1min",
            KlineInterval.MINUTE_3: "3min",
            KlineInterval.MINUTE_5: "5min",
            KlineInterval.MINUTE_15: "15min",
            KlineInterval.MINUTE_30: "30min",
            KlineInterval.HOUR_1: "1hour",
            KlineInterval.HOUR_2: "2hour",
            KlineInterval.HOUR_4: "4hour",
            KlineInterval.HOUR_6: "6hour",
            KlineInterval.HOUR_8: "8hour",
            KlineInterval.HOUR_12: "12hour",
            KlineInterval.DAY_1: "1day",
            KlineInterval.WEEK_1: "1week",
            KlineInterval.MONTH_1: "1month",
        }
        val = mapping.get(interval)
        if not val:
            raise ValueError(f"Unsupported interval {interval} for KuCoin spot kline")
        return val

    @staticmethod
    def futures_granularity(interval: KlineInterval) -> int:
        """Convert `KlineInterval` to KuCoin REST futures granularity (minutes)."""
        mapping = {
            KlineInterval.MINUTE_1: 1,
            KlineInterval.MINUTE_5: 5,
            KlineInterval.MINUTE_15: 15,
            KlineInterval.MINUTE_30: 30,
            KlineInterval.HOUR_1: 60,
            KlineInterval.HOUR_2: 120,
            KlineInterval.HOUR_4: 240,
            KlineInterval.HOUR_8: 480,
            KlineInterval.HOUR_12: 720,
            KlineInterval.DAY_1: 1440,
            KlineInterval.WEEK_1: 10080,
        }
        val = mapping.get(interval)
        if val is None:
            raise ValueError(f"Unsupported interval {interval} for KuCoin futures kline")
        return val

# String-to-KlineInterval map for KuCoin interval labels used across WS/REST.
# Includes both short forms (e.g., "1m", "1h") and KuCoin-specific forms (e.g., "1min", "1hour").
KUCOIN_INTERVAL_MAP: dict[str, KlineInterval] = {
    # Short forms
    "1s": KlineInterval.SECOND_1,
    "1m": KlineInterval.MINUTE_1,
    "3m": KlineInterval.MINUTE_3,
    "5m": KlineInterval.MINUTE_5,
    "15m": KlineInterval.MINUTE_15,
    "30m": KlineInterval.MINUTE_30,
    "1h": KlineInterval.HOUR_1,
    "2h": KlineInterval.HOUR_2,
    "4h": KlineInterval.HOUR_4,
    "6h": KlineInterval.HOUR_6,
    "8h": KlineInterval.HOUR_8,
    "12h": KlineInterval.HOUR_12,
    "1d": KlineInterval.DAY_1,
    "1w": KlineInterval.WEEK_1,
    "1M": KlineInterval.MONTH_1,
    # KuCoin long forms
    "1min": KlineInterval.MINUTE_1,
    "3min": KlineInterval.MINUTE_3,
    "5min": KlineInterval.MINUTE_5,
    "15min": KlineInterval.MINUTE_15,
    "30min": KlineInterval.MINUTE_30,
    "1hour": KlineInterval.HOUR_1,
    "2hour": KlineInterval.HOUR_2,
    "4hour": KlineInterval.HOUR_4,
    "6hour": KlineInterval.HOUR_6,
    "8hour": KlineInterval.HOUR_8,
    "12hour": KlineInterval.HOUR_12,
    "1day": KlineInterval.DAY_1,
    "1week": KlineInterval.WEEK_1,
    "1month": KlineInterval.MONTH_1,
}

class KucoinWsEventType(Enum):
    SPOTTRADE = "trade.l3match"
    FUTURESTRADE = "match"
    BOOK_L1 = "level1"
    BOOK_L2 = "level2"
    SPOTKLINE = "trade.candles.update"
    FUTURESKLINE = "candle.stick"

class KucoinRateLimiter(RateLimiter):
    def __init__(self, enable_rate_limit: bool = True):
        timeout = 60 if enable_rate_limit else -1
        # Map endpoint prefixes to Throttled instances (GCRA)
        self._throttled_prefixes: list[tuple[str, Throttled]] = [
            # Spot account
            ("/api/v1/accounts", Throttled(quota=rate_limiter.per_sec(10), timeout=timeout, using=RateLimiterType.GCRA.value)),
            # Spot market data
            ("/api/v1/market/candles", Throttled(quota=rate_limiter.per_sec(20), timeout=timeout, using=RateLimiterType.GCRA.value)),
            # Spot HF orders
            ("/api/v1/hf/orders/multi", Throttled(quota=rate_limiter.per_sec(50), timeout=timeout, using=RateLimiterType.GCRA.value)),
            ("/api/v1/hf/orders/client-order", Throttled(quota=rate_limiter.per_sec(50), timeout=timeout, using=RateLimiterType.GCRA.value)),
            ("/api/v1/hf/orders/alter", Throttled(quota=rate_limiter.per_sec(50), timeout=timeout, using=RateLimiterType.GCRA.value)),
            ("/api/v1/hf/orders/cancelAll", Throttled(quota=rate_limiter.per_sec(20), timeout=timeout, using=RateLimiterType.GCRA.value)),
            ("/api/v1/hf/orders", Throttled(quota=rate_limiter.per_sec(50), timeout=timeout, using=RateLimiterType.GCRA.value)),
            # Futures account/positions
            ("/api/v1/account-overview", Throttled(quota=rate_limiter.per_sec(5), timeout=timeout, using=RateLimiterType.GCRA.value)),
            ("/api/v1/positions", Throttled(quota=rate_limiter.per_sec(5), timeout=timeout, using=RateLimiterType.GCRA.value)),
            ("/api/v1/position/mode", Throttled(quota=rate_limiter.per_sec(2), timeout=timeout, using=RateLimiterType.GCRA.value)),
            # Futures market data
            ("/api/v1/kline/query", Throttled(quota=rate_limiter.per_sec(20), timeout=timeout, using=RateLimiterType.GCRA.value)),
            # Futures orders
            ("/api/v1/orders/client-order", Throttled(quota=rate_limiter.per_sec(30), timeout=timeout, using=RateLimiterType.GCRA.value)),
            ("/api/v1/orders", Throttled(quota=rate_limiter.per_sec(30), timeout=timeout, using=RateLimiterType.GCRA.value)),
            # WS token
            ("/api/v1/bullet-private", Throttled(quota=rate_limiter.per_sec(2), timeout=timeout, using=RateLimiterType.GCRA.value)),
            ("/api/v1/bullet-public", Throttled(quota=rate_limiter.per_sec(2), timeout=timeout, using=RateLimiterType.GCRA.value)),
        ]

    def __call__(self, endpoint: str) -> Throttled:
        for prefix, throttled in self._throttled_prefixes:
            if endpoint.startswith(prefix):
                return throttled
        raise KeyError(f"No rate limiter configured for endpoint: {endpoint}")
    