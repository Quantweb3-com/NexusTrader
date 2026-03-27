"""
Tests for WebSocket ACK error handling.

Covers:
1. WsRequestNotSentError  — socket not connected when send is attempted
2. WsAckTimeoutError      — send succeeded but exchange never replied within 5 s
3. WsAckRejectedError     — exchange explicitly rejected the request (ACK with error)
4. ACK success            — exchange accepted; order moves to PENDING / CANCELING

Each test drives the OMS layer directly (no real network), injecting fake ACK
messages via the internal _ws_api_msg_handler and simulating send failures by
patching _send_or_raise.
"""

import asyncio
import msgspec
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

from nexustrader.error import WsRequestNotSentError, WsAckTimeoutError, WsAckRejectedError
from nexustrader.schema import Order
from nexustrader.constants import ExchangeType, OrderStatus, OrderSide, OrderType


# ---------------------------------------------------------------------------
# Minimal shared fixtures
# ---------------------------------------------------------------------------


def _make_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


def _make_task_manager(loop):
    from nexustrader.core.entity import TaskManager
    return TaskManager(loop=loop, enable_signal_handlers=False)


def _make_clock():
    from nexustrader.core.nautilius_core import LiveClock
    return LiveClock()


def _make_msgbus():
    from nexustrader.core.nautilius_core import MessageBus, TraderId, LiveClock
    return MessageBus(trader_id=TraderId("TEST-001"), clock=LiveClock())


def _make_registry():
    from nexustrader.core.registry import OrderRegistry
    return OrderRegistry()


def _make_cache():
    cache = MagicMock()
    cache.get_open_orders = MagicMock(return_value=[])
    cache.get_inflight_orders = MagicMock(return_value=[])
    cache._apply_balance = MagicMock()
    cache._apply_position = MagicMock()
    return cache


# ===========================================================================
# Helpers: build lightweight WS ACK payloads
# ===========================================================================


def _okx_place_order_ack(oid: str, success: bool, error_msg: str = "") -> bytes:
    """Build a minimal OKX WS API order-place ACK."""
    ts = "1700000000000"
    if success:
        return msgspec.json.encode({
            "id": oid,
            "op": "order",
            "code": "0",
            "msg": "",
            "inTime": ts,
            "outTime": ts,
            "data": [{"clOrdId": oid, "ordId": "9999000001", "sCode": "0", "sMsg": "", "ts": ts}],
        })
    return msgspec.json.encode({
        "id": oid,
        "op": "order",
        "code": "1",
        "msg": error_msg or "Order rejected",
        "inTime": ts,
        "outTime": ts,
        "data": [{"clOrdId": oid, "ordId": "", "sCode": "51008", "sMsg": error_msg or "Order rejected", "ts": ts}],
    })


def _okx_cancel_order_ack(oid: str, success: bool, error_msg: str = "") -> bytes:
    """Build a minimal OKX WS API order-cancel ACK."""
    ts = "1700000000000"
    if success:
        return msgspec.json.encode({
            "id": oid,
            "op": "cancel-order",
            "code": "0",
            "msg": "",
            "inTime": ts,
            "outTime": ts,
            "data": [{"clOrdId": oid, "ordId": "9999000001", "sCode": "0", "sMsg": "", "ts": ts}],
        })
    return msgspec.json.encode({
        "id": oid,
        "op": "cancel-order",
        "code": "1",
        "msg": error_msg or "Cancel rejected",
        "inTime": ts,
        "outTime": ts,
        "data": [{"clOrdId": oid, "ordId": "", "sCode": "51400", "sMsg": error_msg or "Cancel rejected", "ts": ts}],
    })


# ===========================================================================
# 1. WsRequestNotSentError – raised by _send_or_raise when not connected
# ===========================================================================


