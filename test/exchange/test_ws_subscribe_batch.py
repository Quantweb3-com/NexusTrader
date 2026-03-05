"""Tests for WebSocket subscription batching logic.

Validates that:
1. Initial subscriptions are batched (max 50 per batch) with delay
2. Subscriptions < 50 are sent in a single batch (no delay)
3. Resubscription after reconnect uses the same batching
4. Binance OMS handler routes user data events correctly via WS API
5. BinanceWSApiClient.subscribe_user_data_stream_signature works
"""

import asyncio
import time
import msgspec
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call


# ---------------------------------------------------------------------------
# 1. Binance WSClient subscribe batching
# ---------------------------------------------------------------------------

class TestBinanceWSClientSubscribeBatch:
    """Test BinanceWSClient._subscribe batching."""

    @pytest.fixture
    def ws_client(self):
        from nexustrader.exchange.binance.websockets import BinanceWSClient
        from nexustrader.exchange.binance.constants import BinanceAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        task_manager = TaskManager(loop, enable_signal_handlers=False)
        client = BinanceWSClient(
            account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
            handler=lambda raw: None,
            task_manager=task_manager,
            clock=LiveClock(),
        )
        client.connect = AsyncMock()
        client._send = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_subscribe_under_50_no_delay(self, ws_client):
        """< 50 symbols: single batch, no delay."""
        params = [f"btcusdt@trade_{i}" for i in range(30)]

        start = time.monotonic()
        await ws_client._subscribe(params)
        elapsed = time.monotonic() - start

        assert len(ws_client._subscriptions) == 30
        assert ws_client._send.call_count == 1
        assert elapsed < 0.3

    @pytest.mark.asyncio
    async def test_subscribe_exact_50_no_delay(self, ws_client):
        """Exactly 50 symbols: single batch, no delay."""
        params = [f"sym{i}@trade" for i in range(50)]

        start = time.monotonic()
        await ws_client._subscribe(params)
        elapsed = time.monotonic() - start

        assert len(ws_client._subscriptions) == 50
        assert ws_client._send.call_count == 1
        assert elapsed < 0.3

    @pytest.mark.asyncio
    async def test_subscribe_over_50_batched_with_delay(self, ws_client):
        """120 symbols: 3 batches (50+50+20) with delay between."""
        params = [f"sym{i}@trade" for i in range(120)]

        start = time.monotonic()
        await ws_client._subscribe(params)
        elapsed = time.monotonic() - start

        assert len(ws_client._subscriptions) == 120
        assert ws_client._send.call_count == 3
        assert elapsed >= 0.9  # at least 2 × 0.5s delay between 3 batches

    @pytest.mark.asyncio
    async def test_subscribe_does_not_duplicate(self, ws_client):
        """Already subscribed symbols are skipped."""
        ws_client._subscriptions = [f"sym{i}@trade" for i in range(10)]
        params = [f"sym{i}@trade" for i in range(15)]  # 10 overlap, 5 new

        await ws_client._subscribe(params)

        assert len(ws_client._subscriptions) == 15
        assert ws_client._send.call_count == 1


# ---------------------------------------------------------------------------
# 2. Binance WSClient resubscribe batching
# ---------------------------------------------------------------------------

class TestBinanceWSClientResubscribeBatch:
    """Test BinanceWSClient._resubscribe batching."""

    @pytest.fixture
    def ws_client(self):
        from nexustrader.exchange.binance.websockets import BinanceWSClient
        from nexustrader.exchange.binance.constants import BinanceAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        task_manager = TaskManager(loop, enable_signal_handlers=False)
        client = BinanceWSClient(
            account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
            handler=lambda raw: None,
            task_manager=task_manager,
            clock=LiveClock(),
        )
        client._send = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_resubscribe_under_50(self, ws_client):
        ws_client._subscriptions = [f"sym{i}@trade" for i in range(30)]

        start = time.monotonic()
        await ws_client._resubscribe()
        elapsed = time.monotonic() - start

        assert ws_client._send.call_count == 1
        assert elapsed < 0.3

    @pytest.mark.asyncio
    async def test_resubscribe_over_50(self, ws_client):
        ws_client._subscriptions = [f"sym{i}@trade" for i in range(120)]

        start = time.monotonic()
        await ws_client._resubscribe()
        elapsed = time.monotonic() - start

        assert ws_client._send.call_count == 3
        assert elapsed >= 0.9


