from abc import ABC
from typing import Optional
import ssl
import certifi
import niquests
from nexustrader.core.log import SpdLog
from nexustrader.core.nautilius_core import LiveClock


class ApiClient(ABC):
    def __init__(
        self,
        api_key: str = None,
        secret: str = None,
        timeout: int = 10,
        enable_rate_limit: bool = True,
    ):
        self._api_key = api_key
        self._secret = secret
        self._timeout = timeout
        self._log = SpdLog.get_logger(type(self).__name__, level="DEBUG", flush=True)
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._session: Optional[niquests.AsyncSession] = None
        self._sync_session: Optional[niquests.Session] = None
        self._clock = LiveClock()
        self._enable_rate_limit = enable_rate_limit

    def _init_session(self, base_url: str | None = None):
        if self._session is None:
            self._session = niquests.AsyncSession(
                base_url=base_url,
                timeout=self._timeout,
            )

    def _get_rate_limit_cost(self, cost: int = 1):
        if not self._enable_rate_limit:
            return 0
        return cost

    def _init_sync_session(self, base_url: str | None = None):
        if self._sync_session is None:
            self._sync_session = niquests.Session(
                base_url=base_url,
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
