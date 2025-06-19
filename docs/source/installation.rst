Installation
============

Prerequisites
-------------

- Python 3.11+
- Redis
- Poetry (recommended)
- build-essential

Install Build Essentials
-----------------------------

.. code-block:: bash

   sudo apt-get update 
   sudo apt-get install build-essential

Install from PyPI
-----------------

.. code-block:: bash

   pip install nexustrader

Install from source
-------------------

.. code-block:: bash

   git clone https://github.com/RiverTrading/NexusTrader
   cd NexusTrader
   poetry install 


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

   Currently, NexusTrader only tested on Linux and MacOS. Windows is not supported yet.
