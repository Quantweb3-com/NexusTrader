import asyncio
from decimal import Decimal
from types import SimpleNamespace

import msgspec
import pytest

from nexustrader.constants import (
    ExchangeType,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from nexustrader.exchange.binance.oms import BinanceOrderManagementSystem
from nexustrader.exchange.binance.schema import BinanceWsOrderResponse
from nexustrader.schema import Order


class DummyRegistry:
    def __init__(self, tmp_order):
        self._tmp_order = tmp_order

    def get_tmp_order(self, oid: str):
        return self._tmp_order


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


def make_oms(tmp_order, latest_order):
    oms = BinanceOrderManagementSystem.__new__(BinanceOrderManagementSystem)
    oms._ws_msg_ws_api_response_decoder = msgspec.json.Decoder(BinanceWsOrderResponse)
    oms._pending_ws_acks = {}
    oms._registry = DummyRegistry(tmp_order)
    oms._clock = DummyClock()
    oms._task_manager = DummyTaskManager()
    oms._exchange_id = ExchangeType.BINANCE
    oms._log = SimpleNamespace(
        error=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    oms.updated_orders = []

    async def fetch_order(symbol: str, oid: str, force_refresh: bool = False):
        return latest_order

    oms.fetch_order = fetch_order
    oms.order_status_update = lambda order: oms.updated_orders.append(order)
    return oms


@pytest.mark.asyncio
async def test_binance_cancel_unknown_order_reconciles_closed_order_via_rest():
    oid = "maker-1"
    symbol = "BTCUSDT-PERP.BINANCE"
    tmp_order = SimpleNamespace(
        symbol=symbol,
        amount=Decimal("0.01"),
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        price=Decimal("90000"),
        time_in_force=TimeInForce.GTC,
        reduce_only=False,
    )
    latest_order = Order(
        exchange=ExchangeType.BINANCE,
        symbol=symbol,
        oid=oid,
        status=OrderStatus.FILLED,
        amount=Decimal("0.01"),
        filled=Decimal("0.01"),
        remaining=Decimal("0"),
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        price=Decimal("90000"),
        timestamp=1_001,
    )
    oms = make_oms(tmp_order, latest_order)
    ack_future = asyncio.get_event_loop().create_future()
    oms._pending_ws_acks[oid] = ack_future

    oms._ws_api_msg_handler(
        msgspec.json.encode(
            {
                "id": f"c{oid}",
                "status": 400,
                "error": {"code": -2011, "msg": "Unknown order sent."},
            }
        )
    )
    await oms._task_manager.tasks[0]

    assert ack_future.done()
    assert not ack_future.cancelled()
    assert ack_future.exception() is None
    assert oms.updated_orders == [latest_order]


@pytest.mark.asyncio
async def test_binance_cancel_unknown_order_rejects_when_rest_still_open():
    oid = "maker-2"
    symbol = "BTCUSDT-PERP.BINANCE"
    tmp_order = SimpleNamespace(
        symbol=symbol,
        amount=Decimal("0.01"),
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        price=Decimal("90000"),
        time_in_force=TimeInForce.GTC,
        reduce_only=False,
    )
    latest_order = Order(
        exchange=ExchangeType.BINANCE,
        symbol=symbol,
        oid=oid,
        status=OrderStatus.ACCEPTED,
        amount=Decimal("0.01"),
        filled=Decimal("0"),
        remaining=Decimal("0.01"),
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        price=Decimal("90000"),
        timestamp=1_001,
    )
    oms = make_oms(tmp_order, latest_order)
    ack_future = asyncio.get_event_loop().create_future()
    oms._pending_ws_acks[oid] = ack_future

    oms._ws_api_msg_handler(
        msgspec.json.encode(
            {
                "id": f"c{oid}",
                "status": 400,
                "error": {"code": -2011, "msg": "Unknown order sent."},
            }
        )
    )
    await oms._task_manager.tasks[0]

    assert ack_future.done()
    assert ack_future.exception() is not None
    assert oms.updated_orders == [latest_order]
