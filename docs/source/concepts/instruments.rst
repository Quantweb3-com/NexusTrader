Instruments
===========


Naming Convention
-----------------

There are two types of assets: ``SPOT`` and ``SWAP``. ``SWAP`` is divided into ``PERP`` and ``FUTURE``, and both ``PERP`` and ``FUTURE`` have ``LINEAR`` and ``INVERSE`` categories.

- SPOT: ``BTCUSDT.BINANCE`` 
- SWAP
    - PERP
        - LINEAR: ``BTCUSDT-PERP.BYBIT``
        - INVERSE: ``BTCUSD-PERP.BYBIT``
    - FUTURE
        - LINEAR: ``BTCUSDT-241227.BYBIT``
        - INVERSE: ``BTCUSD-241227.BINANCE``

.. note::

    ``SWAP`` can be either ``FUTURE`` or ``PERP``, depending on whether the character after ``-`` is ``PERP`` or a number. Eg: ``BTCUSD-241227.BINANCE`` is ``FUTURE`` while ``BTCUSDT-PERP.BYBIT`` is ``PERP``. The difference between ``LINEAR`` and ``INVERSE`` is the determination of the asset. ``LINEAR`` is determined by quote asset, while ``INVERSE`` is the price of the base asset.

Bybit TradFi (MT5)
------------------

Bybit TradFi instruments also use the NexusTrader ``symbol.EXCHANGE`` format,
but the symbol prefix is derived from the MT5 broker symbol. Leading ``#`` or
``.`` prefixes are stripped, and internal dots are replaced with underscores
before appending ``.BYBIT_TRADFI``.

.. list-table::
   :header-rows: 1
   :widths: 25 40

   * - MT5 Symbol
     - NexusTrader Symbol
   * - ``EURUSD``
     - ``EURUSD.BYBIT_TRADFI``
   * - ``XAUUSD.s``
     - ``XAUUSD_s.BYBIT_TRADFI``
   * - ``#AAPL``
     - ``AAPL.BYBIT_TRADFI``

Use the NexusTrader symbol everywhere in strategy code, including
subscriptions, order placement, and cache lookups:

.. code-block:: python

    self.subscribe_bookl1("XAUUSD_s.BYBIT_TRADFI")
    position = self.cache.get_position("XAUUSD_s.BYBIT_TRADFI")

The raw MT5 symbol, such as ``XAUUSD.s``, is only used internally by the MT5
connector.

Usage
-----

.. code-block:: python

    from nexustrader.schema import InstrumentId

    ## create an instrument id
    instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BYBIT")

    ## is_spot
    instrument_id.is_spot() # False

    ## is_swap
    instrument_id.is_linear() # True

    ## is_future
    instrument_id.is_inverse() # False


