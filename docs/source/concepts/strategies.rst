Strategies
============

The core of the nexustrader user experience lies in creating and managing trading strategies. A trading strategy is defined by subclassing the ``Strategy`` class and implementing the methods necessary for the user's trading logic.

.. note::

    See the ``Strategy`` :doc:`API Reference <../api/strategy>` for a complete description of all available methods.


Strategy Implementation
--------------------------

.. code-block:: python

    from nexustrader.strategy import Strategy

    class Demo(Strategy):
        def __init__(self):
            super().__init__() # <-- the super class must be called to initialize the strategy

Lifecycle Hooks
----------------

Two special hooks are called by the engine automatically:

.. code-block:: python

    class Demo(Strategy):
        def on_start(self):
            """Called once after the engine has connected to all exchanges.
            Use this to subscribe to market data and register indicators."""
            self.subscribe_bookl1(symbols=["BTCUSDT-PERP.OKX"])

        def on_stop(self):
            """Called when the engine is shutting down."""
            self.log.info("Strategy stopping")

.. important::

   Always perform subscriptions inside ``on_start`` (not ``__init__``), because connectors are
   not ready until the engine has started.

Handlers
-----------

Handlers are methods within the Strategy class which may perform actions based on different types
of events or on state changes. These methods are named with the prefix ``on_*``. You can choose to
implement any or all of them depending on your strategy.


Live Data Handlers
^^^^^^^^^^^^^^^^^^^^
These handlers receive data updates from the exchange.

.. code-block:: python

    from nexustrader.schema import BookL1, BookL2, Trade, Kline, FundingRate, MarkPrice, IndexPrice
    from nexustrader.constants import KlineInterval, BookLevel

    class Demo(Strategy):

        def on_start(self):
            self.subscribe_bookl1(symbols=["BTCUSDT-PERP.OKX"])
            self.subscribe_bookl2(symbols=["BTCUSDT-PERP.OKX"], level=BookLevel.L20)
            self.subscribe_trade(symbols=["BTCUSDT-PERP.OKX"])
            self.subscribe_kline(symbols=["BTCUSDT-PERP.OKX"], interval=KlineInterval.MINUTE_1)
            self.subscribe_funding_rate(symbols=["BTCUSDT-PERP.OKX"])
            self.subscribe_mark_price(symbols=["BTCUSDT-PERP.OKX"])
            self.subscribe_index_price(symbols=["BTCUSDT-PERP.OKX"])

        def on_bookl1(self, bookl1: BookL1):
            # bookl1.bid, bookl1.ask, bookl1.mid, bookl1.weighted_mid
            ...

        def on_bookl2(self, bookl2: BookL2):
            # bookl2.bids, bookl2.asks (list of [price, size])
            ...

        def on_trade(self, trade: Trade):
            # trade.price, trade.size, trade.side
            ...

        def on_kline(self, kline: Kline):
            # kline.open, kline.high, kline.low, kline.close, kline.volume
            # kline.confirm == True means the bar has closed
            ...

        def on_funding_rate(self, rate: FundingRate):
            # rate.rate, rate.next_funding_time
            ...

        def on_mark_price(self, price: MarkPrice):
            # price.price
            ...

        def on_index_price(self, price: IndexPrice):
            # price.price
            ...

Unsubscribing from Data
^^^^^^^^^^^^^^^^^^^^^^^^

You can unsubscribe at runtime:

.. code-block:: python

    self.unsubscribe_bookl1(symbols=["BTCUSDT-PERP.OKX"])
    self.unsubscribe_trade(symbols=["BTCUSDT-PERP.OKX"])
    self.unsubscribe_kline(symbols=["BTCUSDT-PERP.OKX"], interval=KlineInterval.MINUTE_1)
    self.unsubscribe_bookl2(symbols=["BTCUSDT-PERP.OKX"], level=BookLevel.L20)

Order Management Handlers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
These handlers receive order status updates from the exchange.

