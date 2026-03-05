"""Tests for Phase 1 changes:
1. Order.reason field + oid null guard
2. Inflight order tracking (cache + EMS)
3. Cancel intent moved to Strategy layer
4. RetryManager utility
"""

import asyncio
import time
import msgspec
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# 1. Order schema: reason field
# ---------------------------------------------------------------------------

class TestOrderReasonField:

    def test_order_reason_default_none(self):
        from nexustrader.schema import Order
        from nexustrader.constants import ExchangeType, OrderStatus

        order = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.FILLED,
        )
        assert order.reason is None

    def test_order_reason_set(self):
        from nexustrader.schema import Order
        from nexustrader.constants import ExchangeType, OrderStatus

        order = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.FAILED,
            reason="BinanceClientError: insufficient balance",
        )
        assert order.reason == "BinanceClientError: insufficient balance"

    def test_order_reason_json_roundtrip(self):
        from nexustrader.schema import Order
        from nexustrader.constants import ExchangeType, OrderStatus

        order = Order(
            exchange=ExchangeType.OKX,
            symbol="BTCUSDT-PERP.OKX",
            status=OrderStatus.CANCEL_FAILED,
            reason="code=51010, msg=Order not found",
        )
        raw = msgspec.json.encode(order)
        decoded = msgspec.json.decode(raw, type=Order)
        assert decoded.reason == "code=51010, msg=Order not found"

    def test_order_reason_missing_in_json(self):
        from nexustrader.schema import Order
        from nexustrader.constants import ExchangeType, OrderStatus

        order = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.FILLED,
        )
        raw = msgspec.json.encode(order)
        decoded = msgspec.json.decode(raw, type=Order)
        assert decoded.reason is None


# ---------------------------------------------------------------------------
# 2. OMS oid null guard
# ---------------------------------------------------------------------------

class TestOMSOidNullGuard:

    def test_order_with_none_oid_is_skipped(self):
        """order_status_update should return immediately if order.oid is None."""
        from nexustrader.schema import Order
        from nexustrader.constants import ExchangeType, OrderStatus

        order = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.FILLED,
            oid=None,
        )

        registry = MagicMock()
        cache = MagicMock()

        from nexustrader.base.oms import OrderManagementSystem

        class TestOMS(OrderManagementSystem):
            def _init_account_balance(self): pass
            def _init_position(self): pass
            def _position_mode_check(self): pass
            async def create_tp_sl_order(self, *a, **kw): pass
            async def create_order(self, *a, **kw): pass
            async def create_order_ws(self, *a, **kw): pass
            async def create_batch_orders(self, *a, **kw): pass
            async def cancel_order(self, *a, **kw): pass
            async def cancel_order_ws(self, *a, **kw): pass
            async def modify_order(self, *a, **kw): pass
            async def cancel_all_orders(self, *a, **kw): pass

        oms = TestOMS.__new__(TestOMS)
        oms._registry = registry
        oms._cache = cache
        oms._log = MagicMock()

        oms.order_status_update(order)

        registry.is_registered.assert_not_called()
        cache._order_status_update.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Inflight order tracking
# ---------------------------------------------------------------------------

