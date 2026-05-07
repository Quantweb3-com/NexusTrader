import msgspec
import pytest
from decimal import Decimal
from types import SimpleNamespace

from nexustrader.constants import ExchangeType, PositionSide
from nexustrader.core.nautilius_core import LiveClock
from nexustrader.exchange.bitget.oms import BitgetOrderManagementSystem
from nexustrader.exchange.bitget.rest_api import BitgetApiClient
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


def test_bitget_init_position_clears_stale_cache_when_rest_snapshot_is_empty():
    symbol = "BTCUSDT-PERP.BITGET"
    oms = BitgetOrderManagementSystem.__new__(BitgetOrderManagementSystem)
    oms._exchange_id = ExchangeType.BITGET
    oms._account_type = SimpleNamespace(is_uta=False)
    oms._cache = DummyPositionCache()
    oms._api_client = SimpleNamespace(
        get_api_v2_mix_position_all_position=lambda productType: productType
    )
    oms._run_sync = lambda coro: SimpleNamespace(data=[])
    oms._log = SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    oms._market_id = {}
    oms._cache._apply_position(
        Position(
            symbol=symbol,
            exchange=ExchangeType.BITGET,
            signed_amount=Decimal("1"),
            side=PositionSide.LONG,
        )
    )

    oms._init_position()

    assert oms._cache.get_position(symbol) is None


@pytest.mark.asyncio
async def test_bitget_get_all_positions_uses_async_fetch_and_limiter():
    clock = LiveClock()
    client = BitgetApiClient(
        clock=clock, api_key="k", secret="s", passphrase="p", testnet=True
    )

    limiter = DummyLimiter()
    session = DummySession(DummyResponse(200, msgspec.json.encode({"ok": True})))

    client._limiter = limiter
    client._session = session
    client._position_list_decoder = SimpleNamespace(decode=lambda raw: {"ok": True})

    res = await client.get_api_v2_mix_position_all_position(
        productType="USDT-FUTURES", marginCoin="USDT"
    )

    assert res == {"ok": True}
    assert (
        "/api/v2/mix/position/all-position",
        "/api/v2/mix/position/all-position",
        1,
    ) in limiter.calls
    assert session.requests
    assert session.requests[0]["method"] == "GET"


@pytest.mark.asyncio
async def test_bitget_get_market_tickers_uses_async_fetch_and_limiter():
    clock = LiveClock()
    client = BitgetApiClient(
        clock=clock, api_key="k", secret="s", passphrase="p", testnet=True
    )

    limiter = DummyLimiter()
    session = DummySession(DummyResponse(200, msgspec.json.encode({"ok": True})))

    client._limiter = limiter
    client._session = session
    client._ticker_response_decoder = SimpleNamespace(decode=lambda raw: {"ok": True})

    res = await client.get_api_v3_market_tickers(
        category="USDT-FUTURES", symbol="BTCUSDT"
    )

    assert res == {"ok": True}
    assert ("/api/v3/market/tickers", "/api/v3/market/tickers", 1) in limiter.calls
    assert session.requests
    assert session.requests[0]["method"] == "GET"