.. code-block:: python

    from nexustrader.schema import Order

    class Demo(Strategy):
        def on_pending_order(self, order: Order):
            """Order sent to exchange; awaiting confirmation."""
            ...

        def on_accepted_order(self, order: Order):
            """Exchange accepted the order (open on the book)."""
            ...

        def on_partially_filled_order(self, order: Order):
            """Order partially filled; ``order.filled`` shows how much."""
            ...

        def on_filled_order(self, order: Order):
            """Order completely filled."""
            ...

        def on_canceling_order(self, order: Order):
            """Cancel request sent; awaiting exchange confirmation."""
            ...

        def on_canceled_order(self, order: Order):
            """Order successfully cancelled."""
            ...

        def on_failed_order(self, order: Order):
            """Order creation failed."""
            ...

        def on_cancel_failed_order(self, order: Order):
            """Order cancellation failed."""
            ...

Private WebSocket Handlers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

These handlers are called when the private WebSocket connection changes state, when a
post-reconnect reconciliation diff is available, or when a WS order/cancel request
produces a structured ACK outcome.

.. code-block:: python

    class Demo(Strategy):
        def on_private_ws_status(self, status: dict):
            """Called on private WS connect / disconnect / reconnect / resynced events.

            status keys:
              - exchange (str): e.g. "okx", "binance", "bybit"
              - account_type (str): e.g. "live", "demo"
              - event (str): "connected" | "disconnected" | "reconnected" | "resynced"
              - timestamp (int): milliseconds since epoch
            """
            self.log.info(f"Private WS {status['event']} on {status['exchange']}")

        def on_private_ws_resync_diff(self, payload: dict):
            """Called after a successful post-reconnect reconciliation.

            payload keys:
              - exchange, account_type, timestamp (same as above)
              - diff (dict):
                  - positions_opened (list[str]): symbols with newly detected positions
                  - positions_closed (list[str]): symbols whose positions disappeared
                  - open_orders_added (list[str]): OIDs newly found open
                  - open_orders_removed (list[str]): OIDs no longer open
            """
            diff = payload.get("diff", {})
            if diff.get("open_orders_removed"):
                self.log.warning(f"Orders closed during disconnect: {diff['open_orders_removed']}")

        def on_ws_order_request_result(self, result: dict):
            """Called when a background WS order/cancel task produces a structured ACK result.

            Fired for every non-success outcome of a ``create_order_ws()`` or
            ``cancel_order_ws()`` call — the background task catches the exception and
            publishes it here so you do not need to wrap individual calls in try/except.

            result keys:
              - oid         (str): client order ID
              - symbol      (str): e.g. "BTCUSDT-PERP.OKX"
              - exchange    (str): exchange name
              - result_type (WsOrderResultType):
                    REQUEST_NOT_SENT     — socket was down; request never left
                    ACK_REJECTED         — exchange explicitly rejected the request
                    ACK_TIMEOUT          — no ACK received; REST also could not confirm
                    ACK_TIMEOUT_CONFIRMED — no ACK received, but REST confirmed the order
              - reason      (str): human-readable description
              - timestamp   (int): milliseconds since epoch
            """
            from nexustrader.constants import WsOrderResultType
            rt = result["result_type"]
            oid = result["oid"]
            symbol = result["symbol"]
            if rt == WsOrderResultType.ACK_TIMEOUT_CONFIRMED:
                # order actually went through — no action needed
                self.log.info(f"[{symbol}] WS ACK timeout but REST confirmed oid={oid}")
            elif rt == WsOrderResultType.ACK_REJECTED:
                self.log.warning(f"[{symbol}] WS order rejected oid={oid}: {result['reason']}")
            elif rt == WsOrderResultType.ACK_TIMEOUT:
                # order state unknown — consider REST query or retry logic
                self.log.error(f"[{symbol}] WS ACK timeout, state unknown oid={oid}")
            elif rt == WsOrderResultType.REQUEST_NOT_SENT:
                # ws_fallback=False was used and the socket was down
                self.log.error(f"[{symbol}] WS request not sent oid={oid}: {result['reason']}")

