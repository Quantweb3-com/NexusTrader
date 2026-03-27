Reliable WS Order Flow
=======================

This guide shows how to combine NexusTrader's WS reliability features into a
production-grade strategy that handles duplicate signals, connection drops, and
delayed exchange ACKs without manual bookkeeping.

The four pillars covered here are:

1. **Idempotent order creation** — ``idempotency_key`` prevents duplicate submissions
2. **WS fallback** — automatic REST retry when the WS socket is down
3. **Structured ACK error handling** — ``on_ws_order_request_result()`` callback
4. **Reconnect reconciliation** — ``on_private_ws_resync_diff()`` and ``on_private_ws_status()``

.. contents:: Sections
   :local:
   :depth: 1

----

Idempotent Order Creation
--------------------------

Problem
^^^^^^^^

A fast signal loop may call ``create_order_ws()`` several times before the
first exchange ACK arrives (e.g. every tick while price is in range). Without
a deduplication mechanism this floods the exchange with identical orders.

Solution
^^^^^^^^^

Pass an ``idempotency_key`` that is stable for the *logical* order. The cache
maps every key to a single canonical OID; repeated calls with the same key are
silently no-ops.

.. code-block:: python

    from decimal import Decimal
    from nexustrader.strategy import Strategy
    from nexustrader.constants import OrderSide, OrderType
    from nexustrader.schema import BookL1

    SYMBOL = "BTCUSDT-PERP.OKX"

    class IdempotentEntry(Strategy):
        def on_bookl1(self, bookl1: BookL1):
            if bookl1.ask < 90_000:
                # No matter how many ticks fire, only one order is submitted
                self.create_order_ws(
                    symbol=SYMBOL,
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    amount=Decimal("0.001"),
                    price=self.price_to_precision(SYMBOL, bookl1.ask),
                    idempotency_key="entry:btc:long",   # stable key for this signal
                )

You can also supply a deterministic ``client_oid`` (shown to the exchange as
the client order ID) alongside the idempotency key:

.. code-block:: python

    self.create_order_ws(
        symbol=SYMBOL,
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        amount=Decimal("0.001"),
        price=Decimal("89500"),
        client_oid="entry_btc_001",       # stable exchange-visible ID
        idempotency_key="entry:btc:long", # deduplication key
    )

.. tip::

   ``idempotency_key`` and ``client_oid`` are independent. You can use one or
   both. ``idempotency_key`` controls *local* deduplication; ``client_oid``
   controls the ID sent to the exchange.

----

WS Fallback on Connection Failure
-----------------------------------

Both ``create_order_ws()`` and ``cancel_order_ws()`` accept a ``ws_fallback``
keyword argument (default ``True``):

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - ``ws_fallback``
     - Behaviour when the WS socket is unavailable
   * - ``True`` *(default)*
     - Transparently retries the same request via REST. The order lifecycle
       proceeds normally — no extra handler code needed.
   * - ``False``
     - Immediately marks the order ``FAILED`` / ``CANCEL_FAILED`` with
       ``reason="WS_REQUEST_NOT_SENT: …"`` and fires ``on_failed_order`` /
       ``on_cancel_failed_order``. Use this for strict latency-critical
       strategies that must not silently fall back to a slower path.

.. code-block:: python

    # Default: if WS is down, retry via REST automatically
    self.create_order_ws(symbol=SYMBOL, ..., ws_fallback=True)

    # Strict: fail fast if WS is unavailable, never fall back
    self.create_order_ws(symbol=SYMBOL, ..., ws_fallback=False)

    # Cancel with explicit fail-fast
    self.cancel_order_ws(symbol=SYMBOL, oid=oid, ws_fallback=False)

----

Handling WS ACK Errors
------------------------

Even when the WS socket is healthy, the exchange may be slow to acknowledge
or may reject the request outright. NexusTrader categorises every non-success
outcome with ``WsOrderResultType`` and delivers it to the
``on_ws_order_request_result()`` callback.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - ``result_type``
     - When it fires
   * - ``REQUEST_NOT_SENT``
     - Socket was down and ``ws_fallback=False``.
   * - ``ACK_REJECTED``
     - Exchange explicitly rejected the request (e.g. bad price, insufficient margin).
   * - ``ACK_TIMEOUT``
     - No ACK within 5 s *and* REST could not confirm the order — state truly unknown.
   * - ``ACK_TIMEOUT_CONFIRMED``
     - No ACK within 5 s but REST found the order — treat as success.

.. code-block:: python

    from nexustrader.constants import WsOrderResultType

    class RobustStrategy(Strategy):

        def on_ws_order_request_result(self, result: dict):
            rt     = result["result_type"]
            oid    = result["oid"]
            symbol = result["symbol"]
            reason = result["reason"]

            if rt == WsOrderResultType.ACK_TIMEOUT_CONFIRMED:
                # Order exists on exchange — nothing to do
                self.log.info(f"[{symbol}] {oid} confirmed via REST after ACK timeout")

            elif rt == WsOrderResultType.ACK_REJECTED:
                # Exchange said no — log and optionally resubmit with corrected params
                self.log.warning(f"[{symbol}] order rejected: {reason}")

            elif rt == WsOrderResultType.ACK_TIMEOUT:
                # Unknown state — query REST directly to decide
                order = self.fetch_order(symbol, oid, force_refresh=True)
                if order is None:
                    self.log.error(
                        f"[{symbol}] {oid} not found after ACK timeout — may need resubmit"
                    )
                else:
                    self.log.info(f"[{symbol}] {oid} found on exchange: {order.status}")

            elif rt == WsOrderResultType.REQUEST_NOT_SENT:
                # ws_fallback=False was used and the socket was down
                self.log.error(f"[{symbol}] WS was disconnected — {oid} was never sent")

