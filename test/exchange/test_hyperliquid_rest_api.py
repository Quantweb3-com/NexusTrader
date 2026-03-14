import msgspec
import pytest
from types import SimpleNamespace

from nexustrader.core.nautilius_core import LiveClock
from nexustrader.exchange.hyperliquid.rest_api import HyperLiquidApiClient


class DummyLimiter:
    def __init__(self):
        self.calls: list[tuple[str, str, int]] = []

    def __call__(self, bucket: str):
        self._bucket = bucket
        return self

    async def limit(self, key: str, cost: int = 1):
        self.calls.append((self._bucket, key, cost))


class DummyResponse:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content


class DummySession:
    def __init__(self, response: DummyResponse):
        self._response = response
        self.requests: list[dict] = []

    async def request(self, method: str, url: str, headers=None, data=None):
        self.requests.append(
            {"method": method, "url": url, "headers": headers, "data": data}
        )
        return self._response

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_hyperliquid_get_user_perps_summary_uses_limiter_and_fetch():
    clock = LiveClock()
    client = HyperLiquidApiClient(clock=clock, api_key="addr", secret=None, testnet=True)

    limiter = DummyLimiter()
    session = DummySession(DummyResponse(200, msgspec.json.encode({"ok": True})))

    client._limiter = limiter
    client._session = session
    client._user_perps_summary_decoder = SimpleNamespace(
        decode=lambda raw: {"ok": True}
    )

    res = await client.get_user_perps_summary()

    assert res == {"ok": True}
    assert ("/info", "/info", 2) in limiter.calls
    assert session.requests
    assert session.requests[0]["method"] == "POST"


@pytest.mark.asyncio
async def test_hyperliquid_get_klines_uses_limiter_and_fetch():
    clock = LiveClock()
    client = HyperLiquidApiClient(clock=clock, api_key="addr", secret=None, testnet=True)

    limiter = DummyLimiter()
    session = DummySession(DummyResponse(200, msgspec.json.encode([{}])))

    client._limiter = limiter
    client._session = session
    client._kline_decoder = SimpleNamespace(decode=lambda raw: [{"ok": True}])

    res = await client.get_klines("BTC", "1m")

    assert res == [{"ok": True}]
    assert ("/info", "/info", 20) in limiter.calls
    assert session.requests
    assert session.requests[0]["method"] == "POST"
