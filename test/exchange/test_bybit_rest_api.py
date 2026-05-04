import msgspec
import pytest
from types import SimpleNamespace

from nexustrader.core.nautilius_core import LiveClock
from nexustrader.exchange.bybit.rest_api import BybitApiClient


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


class SequenceClock:
    def __init__(self, *timestamps: int):
        self._timestamps = list(timestamps)
        self._last = timestamps[-1] if timestamps else 0

    def timestamp_ms(self) -> int:
        if self._timestamps:
            self._last = self._timestamps.pop(0)
        return self._last


@pytest.mark.asyncio
async def test_bybit_get_wallet_balance_uses_async_fetch_and_limiter():
    clock = LiveClock()
    client = BybitApiClient(clock=clock, api_key="k", secret="s", testnet=True)

    limiter = DummyLimiter()
    session = DummySession(
        DummyResponse(
            200,
            msgspec.json.encode(
                {"retCode": 0, "retMsg": "OK", "result": {}, "time": 1000}
            ),
        )
    )

    client._limiter = limiter
    client._session = session
    client._wallet_balance_response_decoder = SimpleNamespace(
        decode=lambda raw: {"ok": True}
    )

    res = await client.get_v5_account_wallet_balance(account_type="UNIFIED")

    assert res == {"ok": True}
    assert ("50/s", "/v5/account/wallet-balance", 1) in limiter.calls
    assert session.requests
    assert session.requests[0]["method"] == "GET"


@pytest.mark.asyncio
async def test_bybit_time_sync_uses_curl_cffi_response_content():
    clock = SequenceClock(1_000, 1_100)
    client = BybitApiClient(clock=clock, api_key="k", secret="s", testnet=True)
    session = DummySession(
        DummyResponse(
            200,
            msgspec.json.encode(
                {"retCode": 0, "retMsg": "OK", "result": {}, "time": 1_500}
            ),
        )
    )

    client._session = session

    await client._sync_time_if_needed()

    assert client._time_offset_ms == 400
    assert client._last_time_sync_ms == 1_100
    assert session.requests


@pytest.mark.asyncio
async def test_bybit_time_sync_failure_uses_short_retry_backoff():
    clock = SequenceClock(1_000, 1_100, 1_200)
    client = BybitApiClient(clock=clock, api_key="k", secret="s", testnet=True)
    session = DummySession(
        DummyResponse(
            500,
            msgspec.json.encode({"retCode": 10000, "retMsg": "error"}),
        )
    )

    client._session = session

    await client._sync_time_if_needed()
    await client._sync_time_if_needed()

    assert len(session.requests) == 1
    assert client._next_time_sync_ms == 6_100


@pytest.mark.asyncio
async def test_bybit_get_kline_uses_async_fetch_and_limiter():
    clock = LiveClock()
    client = BybitApiClient(clock=clock, api_key="k", secret="s", testnet=True)

    limiter = DummyLimiter()
    session = DummySession(
        DummyResponse(
            200,
            msgspec.json.encode(
                {"retCode": 0, "retMsg": "OK", "result": {}, "time": 1000}
            ),
        )
    )

    client._limiter = limiter
    client._session = session
    client._kline_response_decoder = SimpleNamespace(decode=lambda raw: {"ok": True})

    res = await client.get_v5_market_kline(
        category="linear", symbol="BTCUSDT", interval="1"
    )

    assert res == {"ok": True}
    assert ("public", "/v5/market/kline", 1) in limiter.calls
    assert session.requests
    assert session.requests[0]["method"] == "GET"
