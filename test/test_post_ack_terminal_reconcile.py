import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nexustrader.base.oms import OrderManagementSystem
from nexustrader.constants import (
    ExchangeType,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
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
    def __init__(self, order):
        self.order = order

    def get_order(self, oid: str):
        if self.order is not None and self.order.oid == oid:
            return self.order
        return None

    def update_order_status(self, order):
        self.order = order
        return True


class DummyRegistry:
    def __init__(self, registered=True):
        self.registered = registered

    def is_registered(self, oid: str):
        return self.registered

    def unregister_order(self, oid: str):
        self.registered = False

    def unregister_tmp_order(self, oid: str):
        pass


class DummyTaskManager:
    def __init__(self):
        self.tasks = []

    def create_task(self, coro, name=None):
        task = asyncio.create_task(coro, name=name)
        self.tasks.append(task)
        return task


def make_order(
    oid: str = "oid-1",
    status: OrderStatus = OrderStatus.PENDING,
    order_type: OrderType = OrderType.MARKET,
    time_in_force: TimeInForce = TimeInForce.GTC,
    filled: Decimal = Decimal("0"),
):
    return Order(
        exchange=ExchangeType.BINANCE,
        symbol="BTCUSDT-PERP.BINANCE",
        oid=oid,
        eid="123",
        status=status,
        amount=Decimal("0.01"),
        filled=filled,
        remaining=Decimal("0.01") - filled,
        type=order_type,
        side=OrderSide.BUY,
        time_in_force=time_in_force,
        timestamp=1_000,
    )


def make_oms(cached_order, latest_orders):
    oms = DummyOms.__new__(DummyOms)
    oms._cache = DummyCache(cached_order)
    oms._registry = DummyRegistry()
    oms._task_manager = DummyTaskManager()
    oms._exchange_id = ExchangeType.BINANCE
    oms._post_ack_terminal_reconcile_delay_sec = 0
    oms._post_ack_terminal_reconcile_max_attempts = len(latest_orders)
    oms._post_ack_terminal_reconcile_oids = set()
    oms._log = SimpleNamespace(warning=lambda *args, **kwargs: None)
    oms.updated_orders = []
    oms.fetch_calls = []
    latest_iter = iter(latest_orders)

    async def fetch_order(symbol: str, oid: str, force_refresh: bool = False):
        oms.fetch_calls.append((symbol, oid, force_refresh))
        return next(latest_iter)

    def order_status_update(order):
        oms.updated_orders.append(order)
        oms._cache.update_order_status(order)
        if order.is_closed:
            oms._registry.unregister_order(order.oid)

    oms.fetch_order = fetch_order
    oms.order_status_update = order_status_update
    return oms


def test_post_ack_terminal_reconcile_ignores_gtc_limit_orders():
    order = make_order(order_type=OrderType.LIMIT, time_in_force=TimeInForce.GTC)
    oms = make_oms(order, [order])

    oms._schedule_post_ack_terminal_reconcile(order)

    assert oms._task_manager.tasks == []


@pytest.mark.asyncio
async def test_post_ack_terminal_reconcile_updates_market_order_from_rest():
    cached = make_order(status=OrderStatus.PENDING, order_type=OrderType.MARKET)
    latest = make_order(status=OrderStatus.FILLED, order_type=OrderType.MARKET)
    latest.filled = latest.amount
    latest.remaining = Decimal("0")
    oms = make_oms(cached, [latest])

    oms._schedule_post_ack_terminal_reconcile(cached)
    await oms._task_manager.tasks[0]

    assert oms.fetch_calls == [(cached.symbol, cached.oid, True)]
    assert oms.updated_orders == [latest]
    assert oms._cache.get_order(cached.oid).status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_post_ack_terminal_reconcile_retries_until_terminal():
    cached = make_order(status=OrderStatus.PENDING, order_type=OrderType.MARKET)
    still_pending = make_order(status=OrderStatus.PENDING, order_type=OrderType.MARKET)
    latest = make_order(status=OrderStatus.FILLED, order_type=OrderType.MARKET)
    latest.filled = latest.amount
    latest.remaining = Decimal("0")
    oms = make_oms(cached, [still_pending, latest])

    oms._schedule_post_ack_terminal_reconcile(cached)
    oms._schedule_post_ack_terminal_reconcile(cached)
    await oms._task_manager.tasks[0]

    assert len(oms._task_manager.tasks) == 1
    assert len(oms.fetch_calls) == 2
    assert oms.updated_orders == [latest]


@pytest.mark.asyncio
async def test_post_ack_terminal_reconcile_updates_ioc_limit_order():
    cached = make_order(
        status=OrderStatus.PENDING,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.IOC,
    )
    latest = make_order(
        status=OrderStatus.CANCELED,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.IOC,
    )
    oms = make_oms(cached, [latest])

    oms._schedule_post_ack_terminal_reconcile(cached)
    await oms._task_manager.tasks[0]

    assert oms.updated_orders == [latest]
