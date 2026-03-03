Take-Profit & Stop-Loss Orders
================================

NexusTrader supports attaching take-profit (TP) and stop-loss (SL) legs to a parent order in a
single API call via :meth:`~nexustrader.strategy.Strategy.create_tp_sl_order`. When the parent
order fills, the exchange automatically activates both conditional legs.

Overview
--------

.. code-block:: python

    self.create_tp_sl_order(
        symbol="BTCUSDT-PERP.BYBIT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        amount=Decimal("0.001"),
        # Take-profit: trigger at 0.1 % above ask
        tp_order_type=OrderType.MARKET,
        tp_trigger_price=self.price_to_precision(symbol, bookl1.ask * 1.001),
        # Stop-loss: trigger at 0.1 % below bid
        sl_order_type=OrderType.MARKET,
        sl_trigger_price=self.price_to_precision(symbol, bookl1.bid * 0.999),
    )

Parameters
----------

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Parameter
     - Type
     - Description
   * - ``symbol``
     - ``str``
     - Instrument ID
   * - ``side``
     - ``OrderSide``
     - Parent order side (``BUY`` or ``SELL``)
   * - ``type``
     - ``OrderType``
     - Parent order type (``MARKET`` or ``LIMIT``)
   * - ``amount``
     - ``Decimal``
     - Parent order quantity
   * - ``price``
     - ``Decimal`` (optional)
     - Parent limit price (required when ``type=LIMIT``)
   * - ``tp_order_type``
     - ``OrderType``
     - Take-profit order type (``MARKET`` or ``LIMIT``)
   * - ``tp_trigger_price``
     - ``Decimal``
     - Price that activates the take-profit leg
   * - ``tp_price``
     - ``Decimal`` (optional)
     - Take-profit limit price (required when ``tp_order_type=LIMIT``)
   * - ``sl_order_type``
     - ``OrderType``
     - Stop-loss order type (``MARKET`` or ``LIMIT``)
   * - ``sl_trigger_price``
     - ``Decimal``
     - Price that activates the stop-loss leg
   * - ``sl_price``
     - ``Decimal`` (optional)
     - Stop-loss limit price (required when ``sl_order_type=LIMIT``)
   * - ``account_type``
     - ``AccountType`` (optional)
     - Override the default account type

.. note::

   Support for TP/SL orders varies by exchange. Currently fully supported on **Bybit** and **OKX**.
   Check your exchange documentation for conditional order requirements.

Full Example
------------

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
    from nexustrader.constants import ExchangeType, OrderSide, OrderType
    from nexustrader.exchange import BybitAccountType
    from nexustrader.schema import BookL1, Order
    from nexustrader.engine import Engine


    BYBIT_API_KEY = settings.BYBIT.TESTNET.API_KEY
    BYBIT_SECRET = settings.BYBIT.TESTNET.SECRET


    class TpSlDemo(Strategy):
        def __init__(self):
            super().__init__()
            self.signal = True

        def on_start(self):
            self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BYBIT"])

        def on_failed_order(self, order: Order):
            self.log.info(str(order))

        def on_accepted_order(self, order: Order):
            self.log.info(str(order))

        def on_filled_order(self, order: Order):
            self.log.info(str(order))

        def on_bookl1(self, bookl1: BookL1):
            if self.signal:
                symbol = "BTCUSDT-PERP.BYBIT"
                self.create_tp_sl_order(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    amount=Decimal("0.001"),
                    tp_order_type=OrderType.MARKET,
                    tp_trigger_price=self.price_to_precision(
                        symbol, bookl1.ask * 1.001
                    ),
                    sl_order_type=OrderType.MARKET,
                    sl_trigger_price=self.price_to_precision(
                        symbol, bookl1.bid * 0.999
                    ),
                )
                self.signal = False


    config = Config(
        strategy_id="bybit_tp_sl_order",
        user_id="user_test",
        strategy=TpSlDemo(),
        basic_config={
            ExchangeType.BYBIT: BasicConfig(
                api_key=BYBIT_API_KEY,
                secret=BYBIT_SECRET,
                testnet=True,
            )
        },
        public_conn_config={
            ExchangeType.BYBIT: [
                PublicConnectorConfig(account_type=BybitAccountType.LINEAR_TESTNET)
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

Price Precision Helper
----------------------

Always use :meth:`~nexustrader.strategy.Strategy.price_to_precision` to round prices to the
exchange's tick size before passing them to order methods:

.. code-block:: python

    tp_price = self.price_to_precision("BTCUSDT-PERP.BYBIT", bookl1.ask * 1.005)
    sl_price = self.price_to_precision("BTCUSDT-PERP.BYBIT", bookl1.bid * 0.995)

Similarly use :meth:`~nexustrader.strategy.Strategy.amount_to_precision` for quantities.

.. seealso::

   :doc:`../concepts/orders` for the full order status lifecycle.
