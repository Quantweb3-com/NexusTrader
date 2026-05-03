"""
Unified test suite for all v0.3.3 changes.

Covers:
1. Batched WebSocket subscriptions (Binance, Bybit, OKX, Bitget, Hyperliquid)
2. Binance Spot: signature-based user data stream (listenKey replacement)
3. OKX: instIdCode support for WebSocket order operations
4. Inflight order tracking
5. Synchronous cancel-intent marking at Strategy layer
6. Order `reason` field
7. OMS null-OID guard
8. RetryManager utility
"""

import asyncio
import threading
import time
import msgspec
import pytest
from collections import defaultdict
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock

from nexustrader.schema import Order
from nexustrader.constants import (
    ExchangeType,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)


# ===========================================================================
# 1. Batched WebSocket subscriptions
# ===========================================================================


class TestBinanceWSClientBatch:
    @pytest.fixture
    def client(self):
        from nexustrader.exchange.binance.websockets import BinanceWSClient
        from nexustrader.exchange.binance.constants import BinanceAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        tm = TaskManager(loop, enable_signal_handlers=False)
        c = BinanceWSClient(
            account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
            handler=lambda raw: None,
            task_manager=tm,
            clock=LiveClock(),
        )
        c.connect = AsyncMock()
        c._send = MagicMock()
        return c

    @pytest.mark.asyncio
    async def test_subscribe_under_50_single_batch(self, client):
        params = [f"btcusdt@trade_{i}" for i in range(30)]
        start = time.monotonic()
        await client._subscribe(params)
        elapsed = time.monotonic() - start

        assert len(client._subscriptions) == 30
        assert client._send.call_count == 1
        assert elapsed < 0.3

    @pytest.mark.asyncio
    async def test_subscribe_over_50_batched_with_delay(self, client):
        params = [f"sym{i}@trade" for i in range(120)]
        start = time.monotonic()
        await client._subscribe(params)
        elapsed = time.monotonic() - start

        assert len(client._subscriptions) == 120
        assert client._send.call_count == 3  # 50+50+20
        assert elapsed >= 0.9  # 2 * 0.5s delay

    @pytest.mark.asyncio
    async def test_subscribe_skips_duplicates(self, client):
        client._subscriptions = [f"sym{i}@trade" for i in range(10)]
        params = [f"sym{i}@trade" for i in range(15)]  # 10 overlap + 5 new
        await client._subscribe(params)

        assert len(client._subscriptions) == 15
        assert client._send.call_count == 1

    @pytest.mark.asyncio
    async def test_resubscribe_over_50(self, client):
        client._subscriptions = [f"sym{i}@trade" for i in range(120)]
        start = time.monotonic()
        await client._resubscribe()
        elapsed = time.monotonic() - start

        assert client._send.call_count == 3
        assert elapsed >= 0.9


class TestBybitWSClientBatch:
    @pytest.fixture
    def client(self):
        from nexustrader.exchange.bybit.websockets import BybitWSClient
        from nexustrader.exchange.bybit.constants import BybitAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        tm = TaskManager(loop, enable_signal_handlers=False)
        c = BybitWSClient(
            account_type=BybitAccountType.LINEAR,
            handler=lambda raw: None,
            task_manager=tm,
            clock=LiveClock(),
        )
        c.connect = AsyncMock()
        c._send = MagicMock()
        return c

    @pytest.mark.asyncio
    async def test_subscribe_over_50_batched(self, client):
        topics = [f"tickers.SYM{i}" for i in range(120)]
        start = time.monotonic()
        await client._subscribe(topics)
        elapsed = time.monotonic() - start

        assert len(client._subscriptions) == 120
        assert client._send.call_count == 3
        assert elapsed >= 0.9