class TestWsRequestNotSentError:
    """_send_or_raise must raise WsRequestNotSentError when socket is down."""

    def test_raises_when_not_connected(self):
        from nexustrader.base.ws_client import WSClient

        loop = _make_loop()
        tm = _make_task_manager(loop)

        # Use a concrete subclass stub to bypass abstractmethod
        class _StubWS(WSClient):
            async def _resubscribe(self): pass

        ws = _StubWS(
            url="ws://localhost",
            handler=lambda raw: None,
            task_manager=tm,
            clock=_make_clock(),
        )
        # Socket is not connected (transport=None)
        assert not ws.connected
        with pytest.raises(WsRequestNotSentError):
            ws._send_or_raise({"op": "test"})

    def test_no_raise_when_connected(self):
        from nexustrader.base.ws_client import WSClient

        loop = _make_loop()
        tm = _make_task_manager(loop)

        class _StubWS(WSClient):
            async def _resubscribe(self): pass

        ws = _StubWS(
            url="ws://localhost",
            handler=lambda raw: None,
            task_manager=tm,
            clock=_make_clock(),
        )
        # Fake a connected transport
        ws._transport = MagicMock()
        ws._transport.send = MagicMock()
        ws._listener = MagicMock()
        # Should not raise
        ws._send_or_raise({"op": "test"})
        assert ws._transport.send.called


# ===========================================================================
# 2. WsAckTimeoutError – send succeeds but ACK never arrives
# ===========================================================================


class TestWsAckTimeout:
    """create_order_ws raises WsAckTimeoutError when no ACK arrives in time."""

    @pytest.fixture
    def okx_oms(self):
        """Build a minimal OkxOrderManagementSystem with all I/O mocked out."""
        from nexustrader.exchange.okx.oms import OkxOrderManagementSystem
        from nexustrader.exchange.okx.constants import OkxAccountType
        from nexustrader.exchange.okx.schema import OkxMarket

        loop = _make_loop()
        tm = _make_task_manager(loop)
        registry = _make_registry()
        cache = _make_cache()
        cache.get_order = MagicMock(return_value=None)

        # Minimal stub market
        market = MagicMock(spec=OkxMarket)
        market.id = "BTC-USDT-SWAP"
        market.spot = False
        market.info = MagicMock()
        market.info.ctVal = "0.01"
        market.info.instIdCode = None
        market.base = "BTC"
        market.quote = "USDT"

        api_client = MagicMock()
        api_client.get_api_v5_account_balance = AsyncMock(
            return_value=MagicMock(data=[MagicMock(parse_to_balances=lambda: [])])
        )
        api_client.get_api_v5_account_positions = AsyncMock(
            return_value=MagicMock(data=[])
        )
        api_client.get_api_v5_account_config = AsyncMock(
            return_value=MagicMock(
                data=[MagicMock(
                    posMode=MagicMock(is_one_way_mode=True),
                    acctLv=MagicMock(is_portfolio_margin=False, is_futures=False),
                )]
            )
        )

        with (
            patch.object(OkxOrderManagementSystem, "_init_account_balance"),
            patch.object(OkxOrderManagementSystem, "_init_position"),
            patch.object(OkxOrderManagementSystem, "_position_mode_check"),
        ):
            oms = OkxOrderManagementSystem(
                account_type=OkxAccountType.LIVE,
                api_key="k",
                secret="s",
                passphrase="p",
                market={"BTCUSDT-PERP.OKX": market},
                market_id={"BTC-USDT-SWAP": "BTCUSDT-PERP.OKX"},
                registry=registry,
                cache=cache,
                api_client=api_client,
                exchange_id=ExchangeType.OKX,
                clock=_make_clock(),
                msgbus=_make_msgbus(),
                task_manager=tm,
                enable_rate_limit=False,
            )
        oms._acctLv = MagicMock(is_portfolio_margin=False, is_futures=False)
        oms.order_status_update = MagicMock()

        # WS API client: send always "succeeds" but ACK never arrives
        oms._ws_api_client.place_order = AsyncMock()
        oms._ws_api_client.cancel_order = AsyncMock()
        return oms, loop

    @pytest.mark.asyncio
    async def test_create_order_ws_ack_timeout(self, okx_oms):
        oms, loop = okx_oms
        # fetch_order returns None → REST confirmation fails → WsAckTimeoutError
        oms.fetch_order = AsyncMock(return_value=None)

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(WsAckTimeoutError) as exc_info:
                await oms.create_order_ws(
                    oid="oid-timeout-001",
                    symbol="BTCUSDT-PERP.OKX",
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    amount=Decimal("0.01"),
                    price=Decimal("90000"),
                )
        assert exc_info.value.oid == "oid-timeout-001"
        assert exc_info.value.timeout == 5.0
        assert "oid-timeout-001" not in oms._pending_ws_acks

    @pytest.mark.asyncio
    async def test_cancel_order_ws_ack_timeout(self, okx_oms):
        oms, loop = okx_oms
        oms.fetch_order = AsyncMock(return_value=None)
        oms._market["BTCUSDT-PERP.OKX"] = oms._market["BTCUSDT-PERP.OKX"]

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(WsAckTimeoutError) as exc_info:
                await oms.cancel_order_ws(
                    oid="oid-timeout-002",
                    symbol="BTCUSDT-PERP.OKX",
                )
        assert exc_info.value.oid == "oid-timeout-002"
        assert "oid-timeout-002" not in oms._pending_ws_acks

    @pytest.mark.asyncio
    async def test_ack_timeout_rest_confirmation_success(self, okx_oms):
        """When ACK times out but REST fetch_order finds the order, no error is raised."""
        oms, loop = okx_oms
        confirmed_order = Order(
            oid="oid-timeout-003",
            exchange=ExchangeType.OKX,
            symbol="BTCUSDT-PERP.OKX",
            status=OrderStatus.ACCEPTED,
            amount=Decimal("0.01"),
            type=OrderType.LIMIT,
            side=OrderSide.BUY,
            price=90000.0,
            timestamp=0,
        )
        oms.fetch_order = AsyncMock(return_value=confirmed_order)

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            # Should NOT raise because REST confirmation succeeds
            await oms.create_order_ws(
                oid="oid-timeout-003",
                symbol="BTCUSDT-PERP.OKX",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=Decimal("90000"),
            )
        oms.order_status_update.assert_called()
        assert "oid-timeout-003" not in oms._pending_ws_acks


