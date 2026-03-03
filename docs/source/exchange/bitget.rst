Bitget
=======

Bitget is a global cryptocurrency exchange offering spot, futures, and copy-trading products.
NexusTrader supports Bitget through the ``BitgetAccountType`` enum.

Account Types
-------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Account Type
     - Description
   * - ``BitgetAccountType.UTA``
     - Unified Trading Account (live)
   * - ``BitgetAccountType.SPOT``
     - Spot account (live)
   * - ``BitgetAccountType.FUTURE``
     - Futures account (live)
   * - ``BitgetAccountType.UTA_DEMO``
     - Unified Trading Account (demo / paper trading)
   * - ``BitgetAccountType.SPOT_DEMO``
     - Spot demo account
   * - ``BitgetAccountType.FUTURE_DEMO``
     - Futures demo account
   * - ``BitgetAccountType.SPOT_MOCK``
     - Spot mock connector (local simulation)
   * - ``BitgetAccountType.LINEAR_MOCK``
     - Linear futures mock connector
   * - ``BitgetAccountType.INVERSE_MOCK``
     - Inverse futures mock connector

.. note::

   For demo trading use ``UTA_DEMO`` for both ``public_conn_config`` and ``private_conn_config``.
   The ``testnet`` flag in :class:`~nexustrader.config.BasicConfig` enables demo mode.

.. note::

   Bitget requires a **passphrase** in addition to the API key and secret.
   Set it via ``BasicConfig(passphrase=...)``.

API Keys Setup
--------------

Add your credentials to ``.keys/.secrets.toml``:

.. code-block:: toml

   [BITGET.DEMO]
   api_key = "your_api_key"
   secret = "your_secret_key"
   passphrase = "your_passphrase"

Access them in your strategy:

.. code-block:: python

   from nexustrader.constants import settings

   API_KEY   = settings.BITGET.DEMO.API_KEY
   SECRET    = settings.BITGET.DEMO.SECRET
   PASSPHRASE = settings.BITGET.DEMO.PASSPHRASE

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
    from nexustrader.exchange import BitgetAccountType

    config = Config(
        strategy_id="bitget_demo",
        user_id="user_test",
        strategy=MyStrategy(),
        basic_config={
            ExchangeType.BITGET: BasicConfig(
                api_key=API_KEY,
                secret=SECRET,
                passphrase=PASSPHRASE,
                testnet=True,
            )
        },
        public_conn_config={
            ExchangeType.BITGET: [
                PublicConnectorConfig(
                    account_type=BitgetAccountType.UTA_DEMO,
                    enable_rate_limit=True,
                )
            ]
        },
        private_conn_config={
            ExchangeType.BITGET: [
                PrivateConnectorConfig(
                    account_type=BitgetAccountType.UTA_DEMO,
                    enable_rate_limit=True,
                )
            ]
        },
    )

Symbol Format
-------------

Bitget symbols follow the standard NexusTrader convention:

- Spot: ``BTCUSDT.BITGET``
- Perpetual futures: ``BTCUSDT-PERP.BITGET``

.. seealso::

   :doc:`../concepts/instruments` for the full symbol naming convention.