class TestInflightOrderTracking:

    @pytest.fixture
    def cache(self):
        import threading
        from collections import defaultdict
        from nexustrader.core.cache import AsyncCache

        cache = AsyncCache.__new__(AsyncCache)
        cache._order_lock = threading.Lock()
        cache._inflight_orders = defaultdict(set)
        cache._cancel_intent_oids = set()
        cache._mem_orders = {}
        cache._mem_open_orders = defaultdict(set)
        cache._mem_symbol_orders = defaultdict(set)
        cache._mem_symbol_open_orders = defaultdict(set)
        cache._mem_algo_orders = {}
        cache._log = MagicMock()
        return cache

    def test_add_and_get_inflight(self, cache):
        cache.add_inflight_order("BTCUSDT-PERP.BINANCE", "oid_1")
        cache.add_inflight_order("BTCUSDT-PERP.BINANCE", "oid_2")

        inflight = cache.get_inflight_orders("BTCUSDT-PERP.BINANCE")
        assert inflight == {"oid_1", "oid_2"}

    def test_get_inflight_empty(self, cache):
        inflight = cache.get_inflight_orders("ETHUSDT-PERP.BINANCE")
        assert inflight == set()

    def test_inflight_cleared_on_status_update(self, cache):
        from nexustrader.schema import Order
        from nexustrader.constants import ExchangeType, OrderStatus

        cache.add_inflight_order("BTCUSDT-PERP.BINANCE", "oid_1")
        assert "oid_1" in cache.get_inflight_orders("BTCUSDT-PERP.BINANCE")

        order = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.PENDING,
            oid="oid_1",
            timestamp=1000,
        )
        cache._order_status_update(order)

        assert "oid_1" not in cache.get_inflight_orders("BTCUSDT-PERP.BINANCE")

    def test_inflight_returns_copy(self, cache):
        """get_inflight_orders should return a copy, not a reference."""
        cache.add_inflight_order("BTCUSDT-PERP.BINANCE", "oid_1")
        inflight = cache.get_inflight_orders("BTCUSDT-PERP.BINANCE")
        inflight.add("oid_fake")

        assert "oid_fake" not in cache.get_inflight_orders("BTCUSDT-PERP.BINANCE")

    @pytest.mark.asyncio
    async def test_wait_for_inflight_resolves(self, cache):
        """wait_for_inflight_orders should return quickly when no inflight."""
        start = time.monotonic()
        await cache.wait_for_inflight_orders("BTCUSDT-PERP.BINANCE", timeout=1.0)
        elapsed = time.monotonic() - start
        assert elapsed < 0.3

    @pytest.mark.asyncio
    async def test_wait_for_inflight_timeout(self, cache):
        """wait_for_inflight_orders should timeout when inflight orders remain."""
        cache.add_inflight_order("BTCUSDT-PERP.BINANCE", "stuck_oid")

        start = time.monotonic()
        await cache.wait_for_inflight_orders(
            "BTCUSDT-PERP.BINANCE", timeout=0.3, interval=0.1
        )
        elapsed = time.monotonic() - start

        assert elapsed >= 0.25
        assert "stuck_oid" in cache.get_inflight_orders("BTCUSDT-PERP.BINANCE")


# ---------------------------------------------------------------------------
# 4. Cancel intent at strategy level
# ---------------------------------------------------------------------------

class TestCancelIntentStrategy:

    def test_cancel_order_marks_intent_synchronously(self):
        """Strategy.cancel_order should call mark_cancel_intent before submitting."""
        from nexustrader.strategy import Strategy

        strategy = Strategy()
        strategy._initialized = True
        strategy.cache = MagicMock()
        strategy._oidgen = MagicMock()
        strategy._ems = {
            MagicMock(): MagicMock(),
        }

        from nexustrader.constants import ExchangeType
        from nexustrader.schema import InstrumentId

        mock_exchange = MagicMock()
        mock_ems = MagicMock()
        strategy._ems = {ExchangeType.BINANCE: mock_ems}

        strategy.cancel_order("BTCUSDT-PERP.BINANCE", "test_oid")

        strategy.cache.mark_cancel_intent.assert_called_once_with("test_oid")
        mock_ems._submit_order.assert_called_once()

    def test_cancel_order_ws_marks_intent_synchronously(self):
        from nexustrader.strategy import Strategy
        from nexustrader.constants import ExchangeType

        strategy = Strategy()
        strategy._initialized = True
        strategy.cache = MagicMock()
        strategy._oidgen = MagicMock()

        mock_ems = MagicMock()
        strategy._ems = {ExchangeType.BINANCE: mock_ems}

        strategy.cancel_order_ws("BTCUSDT-PERP.BINANCE", "test_oid")

        strategy.cache.mark_cancel_intent.assert_called_once_with("test_oid")

    def test_cancel_all_orders_marks_all_intent(self):
        from nexustrader.strategy import Strategy
        from nexustrader.constants import ExchangeType

        strategy = Strategy()
        strategy._initialized = True
        strategy.cache = MagicMock()
        strategy._oidgen = MagicMock()

        mock_ems = MagicMock()
        strategy._ems = {ExchangeType.BINANCE: mock_ems}

        strategy.cancel_all_orders("BTCUSDT-PERP.BINANCE")

        strategy.cache.mark_all_cancel_intent.assert_called_once_with(
            "BTCUSDT-PERP.BINANCE"
        )