class TestOkxWSClientBatch:
    @pytest.fixture
    def client(self):
        from nexustrader.exchange.okx.websockets import OkxWSClient
        from nexustrader.exchange.okx.constants import OkxAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        tm = TaskManager(loop, enable_signal_handlers=False)
        c = OkxWSClient(
            account_type=OkxAccountType.LIVE,
            handler=lambda raw: None,
            task_manager=tm,
            clock=LiveClock(),
        )
        c.connect = AsyncMock()
        c._send = MagicMock()
        return c

    @pytest.mark.asyncio
    async def test_subscribe_over_50_batched(self, client):
        params = [{"channel": "tickers", "instId": f"SYM{i}"} for i in range(120)]
        start = time.monotonic()
        await client._subscribe(params)
        elapsed = time.monotonic() - start

        assert len(client._subscriptions) == 120
        assert client._send.call_count == 3
        assert elapsed >= 0.9


class TestBitgetWSClientBatch:
    @pytest.fixture
    def client(self):
        from nexustrader.exchange.bitget.websockets import BitgetWSClient
        from nexustrader.exchange.bitget.constants import BitgetAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        tm = TaskManager(loop, enable_signal_handlers=False)
        c = BitgetWSClient(
            account_type=BitgetAccountType.SPOT,
            handler=lambda raw: None,
            task_manager=tm,
            clock=LiveClock(),
        )
        c.connect = AsyncMock()
        c._send = MagicMock()
        return c

    @pytest.mark.asyncio
    async def test_subscribe_over_50_batched(self, client):
        params = [
            {"instType": "USDT-FUTURES", "channel": "ticker", "instId": f"SYM{i}"}
            for i in range(120)
        ]
        start = time.monotonic()
        await client._subscribe(params)
        elapsed = time.monotonic() - start

        assert len(client._subscriptions) == 120
        assert client._send.call_count == 3
        assert elapsed >= 0.9


class TestHyperliquidWSClientBatch:
    @pytest.fixture
    def client(self):
        from nexustrader.exchange.hyperliquid.websockets import HyperLiquidWSClient
        from nexustrader.exchange.hyperliquid.constants import HyperLiquidAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        tm = TaskManager(loop, enable_signal_handlers=False)
        c = HyperLiquidWSClient(
            account_type=HyperLiquidAccountType.MAINNET,
            handler=lambda raw: None,
            task_manager=tm,
            clock=LiveClock(),
        )
        c.connect = AsyncMock()
        c._send = MagicMock()
        return c

    @pytest.mark.asyncio
    async def test_subscribe_over_50_batched(self, client):
        msgs = [{"type": "l2Book", "coin": f"SYM{i}"} for i in range(120)]
        start = time.monotonic()
        await client._subscribe(msgs)
        elapsed = time.monotonic() - start

        assert len(client._subscriptions) == 120
        assert client._send.call_count == 120  # Hyperliquid sends individually
        assert elapsed >= 0.9  # but delays between batches of 50


# ===========================================================================
# 2. Binance Spot: signature-based user data stream
# ===========================================================================


