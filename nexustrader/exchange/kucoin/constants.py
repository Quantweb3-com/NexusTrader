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
