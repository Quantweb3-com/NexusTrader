Bybit TradFi (MT5)
==================

Bybit TradFi provides access to traditional financial markets — Forex, Gold,
Indices, and Stocks — through a MetaTrader 5 terminal. Unlike other NexusTrader
connectors, it does **not** use WebSockets; all market data is obtained by
polling the MT5 Python API from a dedicated single-threaded executor.

.. note::

   The MetaTrader5 Python package is **Windows only**. This connector cannot
   be used on Linux or macOS.

Prerequisites
-------------

1. A Bybit TradFi account (Demo or Live). Register at
   `bybit.com/en/trade/tradfi/ <https://www.bybit.com/en/trade/tradfi/>`_.
2. MetaTrader5 terminal installed on Windows and logged in to your broker.
3. The ``MetaTrader5`` Python package:

   .. code-block:: bash

      uv add MetaTrader5          # recommended
      # or
      pip install MetaTrader5

Account Types
-------------

.. code-block:: python

   from nexustrader.exchange.bybit_tradfi import BybitTradeFiAccountType

   account_type = BybitTradeFiAccountType.DEMO   # demo / paper account
   account_type = BybitTradeFiAccountType.LIVE    # live account

Symbol Format
-------------

MT5 symbol names are mapped to the NexusTrader ``symbol.EXCHANGE`` format.
Leading ``#`` / ``.`` broker prefixes are stripped and any internal dots are
replaced with underscores so they do not conflict with the ``.BYBIT_TRADFI``
exchange suffix:

.. list-table::
   :header-rows: 1
   :widths: 25 40

   * - MT5 Symbol
     - NexusTrader Symbol
   * - ``EURUSD``
     - ``EURUSD.BYBIT_TRADFI``
   * - ``XAUUSD.s``
     - ``XAUUSD_s.BYBIT_TRADFI``
   * - ``TSLA.s``
     - ``TSLA_s.BYBIT_TRADFI``
   * - ``US500``
     - ``US500.BYBIT_TRADFI``
   * - ``#AAPL``
     - ``AAPL.BYBIT_TRADFI``

Credentials
-----------

Add your MT5 account details to ``.secrets.toml`` in the project root:

.. code-block:: toml

   [BYBIT_TRADFI.DEMO]
   API_KEY    = "12345678"           # MT5 account login number
   SECRET     = "your_password"     # MT5 account password
   PASSPHRASE = "BybitBroker-Demo"  # MT5 broker server name

Then load them in your strategy:

.. code-block:: python

   from nexustrader.constants import settings

   MT5_LOGIN    = settings.BYBIT_TRADFI.DEMO.API_KEY
   MT5_PASSWORD = settings.BYBIT_TRADFI.DEMO.SECRET
   MT5_SERVER   = settings.BYBIT_TRADFI.DEMO.PASSPHRASE

Configuration
-------------

.. code-block:: python

   from nexustrader.config import (
       BasicConfig, Config, LogConfig,
       PrivateConnectorConfig, PublicConnectorConfig,
   )
   from nexustrader.constants import ExchangeType, settings
   from nexustrader.engine import Engine
   from nexustrader.exchange.bybit_tradfi import BybitTradeFiAccountType
   from nexustrader.strategy import Strategy

   MT5_LOGIN    = settings.BYBIT_TRADFI.DEMO.API_KEY
   MT5_PASSWORD = settings.BYBIT_TRADFI.DEMO.SECRET
   MT5_SERVER   = settings.BYBIT_TRADFI.DEMO.PASSPHRASE

   class MyStrategy(Strategy):
       ...

   config = Config(
       strategy_id="tradfi_strategy",
       user_id="user_test",
       strategy=MyStrategy(),
       log_config=LogConfig(level_stdout="INFO"),
       basic_config={
           ExchangeType.BYBIT_TRADFI: BasicConfig(
               api_key=MT5_LOGIN,
               secret=MT5_PASSWORD,
               passphrase=MT5_SERVER,
               testnet=True,        # True = DEMO account
           )
       },
       public_conn_config={
           ExchangeType.BYBIT_TRADFI: [
               PublicConnectorConfig(account_type=BybitTradeFiAccountType.DEMO)
           ]
       },
       private_conn_config={
           ExchangeType.BYBIT_TRADFI: [
               PrivateConnectorConfig(account_type=BybitTradeFiAccountType.DEMO)
           ]
       },
   )

   engine = Engine(config)

   if __name__ == "__main__":
       try:
           engine.start()
       finally:
           engine.dispose()

