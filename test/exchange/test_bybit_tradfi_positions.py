import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nexustrader.constants import ExchangeType, PositionSide
from nexustrader.core.cache import AsyncCache
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock, MessageBus
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.bybit_tradfi.constants import BybitTradeFiAccountType
from nexustrader.exchange.bybit_tradfi.exchange import BybitTradeFiExchangeManager
from nexustrader.exchange.bybit_tradfi.oms import BybitTradeFiOrderManagementSystem
from nexustrader.schema import Position


@pytest.fixture
async def tradfi_oms(tmp_path):
    clock = LiveClock()
    task_manager = TaskManager(asyncio.get_event_loop())
    cache = AsyncCache(
        strategy_id="test",
        user_id="user",
        msgbus=MessageBus("TEST-001", clock),
        clock=clock,
        task_manager=task_manager,
        db_path=str(tmp_path / "cache.db"),
    )
    await cache._init_storage()

    exchange = BybitTradeFiExchangeManager({})
    exchange.market_id["XAUUSD.s"] = "XAUUSD_s.BYBIT_TRADFI"

    oms = BybitTradeFiOrderManagementSystem(
        account_type=BybitTradeFiAccountType.DEMO,
        exchange=exchange,
        registry=OrderRegistry(),
        cache=cache,
        clock=clock,
        msgbus=MessageBus("TEST-001", clock),
        task_manager=task_manager,
    )

    try:
        yield oms, cache
    finally:
        await cache.close()
        exchange.close()


@pytest.mark.asyncio
async def test_tradfi_refresh_positions_writes_nexus_symbol(tradfi_oms):
    oms, cache = tradfi_oms
    oms._mt5_positions_get = lambda: [
        SimpleNamespace(
            symbol="XAUUSD.s",
            type=0,
            volume=1.25,
            price_open=2310.5,
            profit=12.3,
        )
    ]

    await oms._async_refresh_positions()

    position = cache.get_position("XAUUSD_s.BYBIT_TRADFI")
    assert position is not None
    assert position.exchange == ExchangeType.BYBIT_TRADFI
    assert position.side == PositionSide.LONG
    assert position.signed_amount == Decimal("1.25")
    assert position.entry_price == 2310.5
    assert position.unrealized_pnl == 12.3


@pytest.mark.asyncio
async def test_tradfi_refresh_positions_clears_stale_positions(tradfi_oms):
    oms, cache = tradfi_oms
    cache._apply_position(
        Position(
            symbol="XAUUSD_s.BYBIT_TRADFI",
            exchange=ExchangeType.BYBIT_TRADFI,
            side=PositionSide.LONG,
            signed_amount=Decimal("1"),
        )
    )
    oms._mt5_positions_get = lambda: []

    await oms._async_refresh_positions()

    assert cache.get_position("XAUUSD_s.BYBIT_TRADFI") is None