# ===========================================================================
# 3. WsAckRejectedError class
# ===========================================================================


class TestWsAckRejectedError:
    """WsAckRejectedError must carry oid and reason."""

    def test_attributes(self):
        err = WsAckRejectedError(oid="oid-rej-001", reason="Insufficient balance")
        assert err.oid == "oid-rej-001"
        assert err.reason == "Insufficient balance"
        assert "oid-rej-001" in str(err)
        assert "Insufficient balance" in str(err)


# ===========================================================================
# 4. ACK success — future is resolved, order moves to PENDING
# ===========================================================================


class TestWsAckSuccess:
    """_resolve_ws_ack resolves pending future; order_status_update called with PENDING."""

    @pytest.mark.asyncio
    async def test_resolve_ws_ack_sets_future(self):
        """Calling _resolve_ws_ack unblocks the awaiting coroutine."""
        from nexustrader.exchange.okx.oms import OkxOrderManagementSystem

        loop = asyncio.get_event_loop()

        with (
            patch.object(OkxOrderManagementSystem, "_init_account_balance"),
            patch.object(OkxOrderManagementSystem, "_init_position"),
            patch.object(OkxOrderManagementSystem, "_position_mode_check"),
        ):
            oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)
            oms._pending_ws_acks = {}
            oms._log = MagicMock()

        oid = "oid-success-001"
        fut: asyncio.Future = loop.create_future()
        oms._pending_ws_acks[oid] = fut

        # Simulate ACK arriving
        oms._resolve_ws_ack(oid)

        assert fut.done()
        assert fut.result() is True
        assert oid not in oms._pending_ws_acks

    @pytest.mark.asyncio
    async def test_resolve_ws_ack_idempotent(self):
        """Calling _resolve_ws_ack twice does not raise."""
        from nexustrader.exchange.okx.oms import OkxOrderManagementSystem

        loop = asyncio.get_event_loop()

        oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()

        oid = "oid-success-002"
        fut: asyncio.Future = loop.create_future()
        oms._pending_ws_acks[oid] = fut

        oms._resolve_ws_ack(oid)
        oms._resolve_ws_ack(oid)  # second call — future already gone, must not raise

        assert fut.done()

    @pytest.mark.asyncio
    async def test_ws_api_msg_handler_resolves_ack_on_success(self):
        """_ws_api_msg_handler calls _resolve_ws_ack after a successful place-order ACK."""
        from nexustrader.exchange.okx.oms import OkxOrderManagementSystem
        from nexustrader.exchange.okx.schema import OkxWsGeneralMsg, OkxWsApiOrderResponse
        from nexustrader.core.registry import OrderRegistry

        loop = asyncio.get_event_loop()

        oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.OKX
        oms._decoder_ws_general_msg = msgspec.json.Decoder(OkxWsGeneralMsg)
        oms._ws_msg_ws_api_response_decoder = msgspec.json.Decoder(OkxWsApiOrderResponse)
        oms.order_status_update = MagicMock()

        registry = OrderRegistry()
        oms._registry = registry

        oid = "oid-success-003"
        # Register a tmp order so the handler can look it up
        registry.register_tmp_order(Order(
            oid=oid,
            exchange=ExchangeType.OKX,
            symbol="BTCUSDT-PERP.OKX",
            status=OrderStatus.INITIALIZED,
            amount=Decimal("0.01"),
            type=OrderType.LIMIT,
            side=OrderSide.BUY,
            price=90000.0,
            timestamp=0,
        ))

        fut: asyncio.Future = loop.create_future()
        oms._pending_ws_acks[oid] = fut

        raw = _okx_place_order_ack(oid, success=True)
        oms._ws_api_msg_handler(raw)

        assert fut.done()
        assert fut.result() is True
        assert oms.order_status_update.call_count == 1
        placed_order: Order = oms.order_status_update.call_args[0][0]
        assert placed_order.status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_ws_api_msg_handler_resolves_ack_on_reject(self):
        """_ws_api_msg_handler calls _resolve_ws_ack even for a rejected ACK."""
        from nexustrader.exchange.okx.oms import OkxOrderManagementSystem
        from nexustrader.exchange.okx.schema import OkxWsGeneralMsg, OkxWsApiOrderResponse
        from nexustrader.core.registry import OrderRegistry

        loop = asyncio.get_event_loop()

        oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.OKX
        oms._decoder_ws_general_msg = msgspec.json.Decoder(OkxWsGeneralMsg)
        oms._ws_msg_ws_api_response_decoder = msgspec.json.Decoder(OkxWsApiOrderResponse)
        oms.order_status_update = MagicMock()

        registry = OrderRegistry()
        oms._registry = registry

        oid = "oid-reject-001"
        registry.register_tmp_order(Order(
            oid=oid,
            exchange=ExchangeType.OKX,
            symbol="BTCUSDT-PERP.OKX",
            status=OrderStatus.INITIALIZED,
            amount=Decimal("0.01"),
            type=OrderType.LIMIT,
            side=OrderSide.BUY,
            price=90000.0,
            timestamp=0,
        ))

        fut: asyncio.Future = loop.create_future()
        oms._pending_ws_acks[oid] = fut

        raw = _okx_place_order_ack(oid, success=False, error_msg="Insufficient balance")
        oms._ws_api_msg_handler(raw)

        assert fut.done()
        assert oms.order_status_update.call_count == 1
        failed_order: Order = oms.order_status_update.call_args[0][0]
        assert failed_order.status == OrderStatus.FAILED
        assert "Insufficient balance" in (failed_order.reason or "")