# ---------------------------------------------------------------------------
# 5. RetryManager
# ---------------------------------------------------------------------------

class TestRetryManager:

    @pytest.mark.asyncio
    async def test_success_first_attempt(self):
        from nexustrader.base.retry import RetryManager

        rm = RetryManager(
            max_retries=3,
            delay_initial_ms=100,
            delay_max_ms=1000,
            backoff_factor=2,
            exc_types=(ValueError,),
        )

        async def good_func():
            return 42

        result = await rm.run("test_op", good_func)
        assert result == 42
        assert rm.result is True

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        from nexustrader.base.retry import RetryManager

        rm = RetryManager(
            max_retries=3,
            delay_initial_ms=50,
            delay_max_ms=100,
            backoff_factor=2,
            exc_types=(ValueError,),
        )

        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary error")
            return "ok"

        result = await rm.run("flaky_op", flaky_func)
        assert result == "ok"
        assert call_count == 3
        assert rm.result is True

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        from nexustrader.base.retry import RetryManager

        rm = RetryManager(
            max_retries=2,
            delay_initial_ms=50,
            delay_max_ms=100,
            backoff_factor=2,
            exc_types=(ValueError,),
        )

        async def always_fail():
            raise ValueError("permanent error")

        with pytest.raises(ValueError, match="permanent error"):
            await rm.run("fail_op", always_fail)

        assert rm.result is False
        assert rm.message == "permanent error"

    @pytest.mark.asyncio
    async def test_non_retryable_exception_propagates(self):
        from nexustrader.base.retry import RetryManager

        rm = RetryManager(
            max_retries=3,
            delay_initial_ms=50,
            delay_max_ms=100,
            backoff_factor=2,
            exc_types=(ValueError,),
        )

        async def type_error_func():
            raise TypeError("not retryable")

        with pytest.raises(TypeError, match="not retryable"):
            await rm.run("type_err_op", type_error_func)

    @pytest.mark.asyncio
    async def test_cancel(self):
        from nexustrader.base.retry import RetryManager

        rm = RetryManager(
            max_retries=10,
            delay_initial_ms=50,
            delay_max_ms=100,
            backoff_factor=2,
            exc_types=(ValueError,),
        )

        rm.cancel()

        async def should_not_run():
            raise ValueError("should not reach here")

        result = await rm.run("cancel_op", should_not_run)
        assert result is None
        assert rm.result is False

    def test_exponential_backoff_values(self):
        from nexustrader.base.retry import get_exponential_backoff

        delay = get_exponential_backoff(
            num_attempts=1,
            delay_initial_ms=100,
            delay_max_ms=10000,
            backoff_factor=2,
            jitter=False,
        )
        assert delay == 100

        delay = get_exponential_backoff(
            num_attempts=3,
            delay_initial_ms=100,
            delay_max_ms=10000,
            backoff_factor=2,
            jitter=False,
        )
        assert delay == 400

        delay = get_exponential_backoff(
            num_attempts=10,
            delay_initial_ms=100,
            delay_max_ms=2000,
            backoff_factor=2,
            jitter=False,
        )
        assert delay == 2000  # capped at max
