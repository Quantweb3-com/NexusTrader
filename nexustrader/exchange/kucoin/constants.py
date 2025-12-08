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


class KucoinRateLimiter(RateLimiter):
    SPOT_RATE_LIMITS_PER_30S = {
        0: 4000,
        1: 6000,
        2: 8000,
        3: 10000,
        4: 13000,
        5: 16000,
        6: 20000,
        7: 23000,
        8: 26000,
        9: 30000,
        10: 33000,
        11: 36000,
        12: 40000,
    }

    FUTURES_RATE_LIMITS_PER_30S = {
        0: 2000,
        1: 2000,
        2: 4000,
        3: 5000,
        4: 6000,
        5: 7000,
        6: 8000,
        7: 10000,
        8: 12000,
        9: 14000,
        10: 16000,
        11: 18000,
        12: 20000,
    }


    def __init__(self, enable_rate_limit: bool = True, vip_level: int = 0) -> None:

        self._rate_lock = threading.Lock()
        # key 可以是 ('SPOT', 'GET'), ('SPOT', 'POST'), ('FUTURES', 'GET') 等
        # value = {'capacity': x, 'tokens': x, 'refill_rate': y, 'last_refill': ts}
        self._rate_buckets: dict[str, dict[str, float]] = {}

        if enable_rate_limit:
            vip = int(vip_level)
            if vip not in self.SPOT_RATE_LIMITS_PER_30S:
                vip = 0

            spot_capacity = float(self.SPOT_RATE_LIMITS_PER_30S[vip])
            futures_capacity = float(self.FUTURES_RATE_LIMITS_PER_30S[vip])

            now = time.time()
            # 现货统一桶（所有现货 REST 请求共用）
            self._rate_buckets["SPOT"] = {
                "capacity": spot_capacity,
                "tokens": spot_capacity,
                "last_refill": now,
            }
            # 合约统一桶
            self._rate_buckets["FUTURES"] = {
                "capacity": futures_capacity,
                "tokens": futures_capacity,
                "last_refill": now,
            }


    def set_rate_limit(
        self,
        scope: str,
        capacity: int,
        refill_per_second: float,
    ) -> None:
        """
        配置简单令牌桶限速:
        - scope: 'SPOT' / 'FUTURES'
        - method: 'GET' / 'POST' / 'DELETE' ...
        - capacity: 桶最大令牌数
        """
        key = (scope.upper())
        now = time.time()
        with self._rate_lock:
            self._rate_buckets[key] = {
                "capacity": float(capacity),
                "tokens": float(capacity),
                "refill_rate": float(refill_per_second),
                "last_refill": now,
            }

    def _acquire_rate_limit(self, scope: str, method: str) -> None:
        """
        在发送请求前调用，按配置的 rate limit 阻塞等待可用令牌。
        如果未配置对应桶，则直接返回不做限制。
        """
        key = (scope.upper(), method.upper())
        while True:
            with self._rate_lock:
                bucket = self._rate_buckets.get(key)
                if bucket is None:
                    return

                now = time.time()
                elapsed = now - bucket["last_refill"]
                if elapsed > 30:
                    bucket["tokens"] = bucket["capacity"]
                    bucket["last_refill"] = now

                if bucket["tokens"] >= 1.0:
                    bucket["tokens"] -= 1.0
                    return

                sleep_time = bucket["last_refill"] + 30

            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                time.sleep(0.1)
    