# ===========================================================================
# 5. WS not-sent → fallback to REST (ws_fallback=True)
# ===========================================================================


# ===========================================================================
# 4b. WS API disconnect – pending ACK futures are rejected
# ===========================================================================


class TestWsApiDisconnectRejectsPendingAcks:
    """When WS API client disconnects, all pending ACK futures are rejected."""

    @pytest.mark.asyncio
    async def test_reject_all_pending_ws_acks(self):
        """_reject_all_pending_ws_acks sets WsRequestNotSentError on all pending futures."""
        from nexustrader.exchange.okx.oms import OkxOrderManagementSystem

        loop = asyncio.get_event_loop()
        oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()

        fut1: asyncio.Future = loop.create_future()
        fut2: asyncio.Future = loop.create_future()
        oms._pending_ws_acks["oid-dc-001"] = fut1
        oms._pending_ws_acks["oid-dc-002"] = fut2

        oms._reject_all_pending_ws_acks()

        assert fut1.done()
        assert fut2.done()
        with pytest.raises(WsRequestNotSentError):
            fut1.result()
        with pytest.raises(WsRequestNotSentError):
            fut2.result()
        assert len(oms._pending_ws_acks) == 0

    @pytest.mark.asyncio
    async def test_on_ws_api_disconnected_calls_reject(self):
        """_on_ws_api_disconnected triggers _reject_all_pending_ws_acks."""
        from nexustrader.exchange.okx.oms import OkxOrderManagementSystem

        oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._reject_all_pending_ws_acks = MagicMock()

        oms._on_ws_api_disconnected()

        oms._reject_all_pending_ws_acks.assert_called_once()