Order Query Methods
^^^^^^^^^^^^^^^^^^^^

You can query live order state from within any strategy method:

.. code-block:: python

    class Demo(Strategy):
        def on_bookl1(self, bookl1: BookL1):
            # Fetch a specific order by OID (checks cache first, then REST)
            order = self.fetch_order(symbol="BTCUSDT-PERP.OKX", oid="my-order-id")

            # Bypass the local cache and query the exchange REST API directly.
            # Use this when authoritative exchange state is required, e.g. after
            # an ACK timeout or after reconnecting.
            order = self.fetch_order(
                symbol="BTCUSDT-PERP.OKX",
                oid="my-order-id",
                force_refresh=True,
            )

            # Fetch all currently open orders for a symbol
            open_orders = self.fetch_open_orders(symbol="BTCUSDT-PERP.OKX")

            # Fetch recent filled/partially-filled orders from cache
            recent = self.fetch_recent_trades(symbol="BTCUSDT-PERP.OKX", limit=10)

Reconnect Reconciliation Grace Period
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

After a private WebSocket reconnects, NexusTrader automatically re-fetches balances,
positions, and open orders to detect any changes that occurred during the outage.  To
avoid false order closures from delayed exchange snapshots, a configurable grace window
(default **700 ms**) is applied before confirming that a missing order is truly closed.

You can adjust this window per exchange in ``on_start``:

.. code-block:: python

    from nexustrader.constants import ExchangeType

    class Demo(Strategy):
        def on_start(self):
            # Wait 1.5 s before confirming missing orders as closed
            self.set_reconnect_reconcile_grace_ms(ExchangeType.OKX, grace_ms=1500)

Waiting for Data Readiness
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use :class:`~nexustrader.core.entity.DataReady` to guard your trading logic until all required
data feeds have received at least one update:

.. code-block:: python

    from nexustrader.core.entity import DataReady

    class Demo(Strategy):
        def __init__(self):
            super().__init__()
            self._ready = DataReady(keys=["BTCUSDT-PERP.OKX", "ETHUSDT-PERP.OKX"])

        def on_bookl1(self, bookl1: BookL1):
            self._ready.mark(bookl1.symbol)
            if not self._ready:
                return
            # safe to trade now
            ...
            


Multi-Mode Support
^^^^^^^^^^^^^^^^^^^^

nexustrader supports multiple modes of operation to cater to different trading strategies and requirements. Each mode allows for flexibility in how trading logic is executed based on market conditions or specific triggers.

Event-Driven Mode
""""""""""""""""""

In this mode, trading logic is executed in response to real-time market events. The methods ``on_bookl1``, ``on_trade``, and ``on_kline`` are triggered whenever relevant data is updated, allowing for immediate reaction to market changes.

.. code-block:: python

    class Demo(Strategy):
        def __init__(self):
            super().__init__()
            self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BINANCE"])

        def on_bookl1(self, bookl1: BookL1):
            # implement the trading logic Here
            pass

Timer Mode
""""""""""""""

This mode allows you to schedule trading logic to run at specific intervals. You can use the ``schedule`` method to define when your trading algorithm should execute, making it suitable for strategies that require periodic checks or actions.

.. code-block:: python

    class Demo2(Strategy):
        def __init__(self):
            super().__init__()
            self.schedule(self.algo, trigger="interval", seconds=1)

        def algo(self):
            # run every 1 second
            # implement the trading logic Here
            pass

Custom Signal Mode
""""""""""""""""""

In this mode, trading logic is executed based on custom signals. You can define your own signals and use the ``on_custom_signal`` method to trigger trading actions when these signals are received. This is particularly useful for integrating with external systems or custom event sources.

.. code-block:: python

    class Demo3(Strategy):
        def __init__(self):
            super().__init__()
            self.signal = True

        def on_custom_signal(self, signal: object):
            # implement the trading logic Here,
            # signal can be any object, it is up to you to define the signal
            pass
