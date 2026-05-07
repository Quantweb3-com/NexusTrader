import msgspec
import pytest
from decimal import Decimal
from types import SimpleNamespace

from nexustrader.constants import ExchangeType, PositionSide
from nexustrader.core.nautilius_core import LiveClock
from nexustrader.exchange.okx.oms import OkxOrderManagementSystem
from nexustrader.exchange.okx.rest_api import OkxApiClient
from nexustrader.schema import Position


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
        self.headers = {}


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


class DummyPositionCache:
    def __init__(self):
        self.positions = {}

    def _apply_position(self, position: Position):
        if position.is_closed:
            self.positions.pop(position.symbol, None)
        else:
            self.positions[position.symbol] = position

    def get_all_positions(self, exchange=None):
        return {
            symbol: position
            for symbol, position in self.positions.items()
            if exchange is None or position.exchange == exchange
        }

    def get_position(self, symbol: str):
        return self.positions.get(symbol)


def test_okx_init_position_clears_stale_cache_when_rest_snapshot_is_empty():
    symbol = "BTCUSDT-PERP.OKX"
    oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)
    oms._exchange_id = ExchangeType.OKX
    oms._cache = DummyPositionCache()
    oms._api_client = SimpleNamespace(get_api_v5_account_positions=lambda: object())
    oms._run_sync = lambda coro: SimpleNamespace(data=[])
    oms._market_id = {}
    oms._market = {}
    oms._cache._apply_position(
        Position(
            symbol=symbol,
            exchange=ExchangeType.OKX,
            signed_amount=Decimal("-1"),
            side=PositionSide.SHORT,
        )
    )

    oms._init_position()

    assert oms._cache.get_position(symbol) is None


@pytest.mark.asyncio
async def test_okx_get_account_balance_uses_async_fetch_and_limiter():
    clock = LiveClock()
    client = OkxApiClient(clock=clock, api_key="k", secret="s", passphrase="p")

    limiter = DummyLimiter()
    session = DummySession(
        DummyResponse(200, msgspec.json.encode({"code": "0", "data": []}))
    )

    client._limiter = limiter
    client._session = session
    client._balance_response_decoder = SimpleNamespace(decode=lambda raw: {"ok": True})
    client._general_response_decoder = SimpleNamespace(
        decode=lambda raw: SimpleNamespace(code="0")
    )

    res = await client.get_api_v5_account_balance()

    assert res == {"ok": True}
    assert ("/api/v5/account/balance", "/api/v5/account/balance", 1) in limiter.calls
    assert session.requests
    assert session.requests[0]["method"] == "GET"


@pytest.mark.asyncio
async def test_okx_get_market_candles_uses_async_fetch_and_limiter():
    clock = LiveClock()
    client = OkxApiClient(clock=clock, api_key="k", secret="s", passphrase="p")

    limiter = DummyLimiter()
    session = DummySession(
        DummyResponse(200, msgspec.json.encode({"code": "0", "data": []}))
    )

    client._limiter = limiter
    client._session = session
    client._candles_response_decoder = SimpleNamespace(decode=lambda raw: {"ok": True})
    client._general_response_decoder = SimpleNamespace(
        decode=lambda raw: SimpleNamespace(code="0")
    )

    res = await client.get_api_v5_market_candles(instId="BTC-USDT")

    assert res == {"ok": True}
    assert ("/api/v5/market/candles", "/api/v5/market/candles", 1) in limiter.calls
    assert session.requests
    assert session.requests[0]["method"] == "GET"
