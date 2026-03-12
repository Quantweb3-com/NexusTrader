Setting up Credentials
======================

NexusTrader supports three ways to provide exchange API credentials, in priority order:

1. **Direct pass** — pass credentials explicitly in code
2. **Settings file** — store in ``.keys/.secrets.toml`` (and/or ``NEXUS_`` prefixed environment variables)
3. **Environment variables** — read from plain environment variables

You can use any combination. Directly passed values always take precedence.

.. note::

   The ``.keys/.secrets.toml`` file is **optional**. If it does not exist, NexusTrader
   emits a warning but continues to run. Public-only, mock, and backtest workflows
   do not require any credentials.

Method 1: Settings File (TOML)
------------------------------

Create a ``.keys`` directory and a ``.secrets.toml`` file:

.. code-block:: bash

   mkdir .keys
   touch .keys/.secrets.toml

Add your exchange credentials:

.. code-block:: toml

   [BYBIT.TESTNET]
   api_key = "your_api_key"
   secret = "your_secret_key"

   [OKX.DEMO_1]
   api_key = "your_api_key"
   secret = "your_secret_key"
   passphrase = "your_passphrase"

Use the ``settings_key`` parameter in ``BasicConfig`` to auto-resolve:

.. code-block:: python

   from nexustrader.config import BasicConfig

   # Auto-resolves api_key, secret, passphrase from [BYBIT.TESTNET]
   config = BasicConfig(settings_key="BYBIT.TESTNET", testnet=True)

Or access settings manually (legacy approach):

.. code-block:: python

   from nexustrader.constants import settings

   print(settings.BYBIT.TESTNET.api_key)
   print(settings.BYBIT.TESTNET.secret)

Method 2: Environment Variables (NEXUS\_ prefix)
-------------------------------------------------

Dynaconf automatically merges ``NEXUS_`` prefixed environment variables with the
TOML file. Use double underscores for nested keys:

.. code-block:: bash

   export NEXUS_BINANCE__DEMO__API_KEY="your_api_key"
   export NEXUS_BINANCE__DEMO__SECRET="your_secret_key"

These are resolved by the same ``settings_key`` parameter:

.. code-block:: python

   # Reads from NEXUS_BINANCE__DEMO__API_KEY / NEXUS_BINANCE__DEMO__SECRET
   config = BasicConfig(settings_key="BINANCE.DEMO", testnet=True)

Method 3: Plain Environment Variables
--------------------------------------

Use ``BasicConfig.from_env()`` to read credentials from plain environment variables
without the ``NEXUS_`` prefix:

.. code-block:: bash

   export BINANCE_API_KEY="your_api_key"
   export BINANCE_SECRET="your_secret_key"

.. code-block:: python

   from nexustrader.config import BasicConfig

   # Reads BINANCE_API_KEY, BINANCE_SECRET, BINANCE_PASSPHRASE
   config = BasicConfig.from_env("BINANCE", testnet=True)

   # Custom variable names
   config = BasicConfig.from_env(
       "X",
       api_key_var="MY_KEY",
       secret_var="MY_SECRET",
   )

Method 4: Direct Pass
---------------------

Pass credentials directly in code (highest priority, always overrides other sources):

.. code-block:: python

   from nexustrader.config import BasicConfig

   config = BasicConfig(
       api_key="your_api_key",
       secret="your_secret_key",
       testnet=True,
   )

Combining Sources
-----------------

You can combine sources. Directly passed values override ``settings_key`` resolution:

.. code-block:: python

   # api_key is the direct value; secret is resolved from settings
   config = BasicConfig(
       api_key="override_key",
       settings_key="BINANCE.DEMO",
       testnet=True,
   )