class TestBinanceUserDataStreamSignature:
    @pytest.fixture
    def ws_api(self):
        from nexustrader.exchange.binance.websockets import BinanceWSApiClient
        from nexustrader.exchange.binance.constants import BinanceAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        tm = TaskManager(loop, enable_signal_handlers=False)
        c = BinanceWSApiClient(
            account_type=BinanceAccountType.SPOT_TESTNET,
            api_key="test_api_key",
            secret="test_secret_key",
            handler=lambda raw: None,
            task_manager=tm,
            clock=LiveClock(),
            enable_rate_limit=False,
        )
        c._send = MagicMock()
        return c

    @pytest.mark.asyncio
    async def test_subscribe_sends_correct_payload(self, ws_api):
        await ws_api.subscribe_user_data_stream_signature()

        assert ws_api._user_data_subscribed is True
        assert ws_api._send.call_count == 1
        payload = ws_api._send.call_args[0][0]
        assert payload["method"] == "userDataStream.subscribe.signature"
        assert payload["id"].startswith("uds_")
        assert "apiKey" in payload["params"]
        assert "timestamp" in payload["params"]
        assert "signature" in payload["params"]
        assert payload["params"]["apiKey"] == "test_api_key"

    @pytest.mark.asyncio
    async def test_resubscribe_when_flag_set(self, ws_api):
        ws_api._user_data_subscribed = True
        await ws_api._resubscribe()

        assert ws_api._send.call_count == 1
        payload = ws_api._send.call_args[0][0]
        assert payload["method"] == "userDataStream.subscribe.signature"

    @pytest.mark.asyncio
    async def test_resubscribe_skips_when_not_subscribed(self, ws_api):
        ws_api._user_data_subscribed = False
        await ws_api._resubscribe()
        assert ws_api._send.call_count == 0

    def test_oms_handler_routes_order_response(self):
        from nexustrader.exchange.binance.schema import BinanceWsOrderResponse

        raw = msgspec.json.encode(
            {
                "id": "n_test123",
                "status": 200,
                "result": {
                    "orderId": 12345,
                    "symbol": "BTCUSDT",
                    "clientOrderId": "test123",
                },
            }
        )
        msg = msgspec.json.Decoder(BinanceWsOrderResponse).decode(raw)
        assert msg.id.startswith("n")
        assert msg.is_success

    def test_oms_handler_skips_subscribe_confirmation(self):
        from nexustrader.exchange.binance.schema import BinanceWsOrderResponse

        raw = msgspec.json.encode(
            {"id": "uds_1234567890", "status": 200, "result": None}
        )
        msg = msgspec.json.Decoder(BinanceWsOrderResponse).decode(raw)
        assert not msg.id.startswith("n")
        assert not msg.id.startswith("c")

    def test_user_data_event_fails_decode_as_order_response(self):
        from nexustrader.exchange.binance.schema import BinanceWsOrderResponse

        raw = msgspec.json.encode(
            {"e": "executionReport", "s": "BTCUSDT", "S": "BUY", "E": 1234567890}
        )
        with pytest.raises(msgspec.DecodeError):
            msgspec.json.Decoder(BinanceWsOrderResponse).decode(raw)


# ===========================================================================
# 3. OKX: instIdCode support
# ===========================================================================


