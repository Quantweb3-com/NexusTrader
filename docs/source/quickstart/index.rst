Quickstart
============

In this section, you'll learn:

- How to setup API keys for the exchanges
- How to manage processes with ``pm2``
- How to create a basic buy & sell strategy
- How to build a strategy using custom signals
- How to receive custom signals with :doc:`ZeroMQSignalRecv <../api/core/entity>`
- How to implement mock (paper) trading
- How to define indicators and use them in the strategy
- How to execute TWAP orders
- How to place batch orders
- How to use take-profit and stop-loss orders
- How to connect multiple accounts simultaneously
- How to integrate web callbacks via FastAPI
- How to build reliable WS order flows with idempotency, ACK handling, and reconnect reconciliation

Strategy Overview
-------------------

.. toctree::
   :maxdepth: 2

   keys
   process
   buyandsell
   custom_signal
   mock
   indicator
   twap
   batch_orders
   tpsl
   multi_account
   web_callback
   reliable_orders
