from abc import ABC
from typing import Optional
from curl_cffi import requests
from nexustrader.core.nautilius_core import LiveClock, Logger
from nexustrader.constants import RateLimiter
from nexustrader.base.retry import RetryManager


class ApiClient(ABC):
    def __init__(
        self,
        clock: LiveClock,
        api_key: str = None,
        secret: str = None,
        timeout: int = 10,
        rate_limiter: RateLimiter = None,
        retry_manager: RetryManager = None,
    ):
        self._api_key = api_key
        self._secret = secret
        self._timeout = timeout
        self._log = Logger(name=type(self).__name__)
        self._session: Optional[requests.AsyncSession] = None
        self._clock = clock
        self._limiter = rate_limiter
        self._retry_manager: RetryManager = retry_manager

    def _init_session(self, base_url: str | None = None):
        if self._session is None:
            self._session = requests.AsyncSession(
                base_url=base_url if base_url else "", timeout=self._timeout
            )

    def _get_rate_limit_cost(self, cost: int = 1):
        return cost

    async def close_session(self):
        """Close the session"""
        if self._session:
            await self._session.close()
            self._session = None