class TestOkxInstIdCodeMigration:
    def test_market_info_default_none(self):
        from nexustrader.exchange.okx.schema import OkxMarketInfo

        assert OkxMarketInfo().instIdCode is None

    def test_market_info_set(self):
        from nexustrader.exchange.okx.schema import OkxMarketInfo

        info = OkxMarketInfo(instId="BTC-USDT-SWAP", instIdCode="BTC-USDT-SWAP")
        assert info.instIdCode == "BTC-USDT-SWAP"

    def test_market_info_decoded_from_json(self):
        from nexustrader.exchange.okx.schema import OkxMarketInfo

        raw = msgspec.json.encode(
            {
                "instId": "BTC-USDT-SWAP",
                "instIdCode": "BTC-USDT-SWAP",
                "instType": "SWAP",
            }
        )
        info = msgspec.json.decode(raw, type=OkxMarketInfo)
        assert info.instIdCode == "BTC-USDT-SWAP"

    def test_market_info_decoded_from_json_int_inst_id_code(self):
        from nexustrader.exchange.okx.schema import OkxMarketInfo

        raw = msgspec.json.encode(
            {
                "instId": "BTC-USDT-SWAP",
                "instIdCode": 2021032622066818,
                "instType": "SWAP",
            }
        )
        info = msgspec.json.decode(raw, type=OkxMarketInfo)
        assert info.instIdCode == 2021032622066818

    def test_market_info_missing_from_json(self):
        from nexustrader.exchange.okx.schema import OkxMarketInfo

        raw = msgspec.json.encode({"instId": "BTC-USDT-SWAP", "instType": "SWAP"})
        info = msgspec.json.decode(raw, type=OkxMarketInfo)
        assert info.instIdCode is None

    def test_parse_swap_market_with_int_inst_id_code(self):
        from nexustrader.exchange.okx.exchange import OkxExchangeManager

        raw_market = {
            "instId": "BTC-USDT-SWAP",
            "instIdCode": 2021032622066818,
            "instType": "SWAP",
            "instFamily": "BTC-USDT",
            "ctType": "linear",
            "settleCcy": "USDT",
            "state": "live",
            "ctVal": "0.01",
            "lotSz": "0.01",
            "tickSz": "0.1",
            "lever": "100",
            "minSz": "0.01",
            "maxLmtSz": "100000",
            "maxLmtAmt": "20000000",
            "listTime": "1600000000000",
        }
        exchange = object.__new__(OkxExchangeManager)
        market = exchange._parse_raw_market(raw_market)

        assert market.info.instIdCode == 2021032622066818
        assert exchange._parse_symbol(market, exchange_suffix="OKX") == "BTCUSDT-PERP.OKX"

    @pytest.fixture
    def ws_api(self):
        from nexustrader.exchange.okx.websockets import OkxWSApiClient
        from nexustrader.exchange.okx.constants import OkxAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        tm = TaskManager(loop, enable_signal_handlers=False)
        c = OkxWSApiClient(
            account_type=OkxAccountType.DEMO,
            api_key="test_key",
            secret="test_secret",
            passphrase="test_pass",
            handler=lambda raw: None,
            task_manager=tm,
            clock=LiveClock(),
            enable_rate_limit=False,
        )
        c._send = MagicMock()
        c._authed = True
        return c

    @pytest.mark.asyncio
    async def test_place_order_with_inst_id_code(self, ws_api):
        await ws_api.place_order(
            id="oid1",
            instIdCode="BTC-USDT-SWAP",
            tdMode="cross",
            side="buy",
            ordType="limit",
            sz="0.1",
            px="50000",
        )
        args = ws_api._send.call_args[0][0]["args"][0]
        assert args["instIdCode"] == "BTC-USDT-SWAP"
        assert "instId" not in args

    @pytest.mark.asyncio
    async def test_place_order_fallback_inst_id(self, ws_api):
        await ws_api.place_order(
            id="oid2",
            instId="BTC-USDT-SWAP",
            tdMode="cross",
            side="buy",
            ordType="limit",
            sz="0.1",
            px="50000",
        )
        args = ws_api._send.call_args[0][0]["args"][0]
        assert args["instId"] == "BTC-USDT-SWAP"
        assert "instIdCode" not in args

    @pytest.mark.asyncio
    async def test_cancel_order_with_inst_id_code(self, ws_api):
        await ws_api.cancel_order(
            id="oid3", clOrdId="order123", instIdCode="BTC-USDT-SWAP"
        )
        args = ws_api._send.call_args[0][0]["args"][0]
        assert args["instIdCode"] == "BTC-USDT-SWAP"
        assert "instId" not in args

    @pytest.mark.asyncio
    async def test_cancel_order_fallback_inst_id(self, ws_api):
        await ws_api.cancel_order(id="oid4", clOrdId="order123", instId="BTC-USDT-SWAP")
        args = ws_api._send.call_args[0][0]["args"][0]
        assert args["instId"] == "BTC-USDT-SWAP"
        assert "instIdCode" not in args


# ===========================================================================
# 4. Inflight order tracking
# ===========================================================================