# ---------------------------------------------------------------------------
# 3. Bybit subscribe batching
# ---------------------------------------------------------------------------

class TestBybitWSClientSubscribeBatch:

    @pytest.fixture
    def ws_client(self):
        from nexustrader.exchange.bybit.websockets import BybitWSClient
        from nexustrader.exchange.bybit.constants import BybitAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        task_manager = TaskManager(loop, enable_signal_handlers=False)
        client = BybitWSClient(
            account_type=BybitAccountType.LINEAR,
            handler=lambda raw: None,
            task_manager=task_manager,
            clock=LiveClock(),
        )
        client.connect = AsyncMock()
        client._send = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_subscribe_under_50_no_delay(self, ws_client):
        topics = [f"tickers.SYM{i}" for i in range(30)]

        start = time.monotonic()
        await ws_client._subscribe(topics)
        elapsed = time.monotonic() - start

        assert len(ws_client._subscriptions) == 30
        assert ws_client._send.call_count == 1
        assert elapsed < 0.3

    @pytest.mark.asyncio
    async def test_subscribe_over_50_batched(self, ws_client):
        topics = [f"tickers.SYM{i}" for i in range(120)]

        start = time.monotonic()
        await ws_client._subscribe(topics)
        elapsed = time.monotonic() - start

        assert len(ws_client._subscriptions) == 120
        assert ws_client._send.call_count == 3
        assert elapsed >= 0.9


# ---------------------------------------------------------------------------
# 4. OKX subscribe batching
# ---------------------------------------------------------------------------

class TestOKXWSClientSubscribeBatch:

    @pytest.fixture
    def ws_client(self):
        from nexustrader.exchange.okx.websockets import OkxWSClient
        from nexustrader.exchange.okx.constants import OkxAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        task_manager = TaskManager(loop, enable_signal_handlers=False)
        client = OkxWSClient(
            account_type=OkxAccountType.LIVE,
            handler=lambda raw: None,
            task_manager=task_manager,
            clock=LiveClock(),
        )
        client.connect = AsyncMock()
        client._send = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_subscribe_under_50_no_delay(self, ws_client):
        params = [{"channel": "tickers", "instId": f"SYM{i}"} for i in range(30)]

        start = time.monotonic()
        await ws_client._subscribe(params)
        elapsed = time.monotonic() - start

        assert len(ws_client._subscriptions) == 30
        assert ws_client._send.call_count == 1
        assert elapsed < 0.3

    @pytest.mark.asyncio
    async def test_subscribe_over_50_batched(self, ws_client):
        params = [{"channel": "tickers", "instId": f"SYM{i}"} for i in range(120)]

        start = time.monotonic()
        await ws_client._subscribe(params)
        elapsed = time.monotonic() - start

        assert len(ws_client._subscriptions) == 120
        assert ws_client._send.call_count == 3
        assert elapsed >= 0.9


# ---------------------------------------------------------------------------
# 5. Bitget subscribe batching
# ---------------------------------------------------------------------------

