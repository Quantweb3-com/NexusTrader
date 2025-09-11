from abc import ABC
from typing import Optional
import ssl
import certifi
import httpx
from nexustrader.core.nautilius_core import LiveClock, Logger
from nexustrader.constants import RateLimiter, RateLimiterSync
from nexustrader.base.retry import RetryManager


class ApiClient(ABC):
    def __init__(
        self,
        clock: LiveClock,
        api_key: str = None,
        secret: str = None,
        timeout: int = 10,
        rate_limiter: RateLimiter = None,
        rate_limiter_sync: RateLimiterSync = None,
        retry_manager: RetryManager = None,
    ):
        self._api_key = api_key
        self._secret = secret
        self._timeout = timeout
        self._log = Logger(name=type(self).__name__)
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._session: Optional[httpx.AsyncClient] = None
        self._sync_session: Optional[httpx.Client] = None
        self._clock = clock
        self._limiter = rate_limiter
        self._limiter_sync = rate_limiter_sync
        self._retry_manager: RetryManager = retry_manager

    def _init_session(self, base_url: str | None = None):
        if self._session is None:
            self._session = httpx.AsyncClient(
                base_url=base_url if base_url else "",
                timeout=self._timeout,
                verify=self._ssl_context,
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0,  # higher value to avoid frequent reconnects
                ),
            )

    def _get_rate_limit_cost(self, cost: int = 1):
        return cost

    def _init_sync_session(self, base_url: str | None = None):
        if self._sync_session is None:
            self._sync_session = httpx.Client(
                base_url=base_url if base_url else "",
                timeout=self._timeout,
                verify=self._ssl_context,
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0,
                ),
            )

    async def close_session(self):
        """Close the session"""
        if self._session:
            await self._session.aclose()
            self._session = None
        if self._sync_session:
            self._sync_session.close()
            self._sync_session = None
