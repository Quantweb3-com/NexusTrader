Orders
========

This guide offers detailed information about the various order types available on the platform, as well as the execution instructions supported for each.

Orders are a fundamental component of any algorithmic trading strategy. nexustrader has integrated a wide range of order types and execution instructions, from standard to advanced, to maximize the potential functionality of trading venues. This allows traders to set specific conditions and instructions for order execution and management, enabling the creation of virtually any type of trading strategy.


Overview
-----------

There are two categories of orders in NexusTrader:

- ``Basic Order``
    - ``Limit Order``
    - ``Market Order``
    - ``Post-Only Order`` (``OrderType.POST_ONLY``)
    - ``Take-Profit / Stop-Loss Order``
    - ``Batch Order``
    - ``Modify Order``
- ``Algorithmic Order``
    - ``TWAP``

Basic Orders
~~~~~~~~~~~~~

Create a basic order using :meth:`~nexustrader.strategy.Strategy.create_order`:

.. code-block:: python

    from nexustrader.strategy import Strategy
    from nexustrader.constants import OrderSide, OrderType
    from decimal import Decimal

    class Demo(Strategy):
        def on_bookl1(self, bookl1):
            self.create_order(
                symbol="BTCUSDT-PERP.BYBIT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                price=self.price_to_precision("BTCUSDT-PERP.BYBIT", bookl1.bid * 0.999),
                amount=Decimal("0.001"),
            )

Key parameters:

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Parameter
     - Type
     - Description
   * - ``symbol``
     - ``str``
     - Instrument ID (e.g. ``"BTCUSDT-PERP.BYBIT"``)
   * - ``side``
     - ``OrderSide``
     - ``BUY`` or ``SELL``
   * - ``type``
     - ``OrderType``
     - ``LIMIT``, ``MARKET``, ``POST_ONLY``, etc.
   * - ``amount``
     - ``Decimal``
     - Order quantity (base currency)
   * - ``price``
     - ``Decimal`` (optional)
     - Limit price; required for ``LIMIT`` and ``POST_ONLY``
   * - ``reduce_only``
     - ``bool`` (optional)
     - Close existing position only (futures)
   * - ``account_type``
     - ``AccountType`` (optional)
     - Override the default account type

Modify Orders
~~~~~~~~~~~~~~

Change the price or quantity of an open order using
:meth:`~nexustrader.strategy.Strategy.modify_order`:

.. code-block:: python

    self.modify_order(
        symbol="BTCUSDT-PERP.BYBIT",
        oid=open_order_oid,
        side=OrderSide.BUY,
        price=new_price,
        amount=new_amount,
    )

Batch Orders
~~~~~~~~~~~~~

Submit multiple orders in a single API call using
:meth:`~nexustrader.strategy.Strategy.create_batch_orders`:

.. code-block:: python

    from nexustrader.schema import BatchOrder

    self.create_batch_orders(
        orders=[
            BatchOrder(symbol="BTCUSDT-PERP.BYBIT", side=OrderSide.BUY,
                       type=OrderType.LIMIT, amount=Decimal("0.01"), price=px1),
            BatchOrder(symbol="BTCUSDT-PERP.BYBIT", side=OrderSide.BUY,
                       type=OrderType.LIMIT, amount=Decimal("0.01"), price=px2),
        ]
    )

Take-Profit & Stop-Loss Orders
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Attach TP and SL legs to a parent order in one call using
:meth:`~nexustrader.strategy.Strategy.create_tp_sl_order`:

.. code-block:: python

    self.create_tp_sl_order(
        symbol="BTCUSDT-PERP.BYBIT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        amount=Decimal("0.001"),
        tp_order_type=OrderType.MARKET,
        tp_trigger_price=self.price_to_precision(symbol, bookl1.ask * 1.001),
        sl_order_type=OrderType.MARKET,
        sl_trigger_price=self.price_to_precision(symbol, bookl1.bid * 0.999),
    )

WebSocket Order Submission
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use :meth:`~nexustrader.strategy.Strategy.create_order_ws` and
:meth:`~nexustrader.strategy.Strategy.cancel_order_ws` to submit and cancel orders via the
low-latency WebSocket API (supported on OKX, Binance, and Bybit).  These methods are lower
latency than the REST equivalents because they avoid an extra HTTP round-trip.

.. code-block:: python

    class Demo(Strategy):
        def on_bookl1(self, bookl1: BookL1):
            self.create_order_ws(
                symbol="BTCUSDT-PERP.OKX",
                side=OrderSide.BUY,
                type=OrderType.POST_ONLY,
                amount=Decimal("0.001"),
                price=self.price_to_precision("BTCUSDT-PERP.OKX", bookl1.bid * 0.999),
            )

**ws_fallback parameter**

Both methods accept a ``ws_fallback`` keyword argument (default ``True``).  When the
WebSocket connection is unavailable and a send fails, the behaviour depends on this flag:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - ``ws_fallback``
     - Behaviour on connection failure
   * - ``True`` *(default)*
     - Transparently retries the same request via the REST API.
   * - ``False``
     - Immediately marks the order as ``FAILED`` (create) or ``CANCEL_FAILED`` (cancel)
       with ``reason="WS_REQUEST_NOT_SENT: …"``, and fires the corresponding handler.

