nexustrader.core.entity
===============================

.. currentmodule:: nexustrader.core.entity

This module contains classes and functions for managing tasks, events, and data readiness in the trading system.

Class Overview
-----------------

.. autoclass:: RateLimit
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: TaskManager
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ZeroMQSignalRecv
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: DataReady
   :members: 
   :undoc-members:
   :show-inheritance:
   :no-index:

   Example
   -------
   Input data to the ``DataReady`` class in the ``on_bookl1`` method. 

   .. code-block:: python

      class Demo(Strategy):
         def __init__(self):
            super().__init__()
            self.symbols = ["BTCUSDT-PERP.BYBIT"]
            self.data_ready = DataReady(symbols=self.symbols)
            
         def on_bookl1(self, bookl1: BookL1):
            self.data_ready.input(bookl1) # input data here
            
         def on_custom_signal(self, signal):
            if not self.data_ready.ready:
               self.log.info("Data not ready, skip")
               return
            
            # other trading logic....
