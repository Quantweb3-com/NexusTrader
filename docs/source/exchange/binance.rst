Binance Exchange
========================

Binance Account Types
--------------------------

Binance provides multiple account types. For testing environment, you can use account types with ``_TESTNET`` suffix.

.. code-block:: python

    from nexustrader.exchange.binance import BinanceAccountType

    account_type = BinanceAccountType.USD_M_FUTURE  # or other account types

- ``BinanceAccountType.SPOT``: Spot account
- ``BinanceAccountType.MARGIN``: Cross margin account
- ``BinanceAccountType.ISOLATED_MARGIN``: Isolated margin account
- ``BinanceAccountType.USD_M_FUTURE``: USD-M futures account
- ``BinanceAccountType.COIN_M_FUTURE``: COIN-M futures account
- ``BinanceAccountType.PORTFOLIO_MARGIN``: Portfolio margin account
- ``BinanceAccountType.SPOT_TESTNET``: Spot testnet account
- ``BinanceAccountType.USD_M_FUTURE_TESTNET``: USD-M futures testnet account
- ``BinanceAccountType.COIN_M_FUTURE_TESTNET``: COIN-M futures testnet account

.. note::

    For futures trading on testnet, make sure to use ``USD_M_FUTURE_TESTNET`` or ``COIN_M_FUTURE_TESTNET`` account types. For spot trading on testnet, use ``SPOT_TESTNET``. Only ``SPOT``, ``USD_M_FUTURE``, ``COIN_M_FUTURE`` can be passed to ``public_conn_config``.

Binance Config
--------------------------

The most important part is the ``config`` object. You need to pass the ``config`` object to the ``Engine`` class. The ``config`` receives the following parameters:

- ``strategy_id``: The id of the strategy
- ``user_id``: The id of the user
- ``strategy``: The strategy class
- ``basic_config``: The basic config of the exchange
- ``public_conn_config``: The public connector config of the exchange
- ``private_conn_config``: The private connector config of the exchange

.. code-block:: python

    from nexustrader.exchange.binance import BinanceAccountType
    from nexustrader.config import Config, PublicConnectorConfig, PrivateConnectorConfig, BasicConfig

    # The strategy code....

    config = Config(
        strategy_id="buy_and_sell_binance",
        user_id="user_test",
        strategy=Demo(),
        basic_config={
            ExchangeType.BINANCE: BasicConfig(
                settings_key="BINANCE.FUTURE.TESTNET_1",
                testnet=True,
            )
        },
        public_conn_config={
            ExchangeType.BINANCE: [
                PublicConnectorConfig(
                    account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
                )
            ]
        },
        private_conn_config={
            ExchangeType.BINANCE: [
                PrivateConnectorConfig(
                    account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
                )
            ]
        }
    )

    engine = Engine(config)

    if __name__ == "__main__":
        try:
            engine.start()
        finally:
            engine.dispose()