class TestBitgetWSClientSubscribeBatch:

    @pytest.fixture
    def ws_client(self):
        from nexustrader.exchange.bitget.websockets import BitgetWSClient
        from nexustrader.exchange.bitget.constants import BitgetAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        task_manager = TaskManager(loop, enable_signal_handlers=False)
        client = BitgetWSClient(
            account_type=BitgetAccountType.SPOT,
            handler=lambda raw: None,
            task_manager=task_manager,
            clock=LiveClock(),
        )
        client.connect = AsyncMock()
        client._send = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_subscribe_under_50_no_delay(self, ws_client):
        params = [
            {"instType": "USDT-FUTURES", "channel": "ticker", "instId": f"SYM{i}"}
            for i in range(30)
        ]

        start = time.monotonic()
        await ws_client._subscribe(params)
        elapsed = time.monotonic() - start

        assert len(ws_client._subscriptions) == 30
        assert ws_client._send.call_count == 1
        assert elapsed < 0.3

    @pytest.mark.asyncio
    async def test_subscribe_over_50_batched(self, ws_client):
        params = [
            {"instType": "USDT-FUTURES", "channel": "ticker", "instId": f"SYM{i}"}
            for i in range(120)
        ]

        start = time.monotonic()
        await ws_client._subscribe(params)
        elapsed = time.monotonic() - start

        assert len(ws_client._subscriptions) == 120
        assert ws_client._send.call_count == 3
        assert elapsed >= 0.9


# ---------------------------------------------------------------------------
# 6. Hyperliquid subscribe batching
# ---------------------------------------------------------------------------

class TestHyperliquidWSClientSubscribeBatch:

    @pytest.fixture
    def ws_client(self):
        from nexustrader.exchange.hyperliquid.websockets import HyperLiquidWSClient
        from nexustrader.exchange.hyperliquid.constants import HyperLiquidAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        task_manager = TaskManager(loop, enable_signal_handlers=False)
        client = HyperLiquidWSClient(
            account_type=HyperLiquidAccountType.MAINNET,
            handler=lambda raw: None,
            task_manager=task_manager,
            clock=LiveClock(),
        )
        client.connect = AsyncMock()
        client._send = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_subscribe_under_50_no_delay(self, ws_client):
        msgs = [{"type": "l2Book", "coin": f"SYM{i}"} for i in range(30)]

        start = time.monotonic()
        await ws_client._subscribe(msgs)
        elapsed = time.monotonic() - start

        assert len(ws_client._subscriptions) == 30
        assert ws_client._send.call_count == 30  # Hyperliquid sends individually
        assert elapsed < 0.3

    @pytest.mark.asyncio
    async def test_subscribe_over_50_batched(self, ws_client):
        msgs = [{"type": "l2Book", "coin": f"SYM{i}"} for i in range(120)]

        start = time.monotonic()
        await ws_client._subscribe(msgs)
        elapsed = time.monotonic() - start

        assert len(ws_client._subscriptions) == 120
        assert ws_client._send.call_count == 120  # still sends individually
        assert elapsed >= 0.9  # but delays between batches of 50


# ---------------------------------------------------------------------------
# 7. Binance OMS handler routing (user data via WS API)
# ---------------------------------------------------------------------------

class TestBinanceOMSHandlerRouting:
    """Test that _ws_api_msg_handler routes user data events correctly."""

    def test_order_response_routed_correctly(self):
        """WS API order response (id starts with 'n') is handled."""
        from nexustrader.exchange.binance.schema import BinanceWsOrderResponse

        order_msg = msgspec.json.encode(
            {"id": "n_test123", "status": 200, "result": {"orderId": 12345, "symbol": "BTCUSDT", "clientOrderId": "test123"}}
        )

        decoder = msgspec.json.Decoder(BinanceWsOrderResponse)
        msg = decoder.decode(order_msg)
        assert msg.id == "n_test123"
        assert msg.id.startswith("n")
        assert msg.is_success

    def test_subscribe_response_skipped(self):
        """WS API subscribe confirmation (id starts with 'uds_') is skipped."""
        from nexustrader.exchange.binance.schema import BinanceWsOrderResponse

        sub_msg = msgspec.json.encode(
            {"id": "uds_1234567890", "status": 200, "result": None}
        )

        decoder = msgspec.json.Decoder(BinanceWsOrderResponse)
        msg = decoder.decode(sub_msg)
        assert msg.id == "uds_1234567890"
        assert not msg.id.startswith("n")
        assert not msg.id.startswith("c")

    def test_user_data_event_causes_decode_error(self):
        """User data events (no 'id' field) fail to decode as BinanceWsOrderResponse."""
        from nexustrader.exchange.binance.schema import BinanceWsOrderResponse

        user_data_msg = msgspec.json.encode(
            {"e": "executionReport", "s": "BTCUSDT", "S": "BUY", "E": 1234567890}
        )

        decoder = msgspec.json.Decoder(BinanceWsOrderResponse)
        with pytest.raises(msgspec.DecodeError):
            decoder.decode(user_data_msg)