class TestInflightOrderTracking:
    @pytest.fixture
    def cache(self):
        from nexustrader.core.cache import AsyncCache

        c = AsyncCache.__new__(AsyncCache)
        c._order_lock = threading.Lock()
        c._inflight_orders = defaultdict(set)
        c._cancel_intent_oids = set()
        c._mem_orders = {}
        c._mem_open_orders = defaultdict(set)
        c._mem_symbol_orders = defaultdict(set)
        c._mem_symbol_open_orders = defaultdict(set)
        c._mem_algo_orders = {}
        c._log = MagicMock()
        return c

    def test_add_and_get(self, cache):
        cache.add_inflight_order("BTCUSDT-PERP.BINANCE", "oid_1")
        cache.add_inflight_order("BTCUSDT-PERP.BINANCE", "oid_2")
        assert cache.get_inflight_orders("BTCUSDT-PERP.BINANCE") == {"oid_1", "oid_2"}

    def test_get_empty(self, cache):
        assert cache.get_inflight_orders("ETHUSDT-PERP.BINANCE") == set()

    def test_cleared_on_status_update(self, cache):
        cache.add_inflight_order("BTCUSDT-PERP.BINANCE", "oid_1")
        order = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.PENDING,
            oid="oid_1",
            timestamp=1000,
        )
        cache._order_status_update(order)
        assert "oid_1" not in cache.get_inflight_orders("BTCUSDT-PERP.BINANCE")

    def test_returns_copy(self, cache):
        cache.add_inflight_order("BTCUSDT-PERP.BINANCE", "oid_1")
        inflight = cache.get_inflight_orders("BTCUSDT-PERP.BINANCE")
        inflight.add("oid_fake")
        assert "oid_fake" not in cache.get_inflight_orders("BTCUSDT-PERP.BINANCE")

    @pytest.mark.asyncio
    async def test_wait_resolves_immediately(self, cache):
        start = time.monotonic()
        await cache.wait_for_inflight_orders("BTCUSDT-PERP.BINANCE", timeout=1.0)
        assert time.monotonic() - start < 0.3

    @pytest.mark.asyncio
    async def test_wait_timeout(self, cache):
        cache.add_inflight_order("BTCUSDT-PERP.BINANCE", "stuck_oid")
        start = time.monotonic()
        await cache.wait_for_inflight_orders(
            "BTCUSDT-PERP.BINANCE", timeout=0.3, interval=0.1
        )
        assert time.monotonic() - start >= 0.25
        assert "stuck_oid" in cache.get_inflight_orders("BTCUSDT-PERP.BINANCE")


# ===========================================================================
# 5. Synchronous cancel-intent marking
# ===========================================================================


class TestCancelIntentStrategy:
    def _make_strategy(self):
        from nexustrader.strategy import Strategy

        s = Strategy()
        s._initialized = True
        s.cache = MagicMock()
        s._oidgen = MagicMock()
        mock_ems = MagicMock()
        s._ems = {ExchangeType.BINANCE: mock_ems}
        return s, mock_ems

    def test_cancel_order_marks_intent(self):
        s, ems = self._make_strategy()
        s.cancel_order("BTCUSDT-PERP.BINANCE", "test_oid")
        s.cache.mark_cancel_intent.assert_called_once_with("test_oid")
        ems._submit_order.assert_called_once()

    def test_cancel_order_ws_marks_intent(self):
        s, _ = self._make_strategy()
        s.cancel_order_ws("BTCUSDT-PERP.BINANCE", "test_oid")
        s.cache.mark_cancel_intent.assert_called_once_with("test_oid")

    def test_cancel_all_orders_marks_all_intent(self):
        s, _ = self._make_strategy()
        s.cancel_all_orders("BTCUSDT-PERP.BINANCE")
        s.cache.mark_all_cancel_intent.assert_called_once_with("BTCUSDT-PERP.BINANCE")


# ===========================================================================
# 6. Order `reason` field
# ===========================================================================


class TestOrderReasonField:
    def test_default_none(self):
        order = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.FILLED,
        )
        assert order.reason is None

    def test_set_value(self):
        order = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.FAILED,
            reason="insufficient balance",
        )
        assert order.reason == "insufficient balance"

    def test_json_roundtrip(self):
        order = Order(
            exchange=ExchangeType.OKX,
            symbol="BTCUSDT-PERP.OKX",
            status=OrderStatus.CANCEL_FAILED,
            reason="code=51010",
        )
        decoded = msgspec.json.decode(msgspec.json.encode(order), type=Order)
        assert decoded.reason == "code=51010"

    def test_absent_in_json_yields_none(self):
        order = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.FILLED,
        )
        decoded = msgspec.json.decode(msgspec.json.encode(order), type=Order)
        assert decoded.reason is None


# ===========================================================================
# 7. OMS null-OID guard
# ===========================================================================