----

Reconnect Reconciliation
--------------------------

When the private WebSocket drops and reconnects, NexusTrader automatically
re-fetches balances, positions, and open orders, then emits a diff of what
changed during the outage.

.. code-block:: python

    class RobustStrategy(Strategy):

        def on_private_ws_status(self, status: dict):
            """Fires on every connection state change."""
            event    = status["event"]   # "connected"|"disconnected"|"reconnected"|"resynced"
            exchange = status["exchange"]
            self.log.info(f"[{exchange}] WS {event}")

            if event == "disconnected":
                # Optionally suspend new order submissions until reconnected
                self._ws_ready = False
            elif event == "resynced":
                self._ws_ready = True

        def on_private_ws_resync_diff(self, payload: dict):
            """Fires once after the post-reconnect snapshot is reconciled."""
            diff = payload.get("diff", {})

            closed = diff.get("open_orders_removed", [])
            if closed:
                self.log.warning(
                    f"Orders closed during disconnect: {closed}"
                )
                # Optionally resubmit market orders for filled/expired positions

            opened = diff.get("open_orders_added", [])
            if opened:
                self.log.info(f"New open orders detected after reconnect: {opened}")

            positions_closed = diff.get("positions_closed", [])
            if positions_closed:
                self.log.warning(f"Positions closed during outage: {positions_closed}")

**Adjusting the reconciliation grace window**

To avoid false order closures from delayed exchange snapshots, a grace period
(default **700 ms**) is applied before an order missing from the snapshot is
confirmed as closed.  Increase it on high-latency connections:

.. code-block:: python

    from nexustrader.constants import ExchangeType

    class RobustStrategy(Strategy):
        def on_start(self):
            self.set_reconnect_reconcile_grace_ms(ExchangeType.OKX, grace_ms=1500)
            self.set_reconnect_reconcile_grace_ms(ExchangeType.BINANCE, grace_ms=1000)

----

Full Example
-------------

The snippet below combines all four features into a single strategy skeleton.

.. code-block:: python

    from decimal import Decimal
    from nexustrader.strategy import Strategy
    from nexustrader.constants import OrderSide, OrderType, ExchangeType, WsOrderResultType
    from nexustrader.schema import BookL1, Order

    SYMBOL = "BTCUSDT-PERP.OKX"

    class RobustEntry(Strategy):

        def __init__(self):
            super().__init__()
            self._ws_ready = True

        def on_start(self):
            self.subscribe_bookl1(symbols=[SYMBOL])
            self.set_reconnect_reconcile_grace_ms(ExchangeType.OKX, grace_ms=1200)

        # ── 1. Idempotent WS order submission ──────────────────────────────
        def on_bookl1(self, bookl1: BookL1):
            if not self._ws_ready:
                return
            if bookl1.ask < 90_000:
                self.create_order_ws(
                    symbol=SYMBOL,
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    amount=Decimal("0.001"),
                    price=self.price_to_precision(SYMBOL, bookl1.ask),
                    idempotency_key="entry:btc:long",
                    ws_fallback=True,   # REST retry if WS drops mid-flight
                )

        # ── 2. Structured ACK error handling ───────────────────────────────
        def on_ws_order_request_result(self, result: dict):
            rt     = result["result_type"]
            oid    = result["oid"]
            reason = result["reason"]

            if rt == WsOrderResultType.ACK_TIMEOUT_CONFIRMED:
                self.log.info(f"Order {oid} confirmed via REST after ACK timeout")
            elif rt == WsOrderResultType.ACK_REJECTED:
                self.log.warning(f"Order {oid} rejected: {reason}")
            elif rt == WsOrderResultType.ACK_TIMEOUT:
                order = self.fetch_order(SYMBOL, oid, force_refresh=True)
                if order is None:
                    self.log.error(f"Order {oid} missing after timeout — resubmit?")

        # ── 3. Reconnect awareness ─────────────────────────────────────────
        def on_private_ws_status(self, status: dict):
            if status["event"] == "disconnected":
                self._ws_ready = False
            elif status["event"] in ("reconnected", "resynced"):
                self._ws_ready = True

        def on_private_ws_resync_diff(self, payload: dict):
            diff = payload.get("diff", {})
            removed = diff.get("open_orders_removed", [])
            if removed:
                self.log.warning(f"Orders gone during outage: {removed}")

        # ── 4. Standard order lifecycle callbacks ──────────────────────────
        def on_filled_order(self, order: Order):
            self.log.info(f"Filled {order.oid} @ {order.avg_price}")

        def on_failed_order(self, order: Order):
            self.log.error(f"Failed {order.oid}: {order.reason}")
