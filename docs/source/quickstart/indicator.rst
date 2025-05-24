How to define indicators
=========================

Let's start with a simple indicator.

The weighted mid price is calculated as follows:

.. math::

    \text{weighted_mid} = \frac{P_a \times V_b}{V_a + V_b} + \frac{P_b \times V_a}{V_a + V_b}

Where:
- :math:`P_a` is the ask price
- :math:`V_a` is the ask volume 
- :math:`P_b` is the bid price
- :math:`V_b` is the bid volume

.. code-block:: python

    from nexustrader.indicator import Indicator
    from nexustrader.schema import Kline, BookL1, BookL2, Trade

    class WeightedMidIndicator(Indicator):
        def __init__(self):
            self.value = None

        def handle_kline(self, kline: Kline):
            pass

        def handle_bookl1(self, bookl1: BookL1):
            self.value = bookl1.weighted_mid

        def handle_bookl2(self, bookl2: BookL2):
            pass

        def handle_trade(self, trade: Trade):
            pass

Then we can use the indicator in the strategy.

.. code-block:: python

    class Demo(Strategy):
        def __init__(self):
            super().__init__()
            self.signal = True
            self.symbol = "UNIUSDT-PERP.BYBIT"
            self.micro_price_indicator = MicroPriceIndicator()

        def on_start(self):
            self.subscribe_bookl1(
                symbols=self.symbol,
            )
            self.register_indicator(
                symbols=self.symbol,
                indicator=self.micro_price_indicator,
                data_type=DataType.BOOKL1,
            )

        def on_bookl1(self, bookl1: BookL1):
            if not self.micro_price_indicator.value:
                return
            self.log.info(
                f"micro_price: {self.micro_price_indicator.value:.4f}, bookl1: {bookl1.mid:.4f}"
            )
