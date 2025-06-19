from abc import ABC
from typing import Optional
import ssl
import certifi
import httpx
import aiohttp
import msgspec
from nexustrader.core.nautilius_core import LiveClock, Logger
from nexustrader.constants import RateLimiter, RateLimiterSync


class ApiClient(ABC):
    def __init__(
        self,
        api_key: str = None,
        secret: str = None,
        timeout: int = 10,
        enable_rate_limit: bool = True,
        rate_limiter: RateLimiter = None,
        rate_limiter_sync: RateLimiterSync = None,
    ):
        self._api_key = api_key
        self._secret = secret
        self._timeout = timeout
        self._log = Logger(name=type(self).__name__)
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._session: Optional[aiohttp.ClientSession] = None
        self._sync_session: Optional[httpx.Client] = None
        self._clock = LiveClock()
        self._enable_rate_limit = enable_rate_limit
        self._limiter = rate_limiter
        self._limiter_sync = rate_limiter_sync

    def _init_session(self, base_url: str | None = None):
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            tcp_connector = aiohttp.TCPConnector(
                ssl=self._ssl_context, enable_cleanup_closed=True
            )
            self._session = aiohttp.ClientSession(
                base_url=base_url,
                connector=tcp_connector,
                json_serialize=msgspec.json.encode,
                timeout=timeout,
            )

    def _get_rate_limit_cost(self, cost: int = 1):
        if not self._enable_rate_limit:
            return 0
        return cost

    def _init_sync_session(self, base_url: str | None = None):
        if self._sync_session is None:
            self._sync_session = httpx.Client(
                base_url=base_url if base_url else "",
                timeout=self._timeout,
            )

    async def close_session(self):
        """Close the session"""
        if self._session:
            await self._session.close()
            self._session = None
        if self._sync_session:
            self._sync_session.close()
            self._sync_session = None