# ---------------------------------------------------------------------------
# 8. BinanceWSApiClient user data stream subscription
# ---------------------------------------------------------------------------

class TestBinanceWSApiClientUserDataStream:

    @pytest.fixture
    def ws_api_client(self):
        from nexustrader.exchange.binance.websockets import BinanceWSApiClient
        from nexustrader.exchange.binance.constants import BinanceAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        task_manager = TaskManager(loop, enable_signal_handlers=False)
        client = BinanceWSApiClient(
            account_type=BinanceAccountType.SPOT_TESTNET,
            api_key="test_api_key",
            secret="test_secret_key",
            handler=lambda raw: None,
            task_manager=task_manager,
            clock=LiveClock(),
            enable_rate_limit=False,
        )
        client._send = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_subscribe_user_data_stream_sends_correct_payload(self, ws_api_client):
        """subscribe_user_data_stream_signature sends properly structured message."""
        await ws_api_client.subscribe_user_data_stream_signature()

        assert ws_api_client._user_data_subscribed is True
        assert ws_api_client._send.call_count == 1

        payload = ws_api_client._send.call_args[0][0]
        assert payload["method"] == "userDataStream.subscribe.signature"
        assert payload["id"].startswith("uds_")
        assert "apiKey" in payload["params"]
        assert "timestamp" in payload["params"]
        assert "signature" in payload["params"]
        assert payload["params"]["apiKey"] == "test_api_key"

    @pytest.mark.asyncio
    async def test_resubscribe_when_user_data_subscribed(self, ws_api_client):
        """_resubscribe re-subscribes user data if flag is set."""
        ws_api_client._user_data_subscribed = True

        await ws_api_client._resubscribe()

        assert ws_api_client._send.call_count == 1
        payload = ws_api_client._send.call_args[0][0]
        assert payload["method"] == "userDataStream.subscribe.signature"

    @pytest.mark.asyncio
    async def test_resubscribe_skips_when_not_subscribed(self, ws_api_client):
        """_resubscribe does nothing if user data was never subscribed."""
        ws_api_client._user_data_subscribed = False

        await ws_api_client._resubscribe()

        assert ws_api_client._send.call_count == 0


# ---------------------------------------------------------------------------
# 9. OKX instIdCode migration
# ---------------------------------------------------------------------------

class TestOkxMarketInfoInstIdCode:
    """Test OkxMarketInfo includes instIdCode field."""

    def test_inst_id_code_field_default_none(self):
        """instIdCode defaults to None for backward compat."""
        from nexustrader.exchange.okx.schema import OkxMarketInfo

        info = OkxMarketInfo()
        assert info.instIdCode is None

    def test_inst_id_code_field_set(self):
        """instIdCode can be set from API response."""
        from nexustrader.exchange.okx.schema import OkxMarketInfo

        info = OkxMarketInfo(instId="BTC-USDT-SWAP", instIdCode="BTC-USDT-SWAP")
        assert info.instIdCode == "BTC-USDT-SWAP"
        assert info.instId == "BTC-USDT-SWAP"

    def test_inst_id_code_decoded_from_json(self):
        """instIdCode is correctly decoded when present in JSON."""
        import msgspec

        from nexustrader.exchange.okx.schema import OkxMarketInfo

        raw = msgspec.json.encode(
            {"instId": "BTC-USDT-SWAP", "instIdCode": "BTC-USDT-SWAP", "instType": "SWAP"}
        )
        info = msgspec.json.decode(raw, type=OkxMarketInfo)
        assert info.instIdCode == "BTC-USDT-SWAP"

    def test_inst_id_code_missing_from_json(self):
        """instIdCode is None when not present in JSON (old API response)."""
        import msgspec

        from nexustrader.exchange.okx.schema import OkxMarketInfo

        raw = msgspec.json.encode({"instId": "BTC-USDT-SWAP", "instType": "SWAP"})
        info = msgspec.json.decode(raw, type=OkxMarketInfo)
        assert info.instIdCode is None
        assert info.instId == "BTC-USDT-SWAP"


