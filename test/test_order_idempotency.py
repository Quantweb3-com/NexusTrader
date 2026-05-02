import asyncio
import threading
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexustrader.constants import ExchangeType, OrderSide, OrderStatus, OrderType
from nexustrader.schema import CreateOrderSubmit, InstrumentId, Order


class TestCacheCreateIdempotency:
    @pytest.fixture
    def cache(self):
        from nexustrader.core.cache import AsyncCache

        c = AsyncCache.__new__(AsyncCache)
        c._order_lock = threading.Lock()
        c._idempotent_create_oids = {}
        c._oid_to_idempotency_key = {}
        return c

    def test_reserve_same_key_returns_same_oid(self, cache):
        first = cache.reserve_idempotent_create_order("signal:btc:entry", "oid_1")
        second = cache.reserve_idempotent_create_order("signal:btc:entry", "oid_2")

        assert first == "oid_1"
        assert second == "oid_1"
        assert cache.get_idempotent_create_order_oid("signal:btc:entry") == "oid_1"
        assert cache.get_idempotency_key_for_oid("oid_1") == "signal:btc:entry"


class TestStrategyCreateOrderIdempotency:
    def _make_strategy(self):
        from nexustrader.strategy import Strategy

        strategy = Strategy()
        strategy._initialized = True
        strategy._oidgen = MagicMock()
        strategy._oidgen.oid = "generated_oid_1"
        strategy.cache = MagicMock()
        strategy.cache.reserve_idempotent_create_order = MagicMock(
            side_effect=lambda key, oid: "canonical_oid_1"
        )
        strategy._ems = {ExchangeType.BINANCE: MagicMock()}
        return strategy

    def test_create_order_reuses_canonical_oid_for_same_key(self):
        strategy = self._make_strategy()

        oid = strategy.create_order(
            symbol="BTCUSDT-PERP.BINANCE",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("90000"),
            idempotency_key="signal:btc:entry",
        )

        assert oid == "canonical_oid_1"
        submitted = strategy._ems[ExchangeType.BINANCE]._submit_order.call_args[0][0]
        assert submitted.oid == "canonical_oid_1"
        assert submitted.idempotency_key == "signal:btc:entry"

    def test_create_order_ws_respects_explicit_client_oid(self):
        strategy = self._make_strategy()
        strategy.cache.reserve_idempotent_create_order = MagicMock(
            side_effect=lambda key, oid: oid
        )

        oid = strategy.create_order_ws(
            symbol="BTCUSDT-PERP.BINANCE",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("90000"),
            client_oid="manual_oid_123",
            idempotency_key="signal:btc:entry:ws",
        )

        assert oid == "manual_oid_123"
        submitted = strategy._ems[ExchangeType.BINANCE]._submit_order.call_args[0][0]
        assert submitted.oid == "manual_oid_123"
        assert submitted.idempotency_key == "signal:btc:entry:ws"


class _DummyEMSBase:
    from nexustrader.base.ems import ExecutionManagementSystem


class DummyEMS(_DummyEMSBase.ExecutionManagementSystem):
    def _instrument_id_to_account_type(self, instrument_id):
        return "dummy"

    def _build_order_submit_queues(self):
        pass

    def _set_account_type(self):
        pass

    def _submit_order(self, order, submit_type, account_type=None):
        pass

    def _get_min_order_amount(self, symbol, market, px):
        return Decimal("0.001")


class TestExecutionManagementIdempotency:
    @pytest.mark.asyncio
    async def test_skip_duplicate_create_when_registered(self):
        from nexustrader.core.entity import TaskManager

        loop = asyncio.get_running_loop()
        task_manager = TaskManager(loop=loop, enable_signal_handlers=False)
        cache = MagicMock()
        cache.get_inflight_orders = MagicMock(return_value=set())
        cache.get_order = MagicMock(return_value=None)
        cache.add_inflight_order = MagicMock()
        registry = MagicMock()
        registry.is_registered = MagicMock(return_value=True)

        ems = DummyEMS(
            market={},
            cache=cache,
            msgbus=MagicMock(),
            clock=MagicMock(),
            task_manager=task_manager,
            registry=registry,
            is_mock=False,
        )
        private_oms = MagicMock()
        private_oms.create_order = AsyncMock()
        ems._private_connectors = {"dummy": MagicMock(_oms=private_oms)}

        order_submit = CreateOrderSubmit(
            symbol="BTCUSDT-PERP.BINANCE",
            instrument_id=InstrumentId.from_str("BTCUSDT-PERP.BINANCE"),
            oid="dup_oid_1",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("90000"),
        )

        await ems._create_order(order_submit, "dummy")
        await asyncio.sleep(0)

        private_oms.create_order.assert_not_awaited()
        cache.add_inflight_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_duplicate_create_when_cached_order_exists(self):
        from nexustrader.core.entity import TaskManager

        loop = asyncio.get_running_loop()
        task_manager = TaskManager(loop=loop, enable_signal_handlers=False)
        existing = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.ACCEPTED,
            oid="dup_oid_2",
            amount=Decimal("0.01"),
            type=OrderType.LIMIT,
            side=OrderSide.BUY,
            price=90000.0,
            timestamp=0,
        )
        cache = MagicMock()
        cache.get_inflight_orders = MagicMock(return_value=set())
        cache.get_order = MagicMock(return_value=existing)
        cache.add_inflight_order = MagicMock()
        registry = MagicMock()
        registry.is_registered = MagicMock(return_value=False)

        ems = DummyEMS(
            market={},
            cache=cache,
            msgbus=MagicMock(),
            clock=MagicMock(),
            task_manager=task_manager,
            registry=registry,
            is_mock=False,
        )
        private_oms = MagicMock()
        private_oms.create_order_ws = AsyncMock()
        ems._private_connectors = {"dummy": MagicMock(_oms=private_oms)}

        order_submit = CreateOrderSubmit(
            symbol="BTCUSDT-PERP.BINANCE",
            instrument_id=InstrumentId.from_str("BTCUSDT-PERP.BINANCE"),
            oid="dup_oid_2",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("90000"),
        )

        await ems._create_order_ws(order_submit, "dummy")
        await asyncio.sleep(0)

        private_oms.create_order_ws.assert_not_awaited()
        cache.add_inflight_order.assert_not_called()
