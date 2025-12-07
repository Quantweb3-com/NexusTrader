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


class KucoinRateLimiter(RateLimiter):
    """Simple rate limiter buckets for KuCoin REST requests."""

    def __init__(self, enable_rate_limit: bool = True):
        timeout = 60 if enable_rate_limit else -1
        self._spot_public = Throttled(
            quota=rate_limiter.per_sec(30),
            timeout=timeout,
            using=RateLimiterType.GCRA.value,
        )
        self._spot_private = Throttled(
            quota=rate_limiter.per_sec(15),
            timeout=timeout,
            using=RateLimiterType.GCRA.value,
        )
        self._futures_public = Throttled(
            quota=rate_limiter.per_sec(30),
            timeout=timeout,
            using=RateLimiterType.GCRA.value,
        )
        self._futures_private = Throttled(
            quota=rate_limiter.per_sec(12),
            timeout=timeout,
            using=RateLimiterType.GCRA.value,
        )

    def _resolve(self, account_type: KucoinAccountType, signed: bool) -> Throttled:
        if account_type == KucoinAccountType.FUTURES:
            return self._futures_private if signed else self._futures_public

        # Treat spot and margin keys identically for now.
        return self._spot_private if signed else self._spot_public

    async def limit(
        self,
        account_type: KucoinAccountType,
        endpoint: str,
        signed: bool,
        cost: int = 1,
    ) -> None:
        throttled = self._resolve(account_type, signed)
        await throttled.limit(key=endpoint, cost=cost)


class KucoinRateLimiterSync(RateLimiterSync):
    """Synchronous companion to :class:`KucoinRateLimiter`."""

    def __init__(self, enable_rate_limit: bool = True):
        timeout = 60 if enable_rate_limit else -1
        self._spot_public = ThrottledSync(
            quota=rate_limiter_sync.per_sec(30),
            timeout=timeout,
            using=RateLimiterType.GCRA.value,
        )
        self._spot_private = ThrottledSync(
            quota=rate_limiter_sync.per_sec(15),
            timeout=timeout,
            using=RateLimiterType.GCRA.value,
        )
        self._futures_public = ThrottledSync(
            quota=rate_limiter_sync.per_sec(30),
            timeout=timeout,
            using=RateLimiterType.GCRA.value,
        )
        self._futures_private = ThrottledSync(
            quota=rate_limiter_sync.per_sec(12),
            timeout=timeout,
            using=RateLimiterType.GCRA.value,
        )

    def _resolve(
        self, account_type: KucoinAccountType, signed: bool
    ) -> ThrottledSync:
        if account_type == KucoinAccountType.FUTURES:
            return self._futures_private if signed else self._futures_public

        return self._spot_private if signed else self._spot_public

    def limit(
        self,
        account_type: KucoinAccountType,
        endpoint: str,
        signed: bool,
        cost: int = 1,
    ) -> None:
        throttled = self._resolve(account_type, signed)
        throttled.limit(key=endpoint, cost=cost)
