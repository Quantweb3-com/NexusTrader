"""
Tests for the three remaining fix areas:

1. _confirm_missing_open_orders() uses force_refresh=True (reconnect reconcile path)
2. Strategy.fetch_order() exposes force_refresh parameter
3. EMS _create_order_ws / _cancel_order_ws publish structured ws_order_request_result events
   for WsAckRejectedError, WsAckTimeoutError, WsRequestNotSentError
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from nexustrader.constants import ExchangeType, OrderSide, OrderStatus, OrderType, WsOrderResultType
from nexustrader.error import WsAckRejectedError, WsAckTimeoutError, WsRequestNotSentError
from nexustrader.schema import Order


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_clock():
    from nexustrader.core.nautilius_core import LiveClock
    return LiveClock()


def _make_msgbus():
    from nexustrader.core.nautilius_core import MessageBus, TraderId, LiveClock
    return MessageBus(trader_id=TraderId("TEST-001"), clock=LiveClock())


def _make_registry():
    from nexustrader.core.registry import OrderRegistry
    return OrderRegistry()


def _make_task_manager():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from nexustrader.core.entity import TaskManager
    return TaskManager(loop=loop, enable_signal_handlers=False), loop


def _make_order(oid: str, symbol: str, status=OrderStatus.ACCEPTED) -> Order:
    return Order(
        oid=oid,
        exchange=ExchangeType.OKX,
        symbol=symbol,
        status=status,
        amount=Decimal("0.01"),
        type=OrderType.LIMIT,
        side=OrderSide.BUY,
        price=90000.0,
        timestamp=0,
    )


# ===========================================================================
# 1. _confirm_missing_open_orders – must pass force_refresh=True
# ===========================================================================


class TestConfirmMissingOpenOrdersForcesRefresh:
    """_confirm_missing_open_orders must query the exchange, not the local cache."""

    def _make_concrete_oms(self):
        from nexustrader.exchange.okx.oms import OkxOrderManagementSystem

        with (
            patch.object(OkxOrderManagementSystem, "_init_account_balance"),
            patch.object(OkxOrderManagementSystem, "_init_position"),
            patch.object(OkxOrderManagementSystem, "_position_mode_check"),
        ):
            oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)
        oms._log = MagicMock()
        oms._reconnect_reconcile_grace_ms = 0
        return oms

    @pytest.mark.asyncio
    async def test_calls_fetch_order_with_force_refresh_true(self):
        """Every missing oid must be confirmed with force_refresh=True."""
        oms = self._make_concrete_oms()

        symbol = "BTCUSDT-PERP.OKX"
        oid = "reconnect-oid-001"
        cached_order = _make_order(oid, symbol)

        cache = MagicMock()
        cache.get_order = MagicMock(return_value=cached_order)
        oms._cache = cache

        fresh_order = _make_order(oid, symbol, status=OrderStatus.FILLED)
        oms.fetch_order = AsyncMock(return_value=fresh_order)
        oms.order_status_update = MagicMock()

        confirmed = await oms._confirm_missing_open_orders({oid}, grace_ms=0)

        oms.fetch_order.assert_awaited_once_with(symbol, oid, force_refresh=True)
        assert oid in confirmed

    @pytest.mark.asyncio
    async def test_multiple_oids_all_use_force_refresh(self):
        """All missing oids must be fetched with force_refresh=True."""
        oms = self._make_concrete_oms()

        symbol = "BTCUSDT-PERP.OKX"
        oids = {"oid-a", "oid-b", "oid-c"}

        def _get_order(oid):
            return _make_order(oid, symbol)

        cache = MagicMock()
        cache.get_order = MagicMock(side_effect=_get_order)
        oms._cache = cache

        closed_order = _make_order("x", symbol, status=OrderStatus.CANCELED)

        async def _fetch(sym, o, force_refresh=False):
            assert force_refresh is True, "force_refresh must be True in reconnect reconcile"
            closed_order.oid = o
            return closed_order

        oms.fetch_order = _fetch
        oms.order_status_update = MagicMock()

        confirmed = await oms._confirm_missing_open_orders(oids, grace_ms=0)
        assert confirmed == oids

    @pytest.mark.asyncio
    async def test_fetch_returning_none_keeps_order_open(self):
        """If fetch_order returns None for an oid, it must NOT be added to confirmed_closed."""
        oms = self._make_concrete_oms()

        symbol = "BTCUSDT-PERP.OKX"
        oid = "oid-unconfirmed"
        cache = MagicMock()
        cache.get_order = MagicMock(return_value=_make_order(oid, symbol))
        oms._cache = cache

        oms.fetch_order = AsyncMock(return_value=None)
        oms.order_status_update = MagicMock()

        confirmed = await oms._confirm_missing_open_orders({oid}, grace_ms=0)

        oms.fetch_order.assert_awaited_once_with(symbol, oid, force_refresh=True)
        assert len(confirmed) == 0
        oms.order_status_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_exception_is_swallowed_keeps_order_open(self):
        """A REST error during confirmation must be swallowed conservatively."""
        oms = self._make_concrete_oms()

        symbol = "BTCUSDT-PERP.OKX"
        oid = "oid-rest-error"
        cache = MagicMock()
        cache.get_order = MagicMock(return_value=_make_order(oid, symbol))
        oms._cache = cache

        oms.fetch_order = AsyncMock(side_effect=RuntimeError("REST timeout"))
        oms.order_status_update = MagicMock()

        confirmed = await oms._confirm_missing_open_orders({oid}, grace_ms=0)

        assert len(confirmed) == 0
        oms.order_status_update.assert_not_called()


# ===========================================================================
# 2. Strategy.fetch_order – force_refresh is forwarded
# ===========================================================================


class TestStrategyFetchOrderForceRefresh:
    """Strategy.fetch_order must pass force_refresh to OMS.fetch_order."""

    def _make_strategy_with_mock_oms(self):
        from nexustrader.strategy import Strategy

        strategy = Strategy()
        strategy._initialized = True
        strategy._oidgen = MagicMock()

        fresh_order = _make_order("oid-s1", "BTCUSDT-PERP.OKX")

        mock_oms = MagicMock()
        mock_oms.fetch_order = AsyncMock(return_value=fresh_order)

        tm, loop = _make_task_manager()
        mock_connector = MagicMock()
        mock_connector._oms = mock_oms
        mock_connector._task_manager = tm

        from nexustrader.constants import AccountType

        strategy._private_connectors = {}
        strategy._get_private_connector = MagicMock(return_value=mock_connector)

        return strategy, mock_oms, fresh_order

    def test_fetch_order_default_no_force_refresh(self):
        """By default force_refresh=False is forwarded to OMS."""
        strategy, mock_oms, expected = self._make_strategy_with_mock_oms()

        result = strategy.fetch_order("BTCUSDT-PERP.OKX", "oid-s1")

        mock_oms.fetch_order.assert_awaited_once_with(
            "BTCUSDT-PERP.OKX", "oid-s1", force_refresh=False
        )
        assert result == expected

    def test_fetch_order_with_force_refresh_true(self):
        """force_refresh=True must be forwarded to OMS."""
        strategy, mock_oms, expected = self._make_strategy_with_mock_oms()

        result = strategy.fetch_order("BTCUSDT-PERP.OKX", "oid-s1", force_refresh=True)

        mock_oms.fetch_order.assert_awaited_once_with(
            "BTCUSDT-PERP.OKX", "oid-s1", force_refresh=True
        )
        assert result == expected


# ===========================================================================
# 3. EMS _create_order_ws_task / _cancel_order_ws_task publish structured events
# ===========================================================================


class TestEmsWsOrderRequestResultEvents:
    """
    EMS must catch WsAck* errors from OMS and publish ws_order_request_result events
    instead of letting them propagate as unhandled background task exceptions.
    """

    def _make_ems(self, msgbus=None):
        """Build a minimal concrete EMS with a real msgbus for event capture."""
        from nexustrader.base.ems import ExecutionManagementSystem
        from nexustrader.schema import InstrumentId

        # Concrete stub subclass
        class _StubEMS(ExecutionManagementSystem):
            def _instrument_id_to_account_type(self, iid):
                return "stub"

            def _build_order_submit_queues(self):
                pass

            def _set_account_type(self):
                pass

            def _submit_order(self, order, submit_type, account_type=None):
                pass

            def _get_min_order_amount(self, symbol, market, px):
                return Decimal("0.001")

        tm, loop = _make_task_manager()
        mb = msgbus or _make_msgbus()
        ems = _StubEMS.__new__(_StubEMS)
        ems._log = MagicMock()
        ems._clock = _make_clock()
        ems._msgbus = mb
        ems._task_manager = tm
        ems._registry = _make_registry()
        ems._cache = MagicMock()
        ems._private_connectors = {}
        ems._is_mock = False
        return ems, mb, tm._loop

    def _make_order_submit(self, oid="oid-ems-001", symbol="BTCUSDT-PERP.OKX"):
        from nexustrader.schema import CreateOrderSubmit, InstrumentId

        return CreateOrderSubmit(
            oid=oid,
            symbol=symbol,
            instrument_id=InstrumentId.from_str(symbol),
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("90000"),
        )

    def _make_cancel_submit(self, oid="oid-cancel-001", symbol="BTCUSDT-PERP.OKX"):
        from nexustrader.schema import CancelOrderSubmit, InstrumentId

        return CancelOrderSubmit(
            oid=oid,
            symbol=symbol,
            instrument_id=InstrumentId.from_str(symbol),
        )

    @pytest.mark.asyncio
    async def test_create_order_ws_ack_rejected_publishes_event(self):
        """WsAckRejectedError from OMS must produce a ws_order_request_result event."""
        ems, msgbus, loop = self._make_ems()

        captured = []
        msgbus.subscribe(topic="ws_order_request_result", handler=lambda m: captured.append(m))

        mock_oms = MagicMock()
        mock_oms.create_order_ws = AsyncMock(
            side_effect=WsAckRejectedError(oid="oid-ems-001", reason="Insufficient balance")
        )
        mock_connector = MagicMock()
        mock_connector._oms = mock_oms
        ems._private_connectors["stub"] = mock_connector

        order_submit = self._make_order_submit("oid-ems-001")

        await ems._create_order_ws_task(order_submit, "stub")

        assert len(captured) == 1
        evt = captured[0]
        assert evt["oid"] == "oid-ems-001"
        assert evt["result_type"] == WsOrderResultType.ACK_REJECTED
        assert "Insufficient balance" in evt["reason"]
        assert evt["symbol"] == "BTCUSDT-PERP.OKX"

    @pytest.mark.asyncio
    async def test_create_order_ws_ack_timeout_publishes_event(self):
        """WsAckTimeoutError from OMS must produce a ws_order_request_result event."""
        ems, msgbus, loop = self._make_ems()

        captured = []
        msgbus.subscribe(topic="ws_order_request_result", handler=lambda m: captured.append(m))

        mock_oms = MagicMock()
        mock_oms.create_order_ws = AsyncMock(
            side_effect=WsAckTimeoutError(oid="oid-ems-002", timeout=5.0)
        )
        mock_connector = MagicMock()
        mock_connector._oms = mock_oms
        ems._private_connectors["stub"] = mock_connector

        order_submit = self._make_order_submit("oid-ems-002")

        await ems._create_order_ws_task(order_submit, "stub")

        assert len(captured) == 1
        evt = captured[0]
        assert evt["oid"] == "oid-ems-002"
        assert evt["result_type"] == WsOrderResultType.ACK_TIMEOUT

    @pytest.mark.asyncio
    async def test_create_order_ws_request_not_sent_publishes_event(self):
        """WsRequestNotSentError re-raised by OMS must produce a ws_order_request_result event."""
        ems, msgbus, loop = self._make_ems()

        captured = []
        msgbus.subscribe(topic="ws_order_request_result", handler=lambda m: captured.append(m))

        mock_oms = MagicMock()
        mock_oms.create_order_ws = AsyncMock(
            side_effect=WsRequestNotSentError("socket down")
        )
        mock_connector = MagicMock()
        mock_connector._oms = mock_oms
        ems._private_connectors["stub"] = mock_connector

        order_submit = self._make_order_submit("oid-ems-003")

        await ems._create_order_ws_task(order_submit, "stub")

        assert len(captured) == 1
        evt = captured[0]
        assert evt["result_type"] == WsOrderResultType.REQUEST_NOT_SENT

    @pytest.mark.asyncio
    async def test_cancel_order_ws_ack_rejected_publishes_event(self):
        """WsAckRejectedError from cancel OMS must produce a ws_order_request_result event."""
        ems, msgbus, loop = self._make_ems()

        captured = []
        msgbus.subscribe(topic="ws_order_request_result", handler=lambda m: captured.append(m))

        mock_oms = MagicMock()
        mock_oms.cancel_order_ws = AsyncMock(
            side_effect=WsAckRejectedError(oid="oid-cancel-001", reason="order not found")
        )
        mock_connector = MagicMock()
        mock_connector._oms = mock_oms
        ems._private_connectors["stub"] = mock_connector

        cancel_submit = self._make_cancel_submit("oid-cancel-001")

        await ems._cancel_order_ws_task(cancel_submit, "stub")

        assert len(captured) == 1
        evt = captured[0]
        assert evt["oid"] == "oid-cancel-001"
        assert evt["result_type"] == WsOrderResultType.ACK_REJECTED
        assert "order not found" in evt["reason"]

    @pytest.mark.asyncio
    async def test_cancel_order_ws_ack_timeout_publishes_event(self):
        """WsAckTimeoutError from cancel OMS must produce a ws_order_request_result event."""
        ems, msgbus, loop = self._make_ems()

        captured = []
        msgbus.subscribe(topic="ws_order_request_result", handler=lambda m: captured.append(m))

        mock_oms = MagicMock()
        mock_oms.cancel_order_ws = AsyncMock(
            side_effect=WsAckTimeoutError(oid="oid-cancel-002", timeout=5.0)
        )
        mock_connector = MagicMock()
        mock_connector._oms = mock_oms
        ems._private_connectors["stub"] = mock_connector

        cancel_submit = self._make_cancel_submit("oid-cancel-002")

        await ems._cancel_order_ws_task(cancel_submit, "stub")

        assert len(captured) == 1
        evt = captured[0]
        assert evt["result_type"] == WsOrderResultType.ACK_TIMEOUT

    @pytest.mark.asyncio
    async def test_successful_create_order_ws_publishes_no_event(self):
        """A successful WS order must NOT produce a ws_order_request_result event."""
        ems, msgbus, loop = self._make_ems()

        captured = []
        msgbus.subscribe(topic="ws_order_request_result", handler=lambda m: captured.append(m))

        mock_oms = MagicMock()
        mock_oms.create_order_ws = AsyncMock(return_value=None)
        mock_connector = MagicMock()
        mock_connector._oms = mock_oms
        ems._private_connectors["stub"] = mock_connector

        order_submit = self._make_order_submit("oid-success")

        await ems._create_order_ws_task(order_submit, "stub")

        assert len(captured) == 0

    @pytest.mark.asyncio
    async def test_event_payload_has_all_required_fields(self):
        """ws_order_request_result events must carry oid/symbol/exchange/result_type/reason/timestamp."""
        ems, msgbus, loop = self._make_ems()

        captured = []
        msgbus.subscribe(topic="ws_order_request_result", handler=lambda m: captured.append(m))

        mock_oms = MagicMock()
        mock_oms.create_order_ws = AsyncMock(
            side_effect=WsAckRejectedError(oid="oid-fields", reason="price out of range")
        )
        mock_connector = MagicMock()
        mock_connector._oms = mock_oms
        ems._private_connectors["stub"] = mock_connector

        order_submit = self._make_order_submit("oid-fields")
        await ems._create_order_ws_task(order_submit, "stub")

        evt = captured[0]
        required_keys = {"oid", "symbol", "exchange", "result_type", "reason", "timestamp"}
        assert required_keys.issubset(evt.keys()), f"Missing keys: {required_keys - evt.keys()}"
        assert isinstance(evt["timestamp"], int)
        assert evt["exchange"] == ExchangeType.OKX.value


# ===========================================================================
# 4. Strategy.on_ws_order_request_result – callback is registered and invoked
# ===========================================================================


class TestStrategyWsOrderRequestResultCallback:
    """Strategy must receive ws_order_request_result events via on_ws_order_request_result."""

    def _make_minimal_strategy(self):
        from nexustrader.strategy import Strategy
        from nexustrader.constants import AccountType

        strategy = Strategy()

        tm, loop = _make_task_manager()
        msgbus = _make_msgbus()

        # Minimal _init_core wiring without real connectors
        strategy._initialized = False
        strategy.cache = MagicMock()
        strategy.clock = _make_clock()
        strategy._oidgen = MagicMock()
        strategy._ems = {}
        strategy._sms = MagicMock()
        strategy._task_manager = tm
        strategy._msgbus = msgbus
        strategy._private_connectors = {}
        strategy._public_connectors = {}
        strategy._exchanges = {}
        strategy._indicator_manager = MagicMock()
        strategy._state_exporter = None

        # Register all endpoints/topics as _init_core would
        msgbus.register(endpoint="pending", handler=strategy.on_pending_order)
        msgbus.register(endpoint="accepted", handler=strategy.on_accepted_order)
        msgbus.register(endpoint="partially_filled", handler=strategy.on_partially_filled_order)
        msgbus.register(endpoint="filled", handler=strategy.on_filled_order)
        msgbus.register(endpoint="canceling", handler=strategy.on_canceling_order)
        msgbus.register(endpoint="canceled", handler=strategy.on_canceled_order)
        msgbus.register(endpoint="failed", handler=strategy.on_failed_order)
        msgbus.register(endpoint="cancel_failed", handler=strategy.on_cancel_failed_order)
        msgbus.register(endpoint="balance", handler=strategy.on_balance)
        msgbus.subscribe(topic="private_ws_status", handler=strategy.on_private_ws_status)
        msgbus.subscribe(topic="private_ws_resync_diff", handler=strategy.on_private_ws_resync_diff)
        msgbus.subscribe(topic="ws_order_request_result", handler=strategy.on_ws_order_request_result)

        strategy._initialized = True
        return strategy, msgbus

    def test_on_ws_order_request_result_called_on_publish(self):
        """Publishing ws_order_request_result topic must invoke on_ws_order_request_result."""
        strategy, msgbus = self._make_minimal_strategy()

        received = []
        strategy.on_ws_order_request_result = lambda r: received.append(r)
        # Re-subscribe after monkey-patch so the new callable is registered
        msgbus.subscribe(topic="ws_order_request_result", handler=strategy.on_ws_order_request_result)

        payload = {
            "oid": "oid-cb-001",
            "symbol": "BTCUSDT-PERP.OKX",
            "exchange": ExchangeType.OKX.value,
            "result_type": WsOrderResultType.ACK_REJECTED,
            "reason": "Insufficient balance",
            "timestamp": 1700000000000,
        }
        msgbus.publish(topic="ws_order_request_result", msg=payload)

        assert len(received) == 1
        assert received[0]["oid"] == "oid-cb-001"
        assert received[0]["result_type"] == WsOrderResultType.ACK_REJECTED

    def test_on_ws_order_request_result_timeout_result_type(self):
        """ACK_TIMEOUT result type must be delivered correctly."""
        strategy, msgbus = self._make_minimal_strategy()

        received = []
        strategy.on_ws_order_request_result = lambda r: received.append(r)
        msgbus.subscribe(topic="ws_order_request_result", handler=strategy.on_ws_order_request_result)

        payload = {
            "oid": "oid-cb-002",
            "symbol": "BTCUSDT-PERP.BINANCE",
            "exchange": ExchangeType.BINANCE.value,
            "result_type": WsOrderResultType.ACK_TIMEOUT,
            "reason": "No WS ACK received for oid=oid-cb-002 within 5.0s",
            "timestamp": 1700000001000,
        }
        msgbus.publish(topic="ws_order_request_result", msg=payload)

        assert len(received) == 1
        assert received[0]["result_type"] == WsOrderResultType.ACK_TIMEOUT


# ===========================================================================
# 5. WsOrderResultType enum sanity checks
# ===========================================================================


class TestWsOrderResultTypeEnum:
    def test_all_expected_values_present(self):
        assert WsOrderResultType.REQUEST_NOT_SENT == "REQUEST_NOT_SENT"
        assert WsOrderResultType.ACK_REJECTED == "ACK_REJECTED"
        assert WsOrderResultType.ACK_TIMEOUT == "ACK_TIMEOUT"
        assert WsOrderResultType.ACK_TIMEOUT_CONFIRMED == "ACK_TIMEOUT_CONFIRMED"

    def test_is_string_subclass(self):
        """WsOrderResultType values must be usable as plain strings."""
        result_type = WsOrderResultType.ACK_REJECTED
        assert isinstance(result_type, str)
        assert result_type in {"REQUEST_NOT_SENT", "ACK_REJECTED", "ACK_TIMEOUT", "ACK_TIMEOUT_CONFIRMED"}