class TestOMSNullOidGuard:
    def test_order_with_none_oid_is_skipped(self):
        from nexustrader.base.oms import OrderManagementSystem

        class StubOMS(OrderManagementSystem):
            def _init_account_balance(self):
                pass

            def _init_position(self):
                pass

            def _position_mode_check(self):
                pass

            async def create_tp_sl_order(self, *a, **kw):
                pass

            async def create_order(self, *a, **kw):
                pass

            async def create_order_ws(self, *a, **kw):
                pass

            async def create_batch_orders(self, *a, **kw):
                pass

            async def cancel_order(self, *a, **kw):
                pass

            async def cancel_order_ws(self, *a, **kw):
                pass

            async def modify_order(self, *a, **kw):
                pass

            async def cancel_all_orders(self, *a, **kw):
                pass

        oms = StubOMS.__new__(StubOMS)
        oms._registry = MagicMock()
        oms._cache = MagicMock()
        oms._log = MagicMock()

        order = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.FILLED,
            oid=None,
        )
        oms.order_status_update(order)

        oms._registry.is_registered.assert_not_called()
        oms._cache._order_status_update.assert_not_called()


# ===========================================================================
# 8. RetryManager utility
# ===========================================================================


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
        result = await rm.run("op", self._good_func)
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

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temp")
            return "ok"

        result = await rm.run("flaky", flaky)
        assert result == "ok"
        assert call_count == 3

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
        with pytest.raises(ValueError, match="always"):
            await rm.run("fail", self._always_fail)
        assert rm.result is False

    @pytest.mark.asyncio
    async def test_non_retryable_propagates(self):
        from nexustrader.base.retry import RetryManager

        rm = RetryManager(
            max_retries=3,
            delay_initial_ms=50,
            delay_max_ms=100,
            backoff_factor=2,
            exc_types=(ValueError,),
        )
        with pytest.raises(TypeError, match="not retryable"):
            await rm.run("type_err", self._type_error)

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
        result = await rm.run("cancel", self._always_fail)
        assert result is None
        assert rm.result is False

    def test_exponential_backoff_values(self):
        from nexustrader.base.retry import get_exponential_backoff

        assert get_exponential_backoff(1, 100, 10000, 2, jitter=False) == 100
        assert get_exponential_backoff(3, 100, 10000, 2, jitter=False) == 400
        assert get_exponential_backoff(10, 100, 2000, 2, jitter=False) == 2000

    # --- helpers ---
    @staticmethod
    async def _good_func():
        return 42

    @staticmethod
    async def _always_fail():
        raise ValueError("always")

    @staticmethod
    async def _type_error():
        raise TypeError("not retryable")


# ===========================================================================
# 9. Reconnect reconcile risk controls
# ===========================================================================


