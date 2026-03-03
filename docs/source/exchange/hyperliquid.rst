Hyperliquid
============

Hyperliquid is a high-performance decentralized exchange (DEX) for perpetual futures trading.
NexusTrader connects to Hyperliquid via ``HyperLiquidAccountType``.

Account Types
-------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Account Type
     - Description
   * - ``HyperLiquidAccountType.MAINNET``
     - Mainnet (live trading)
   * - ``HyperLiquidAccountType.TESTNET``
     - Testnet (paper / sandbox)
   * - ``HyperLiquidAccountType.LINEAR_MOCK``
     - Linear futures mock connector (local simulation)
   * - ``HyperLiquidAccountType.INVERSE_MOCK``
     - Inverse futures mock connector
   * - ``HyperLiquidAccountType.SPOT_MOCK``
     - Spot mock connector

.. note::

   Hyperliquid uses an Ethereum wallet (private key) for authentication.
   Provide the wallet address as ``api_key`` and the private key as ``secret``.

API Keys Setup
--------------

Add your credentials to ``.keys/.secrets.toml``:

.. code-block:: toml

   [HYPER.TESTNET]
   api_key = "0xYourWalletAddress"
   secret  = "your_private_key"

Access them in your strategy:

.. code-block:: python

   from nexustrader.constants import settings

   HYPER_API_KEY = settings.HYPER.TESTNET.API_KEY
   HYPER_SECRET  = settings.HYPER.TESTNET.SECRET

Configuration Example
---------------------

.. code-block:: python

    from nexustrader.config import (
        Config,
        PublicConnectorConfig,
        PrivateConnectorConfig,
        BasicConfig,
    )
    from nexustrader.constants import ExchangeType
    from nexustrader.exchange import HyperLiquidAccountType

    config = Config(
        strategy_id="hyperliquid_demo",
        user_id="user_test",
        strategy=MyStrategy(),
        basic_config={
            ExchangeType.HYPERLIQUID: BasicConfig(
                api_key=HYPER_API_KEY,
                secret=HYPER_SECRET,
                testnet=True,
            )
        },
        public_conn_config={
            ExchangeType.HYPERLIQUID: [
                PublicConnectorConfig(
                    account_type=HyperLiquidAccountType.TESTNET,
                    enable_rate_limit=True,
                )
            ]
        },
        private_conn_config={
            ExchangeType.HYPERLIQUID: [
                PrivateConnectorConfig(
                    account_type=HyperLiquidAccountType.TESTNET,
                    enable_rate_limit=True,
                )
            ]
        },
    )

Symbol Format
-------------

Hyperliquid perpetual futures use USDC as the quote currency:

- ``BTCUSDC-PERP.HYPERLIQUID``
- ``ETHUSDC-PERP.HYPERLIQUID``

.. note::

   Unlike CEX perpetuals (which use USDT), Hyperliquid uses **USDC** as the margin currency.
   Make sure to use the ``USDC`` suffix in symbol names.

.. seealso::

   :doc:`../concepts/instruments` for the full symbol naming convention.
