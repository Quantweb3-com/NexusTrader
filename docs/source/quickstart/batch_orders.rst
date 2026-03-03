Batch Orders
=============

Batch orders let you submit multiple orders to the exchange in a single API call, reducing round
trips and improving execution speed. Use :meth:`~nexustrader.strategy.Strategy.create_batch_orders`
with a list of :class:`~nexustrader.schema.BatchOrder` objects.

Overview
--------

.. code-block:: python

    from nexustrader.schema import BatchOrder

    self.create_batch_orders(
        orders=[
            BatchOrder(
                symbol="BTCUSDT-PERP.BYBIT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=price1,
            ),
            BatchOrder(
                symbol="BTCUSDT-PERP.BYBIT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.01"),
                price=price2,
            ),
        ]
    )

BatchOrder Parameters
---------------------

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Field
     - Type
     - Description
   * - ``symbol``
     - ``str``
     - Instrument ID
   * - ``side``
     - ``OrderSide``
     - ``BUY`` or ``SELL``
   * - ``type``
     - ``OrderType``
     - Order type (e.g. ``LIMIT``, ``MARKET``)
   * - ``amount``
     - ``Decimal``
     - Order quantity
   * - ``price``
     - ``Decimal`` (optional)
     - Limit price

.. note::

   Each exchange has a maximum batch size. Bybit supports up to **10** orders per batch.
   Binance supports up to **5** orders per batch (USD-M futures).

Full Example
------------

The example below places six staggered BUY limit orders at decreasing price levels below the
current best bid.

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
    from nexustrader.schema import BookL1, Order, BatchOrder
    from nexustrader.engine import Engine


    BYBIT_API_KEY = settings.BYBIT.TESTNET.API_KEY
    BYBIT_SECRET = settings.BYBIT.TESTNET.SECRET


    class BatchOrderDemo(Strategy):
        def __init__(self):
            super().__init__()
            self.signal = True

        def on_start(self):
            self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BYBIT"])

        def on_accepted_order(self, order: Order):
            self.log.info(str(order))

        def on_filled_order(self, order: Order):
            self.log.info(str(order))

        def on_bookl1(self, bookl1: BookL1):
            if self.signal:
                symbol = "BTCUSDT-PERP.BYBIT"
                bid = bookl1.bid

                prices = [
                    self.price_to_precision(symbol, bid * (1 - 0.001 * i))
                    for i in range(1, 7)
                ]

                self.create_batch_orders(
                    orders=[
                        BatchOrder(
                            symbol=symbol,
                            side=OrderSide.BUY,
                            type=OrderType.LIMIT,
                            amount=Decimal("0.01"),
                            price=px,
                        )
                        for px in prices
                    ]
                )
                self.signal = False


    config = Config(
        strategy_id="bybit_batch_orders",
        user_id="user_test",
        strategy=BatchOrderDemo(),
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

Cancelling All Orders
---------------------

To cancel all open orders for a symbol at once use
:meth:`~nexustrader.strategy.Strategy.cancel_all_orders`:

.. code-block:: python

    self.cancel_all_orders(symbol="BTCUSDT-PERP.BYBIT")

.. seealso::

   :doc:`../concepts/orders` for the full order status lifecycle.
