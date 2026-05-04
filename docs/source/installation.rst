Installation
============

Prerequisites
-------------

- Python 3.11+
- ``uv`` (recommended) or ``pip``

.. note::

   Since 0.3.7, ``nautilus-trader`` has been removed. A Rust toolchain or
   ``build-essential`` is **no longer required** on any platform.

Install from PyPI
-----------------

.. code-block:: bash

   pip install nexustrader

Optional: ZeroMQ signal support
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you use custom signals via ``ZeroMQSignalConfig``, install the extra:

.. code-block:: bash

   pip install nexustrader[signal]

Optional: Bybit TradFi (MT5) support
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To trade traditional financial markets (Forex, Gold, Indices, Stocks) via the
Bybit TradFi brokerage (MetaTrader 5 backend):

.. code-block:: bash

   pip install "nexustrader[tradfi]"
   # or
   uv add "nexustrader[tradfi]"

.. note::

   The ``tradfi`` extra installs ``MetaTrader5`` only on Windows. Base
   installs on Linux/macOS do not install ``MetaTrader5``. The MetaTrader5
   terminal must be installed and logged in before starting NexusTrader.
   See :doc:`/exchange/bybit_tradfi` for full setup instructions.

Install from source
-------------------

Using ``uv`` (recommended):

.. code-block:: bash

   git clone https://github.com/Quantweb3-com/NexusTrader
   cd NexusTrader
   uv sync

Using ``pip``:

.. code-block:: bash

   git clone https://github.com/Quantweb3-com/NexusTrader
   cd NexusTrader
   pip install -e .


Install Redis
---------------

In the newest version, redis is not required. You can specify the `storage_backend` in the `Config` to use other storage backends.

.. code-block:: python

   from nexustrader.config import Config
   from nexustrader.constants import StorageType

   config = Config(
       storage_backend=StorageType.SQLITE,
   )

.. note::

   It is recommended to use `StorageType.SQLITE` for production environment, since `StorageType.REDIS` will be deprecated in the future version.

First, create a ``.env`` file in the root directory of the project and add the following environment variables:

.. code-block:: bash

   NEXUS_REDIS_HOST=127.0.0.1
   NEXUS_REDIS_PORT=6379
   NEXUS_REDIS_DB=0
   NEXUS_REDIS_PASSWORD=your_password

Create the ``docker-compose.yml`` file to the root directory of the project 

.. code-block:: yaml

   version: '3.8'
   services:
     redis:
        image: redis:alpine
        container_name: redis
        restart: always
        ports:
           - '${NEXUS_REDIS_PORT}:6379'
        volumes:
           - redis_data:/data
        command: redis-server --appendonly yes --requirepass ${NEXUS_REDIS_PASSWORD}
        environment:
           - REDIS_PASSWORD=${NEXUS_REDIS_PASSWORD}

Run the following command to start the Redis container:

.. code-block:: bash

   docker-compose up -d redis

.. note::

   NexusTrader is tested on Linux, macOS, and Windows. On Windows, ``uvloop`` is automatically skipped and the standard ``asyncio`` event loop is used.