Tick Poll Interval
------------------

Because the MT5 connector uses polling rather than a WebSocket push feed, you
can tune the tick polling interval via ``PublicConnectorConfig.tick_poll_interval``
(in seconds).  The default is **10 ms** (``0.01``).

.. code-block:: python

   # Default: 10 ms polling
   PublicConnectorConfig(account_type=BybitTradeFiAccountType.DEMO)

   # Custom: 20 ms polling
   PublicConnectorConfig(account_type=BybitTradeFiAccountType.DEMO, tick_poll_interval=0.02)

   # Aggressive: 5 ms polling (higher CPU load)
   PublicConnectorConfig(account_type=BybitTradeFiAccountType.DEMO, tick_poll_interval=0.005)

.. note::

   Each ``symbol_info_tick()`` call to MT5 takes roughly 15–60 µs over the
   local named-pipe IPC.  A 10 ms interval is well within the practical limit
   and gives an average tick-detection latency of ~5 ms.  Going below 5 ms
   yields diminishing returns because retail broker tick feeds typically arrive
   at 2–10 ticks/second under normal market conditions.

Market Data
-----------

Historical klines
~~~~~~~~~~~~~~~~~

Call ``request_klines()`` inside ``on_start()`` to load historical bars before
subscribing to live data:

.. code-block:: python

   from nexustrader.constants import KlineInterval
   from nexustrader.exchange.bybit_tradfi import BybitTradeFiAccountType

   def on_start(self):
       klines = self.request_klines(
           symbol="EURUSD.BYBIT_TRADFI",
           interval=KlineInterval.MINUTE_1,
           limit=100,
           account_type=BybitTradeFiAccountType.DEMO,
       )
       self.log.info(f"Loaded {len(klines)} bars")
       self.log.info(f"\n{klines.df.tail(5).to_string()}")

Live subscriptions
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from nexustrader.schema import BookL1, Kline, Trade

   def on_start(self):
       self.subscribe_bookl1(symbols="EURUSD.BYBIT_TRADFI", ready=False)
       self.subscribe_trade(symbols="EURUSD.BYBIT_TRADFI", ready=False)
       self.subscribe_kline(
           symbols="EURUSD.BYBIT_TRADFI",
           interval=KlineInterval.MINUTE_1,
           ready=False,
       )

   def on_bookl1(self, bookl1: BookL1):
       self.log.info(f"bid={bookl1.bid}  ask={bookl1.ask}  spread={bookl1.spread}")

   def on_trade(self, trade: Trade):
       self.log.info(f"price={trade.price}  side={trade.side.value}")

   def on_kline(self, kline: Kline):
       if kline.confirm:
           self.log.info(f"Closed  O={kline.open} H={kline.high} L={kline.low} C={kline.close}")

.. note::

   Kline events are emitted on bar open, when the close price changes within
   the current bar, and once on bar close (``kline.confirm = True``). They are
   **not** emitted on every poll tick.

Trading
-------

Order placement
~~~~~~~~~~~~~~~

Use ``trigger="date"`` with ``run_date`` for one-shot scheduled steps.
``trigger="interval"`` fires repeatedly and will place multiple orders:

