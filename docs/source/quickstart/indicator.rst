How to define indicators
=========================

Indicators in NexusTrader are objects that consume market data and produce derived values (e.g.,
moving averages, volatility measures). They integrate with the engine's warmup system so that
historical data can be fetched automatically before live trading starts.

Simple Indicator (No Warmup)
------------------------------

Let's start with a simple indicator that needs no historical warmup.

The **weighted mid price** is calculated as:

.. math::

    \text{weighted\_mid} = \frac{P_a \times V_b}{V_a + V_b} + \frac{P_b \times V_a}{V_a + V_b}

Where:

- :math:`P_a` / :math:`P_b` — ask / bid price
- :math:`V_a` / :math:`V_b` — ask / bid volume

.. code-block:: python

    from nexustrader.indicator import Indicator
    from nexustrader.schema import Kline, BookL1, BookL2, Trade

    class WeightedMidIndicator(Indicator):
        def __init__(self):
            super().__init__()
            self._value = None

        def handle_bookl1(self, bookl1: BookL1):
            self._value = bookl1.weighted_mid

        def handle_kline(self, kline: Kline):
            pass

        def handle_bookl2(self, bookl2: BookL2):
            pass

        def handle_trade(self, trade: Trade):
            pass

        @property
        def value(self):
            return self._value

Using the indicator in a strategy:

.. code-block:: python

    from nexustrader.strategy import Strategy
    from nexustrader.constants import DataType
    from nexustrader.schema import BookL1

    class Demo(Strategy):
        def __init__(self):
            super().__init__()
            self.wmid = WeightedMidIndicator()
            self.symbol = "UNIUSDT-PERP.BYBIT"

        def on_start(self):
            self.subscribe_bookl1(symbols=[self.symbol])
            self.register_indicator(
                symbols=self.symbol,
                indicator=self.wmid,
                data_type=DataType.BOOKL1,
            )

        def on_bookl1(self, bookl1: BookL1):
            if self.wmid.value is None:
                return
            self.log.info(
                f"weighted_mid={self.wmid.value:.4f}  mid={bookl1.mid:.4f}"
            )

Indicator with Warmup (Historical Data)
-----------------------------------------

Indicators that require historical data (e.g., moving averages) set ``warmup_period`` and
``kline_interval`` in the constructor. The engine will automatically fetch the required number
of historical klines before the strategy starts.

.. code-block:: python

    from collections import deque
    from nexustrader.indicator import Indicator
    from nexustrader.constants import KlineInterval
    from nexustrader.schema import Kline

    class MovingAverageIndicator(Indicator):
        def __init__(self, period: int = 20):
            super().__init__(
                params={"period": period},
                name=f"MA_{period}",
                warmup_period=period * 2,          # fetch 2× the period worth of history
                kline_interval=KlineInterval.MINUTE_1,
            )
            self.period = period
            self.prices = deque(maxlen=period)
            self._value = None

        def handle_kline(self, kline: Kline):
            if not kline.confirm:          # only process closed bars
                return
            self.prices.append(kline.close)
            if len(self.prices) >= self.period:
                self._value = sum(self.prices) / len(self.prices)

        @property
        def value(self):
            return self._value

Multi-Symbol Indicator with Warmup
-------------------------------------

When an indicator is registered for multiple symbols each symbol gets its own independent
indicator instance. Access per-symbol values via the ``indicator`` proxy:

.. code-block:: python

    from nexustrader.strategy import Strategy
    from nexustrader.constants import DataType, KlineInterval, LogColor
    from nexustrader.schema import Kline
    from nexustrader.exchange import BybitAccountType

    class WarmupDemo(Strategy):
        def __init__(self):
            super().__init__()
            self.symbols = [
                "BTCUSDT-PERP.BYBIT",
                "ETHUSDT-PERP.BYBIT",
                "UNIUSDT-PERP.BYBIT",
            ]
            self.ma_20 = MovingAverageIndicator(period=20)
            self.ma_50 = MovingAverageIndicator(period=50)

        def on_start(self):
            self.subscribe_kline(symbols=self.symbols, interval=KlineInterval.MINUTE_1)

            self.register_indicator(
                symbols=self.symbols,
                indicator=self.ma_20,
                data_type=DataType.KLINE,
                account_type=BybitAccountType.LINEAR,
            )
            self.register_indicator(
                symbols=self.symbols,
                indicator=self.ma_50,
                data_type=DataType.KLINE,
                account_type=BybitAccountType.LINEAR,
            )

        def on_kline(self, kline: Kline):
            symbol = kline.symbol

            # Access per-symbol indicator instances via the proxy
            ma_20 = self.indicator.MA_20[symbol]
            ma_50 = self.indicator.MA_50[symbol]

            if not ma_20 or not ma_50:
                return

            if not ma_20.is_warmed_up or not ma_50.is_warmed_up:
                self.log.info(f"{symbol}: warming up…", color=LogColor.BLUE)
                return

            if not kline.confirm:
                return

            if ma_20.value and ma_50.value:
                self.log.info(
                    f"{symbol} MA20={ma_20.value:.4f}  MA50={ma_50.value:.4f}  "
                    f"close={kline.close:.4f}",
                    color=LogColor.BLUE,
                )
                if ma_20.value > ma_50.value:
                    self.log.info(f"{symbol}: Golden Cross — Bullish", color=LogColor.BLUE)
                else:
                    self.log.info(f"{symbol}: Death Cross — Bearish", color=LogColor.BLUE)

Indicator API Summary
----------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Attribute / Method
     - Description
   * - ``warmup_period``
     - Number of historical bars required (set in ``__init__``)
   * - ``kline_interval``
     - Kline interval used for warmup data
   * - ``is_warmed_up``
     - ``True`` once warmup data has been fully consumed
   * - ``requires_warmup``
     - ``True`` if ``warmup_period`` was set
   * - ``value``
     - Current indicator value (implement as a ``@property``)
   * - ``handle_kline(kline)``
     - Called for each kline update
   * - ``handle_bookl1(bookl1)``
     - Called for each level-1 book update
   * - ``handle_trade(trade)``
     - Called for each trade update
   * - ``handle_bookl2(bookl2)``
     - Called for each level-2 book update

Registering Indicators
-----------------------

Use :meth:`~nexustrader.strategy.Strategy.register_indicator` inside ``on_start``:

.. code-block:: python

    self.register_indicator(
        symbols="BTCUSDT-PERP.BYBIT",          # str or list[str]
        indicator=self.my_indicator,
        data_type=DataType.KLINE,              # DataType.BOOKL1 / TRADE / etc.
        account_type=BybitAccountType.LINEAR,  # needed for warmup data fetching
    )

.. note::

   ``account_type`` is required when ``warmup_period`` is set, as the engine needs to know
   which exchange endpoint to fetch historical klines from.
