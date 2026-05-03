cache
===============

Cache is used to store trading data in memory and persistent storage. You can access ``Cache`` in ``Strategy`` class.

.. note::

    See the ``Cache`` :doc:`API Reference <../api/core/cache>` for a complete description of all available methods.



Data Accessing
------------------------------------------

Public Trading Data
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let's start with a simple example, you want to get the ``bookl1`` and print it every 1 second.

.. code-block:: python

    from nexustrader.strategy import Strategy

    class Demo(Strategy):
        def __init__(self):
            super().__init__()
            self.subscribe_bookl1(symbols=["BTCUSDT-PERP.OKX"])
            self.schedule(self.algo, trigger="interval", seconds=1)

        def algo(self):
            bookl1 = self.cache.bookl1("BTCUSDT-PERP.OKX") # return None or BookL1 object
            if bookl1:
                print(bookl1)

``self.cache.bookl1()`` returns ``None`` if the data is not available in cache. Thus, we introduce ``DataReady`` to check if the data is ready.

.. code-block:: python

    class Demo(Strategy):
        def __init__(self):
            super().__init__()
            self.subscribe_bookl1(symbols=["BTCUSDT-PERP.OKX"])
            self.data_ready = DataReady(symbols=["BTCUSDT-PERP.OKX"])
        
        def on_bookl1(self, bookl1: BookL1):
            self.data_ready.input(bookl1)

        def algo(self):
            if not self.data_ready.ready:
                self.log.info("Data not ready, skip")
                return
            bookl1 = self.cache.bookl1("BTCUSDT-PERP.OKX")
            print(bookl1)

Position Data
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``self.cache.get_position()`` returns the position of the symbol, or ``None`` if no position
exists.

.. code-block:: python

    position = self.cache.get_position("BTCUSDT-PERP.OKX")
    if position:
        print(position.signed_amount)

``Position.side`` uses position direction:
``PositionSide.LONG`` / ``PositionSide.SHORT`` / ``PositionSide.FLAT``. It is
not the same enum as order direction, which uses ``OrderSide.BUY`` /
``OrderSide.SELL``.

.. code-block:: python

    from nexustrader.constants import PositionSide

    position = self.cache.get_position("BTCUSDT-PERP.OKX")
    if position and position.side == PositionSide.LONG:
        print("long position")

For Bybit TradFi (MT5), cache keys are NexusTrader symbols, not raw MT5
symbols. For example, MT5 ``XAUUSD.s`` is cached as
``XAUUSD_s.BYBIT_TRADFI``:

.. code-block:: python

    # Correct
    position = self.cache.get_position("XAUUSD_s.BYBIT_TRADFI")

    # Wrong: raw MT5 symbol is not used as a cache key
    position = self.cache.get_position("XAUUSD.s")

Order Data
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- ``self.cache.get_order()`` returns the ``Order`` object, or ``None`` if not found.

.. code-block:: python

    order = self.cache.get_order(oid)
    if order and order.is_opened:
        # cancel the order
        ...

- ``self.cache.get_symbol_orders()`` returns the ``Set[str]`` of the orders of the symbol.
- ``self.cache.get_open_orders()`` returns the ``Set[str]`` of the open orders.

Inflight Orders
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Orders that have been submitted to the exchange but not yet acknowledged are tracked as
*inflight*. This is useful to avoid double-submitting or to wait before cancelling.

.. code-block:: python

    # Check current inflight orders for a symbol
    inflight = self.cache.get_inflight_orders("BTCUSDT-PERP.BINANCE")
    self.log.info(f"Inflight orders: {inflight}")

    # Wait (async) until all inflight orders are acknowledged or timeout
    await self.cache.wait_for_inflight_orders("BTCUSDT-PERP.BINANCE", timeout=5.0)


