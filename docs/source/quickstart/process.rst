Process Management
====================

In this section, you'll learn how to manage the trading process using ``pm2``.

Install pm2
------------

.. code-block:: bash

    npm install -g pm2

Start the process
------------------

Create a process named "trader". The ``--kill-timeout`` gives the strategy time to release
resources on shutdown.

.. code-block:: bash

   pm2 start trader.py --name "trader" --kill-timeout 10000

List all processes
------------------

.. code-block:: bash

   pm2 ls

Stop the process
-----------------

.. code-block:: bash

   pm2 stop trader

Using a Config File
--------------------

Generate a template config file:

.. code-block:: bash

   pm2 init

Then start with the config:

.. code-block:: bash

   pm2 start ecosystem.config.js

Example ``ecosystem.config.js``:

.. code-block:: javascript

   module.exports = {
     apps: [
       {
         name: 'demo',
         interpreter: '/root/NexusTrader/.venv/bin/python',
         cmd: 'demo.py',
         args: '--name test --age 25 --city shanghai',
         instances: 1,
         kill_timeout: 20000,
         max_memory_restart: '8G',
         autorestart: true,
       },
     ],
   };

More resources
--------------

- `pm2 documentation <https://pm2.keymetrics.io/docs/usage/process-management/>`_
- `pm2 python <https://pm2.io/blog/2018/09/19/Manage-Python-Processes>`_
- `pm2 github <https://github.com/Unitech/pm2>`_