.. code-block:: python

   from datetime import datetime, timedelta
   from decimal import Decimal
   from nexustrader.constants import OrderSide, OrderType

   def on_start(self):
       self.subscribe_bookl1(symbols="XAUUSD_s.BYBIT_TRADFI", ready=False)
       now = datetime.now()
       self.schedule(self._place_limit,  trigger="date", run_date=now + timedelta(seconds=5))
       self.schedule(self._cancel_limit, trigger="date", run_date=now + timedelta(seconds=15))
       self.schedule(self._place_market, trigger="date", run_date=now + timedelta(seconds=20))

   def _place_limit(self):
       book = self.cache.bookl1("XAUUSD_s.BYBIT_TRADFI")
       price = self.price_to_precision("XAUUSD_s.BYBIT_TRADFI", book.bid * 0.98)
       self._oid = self.create_order(
           symbol="XAUUSD_s.BYBIT_TRADFI",
           side=OrderSide.BUY,
           type=OrderType.LIMIT,
           amount=Decimal("0.01"),
           price=price,
       )

   def _cancel_limit(self):
       open_orders = self.cache.get_open_orders("XAUUSD_s.BYBIT_TRADFI")
       if self._oid and self._oid in open_orders:
           self.cancel_order(symbol="XAUUSD_s.BYBIT_TRADFI", oid=self._oid)

   def _place_market(self):
       self.create_order(
           symbol="XAUUSD_s.BYBIT_TRADFI",
           side=OrderSide.BUY,
           type=OrderType.MARKET,
           amount=Decimal("0.01"),
       )

Fresh-price limit orders (``price_type``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When placing a limit order on MT5, the price your strategy computed from the
last ``on_bookl1`` event may be slightly stale by the time the order reaches
the broker.  Pass the ``price_type`` keyword to ``create_order`` or
``create_order_ws`` to have the OMS call ``symbol_info_tick()`` **at submission
time** and use the freshest available quote:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - ``price_type``
     - Price used for the limit order
   * - *(not set)*
     - The ``price`` value you passed (default behaviour)
   * - ``"bid"``
     - Latest MT5 best bid, re-fetched at submission time
   * - ``"ask"``
     - Latest MT5 best ask, re-fetched at submission time
   * - ``"opponent"``
     - Best ask for a buy order, best bid for a sell order (taker-side price)

.. code-block:: python

   # Join the bid — price re-fetched from MT5 when the order is sent
   self.create_order(
       symbol="EURUSD.BYBIT_TRADFI",
       side=OrderSide.BUY,
       type=OrderType.LIMIT,
       amount=Decimal("0.1"),
       price_type="bid",
   )

   # Cross the spread (opponent price) — most aggressive limit
   self.create_order(
       symbol="EURUSD.BYBIT_TRADFI",
       side=OrderSide.BUY,
       type=OrderType.LIMIT,
       amount=Decimal("0.1"),
       price_type="opponent",
   )

.. warning::

   ``price_type`` is **only supported for Bybit TradFi (MT5) limit orders**.
   Passing it to any other exchange connector (Binance, Bybit crypto, OKX,
   etc.) has no effect — the ``price`` you supply will be used unchanged.

Order callbacks
~~~~~~~~~~~~~~~

.. code-block:: python

   from nexustrader.schema import Order

   def on_pending_order(self, order: Order):
       self.log.info(f"Pending  oid={order.oid}  {order.side.value} {order.amount} @ {order.price}")

   def on_accepted_order(self, order: Order):
       self.log.info(f"Accepted oid={order.oid}")

   def on_filled_order(self, order: Order):
       self.log.info(f"Filled   oid={order.oid}  avg={order.average}")

   def on_canceled_order(self, order: Order):
       self.log.info(f"Canceled oid={order.oid}")

   def on_failed_order(self, order: Order):
       self.log.error(f"Failed   oid={order.oid}  reason={order.reason}")

Examples
--------

Full runnable examples are in ``strategy/bybit_tradfi/``:

- ``demo_market_data.py`` — historical klines + live BookL1 / Trade / Kline
- ``demo_trading.py`` — limit order → cancel → market order lifecycle
