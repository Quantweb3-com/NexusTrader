Bybit Exchange
===============

Bybit Account Types
------------------------

Bybit provides multiple account types. For testing environment, you can use account types with ``_TESTNET`` suffix.

.. code-block:: python

    from nexustrader.exchange.bybit import BybitAccountType

    account_type = BybitAccountType.LINEAR  # or other account types
    
- ``BybitAccountType.SPOT``: Spot account
- ``BybitAccountType.LINEAR``: Linear perpetual account
- ``BybitAccountType.INVERSE``: Inverse perpetual account
- ``BybitAccountType.OPTION``: Option account
- ``BybitAccountType.UNIFIED``: Unified account
- ``BybitAccountType.SPOT_TESTNET``: Spot testnet account
- ``BybitAccountType.LINEAR_TESTNET``: Linear perpetual testnet account
- ``BybitAccountType.INVERSE_TESTNET``: Inverse perpetual testnet account
- ``BybitAccountType.OPTION_TESTNET``: Option testnet account
- ``BybitAccountType.UNIFIED_TESTNET``: Unified testnet account

.. note::

    For ``PrivateConnectorConfig``, ``BYBIT Exchange`` only needs to use ``BybitAccountType.UNIFIED`` for live trading, else use ``BybitAccountType.UNIFIED_TESTNET`` for testing.




Bybit Config
-------------------

The most important part is the ``config`` object. You need to pass the ``config`` object to the ``Engine`` class. The ``config`` receives the following parameters:

- ``strategy_id``: The id of the strategy
- ``user_id``: The id of the user
- ``strategy``: The strategy class
- ``basic_config``: The basic config of the exchange
- ``public_conn_config``: The public connector config of the exchange
- ``private_conn_config``: The private connector config of the exchange

.. code-block:: python

    from nexustrader.constants import settings
    from nexustrader.exchange.bybit import BybitAccountType
    from nexustrader.config import Config, PublicConnectorConfig, PrivateConnectorConfig, BasicConfig

    BYBIT_API_KEY = settings.BYBIT.TESTNET.api_key
    BYBIT_SECRET = settings.BYBIT.TESTNET.secret

    # The strategy code....

    config = Config(
        strategy_id="bybit_buy_and_sell",
        user_id="user_test",
        strategy=Demo(),
        basic_config={
            ExchangeType.BYBIT: BasicConfig(
                api_key=BYBIT_API_KEY,
                secret=BYBIT_SECRET,
                testnet=True,
            )
        },
        public_conn_config={
            ExchangeType.BYBIT: [
                PublicConnectorConfig(
                    account_type=BybitAccountType.LINEAR_TESTNET,
                ),
                PublicConnectorConfig(
                    account_type=BybitAccountType.SPOT_TESTNET,
                ),
            ]
        },
        private_conn_config={
            ExchangeType.BYBIT: [
                PrivateConnectorConfig(
                    account_type=BybitAccountType.UNIFIED_TESTNET,
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