class TestReconnectReconcileControls:
    @pytest.mark.asyncio
    async def test_confirm_missing_orders_requires_second_check(self):
        from nexustrader.base.oms import OrderManagementSystem
        from nexustrader.constants import OrderSide, OrderType, TimeInForce

        class StubOMS(OrderManagementSystem):
            def _init_account_balance(self):
                pass

            def _init_position(self):
                pass

            def _position_mode_check(self):
                pass

            async def create_tp_sl_order(self, *a, **kw):
                pass

            async def create_order(self, *a, **kw):
                pass

            async def create_order_ws(self, *a, **kw):
                pass

            async def create_batch_orders(self, *a, **kw):
                pass

            async def cancel_order(self, *a, **kw):
                pass

            async def cancel_order_ws(self, *a, **kw):
                pass

            async def modify_order(self, *a, **kw):
                pass

            async def cancel_all_orders(self, *a, **kw):
                pass

        oms = StubOMS.__new__(StubOMS)
        oms._log = MagicMock()
        oms._reconnect_reconcile_grace_ms = 700
        oms.order_status_update = MagicMock()

        open_order_1 = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.PENDING,
            oid="oid_1",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            amount=1,
            timestamp=1000,
        )
        open_order_2 = Order(
            exchange=ExchangeType.BINANCE,
            symbol="ETHUSDT-PERP.BINANCE",
            status=OrderStatus.PENDING,
            oid="oid_2",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            amount=1,
            timestamp=1001,
        )
        filled_order_1 = Order(
            exchange=ExchangeType.BINANCE,
            symbol="BTCUSDT-PERP.BINANCE",
            status=OrderStatus.FILLED,
            oid="oid_1",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            amount=1,
            filled=1,
            timestamp=1002,
        )

        cache_by_oid = {"oid_1": open_order_1, "oid_2": open_order_2}
        oms._cache = MagicMock()
        oms._cache.get_order.side_effect = lambda oid: cache_by_oid.get(oid)

        async def _fetch_order(symbol, oid, force_refresh=False):
            assert force_refresh is True, (
                "_confirm_missing_open_orders must pass force_refresh=True"
            )
            if oid == "oid_1":
                return filled_order_1
            return None  # remain conservative-open when not confirmed

        oms.fetch_order = _fetch_order

        confirmed = await oms._confirm_missing_open_orders(
            {"oid_1", "oid_2"}, grace_ms=0
        )

        assert confirmed == {"oid_1"}
        oms.order_status_update.assert_called_once_with(filled_order_1)

    def test_set_reconnect_reconcile_grace_ms_validation(self):
        from nexustrader.base.oms import OrderManagementSystem

        class StubOMS(OrderManagementSystem):
            def _init_account_balance(self):
                pass

            def _init_position(self):
                pass

            def _position_mode_check(self):
                pass

            async def create_tp_sl_order(self, *a, **kw):
                pass

            async def create_order(self, *a, **kw):
                pass

            async def create_order_ws(self, *a, **kw):
                pass

            async def create_batch_orders(self, *a, **kw):
                pass

            async def cancel_order(self, *a, **kw):
                pass

            async def cancel_order_ws(self, *a, **kw):
                pass

            async def modify_order(self, *a, **kw):
                pass

            async def cancel_all_orders(self, *a, **kw):
                pass

        oms = StubOMS.__new__(StubOMS)
        oms._reconnect_reconcile_grace_ms = 700

        oms.set_reconnect_reconcile_grace_ms(1200)
        assert oms._reconnect_reconcile_grace_ms == 1200

        with pytest.raises(ValueError, match="grace_ms must be >= 0"):
            oms.set_reconnect_reconcile_grace_ms(-1)

    def test_strategy_set_reconnect_reconcile_grace_ms_routes_per_exchange(self):
        from nexustrader.strategy import Strategy

        class AccountTypeStub:
            def __init__(self, exchange_id):
                self.exchange_id = exchange_id

        strategy = Strategy()
        strategy._ems = {
            ExchangeType.BINANCE: MagicMock(),
            ExchangeType.OKX: MagicMock(),
        }

        bnc_connector = MagicMock()
        okx_connector = MagicMock()

        strategy._private_connectors = {
            AccountTypeStub("binance"): bnc_connector,
            AccountTypeStub("okx"): okx_connector,
        }

        strategy.set_reconnect_reconcile_grace_ms(ExchangeType.BINANCE, 900)
        bnc_connector._oms.set_reconnect_reconcile_grace_ms.assert_called_once_with(900)
        okx_connector._oms.set_reconnect_reconcile_grace_ms.assert_not_called()


# ===========================================================================
# 10. Modify-order cache preservation
# ===========================================================================


