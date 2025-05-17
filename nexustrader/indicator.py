from collections import defaultdict
from nexustrader.schema import BookL1, BookL2, Kline, Trade
from nexustrader.core.nautilius_core import MessageBus


class Indicator:
    def __init__(self, params: dict | None = None, name: str | None = None):
        self.name = name or type(self).__name__
        self.params = params

    def handle_bookl1(self, bookl1: BookL1):
        raise NotImplementedError

    def handle_bookl2(self, bookl2: BookL2):
        raise NotImplementedError

    def handle_kline(self, kline: Kline):
        raise NotImplementedError

    def handle_trade(self, trade: Trade):
        raise NotImplementedError


class IndicatorManager:
    def __init__(self, msgbus: MessageBus):
        self._bookl1_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._bookl2_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._kline_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._trade_indicators: dict[str, list[Indicator]] = defaultdict(list)

        msgbus.subscribe(topic="bookl1", handler=self.on_bookl1)
        msgbus.subscribe(topic="bookl2", handler=self.on_bookl2)
        msgbus.subscribe(topic="kline", handler=self.on_kline)
        msgbus.subscribe(topic="trade", handler=self.on_trade)

    def add_bookl1_indicator(self, symbol: str, indicator: Indicator):
        self._bookl1_indicators[symbol].append(indicator)

    def add_bookl2_indicator(self, symbol: str, indicator: Indicator):
        self._bookl2_indicators[symbol].append(indicator)

    def add_kline_indicator(self, symbol: str, indicator: Indicator):
        self._kline_indicators[symbol].append(indicator)

    def add_trade_indicator(self, symbol: str, indicator: Indicator):
        self._trade_indicators[symbol].append(indicator)

    def on_bookl1(self, bookl1: BookL1):
        symbol = bookl1.symbol
        for indicator in self._bookl1_indicators[symbol]:
            indicator.handle_bookl1(bookl1)

    def on_bookl2(self, bookl2: BookL2):
        symbol = bookl2.symbol
        for indicator in self._bookl2_indicators[symbol]:
            indicator.handle_bookl2(bookl2)

    def on_kline(self, kline: Kline):
        if not kline.confirm:
            return

        symbol = kline.symbol
        for indicator in self._kline_indicators[symbol]:
            indicator.handle_kline(kline)

    def on_trade(self, trade: Trade):
        symbol = trade.symbol
        for indicator in self._trade_indicators[symbol]:
            indicator.handle_trade(trade)

    @property
    def bookl1_subscribed_symbols(self):
        return list(self._bookl1_indicators.keys())

    @property
    def bookl2_subscribed_symbols(self):
        return list(self._bookl2_indicators.keys())
    
    @property
    def kline_subscribed_symbols(self):
        return list(self._kline_indicators.keys())

    @property
    def trade_subscribed_symbols(self):
        return list(self._trade_indicators.keys())
