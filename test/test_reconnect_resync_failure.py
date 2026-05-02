"""
Tests for private WS reconnect resync failure semantics.

Acceptance criteria:
- When _resync_after_reconnect() fails, `resync_failed` is published but `resynced` is NOT.
- When _resync_after_reconnect() succeeds, `resynced` is published but `resync_failed` is NOT.
- `private_ws_resync_diff` is always published (on both success and failure).
- The diff payload always contains `exchange`, `account_type`, `timestamp`, and `diff`.
- The inner diff always contains a `success` boolean.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexustrader.constants import ExchangeType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_clock():
    from nexustrader.core.nautilius_core import LiveClock

    return LiveClock()


def _make_msgbus():
    from nexustrader.core.nautilius_core import MessageBus, TraderId, LiveClock

    return MessageBus(trader_id=TraderId("TEST-001"), clock=LiveClock())


def _make_concrete_oms(msgbus):
    """Return a minimal OkxOrderManagementSystem wired to *msgbus*, with all
    init side-effects patched out."""
    from nexustrader.exchange.okx.oms import OkxOrderManagementSystem

    with (
        patch.object(OkxOrderManagementSystem, "_init_account_balance"),
        patch.object(OkxOrderManagementSystem, "_init_position"),
        patch.object(OkxOrderManagementSystem, "_position_mode_check"),
    ):
        oms = OkxOrderManagementSystem.__new__(OkxOrderManagementSystem)

    oms._log = MagicMock()
    oms._exchange_id = ExchangeType.OKX
    oms._account_type = MagicMock()
    oms._account_type.value = "DEMO"
    oms._clock = _make_clock()
    oms._msgbus = msgbus
    oms._cache = MagicMock()
    return oms


# ---------------------------------------------------------------------------
# 1. resync failure → resync_failed published, resynced NOT published
# ---------------------------------------------------------------------------


class TestResyncFailureSemantics:
    """_on_private_ws_reconnected must publish resync_failed when resync fails."""

    @pytest.mark.asyncio
    async def test_resync_failure_publishes_resync_failed(self):
        msgbus = _make_msgbus()
        oms = _make_concrete_oms(msgbus)

        published_events: list[dict] = []
        msgbus.subscribe(
            topic="private_ws_status",
            handler=lambda m: published_events.append(m),
        )

        diff_msgs: list[dict] = []
        msgbus.subscribe(
            topic="private_ws_resync_diff",
            handler=lambda m: diff_msgs.append(m),
        )

        oms._resync_after_reconnect = AsyncMock(
            return_value={
                "success": False,
                "error": "REST API timeout",
                "positions_opened": [],
                "positions_closed": [],
                "open_orders_added": [],
                "open_orders_removed": [],
            }
        )

        await oms._on_private_ws_reconnected()

        status_events = [e["event"] for e in published_events]

        assert "resync_failed" in status_events, (
            "resync_failed must be published when resync returns success=False"
        )
        assert "resynced" not in status_events, (
            "resynced must NOT be published when resync returns success=False"
        )

    @pytest.mark.asyncio
    async def test_resync_failure_never_emits_resynced(self):
        """Regression: even if called multiple times, resynced must not appear on failure."""
        msgbus = _make_msgbus()
        oms = _make_concrete_oms(msgbus)

        events: list[str] = []
        msgbus.subscribe(
            topic="private_ws_status",
            handler=lambda m: events.append(m["event"]),
        )

        oms._resync_after_reconnect = AsyncMock(
            return_value={"success": False, "error": "network error"}
        )

        await oms._on_private_ws_reconnected()
        await oms._on_private_ws_reconnected()

        assert "resynced" not in events
        assert events.count("resync_failed") == 2

    @pytest.mark.asyncio
    async def test_resync_diff_always_published_on_failure(self):
        """`private_ws_resync_diff` must be published even when resync fails."""
        msgbus = _make_msgbus()
        oms = _make_concrete_oms(msgbus)

        diff_msgs: list[dict] = []
        msgbus.subscribe(
            topic="private_ws_resync_diff",
            handler=lambda m: diff_msgs.append(m),
        )

        failure_diff = {
            "success": False,
            "error": "Position fetch failed",
            "positions_opened": [],
            "positions_closed": [],
            "open_orders_added": [],
            "open_orders_removed": [],
        }
        oms._resync_after_reconnect = AsyncMock(return_value=failure_diff)

        await oms._on_private_ws_reconnected()

        assert len(diff_msgs) == 1, (
            "private_ws_resync_diff must be published exactly once"
        )
        msg = diff_msgs[0]
        assert "exchange" in msg
        assert "account_type" in msg
        assert "timestamp" in msg
        assert "diff" in msg
        assert msg["diff"]["success"] is False
        assert msg["diff"]["error"] == "Position fetch failed"

    @pytest.mark.asyncio
    async def test_reconnected_event_always_emitted_first(self):
        """The `reconnected` event must always precede `resync_failed`."""
        msgbus = _make_msgbus()
        oms = _make_concrete_oms(msgbus)

        order: list[str] = []
        msgbus.subscribe(
            topic="private_ws_status",
            handler=lambda m: order.append(m["event"]),
        )

        oms._resync_after_reconnect = AsyncMock(
            return_value={"success": False, "error": "timeout"}
        )

        await oms._on_private_ws_reconnected()

        assert order[0] == "reconnected"
        assert "resync_failed" in order
        reconnected_idx = order.index("reconnected")
        resync_failed_idx = order.index("resync_failed")
        assert reconnected_idx < resync_failed_idx


# ---------------------------------------------------------------------------
# 2. resync success → resynced published, resync_failed NOT published
# ---------------------------------------------------------------------------


class TestResyncSuccessSemantics:
    """_on_private_ws_reconnected must publish resynced when resync succeeds."""

    @pytest.mark.asyncio
    async def test_resync_success_publishes_resynced(self):
        msgbus = _make_msgbus()
        oms = _make_concrete_oms(msgbus)

        events: list[str] = []
        msgbus.subscribe(
            topic="private_ws_status",
            handler=lambda m: events.append(m["event"]),
        )

        oms._resync_after_reconnect = AsyncMock(
            return_value={
                "success": True,
                "positions_opened": [],
                "positions_closed": [],
                "open_orders_added": [],
                "open_orders_removed": [],
            }
        )

        await oms._on_private_ws_reconnected()

        assert "resynced" in events, "resynced must be published on success"
        assert "resync_failed" not in events, (
            "resync_failed must NOT be published on success"
        )

    @pytest.mark.asyncio
    async def test_resync_diff_published_on_success(self):
        """`private_ws_resync_diff` must be published on success too."""
        msgbus = _make_msgbus()
        oms = _make_concrete_oms(msgbus)

        diff_msgs: list[dict] = []
        msgbus.subscribe(
            topic="private_ws_resync_diff",
            handler=lambda m: diff_msgs.append(m),
        )

        oms._resync_after_reconnect = AsyncMock(
            return_value={
                "success": True,
                "positions_opened": ["BTCUSDT-PERP.OKX"],
                "positions_closed": [],
                "open_orders_added": [],
                "open_orders_removed": ["old-oid-1"],
            }
        )

        await oms._on_private_ws_reconnected()

        assert len(diff_msgs) == 1
        msg = diff_msgs[0]
        assert msg["diff"]["success"] is True
        assert msg["diff"]["positions_opened"] == ["BTCUSDT-PERP.OKX"]

    @pytest.mark.asyncio
    async def test_event_order_reconnected_then_resynced(self):
        """`reconnected` must always come before `resynced`."""
        msgbus = _make_msgbus()
        oms = _make_concrete_oms(msgbus)

        order: list[str] = []
        msgbus.subscribe(
            topic="private_ws_status",
            handler=lambda m: order.append(m["event"]),
        )

        oms._resync_after_reconnect = AsyncMock(return_value={"success": True})

        await oms._on_private_ws_reconnected()

        assert order[0] == "reconnected"
        assert "resynced" in order
        assert order.index("reconnected") < order.index("resynced")


# ---------------------------------------------------------------------------
# 3. Structural payload validation
# ---------------------------------------------------------------------------


class TestResyncEventPayloadStructure:
    """All private_ws_status events must carry required metadata fields."""

    @pytest.mark.asyncio
    async def test_status_event_payload_has_required_fields(self):
        msgbus = _make_msgbus()
        oms = _make_concrete_oms(msgbus)

        received: list[dict] = []
        msgbus.subscribe(
            topic="private_ws_status",
            handler=lambda m: received.append(m),
        )

        oms._resync_after_reconnect = AsyncMock(
            return_value={"success": False, "error": "test"}
        )

        await oms._on_private_ws_reconnected()

        for evt in received:
            assert "exchange" in evt, f"Missing 'exchange' in {evt}"
            assert "account_type" in evt, f"Missing 'account_type' in {evt}"
            assert "event" in evt, f"Missing 'event' in {evt}"
            assert "timestamp" in evt, f"Missing 'timestamp' in {evt}"
            assert isinstance(evt["timestamp"], int)

    @pytest.mark.asyncio
    async def test_resync_diff_payload_has_required_fields_on_failure(self):
        msgbus = _make_msgbus()
        oms = _make_concrete_oms(msgbus)

        diff_msgs: list[dict] = []
        msgbus.subscribe(
            topic="private_ws_resync_diff",
            handler=lambda m: diff_msgs.append(m),
        )

        oms._resync_after_reconnect = AsyncMock(
            return_value={"success": False, "error": "boom"}
        )

        await oms._on_private_ws_reconnected()

        assert len(diff_msgs) == 1
        msg = diff_msgs[0]
        required_outer = {"exchange", "account_type", "timestamp", "diff"}
        assert required_outer.issubset(msg.keys()), (
            f"Missing outer keys: {required_outer - msg.keys()}"
        )
        inner = msg["diff"]
        assert "success" in inner
        assert "error" in inner
        assert inner["success"] is False

    @pytest.mark.asyncio
    async def test_resync_diff_payload_on_success_has_diff_fields(self):
        msgbus = _make_msgbus()
        oms = _make_concrete_oms(msgbus)

        diff_msgs: list[dict] = []
        msgbus.subscribe(
            topic="private_ws_resync_diff",
            handler=lambda m: diff_msgs.append(m),
        )

        oms._resync_after_reconnect = AsyncMock(
            return_value={
                "success": True,
                "positions_opened": [],
                "positions_closed": [],
                "open_orders_added": [],
                "open_orders_removed": [],
            }
        )

        await oms._on_private_ws_reconnected()

        inner = diff_msgs[0]["diff"]
        assert inner["success"] is True
        assert "positions_opened" in inner
        assert "positions_closed" in inner
        assert "open_orders_added" in inner
        assert "open_orders_removed" in inner


# ---------------------------------------------------------------------------
# 4. Exchange-specific OMS resync failure propagation
# ---------------------------------------------------------------------------


class TestExchangeOmsResyncFailurePropagation:
    """Each exchange OMS must return success=False on exception; base handler
    must publish resync_failed accordingly."""

    def _oms_factory(self, exchange: str):
        """Return (oms, msgbus) for the given exchange OMS class."""
        factory_map = {
            "okx": (
                "nexustrader.exchange.okx.oms",
                "OkxOrderManagementSystem",
                ExchangeType.OKX,
            ),
            "binance": (
                "nexustrader.exchange.binance.oms",
                "BinanceOrderManagementSystem",
                ExchangeType.BINANCE,
            ),
            "bybit": (
                "nexustrader.exchange.bybit.oms",
                "BybitOrderManagementSystem",
                ExchangeType.BYBIT,
            ),
        }
        module_path, cls_name, exchange_id = factory_map[exchange]
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, cls_name)

        msgbus = _make_msgbus()

        with (
            patch.object(cls, "_init_account_balance"),
            patch.object(cls, "_init_position"),
            patch.object(cls, "_position_mode_check"),
        ):
            oms = cls.__new__(cls)

        oms._log = MagicMock()
        oms._exchange_id = exchange_id
        oms._account_type = MagicMock()
        oms._account_type.value = "TEST"
        oms._clock = _make_clock()
        oms._msgbus = msgbus
        oms._cache = MagicMock()
        return oms, msgbus

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exchange", ["okx", "binance", "bybit"])
    async def test_exchange_resync_failure_propagates_to_resync_failed(self, exchange):
        """When exchange _resync_after_reconnect returns success=False, the base
        _on_private_ws_reconnected must publish resync_failed."""
        oms, msgbus = self._oms_factory(exchange)

        events: list[str] = []
        msgbus.subscribe(
            topic="private_ws_status",
            handler=lambda m: events.append(m["event"]),
        )

        oms._resync_after_reconnect = AsyncMock(
            return_value={
                "success": False,
                "error": "simulated REST failure",
                "positions_opened": [],
                "positions_closed": [],
                "open_orders_added": [],
                "open_orders_removed": [],
            }
        )

        await oms._on_private_ws_reconnected()

        assert "resync_failed" in events, (
            f"[{exchange}] resync_failed must be published on failure"
        )
        assert "resynced" not in events, (
            f"[{exchange}] resynced must NOT be published on failure"
        )
