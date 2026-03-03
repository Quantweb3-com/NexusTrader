TWAP Orders
============

TWAP (Time-Weighted Average Price) is an algorithmic order type that splits a large order into
smaller child orders executed evenly over a specified time window. This reduces market impact and
achieves an average execution price close to the time-weighted average.

Overview
--------

Use :meth:`~nexustrader.strategy.Strategy.create_twap` to submit a TWAP order and
:meth:`~nexustrader.strategy.Strategy.cancel_twap` to cancel one that is still running.

.. code-block:: python

    uuid = self.create_twap(
        symbol="BTCUSDT-PERP.BYBIT",
        side=OrderSide.BUY,
        amount=Decimal("0.3"),   # total quantity to execute
        duration=300,            # spread over 300 seconds (5 minutes)
        wait=3,                  # place a child order every 3 seconds
    )

Parameters
----------

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
     - ``OrderSide.BUY`` or ``OrderSide.SELL``
   * - ``amount``
     - ``Decimal``
     - Total quantity to execute
   * - ``duration``
     - ``int``
     - Total execution window in seconds
   * - ``wait``
     - ``int``
     - Interval between child orders in seconds
   * - ``account_type``
     - ``AccountType`` (optional)
     - Override the default account type

TWAP Status
-----------

The TWAP order lifecycle has five states:

- ``RUNNING``: actively placing child orders
- ``CANCELING``: cancel has been requested but child orders may still be in-flight
- ``CANCELLED``: all remaining child orders have been cancelled
- ``FINISHED``: all child orders have been filled
- ``FAILED``: a child order failed; the entire TWAP is aborted

Full Example
------------

The following example subscribes to ``BTCUSDT-PERP.BYBIT`` level-1 order book data, then places
a single TWAP BUY order of ``0.3 BTC`` spread over **5 minutes** with a **3-second** interval.

.. code-block:: python

    from decimal import Decimal

    from nexustrader.constants import settings
    from nexustrader.config import (
        Config,
        PublicConnectorConfig,
        PrivateConnectorConfig,
        BasicConfig,
    )
    from nexustrader.strategy import Strategy
    from nexustrader.constants import ExchangeType, OrderSide
    from nexustrader.exchange import BybitAccountType
    from nexustrader.schema import BookL1, Order
    from nexustrader.engine import Engine


    BYBIT_API_KEY = settings.BYBIT.TESTNET.API_KEY
    BYBIT_SECRET = settings.BYBIT.TESTNET.SECRET


    class TwapDemo(Strategy):
        def __init__(self):
            super().__init__()
            self.signal = True

        def on_start(self):
            self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BYBIT"])

        def on_canceled_order(self, order: Order):
            self.log.info(f"canceled: {order.uuid}")

        def on_accepted_order(self, order: Order):
            self.log.info(f"accepted: {order.uuid}")

        def on_filled_order(self, order: Order):
            self.log.info(f"filled: {order.uuid}")

        def on_bookl1(self, bookl1: BookL1):
            if self.signal:
                self.create_twap(
                    symbol="BTCUSDT-PERP.BYBIT",
                    side=OrderSide.BUY,
                    amount=Decimal("0.3"),
                    duration=60 * 5,   # 5 minutes
                    wait=3,            # every 3 seconds
                )
                self.signal = False

            position = self.cache.get_position("BTCUSDT-PERP.BYBIT")
            self.log.info(f"position: {position}")


    config = Config(
        strategy_id="bybit_twap",
        user_id="user_test",
        strategy=TwapDemo(),
        basic_config={
            ExchangeType.BYBIT: BasicConfig(
                api_key=BYBIT_API_KEY,
                secret=BYBIT_SECRET,
                testnet=True,
            )
        },
        public_conn_config={
            ExchangeType.BYBIT: [
                PublicConnectorConfig(account_type=BybitAccountType.LINEAR_TESTNET),
                PublicConnectorConfig(account_type=BybitAccountType.SPOT_TESTNET),
            ]
        },
        private_conn_config={
            ExchangeType.BYBIT: [
                PrivateConnectorConfig(account_type=BybitAccountType.UNIFIED_TESTNET)
            ]
        },
    )

    engine = Engine(config)

    if __name__ == "__main__":
        try:
            engine.start()
        finally:
            engine.dispose()

Cancelling a TWAP
-----------------

Call :meth:`~nexustrader.strategy.Strategy.cancel_twap` with the UUID returned by
``create_twap``:

.. code-block:: python

    class TwapCancelDemo(Strategy):
        def __init__(self):
            super().__init__()
            self.twap_uuid = None

        def on_bookl1(self, bookl1: BookL1):
            if self.twap_uuid is None:
                self.twap_uuid = self.create_twap(
                    symbol="BTCUSDT-PERP.BYBIT",
                    side=OrderSide.BUY,
                    amount=Decimal("0.3"),
                    duration=300,
                    wait=5,
                )
            # Cancel after some condition is met
            elif <some_exit_condition>:
                self.cancel_twap(
                    symbol="BTCUSDT-PERP.BYBIT",
                    uuid=self.twap_uuid,
                )
                self.twap_uuid = None

.. seealso::

   :doc:`../concepts/orders` for a full description of the TWAP order lifecycle diagram.
