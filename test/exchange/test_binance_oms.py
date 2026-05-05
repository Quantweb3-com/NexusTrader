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
from nexustrader.exchange.binance.schema import (
    BinanceUserDataStreamMsg,
    BinanceWsOrderResponse,
)
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


class DummyCache:
    def __init__(self, order=None):
        self.order = order

    def get_order(self, oid: str):
        return self.order


def make_oms(tmp_order, latest_order, cached_order=None):
    oms = BinanceOrderManagementSystem.__new__(BinanceOrderManagementSystem)
    oms._ws_msg_ws_api_response_decoder = msgspec.json.Decoder(BinanceWsOrderResponse)
    oms._ws_msg_general_decoder = msgspec.json.Decoder(BinanceUserDataStreamMsg)
    oms._pending_ws_acks = {}
    oms._registry = DummyRegistry(tmp_order)
    oms._clock = DummyClock()
    oms._task_manager = DummyTaskManager()
    oms._exchange_id = ExchangeType.BINANCE
    oms._account_type = SimpleNamespace(
        is_spot=False,
        is_linear=True,
        is_inverse=False,
    )
    oms._market_id = {"BTCUSDT_linear": tmp_order.symbol}
    oms._cache = DummyCache(cached_order)
    oms._cancel_success_reconcile_delay_sec = 0
    oms._listen_key_expired_handler = None
    oms._last_order_update_ts = 0
    oms._last_account_update_ts = 0
    oms._log = SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    oms.updated_orders = []
    oms.private_ws_events = []

    async def fetch_order(symbol: str, oid: str, force_refresh: bool = False):
        return latest_order

    oms.fetch_order = fetch_order
    oms.order_status_update = lambda order: oms.updated_orders.append(order)
    oms._publish_private_ws_event = lambda event: oms.private_ws_events.append(event)
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


@pytest.mark.asyncio
async def test_binance_cancel_success_with_terminal_status_dispatches_canceled():
    oid = "maker-3"
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
    oms = make_oms(tmp_order, latest_order=None)
    ack_future = asyncio.get_event_loop().create_future()
    oms._pending_ws_acks[oid] = ack_future

    oms._ws_api_msg_handler(
        msgspec.json.encode(
            {
                "id": f"c{oid}",
                "status": 200,
                "result": {
                    "orderId": 123,
                    "symbol": "BTCUSDT",
                    "clientOrderId": oid,
                    "status": "CANCELED",
                    "origQty": "0.01",
                    "executedQty": "0",
                    "price": "90000",
                    "avgPrice": "0",
                    "timeInForce": "GTC",
                    "type": "LIMIT",
                    "side": "BUY",
                    "updateTime": 1_001,
                    "reduceOnly": False,
                    "positionSide": "BOTH",
                },
            }
        )
    )

    assert ack_future.done()
    assert ack_future.exception() is None
    assert len(oms._task_manager.tasks) == 0
    assert len(oms.updated_orders) == 1
    assert oms.updated_orders[0].status == OrderStatus.CANCELED
    assert oms.updated_orders[0].remaining == Decimal("0.01")


@pytest.mark.asyncio
async def test_binance_cancel_success_without_status_reconciles_via_rest():
    oid = "maker-4"
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
                "status": 200,
                "result": {
                    "orderId": 124,
                    "symbol": "BTCUSDT",
                    "clientOrderId": oid,
                },
            }
        )
    )
    await oms._task_manager.tasks[0]

    assert ack_future.done()
    assert ack_future.exception() is None
    assert [order.status for order in oms.updated_orders] == [
        OrderStatus.CANCELING,
        OrderStatus.FILLED,
    ]


@pytest.mark.asyncio
async def test_binance_listen_key_expired_triggers_recovery_task():
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
    oms = make_oms(tmp_order, latest_order=None)

    async def recover():
        oms.private_ws_events.append("recovered")

    oms.set_listen_key_expired_handler(recover)
    oms._ws_msg_handler(msgspec.json.encode({"e": "listenKeyExpired"}))

    assert oms.private_ws_events == ["listen_key_expired"]
    assert len(oms._task_manager.tasks) == 1
    await oms._task_manager.tasks[0]
    assert oms.private_ws_events == ["listen_key_expired", "recovered"]
