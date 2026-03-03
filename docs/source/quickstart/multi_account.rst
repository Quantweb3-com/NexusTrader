Multiple Accounts & Connectors
================================

NexusTrader supports connecting to multiple account types within the same exchange (e.g., Binance
Spot + USD-M Futures) or across different exchanges simultaneously. Each account type gets its own
:class:`~nexustrader.base.connector.PublicConnector` for market data and an optional
:class:`~nexustrader.base.connector.PrivateConnector` for order management.

Connecting Multiple Account Types (Same Exchange)
---------------------------------------------------

Add multiple entries to ``public_conn_config`` and ``private_conn_config``:

.. code-block:: python

    config = Config(
        ...
        public_conn_config={
            ExchangeType.BINANCE: [
                PublicConnectorConfig(account_type=BinanceAccountType.USD_M_FUTURE),
                PublicConnectorConfig(account_type=BinanceAccountType.SPOT),
            ]
        },
        private_conn_config={
            ExchangeType.BINANCE: [
                PrivateConnectorConfig(account_type=BinanceAccountType.USD_M_FUTURE),
                PrivateConnectorConfig(account_type=BinanceAccountType.SPOT),
            ]
        },
    )

Once configured you can subscribe to data and place orders across both accounts from the same
strategy:

.. code-block:: python

    class MultiAccountStrategy(Strategy):
        def on_start(self):
            # Subscribe to both spot and futures book data
            self.subscribe_bookl1(
                symbols=["USDCUSDT.BINANCE", "USDCUSDT-PERP.BINANCE"]
            )

        def on_bookl1(self, bookl1: BookL1):
            # Route orders to the correct account via the symbol suffix
            self.create_order(
                symbol="USDCUSDT.BINANCE",            # spot
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("6"),
            )
            self.create_order(
                symbol="USDCUSDT-PERP.BINANCE",       # futures
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("6"),
            )

.. note::

   NexusTrader automatically routes each order to the correct private connector based on the
   symbol's instrument type. You do **not** need to specify the account type on every order call
   unless you want to override the default.

Full Example — Binance Spot + USD-M Futures
--------------------------------------------

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
    from nexustrader.exchange import BinanceAccountType
    from nexustrader.schema import BookL1, Order
    from nexustrader.engine import Engine


    BINANCE_API_KEY = settings.BINANCE.LIVE.ACCOUNT1.API_KEY
    BINANCE_SECRET = settings.BINANCE.LIVE.ACCOUNT1.SECRET


    class MultiConnDemo(Strategy):
        def __init__(self):
            super().__init__()
            self.signal = True

        def on_start(self):
            self.subscribe_bookl1(
                symbols=["USDCUSDT-PERP.BINANCE", "USDCUSDT.BINANCE"]
            )

        def on_filled_order(self, order: Order):
            self.log.info(str(order))

        def on_bookl1(self, bookl1: BookL1):
            if self.signal:
                # Spot buy and sell
                self.create_order(
                    symbol="USDCUSDT.BINANCE",
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    amount=Decimal("6"),
                )
                self.create_order(
                    symbol="USDCUSDT.BINANCE",
                    side=OrderSide.SELL,
                    type=OrderType.MARKET,
                    amount=Decimal("6"),
                )
                # Futures buy and sell (reduce_only for closing)
                self.create_order(
                    symbol="USDCUSDT-PERP.BINANCE",
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    amount=Decimal("6"),
                )
                self.create_order(
                    symbol="USDCUSDT-PERP.BINANCE",
                    side=OrderSide.SELL,
                    type=OrderType.MARKET,
                    amount=Decimal("6"),
                    reduce_only=True,
                )
                self.signal = False


    config = Config(
        strategy_id="multi_conn_binance",
        user_id="user_test",
        strategy=MultiConnDemo(),
        basic_config={
            ExchangeType.BINANCE: BasicConfig(
                api_key=BINANCE_API_KEY,
                secret=BINANCE_SECRET,
                testnet=False,
            )
        },
        public_conn_config={
            ExchangeType.BINANCE: [
                PublicConnectorConfig(account_type=BinanceAccountType.USD_M_FUTURE),
                PublicConnectorConfig(account_type=BinanceAccountType.SPOT),
            ]
        },
        private_conn_config={
            ExchangeType.BINANCE: [
                PrivateConnectorConfig(account_type=BinanceAccountType.USD_M_FUTURE),
                PrivateConnectorConfig(account_type=BinanceAccountType.SPOT),
            ]
        },
    )

    engine = Engine(config)

    if __name__ == "__main__":
        try:
            engine.start()
        finally:
            engine.dispose()

Multi-Exchange Configuration
-----------------------------

You can trade across different exchanges in one strategy by adding entries for each exchange:

.. code-block:: python

    config = Config(
        ...
        basic_config={
            ExchangeType.BINANCE: BasicConfig(
                api_key=BINANCE_API_KEY, secret=BINANCE_SECRET
            ),
            ExchangeType.BYBIT: BasicConfig(
                api_key=BYBIT_API_KEY, secret=BYBIT_SECRET
            ),
        },
        public_conn_config={
            ExchangeType.BINANCE: [
                PublicConnectorConfig(account_type=BinanceAccountType.USD_M_FUTURE)
            ],
            ExchangeType.BYBIT: [
                PublicConnectorConfig(account_type=BybitAccountType.LINEAR)
            ],
        },
        private_conn_config={
            ExchangeType.BINANCE: [
                PrivateConnectorConfig(account_type=BinanceAccountType.USD_M_FUTURE)
            ],
            ExchangeType.BYBIT: [
                PrivateConnectorConfig(account_type=BybitAccountType.UNIFIED)
            ],
        },
    )

.. seealso::

   - :doc:`../exchange/binance` — Binance account types
   - :doc:`../exchange/bybit` — Bybit account types
   - :doc:`../exchange/okx` — OKX account types