class TestModifyOrderCachePreservation:
    def _cached_order(self, exchange: ExchangeType, symbol: str) -> Order:
        return Order(
            exchange=exchange,
            symbol=symbol,
            status=OrderStatus.PARTIALLY_FILLED,
            oid="oid-1",
            eid="eid-old",
            amount=Decimal("5"),
            filled=Decimal("2"),
            remaining=Decimal("3"),
            timestamp=1000,
            type=OrderType.LIMIT,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            price=100.0,
            average=99.5,
            reduce_only=True,
        )

    @pytest.mark.asyncio
    async def test_binance_price_only_modify_keeps_amount(self):
        from nexustrader.exchange.binance.oms import BinanceOrderManagementSystem
        from nexustrader.exchange.binance.constants import (
            BinanceOrderSide,
            BinanceOrderType,
            BinanceTimeInForce,
        )

        symbol = "BTCUSDT-PERP.BINANCE"
        cached = self._cached_order(ExchangeType.BINANCE, symbol)
        oms = BinanceOrderManagementSystem.__new__(BinanceOrderManagementSystem)
        oms._market = {symbol: SimpleNamespace(id="BTCUSDT", spot=False)}
        oms._cache = MagicMock()
        oms._cache.get_order.return_value = cached
        oms._exchange_id = ExchangeType.BINANCE
        oms._clock = MagicMock()
        oms._log = MagicMock()
        oms.order_status_update = MagicMock()
        oms._execute_modify_order_request = AsyncMock(
            return_value=SimpleNamespace(
                orderId="eid-new",
                executedQty="2",
                updateTime=123456,
                type=BinanceOrderType.LIMIT,
                timeInForce=BinanceTimeInForce.GTC,
                price="101.5",
                avgPrice="99.5",
                origQty="5",
                reduceOnly=True,
                positionSide=None,
                side=BinanceOrderSide.BUY,
            )
        )

        await oms.modify_order(
            oid="oid-1",
            symbol=symbol,
            side=OrderSide.BUY,
            price=Decimal("101.5"),
            amount=None,
        )

        order = oms.order_status_update.call_args.args[0]
        assert order.status is OrderStatus.PARTIALLY_FILLED
        assert order.amount == Decimal("5")
        assert order.filled == Decimal("2")
        assert order.remaining == Decimal("3")

    @pytest.mark.asyncio
    async def test_bybit_price_only_modify_keeps_fill_state(self):
        from nexustrader.exchange.bybit.oms import BybitOrderManagementSystem

        symbol = "BTCUSDT-PERP.BYBIT"
        cached = self._cached_order(ExchangeType.BYBIT, symbol)
        oms = BybitOrderManagementSystem.__new__(BybitOrderManagementSystem)
        oms._market = {symbol: SimpleNamespace(id="BTCUSDT")}
        oms._cache = MagicMock()
        oms._cache.get_order.return_value = cached
        oms._exchange_id = ExchangeType.BYBIT
        oms._clock = MagicMock()
        oms._log = MagicMock()
        oms._api_client = MagicMock()
        oms._api_client.post_v5_order_amend = AsyncMock(
            return_value=SimpleNamespace(
                result=SimpleNamespace(orderId="eid-new"),
                time="123456",
            )
        )
        oms._get_category = MagicMock(return_value="linear")
        oms.order_status_update = MagicMock()

        await oms.modify_order(
            oid="oid-1",
            symbol=symbol,
            price=Decimal("101.5"),
            amount=None,
        )

        order = oms.order_status_update.call_args.args[0]
        assert order.status is OrderStatus.PARTIALLY_FILLED
        assert order.amount == Decimal("5")
        assert order.filled == Decimal("2")
        assert order.remaining == Decimal("3")
        assert order.side is OrderSide.BUY
        assert order.type is OrderType.LIMIT
        assert order.time_in_force is TimeInForce.GTC

    @pytest.mark.asyncio
    async def test_okx_price_only_modify_keeps_fill_state(self):
        from nexustrader.exchange.okx.oms import OkxOrderManagementSystem

        symbol = "BTCUSDT-PERP.OKX"
        cached = self._cached_order(ExchangeType.OKX, symbol)
        oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)
        oms._market = {
            symbol: SimpleNamespace(
                id="BTC-USDT-SWAP",
                spot=False,
                info=SimpleNamespace(ctVal="1"),
            )
        }
        oms._cache = MagicMock()
        oms._cache.get_order.return_value = cached
        oms._exchange_id = ExchangeType.OKX
        oms._clock = MagicMock()
        oms._log = MagicMock()
        oms._api_client = MagicMock()
        oms._api_client.post_api_v5_trade_amend_order = AsyncMock(
            return_value=SimpleNamespace(
                data=[SimpleNamespace(ordId="eid-new", ts="123456")]
            )
        )
        oms.order_status_update = MagicMock()

        await oms.modify_order(
            oid="oid-1",
            symbol=symbol,
            price=Decimal("101.5"),
            amount=None,
        )

        order = oms.order_status_update.call_args.args[0]
        assert order.status is OrderStatus.PARTIALLY_FILLED
        assert order.amount == Decimal("5")
        assert order.filled == Decimal("2")
        assert order.remaining == Decimal("3")
        assert order.side is OrderSide.BUY
        assert order.type is OrderType.LIMIT
        assert order.time_in_force is TimeInForce.GTC