class TestWsRequestNotSentFallback:
    """When socket is down and ws_fallback=True, OMS falls back to REST."""

    @pytest.mark.asyncio
    async def test_create_order_ws_fallback_called(self):
        """When WsRequestNotSentError is raised, create_order (REST) is called instead."""
        from nexustrader.exchange.okx.oms import OkxOrderManagementSystem
        from nexustrader.exchange.okx.schema import OkxMarket

        with (
            patch.object(OkxOrderManagementSystem, "_init_account_balance"),
            patch.object(OkxOrderManagementSystem, "_init_position"),
            patch.object(OkxOrderManagementSystem, "_position_mode_check"),
        ):
            oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)

        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.OKX
        oms._acctLv = MagicMock(is_portfolio_margin=False, is_futures=False)
        oms.order_status_update = MagicMock()
        oms._registry = _make_registry()

        market = MagicMock(spec=OkxMarket)
        market.id = "BTC-USDT-SWAP"
        market.spot = False
        market.info = MagicMock()
        market.info.ctVal = "0.01"
        market.info.instIdCode = None
        market.base = "BTC"
        market.quote = "USDT"
        oms._market = {"BTCUSDT-PERP.OKX": market}

        oms._ws_api_client = MagicMock()
        oms._ws_api_client.place_order = AsyncMock(side_effect=WsRequestNotSentError())
        oms.create_order = AsyncMock()

        await oms.create_order_ws(
            oid="oid-fallback-001",
            symbol="BTCUSDT-PERP.OKX",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("90000"),
            ws_fallback=True,
        )

        oms.create_order.assert_awaited_once()
        # Future must be cleaned up
        assert "oid-fallback-001" not in oms._pending_ws_acks

    @pytest.mark.asyncio
    async def test_create_order_ws_no_fallback_marks_failed(self):
        """When socket is down and ws_fallback=False, order is marked FAILED."""
        from nexustrader.exchange.okx.oms import OkxOrderManagementSystem
        from nexustrader.exchange.okx.schema import OkxMarket

        with (
            patch.object(OkxOrderManagementSystem, "_init_account_balance"),
            patch.object(OkxOrderManagementSystem, "_init_position"),
            patch.object(OkxOrderManagementSystem, "_position_mode_check"),
        ):
            oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)

        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.OKX
        oms._acctLv = MagicMock(is_portfolio_margin=False, is_futures=False)
        oms.order_status_update = MagicMock()
        oms._registry = _make_registry()

        market = MagicMock(spec=OkxMarket)
        market.id = "BTC-USDT-SWAP"
        market.spot = False
        market.info = MagicMock()
        market.info.ctVal = "0.01"
        market.info.instIdCode = None
        market.base = "BTC"
        market.quote = "USDT"
        oms._market = {"BTCUSDT-PERP.OKX": market}

        oms._ws_api_client = MagicMock()
        oms._ws_api_client.place_order = AsyncMock(side_effect=WsRequestNotSentError())

        await oms.create_order_ws(
            oid="oid-nofallback-001",
            symbol="BTCUSDT-PERP.OKX",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("90000"),
            ws_fallback=False,
        )

        assert oms.order_status_update.call_count == 1
        failed: Order = oms.order_status_update.call_args[0][0]
        assert failed.status == OrderStatus.FAILED
        assert "WS_REQUEST_NOT_SENT" in (failed.reason or "")
        assert "oid-nofallback-001" not in oms._pending_ws_acks


