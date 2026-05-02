import msgspec
import pytest

from nexustrader.core.nautilius_core import LiveClock
from nexustrader.exchange.binance.constants import (
    BinanceAccountType,
    BinanceRateLimiter,
)
from nexustrader.exchange.binance.rest_api import BinanceApiClient
from nexustrader.exchange.binance.schema import (
    BinanceSpotAccountInfo,
    BinanceFuturesAccountInfo,
)


class DummyLimiter(BinanceRateLimiter):
    def __init__(self):
        # disable underlying throttled behavior; we just count calls
        super().__init__(enable_rate_limit=False)
        self.calls: list[tuple[str, int]] = []

    async def api_weight_limit(self, cost: int = 1):
        self.calls.append(("api_weight_limit", cost))

    async def fapi_weight_limit(self, cost: int = 1):
        self.calls.append(("fapi_weight_limit", cost))


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
            {
                "method": method,
                "url": url,
                "headers": headers,
                "data": data,
            }
        )
        return self._response

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_get_api_v3_account_uses_async_fetch_and_limiter(monkeypatch):
    clock = LiveClock()

    dummy_account = BinanceSpotAccountInfo(
        makerCommission=0,
        takerCommission=0,
        buyerCommission=0,
        sellerCommission=0,
        canTrade=True,
        canWithdraw=True,
        canDeposit=True,
        updateTime=0,
        accountType="SPOT",
        balances=[],
        permissions=[],
    )
    raw = msgspec.json.encode(dummy_account)

    limiter = DummyLimiter()
    session = DummySession(DummyResponse(200, raw))

    client = BinanceApiClient(clock=clock, api_key="k", secret="s")
    # inject dummy limiter and session
    client._limiter = limiter
    client._session = session

    # patch base url to a stable value
    monkeypatch.setattr(
        client,
        "_get_base_url",
        lambda account_type: "https://api.test",
    )

    res = await client.get_api_v3_account()

    assert isinstance(res, BinanceSpotAccountInfo)
    # limiter called with expected cost
    assert ("api_weight_limit", 20) in limiter.calls
    # async session used
    assert session.requests
    assert session.requests[0]["method"] == "GET"


@pytest.mark.asyncio
async def test_get_fapi_v2_account_uses_async_fetch_and_limiter(monkeypatch):
    clock = LiveClock()

    dummy_account = BinanceFuturesAccountInfo(
        feeTier=0,
        canTrade=True,
        canDeposit=True,
        canWithdraw=True,
        updateTime=0,
        totalInitialMargin="0",
        totalMaintMargin="0",
        totalWalletBalance="0",
        totalUnrealizedProfit="0",
        totalMarginBalance="0",
        totalPositionInitialMargin="0",
        totalOpenOrderInitialMargin="0",
        totalCrossWalletBalance="0",
        totalCrossUnPnl="0",
        availableBalance="0",
        maxWithdrawAmount="0",
        assets=[],
        positions=[],
    )
    raw = msgspec.json.encode(dummy_account)

    limiter = DummyLimiter()
    session = DummySession(DummyResponse(200, raw))

    client = BinanceApiClient(clock=clock, api_key="k", secret="s")
    client._limiter = limiter
    client._session = session

    monkeypatch.setattr(
        client,
        "_get_base_url",
        lambda account_type: "https://fapi.test"
        if account_type == BinanceAccountType.USD_M_FUTURE
        else "https://other.test",
    )

    res = await client.get_fapi_v2_account()

    assert isinstance(res, BinanceFuturesAccountInfo)
    # limiter called with expected cost
    assert ("fapi_weight_limit", 5) in limiter.calls
    assert session.requests
    assert session.requests[0]["method"] == "GET"
