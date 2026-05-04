import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nexustrader.base.oms import OrderManagementSystem
from nexustrader.constants import ExchangeType, OrderSide, OrderStatus, OrderType
from nexustrader.schema import Order


class DummyOms(OrderManagementSystem):
    def _init_account_balance(self):
        pass

    def _init_position(self):
        pass

    def _position_mode_check(self):
        pass

    async def create_order(self, *args, **kwargs):
        pass

    async def create_order_ws(self, *args, **kwargs):
        pass

    async def create_batch_orders(self, *args, **kwargs):
        pass

    async def create_tp_sl_order(self, *args, **kwargs):
        pass

    async def cancel_order(self, *args, **kwargs):
        pass

    async def cancel_order_ws(self, *args, **kwargs):
        pass

    async def cancel_all_orders(self, *args, **kwargs):
        pass

    async def modify_order(self, *args, **kwargs):
        pass


class DummyCache:
    def __init__(self, order=None):
        self.order = order

    def get_order(self, oid: str):
        return self.order


class DummyTaskManager:
    def __init__(self):
        self.tasks = []

    def create_task(self, coro, name=None):
        task = asyncio.create_task(coro, name=name)
        self.tasks.append(task)
        return task


def make_oms(cached_order=None, latest_order=None):
    oms = DummyOms.__new__(DummyOms)
    oms._cache = DummyCache(cached_order)
    oms._task_manager = DummyTaskManager()
    oms._exchange_id = ExchangeType.BINANCE
    oms._cancel_success_reconcile_delay_sec = 0
    oms._log = SimpleNamespace(warning=lambda *args, **kwargs: None)
    oms.updated_orders = []

    async def fetch_order(symbol: str, oid: str, force_refresh: bool = False):
        return latest_order

    oms.fetch_order = fetch_order
    oms.order_status_update = lambda order: oms.updated_orders.append(order)
    return oms


def make_order(oid: str, symbol: str, status: OrderStatus):
    return Order(
        exchange=ExchangeType.BINANCE,
        symbol=symbol,
        oid=oid,
        status=status,
        amount=Decimal("0.01"),
        filled=Decimal("0"),
        remaining=Decimal("0.01"),
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        timestamp=1_000,
    )


@pytest.mark.asyncio
async def test_cancel_success_reconcile_skips_when_cache_is_already_closed():
    oid = "maker-closed"
    symbol = "BTCUSDT-PERP.BINANCE"
    cached_order = make_order(oid, symbol, OrderStatus.CANCELED)
    latest_order = make_order(oid, symbol, OrderStatus.FILLED)
    oms = make_oms(cached_order=cached_order, latest_order=latest_order)

    oms._schedule_cancel_success_reconcile(oid, symbol)
    await oms._task_manager.tasks[0]

    assert oms.updated_orders == []


@pytest.mark.asyncio
async def test_cancel_success_reconcile_updates_from_force_refresh():
    oid = "maker-open"
    symbol = "BTCUSDT-PERP.BINANCE"
    cached_order = make_order(oid, symbol, OrderStatus.CANCELING)
    latest_order = make_order(oid, symbol, OrderStatus.FILLED)
    oms = make_oms(cached_order=cached_order, latest_order=latest_order)

    oms._schedule_cancel_success_reconcile(oid, symbol)
    await oms._task_manager.tasks[0]

    assert oms.updated_orders == [latest_order]