# ===========================================================================
# 6. Bitget/HyperLiquid parity — ACK timeout must REST-confirm before raising
# ===========================================================================


class TestWsAckTimeoutRestConfirmationParity:
    """Bitget/HyperLiquid should match OKX/Bybit/Binance ACK-timeout semantics."""

    @pytest.mark.asyncio
    async def test_bitget_create_order_ws_ack_timeout_confirmed(self):
        """Bitget create_order_ws does not raise when REST confirmation succeeds."""
        from nexustrader.exchange.bitget.oms import BitgetOrderManagementSystem
        from nexustrader.exchange.bitget.constants import BitgetAccountType

        oms = BitgetOrderManagementSystem.__new__(BitgetOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.BITGET
        oms._registry = _make_registry()
        oms._cache = MagicMock()
        oms._cache.bookl1 = MagicMock(return_value=None)
        oms._account_type = BitgetAccountType.UTA
        oms._max_slippage = 0.01
        oms._market = {
            "BTCUSDT-PERP.BITGET": MagicMock(
                id="BTCUSDT",
                spot=False,
                linear=True,
                inverse=False,
                swap=True,
                quote="USDT",
            )
        }
        oms._ws_api_client = MagicMock()
        oms._ws_api_client.uta_place_order = AsyncMock(return_value=None)
        oms.order_status_update = MagicMock()
        oms._confirm_order_after_ack_timeout = AsyncMock(return_value=True)

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            await oms.create_order_ws(
                oid="bg-ack-timeout-001",
                symbol="BTCUSDT-PERP.BITGET",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=Decimal("90000"),
            )

        oms._confirm_order_after_ack_timeout.assert_awaited_once_with(
            "bg-ack-timeout-001", "BTCUSDT-PERP.BITGET"
        )

    @pytest.mark.asyncio
    async def test_bitget_create_order_ws_ack_timeout_unconfirmed_raises(self):
        """Bitget create_order_ws raises WsAckTimeoutError when REST confirm fails."""
        from nexustrader.exchange.bitget.oms import BitgetOrderManagementSystem
        from nexustrader.exchange.bitget.constants import BitgetAccountType

        oms = BitgetOrderManagementSystem.__new__(BitgetOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.BITGET
        oms._registry = _make_registry()
        oms._cache = MagicMock()
        oms._cache.bookl1 = MagicMock(return_value=None)
        oms._account_type = BitgetAccountType.UTA
        oms._max_slippage = 0.01
        oms._market = {
            "BTCUSDT-PERP.BITGET": MagicMock(
                id="BTCUSDT",
                spot=False,
                linear=True,
                inverse=False,
                swap=True,
                quote="USDT",
            )
        }
        oms._ws_api_client = MagicMock()
        oms._ws_api_client.uta_place_order = AsyncMock(return_value=None)
        oms.order_status_update = MagicMock()
        oms._confirm_order_after_ack_timeout = AsyncMock(return_value=False)

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(WsAckTimeoutError) as exc_info:
                await oms.create_order_ws(
                    oid="bg-ack-timeout-002",
                    symbol="BTCUSDT-PERP.BITGET",
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    amount=Decimal("0.01"),
                    price=Decimal("90000"),
                )

        assert exc_info.value.oid == "bg-ack-timeout-002"
        oms._confirm_order_after_ack_timeout.assert_awaited_once_with(
            "bg-ack-timeout-002", "BTCUSDT-PERP.BITGET"
        )

    @pytest.mark.asyncio
    async def test_hyperliquid_create_order_ws_ack_timeout_confirmed(self):
        """HyperLiquid create_order_ws does not raise when REST confirmation succeeds."""
        from nexustrader.exchange.hyperliquid.oms import HyperLiquidOrderManagementSystem

        oms = HyperLiquidOrderManagementSystem.__new__(HyperLiquidOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.HYPERLIQUID
        oms._registry = _make_registry()
        oms._cache = MagicMock()
        oms._cache.bookl1 = MagicMock(return_value=None)
        oms._max_slippage = 0.01
        oms._market = {
            "BTCUSDC-PERP.HYPERLIQUID": MagicMock(baseId=0)
        }
        oms._ws_api_client = MagicMock()
        oms._ws_api_client.place_order = AsyncMock(return_value=None)
        oms.order_status_update = MagicMock()
        oms._confirm_order_after_ack_timeout = AsyncMock(return_value=True)

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            await oms.create_order_ws(
                oid="hl-ack-timeout-001",
                symbol="BTCUSDC-PERP.HYPERLIQUID",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=Decimal("90000"),
            )

        oms._confirm_order_after_ack_timeout.assert_awaited_once_with(
            "hl-ack-timeout-001", "BTCUSDC-PERP.HYPERLIQUID"
        )

    @pytest.mark.asyncio
    async def test_hyperliquid_create_order_ws_ack_timeout_unconfirmed_raises(self):
        """HyperLiquid create_order_ws raises WsAckTimeoutError when REST confirm fails."""
        from nexustrader.exchange.hyperliquid.oms import HyperLiquidOrderManagementSystem

        oms = HyperLiquidOrderManagementSystem.__new__(HyperLiquidOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.HYPERLIQUID
        oms._registry = _make_registry()
        oms._cache = MagicMock()
        oms._cache.bookl1 = MagicMock(return_value=None)
        oms._max_slippage = 0.01
        oms._market = {
            "BTCUSDC-PERP.HYPERLIQUID": MagicMock(baseId=0)
        }
        oms._ws_api_client = MagicMock()
        oms._ws_api_client.place_order = AsyncMock(return_value=None)
        oms.order_status_update = MagicMock()
        oms._confirm_order_after_ack_timeout = AsyncMock(return_value=False)

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(WsAckTimeoutError) as exc_info:
                await oms.create_order_ws(
                    oid="hl-ack-timeout-002",
                    symbol="BTCUSDC-PERP.HYPERLIQUID",
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    amount=Decimal("0.01"),
                    price=Decimal("90000"),
                )

        assert exc_info.value.oid == "hl-ack-timeout-002"
        oms._confirm_order_after_ack_timeout.assert_awaited_once_with(
            "hl-ack-timeout-002", "BTCUSDC-PERP.HYPERLIQUID"
        )

    @pytest.mark.asyncio
    async def test_bitget_cancel_order_ws_ack_timeout_confirmed(self):
        """Bitget cancel_order_ws does not raise when REST confirmation succeeds."""
        from nexustrader.exchange.bitget.oms import BitgetOrderManagementSystem
        from nexustrader.exchange.bitget.constants import BitgetAccountType

        oms = BitgetOrderManagementSystem.__new__(BitgetOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.BITGET
        oms._registry = _make_registry()
        oms._account_type = BitgetAccountType.UTA
        oms._market = {
            "BTCUSDT-PERP.BITGET": MagicMock(
                id="BTCUSDT",
                spot=False,
                linear=True,
                inverse=False,
                swap=True,
                quote="USDT",
            )
        }
        oms._ws_api_client = MagicMock()
        oms._ws_api_client.uta_cancel_order = AsyncMock(return_value=None)
        oms._confirm_order_after_ack_timeout = AsyncMock(return_value=True)

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            await oms.cancel_order_ws(
                oid="bg-cancel-timeout-001",
                symbol="BTCUSDT-PERP.BITGET",
            )

        oms._confirm_order_after_ack_timeout.assert_awaited_once_with(
            "bg-cancel-timeout-001", "BTCUSDT-PERP.BITGET"
        )

    @pytest.mark.asyncio
    async def test_bitget_cancel_order_ws_ack_timeout_unconfirmed_raises(self):
        """Bitget cancel_order_ws raises WsAckTimeoutError when REST confirm fails."""
        from nexustrader.exchange.bitget.oms import BitgetOrderManagementSystem
        from nexustrader.exchange.bitget.constants import BitgetAccountType

        oms = BitgetOrderManagementSystem.__new__(BitgetOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.BITGET
        oms._registry = _make_registry()
        oms._account_type = BitgetAccountType.UTA
        oms._market = {
            "BTCUSDT-PERP.BITGET": MagicMock(
                id="BTCUSDT",
                spot=False,
                linear=True,
                inverse=False,
                swap=True,
                quote="USDT",
            )
        }
        oms._ws_api_client = MagicMock()
        oms._ws_api_client.uta_cancel_order = AsyncMock(return_value=None)
        oms._confirm_order_after_ack_timeout = AsyncMock(return_value=False)

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(WsAckTimeoutError) as exc_info:
                await oms.cancel_order_ws(
                    oid="bg-cancel-timeout-002",
                    symbol="BTCUSDT-PERP.BITGET",
                )

        assert exc_info.value.oid == "bg-cancel-timeout-002"
        oms._confirm_order_after_ack_timeout.assert_awaited_once_with(
            "bg-cancel-timeout-002", "BTCUSDT-PERP.BITGET"
        )

    @pytest.mark.asyncio
    async def test_hyperliquid_cancel_order_ws_ack_timeout_confirmed(self):
        """HyperLiquid cancel_order_ws does not raise when REST confirmation succeeds."""
        from nexustrader.exchange.hyperliquid.oms import HyperLiquidOrderManagementSystem

        oms = HyperLiquidOrderManagementSystem.__new__(HyperLiquidOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.HYPERLIQUID
        oms._registry = _make_registry()
        oms._market = {
            "BTCUSDC-PERP.HYPERLIQUID": MagicMock(baseId=0)
        }
        oms._ws_api_client = MagicMock()
        oms._ws_api_client.cancel_orders_by_cloid = AsyncMock(return_value=None)
        oms._confirm_order_after_ack_timeout = AsyncMock(return_value=True)

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            await oms.cancel_order_ws(
                oid="hl-cancel-timeout-001",
                symbol="BTCUSDC-PERP.HYPERLIQUID",
            )

        oms._confirm_order_after_ack_timeout.assert_awaited_once_with(
            "hl-cancel-timeout-001", "BTCUSDC-PERP.HYPERLIQUID"
        )

    @pytest.mark.asyncio
    async def test_hyperliquid_cancel_order_ws_ack_timeout_unconfirmed_raises(self):
        """HyperLiquid cancel_order_ws raises WsAckTimeoutError when REST confirm fails."""
        from nexustrader.exchange.hyperliquid.oms import HyperLiquidOrderManagementSystem

        oms = HyperLiquidOrderManagementSystem.__new__(HyperLiquidOrderManagementSystem)
        oms._pending_ws_acks = {}
        oms._log = MagicMock()
        oms._clock = _make_clock()
        oms._exchange_id = ExchangeType.HYPERLIQUID
        oms._registry = _make_registry()
        oms._market = {
            "BTCUSDC-PERP.HYPERLIQUID": MagicMock(baseId=0)
        }
        oms._ws_api_client = MagicMock()
        oms._ws_api_client.cancel_orders_by_cloid = AsyncMock(return_value=None)
        oms._confirm_order_after_ack_timeout = AsyncMock(return_value=False)

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(WsAckTimeoutError) as exc_info:
                await oms.cancel_order_ws(
                    oid="hl-cancel-timeout-002",
                    symbol="BTCUSDC-PERP.HYPERLIQUID",
                )

        assert exc_info.value.oid == "hl-cancel-timeout-002"
        oms._confirm_order_after_ack_timeout.assert_awaited_once_with(
            "hl-cancel-timeout-002", "BTCUSDC-PERP.HYPERLIQUID"
        )
