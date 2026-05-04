import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nexustrader.constants import (
    ExchangeType,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from nexustrader.exchange.bitget.oms import BitgetOrderManagementSystem
from nexustrader.exchange.bybit.oms import BybitOrderManagementSystem
from nexustrader.exchange.hyperliquid.oms import HyperLiquidOrderManagementSystem
from nexustrader.exchange.okx.oms import OkxOrderManagementSystem
from nexustrader.schema import Order


class DummyClock:
    def timestamp_ms(self) -> int:
        return 1_000


class DummyTaskManager:
    def __init__(self):
        self.tasks = []

    def create_task(self, coro, name=None):
        task = asyncio.create_task(coro, name=name)
        self.tasks.append(task)
        return task


class DummyLog:
    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


OMS_CASES = [
    (BitgetOrderManagementSystem, ExchangeType.BITGET),
    (BybitOrderManagementSystem, ExchangeType.BYBIT),
    (OkxOrderManagementSystem, ExchangeType.OKX),
    (HyperLiquidOrderManagementSystem, ExchangeType.HYPERLIQUID),
]


def make_tmp_order(symbol: str) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        amount=Decimal("0.01"),
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        price=Decimal("90000"),
        time_in_force=TimeInForce.GTC,
        reduce_only=False,
    )


def make_order(exchange: ExchangeType, symbol: str, oid: str, status: OrderStatus):
    is_closed = status in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.EXPIRED}
    return Order(
        exchange=exchange,
        symbol=symbol,
        oid=oid,
        status=status,
        amount=Decimal("0.01"),
        filled=Decimal("0.01") if status == OrderStatus.FILLED else Decimal("0"),
        remaining=Decimal("0") if is_closed else Decimal("0.01"),
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        price=Decimal("90000"),
        timestamp=1_001,
    )


def make_oms(oms_cls, exchange: ExchangeType, latest_order):
    oms = oms_cls.__new__(oms_cls)
    oms._pending_ws_acks = {}
    oms._exchange_id = exchange
    oms._clock = DummyClock()
    oms._task_manager = DummyTaskManager()
    oms._log = DummyLog()
    oms.updated_orders = []

    async def fetch_order(symbol: str, oid: str, force_refresh: bool = False):
        return latest_order

    oms.fetch_order = fetch_order
    oms.order_status_update = lambda order: oms.updated_orders.append(order)
    return oms


@pytest.mark.parametrize(("oms_cls", "exchange"), OMS_CASES)
@pytest.mark.asyncio
async def test_cancel_reconcile_resolves_closed_rest_state(oms_cls, exchange):
    oid = "maker-closed"
    symbol = f"BTCUSDT-PERP.{exchange.value.upper()}"
    tmp_order = make_tmp_order(symbol)
    latest_order = make_order(exchange, symbol, oid, OrderStatus.FILLED)
    oms = make_oms(oms_cls, exchange, latest_order)
    ack_future = asyncio.get_event_loop().create_future()
    oms._pending_ws_acks[oid] = ack_future

    await oms._reconcile_cancel_rejected_order(
        oid, tmp_order, "Order does not exist or already filled"
    )

    assert ack_future.done()
    assert ack_future.exception() is None
    assert oms.updated_orders == [latest_order]


@pytest.mark.parametrize(("oms_cls", "exchange"), OMS_CASES)
@pytest.mark.asyncio
async def test_cancel_reconcile_rejects_still_open_rest_state(oms_cls, exchange):
    oid = "maker-open"
    symbol = f"BTCUSDT-PERP.{exchange.value.upper()}"
    tmp_order = make_tmp_order(symbol)
    latest_order = make_order(exchange, symbol, oid, OrderStatus.ACCEPTED)
    oms = make_oms(oms_cls, exchange, latest_order)
    ack_future = asyncio.get_event_loop().create_future()
    oms._pending_ws_acks[oid] = ack_future

    await oms._reconcile_cancel_rejected_order(
        oid, tmp_order, "Order does not exist"
    )

    assert ack_future.done()
    assert ack_future.exception() is not None
    assert oms.updated_orders == [latest_order]


@pytest.mark.parametrize(("oms_cls", "exchange"), OMS_CASES)
@pytest.mark.asyncio
async def test_cancel_reconcile_marks_failed_when_rest_has_no_order(oms_cls, exchange):
    oid = "maker-missing"
    symbol = f"BTCUSDT-PERP.{exchange.value.upper()}"
    tmp_order = make_tmp_order(symbol)
    oms = make_oms(oms_cls, exchange, None)
    ack_future = asyncio.get_event_loop().create_future()
    oms._pending_ws_acks[oid] = ack_future

    await oms._reconcile_cancel_rejected_order(oid, tmp_order, "Order not found")

    assert ack_future.done()
    assert ack_future.exception() is not None
    assert len(oms.updated_orders) == 1
    assert oms.updated_orders[0].status == OrderStatus.CANCEL_FAILED