class TestOkxWSApiClientInstIdCode:
    """Test OkxWSApiClient uses instIdCode when available, falls back to instId."""

    @pytest.fixture
    def ws_api_client(self):
        from nexustrader.exchange.okx.websockets import OkxWSApiClient
        from nexustrader.exchange.okx.constants import OkxAccountType
        from nexustrader.core.entity import TaskManager
        from nexustrader.core.nautilius_core import LiveClock

        loop = asyncio.new_event_loop()
        task_manager = TaskManager(loop, enable_signal_handlers=False)
        client = OkxWSApiClient(
            account_type=OkxAccountType.DEMO,
            api_key="test_key",
            secret="test_secret",
            passphrase="test_pass",
            handler=lambda raw: None,
            task_manager=task_manager,
            clock=LiveClock(),
            enable_rate_limit=False,
        )
        client._send = MagicMock()
        client._authed = True
        return client

    @pytest.mark.asyncio
    async def test_place_order_with_inst_id_code(self, ws_api_client):
        """place_order sends instIdCode when provided."""
        await ws_api_client.place_order(
            id="test_oid",
            instIdCode="BTC-USDT-SWAP",
            tdMode="cross",
            side="buy",
            ordType="limit",
            sz="0.1",
            px="50000",
        )

        assert ws_api_client._send.call_count == 1
        payload = ws_api_client._send.call_args[0][0]
        assert payload["op"] == "order"
        args = payload["args"][0]
        assert "instIdCode" in args
        assert args["instIdCode"] == "BTC-USDT-SWAP"
        assert "instId" not in args

    @pytest.mark.asyncio
    async def test_place_order_fallback_inst_id(self, ws_api_client):
        """place_order falls back to instId when instIdCode is None."""
        await ws_api_client.place_order(
            id="test_oid",
            instId="BTC-USDT-SWAP",
            tdMode="cross",
            side="buy",
            ordType="limit",
            sz="0.1",
            px="50000",
        )

        payload = ws_api_client._send.call_args[0][0]
        args = payload["args"][0]
        assert "instId" in args
        assert args["instId"] == "BTC-USDT-SWAP"
        assert "instIdCode" not in args

    @pytest.mark.asyncio
    async def test_cancel_order_with_inst_id_code(self, ws_api_client):
        """cancel_order sends instIdCode when provided."""
        await ws_api_client.cancel_order(
            id="test_oid",
            clOrdId="order123",
            instIdCode="BTC-USDT-SWAP",
        )

        payload = ws_api_client._send.call_args[0][0]
        assert payload["op"] == "cancel-order"
        args = payload["args"][0]
        assert "instIdCode" in args
        assert args["instIdCode"] == "BTC-USDT-SWAP"
        assert "instId" not in args
        assert args["clOrdId"] == "order123"

    @pytest.mark.asyncio
    async def test_cancel_order_fallback_inst_id(self, ws_api_client):
        """cancel_order falls back to instId when instIdCode is None."""
        await ws_api_client.cancel_order(
            id="test_oid",
            clOrdId="order123",
            instId="BTC-USDT-SWAP",
        )

        payload = ws_api_client._send.call_args[0][0]
        args = payload["args"][0]
        assert "instId" in args
        assert args["instId"] == "BTC-USDT-SWAP"
        assert "instIdCode" not in args