.. code-block:: python

    # Explicit REST fallback (default behaviour)
    self.create_order_ws(..., ws_fallback=True)

    # Fail fast – no REST retry
    self.create_order_ws(..., ws_fallback=False)

    # Same options on cancel
    self.cancel_order_ws(symbol="BTCUSDT-PERP.OKX", oid=oid, ws_fallback=False)

TWAP Algorithmic Orders
~~~~~~~~~~~~~~~~~~~~~~~

Use :meth:`~nexustrader.strategy.Strategy.create_twap` to split a large order into time-sliced
child orders:

.. code-block:: python

    self.create_twap(
        symbol=symbol,
        side=OrderSide.BUY if diff > 0 else OrderSide.SELL,
        amount=abs(diff),
        duration=65,   # total seconds
        wait=5,        # seconds between child orders
        account_type=BybitAccountType.UNIFIED_TESTNET,
    )

Order Status
---------------
.. image:: ../_static/order.png
    :alt: Order Status Flow
    :align: center

The Order Status is defined in ``OrderStatus`` class. We define 4 groups of statuses:


- ``LOCAL``: The order is created by the user and not sent to the exchange yet.
    - ``INITIALIZED``: when order is created by ``create_order`` method or ``cancel_order`` method
    - ``FAILED``: when order is failed to be created
    - ``CANCEL_FAILED``: when order is failed to be canceled
- ``IN-FLOW``: The order is sending to the exchange but the websocket response is not received yet.
    - ``PENDING``: when order is pending on the exchange
    - ``CANCElING``: when order is pending to be canceled
- ``OPEN``: The order is open on the exchange which means the websocket response is received.
    - ``ACCEPTED``: when order is accepted by the exchange
    - ``PARTIALLY_FILLED``: when order is partially filled
- ``CLOSED``: The order is closed on the exchange which means the order is ``FILLED``, ``CANCELLED`` or ``EXPIRED``.
    - ``FILLED``: when order is filled
    - ``CANCELLED``: when order is cancelled (cancelled by the user).
    - ``EXPIRED``: when order is expired (canceled by the exchange).

When an order transitions to ``FAILED`` or ``CANCEL_FAILED``, the ``reason`` field contains
a human-readable description of the failure (e.g. an exchange error message). You can inspect
it in the order-status handlers:

.. code-block:: python

    def on_failed_order(self, order: Order):
        self.log.error(f"Order {order.oid} failed: {order.reason}")

Inflight Orders & Cancel Intent
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Between the moment an order is submitted and the first acknowledgement from the exchange, the
order is considered *inflight*. During this window a rapid cancel request could race with the
incoming status update. NexusTrader addresses this with two mechanisms:

1. **Inflight tracking** -- every order submission registers the OID as inflight.  Once the
   exchange responds (any status update), the OID is removed.  Use
   ``cache.get_inflight_orders(symbol)`` to query the current set, or
   ``await cache.wait_for_inflight_orders(symbol)`` to block until all resolve.
2. **Cancel intent** -- calling ``cancel_order`` or ``cancel_all_orders`` immediately marks the
   OIDs with a cancel intent *synchronously* at the Strategy layer, before the cancel request
   is queued.  This prevents the OMS from interpreting a late ``ACCEPTED`` update as a newly
   active order when a cancel is already in progress.


Algorithmic Order
------------------

.. image:: ../_static/algo.png
    :alt: Algorithmic Order
    :align: center
    :width: 70%

The ``AlgoOrder`` is a special type of order that is created by the ``create_twap`` method in ``Strategy`` class. It is used to create a ``TWAP`` order. The status of the ``AlgoOrder`` is defined in ``AlgoOrderStatus`` class. The ``TWAP`` order is used to execute a large order in a series of smaller orders over a specified period of time. There are 5 statuses:

- ``RUNNING``: when the ``TWAP`` order is running
- ``CANCELING``: when the ``TWAP`` order is canceling
- ``CANCELLED``: when the ``TWAP`` order is cancelled
- ``FINISHED``: when the ``TWAP`` order is finished
- ``FAILED``: when the ``TWAP`` order is failed to be created, or one of the orders in the ``TWAP`` order is failed to be created.

Order Linkage
--------------

Order Creation
~~~~~~~~~~~~~~~

nexustrader uses an internal order and exchange order linkage mechanism. When an internal order is created, i.e., the status is ``INITIALIZED``, an ``OID`` (Order ID) is automatically generated internally. When it is submitted to the exchange, if successful, the exchange returns an ``EID`` (Exchange Order ID) which is stored on the order. If it fails, the order status is set to ``FAILED``.

.. image:: ../_static/link.png
    :alt: Order Linkage
    :align: center
    :width: 70%

Order Cancellation
~~~~~~~~~~~~~~~~~~

When an order is canceled, the user specifies the ``OID`` of the order to be canceled by calling the ``cancel_order`` method in the ``Strategy`` class. The ``OID`` is used to look up the ``EID`` and submit the cancellation request to the exchange.

.. image:: ../_static/link_cancel.png
    :alt: Order Cancellation
    :align: center
    :width: 70%
