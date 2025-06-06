from collections import defaultdict
from typing import Optional
from nexustrader.schema import BookL1, BookL2, Kline, Trade
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.constants import KlineInterval


class Indicator:
    def __init__(
        self,
        params: dict | None = None,
        name: str | None = None,
        warmup_period: int | None = None,
        warmup_interval: KlineInterval | None = None,
    ):
        self.name = name or type(self).__name__
        self.params = params
        self.warmup_period = warmup_period
        self.warmup_interval = warmup_interval
        self._is_warmed_up = False
        self._warmup_data_count = 0

    def handle_bookl1(self, bookl1: BookL1):
        raise NotImplementedError

    def handle_bookl2(self, bookl2: BookL2):
        raise NotImplementedError

    def handle_kline(self, kline: Kline):
        raise NotImplementedError

    def handle_trade(self, trade: Trade):
        raise NotImplementedError

    @property
    def requires_warmup(self) -> bool:
        """Check if this indicator requires warmup."""
        return self.warmup_period is not None and self.warmup_interval is not None

    @property
    def is_warmed_up(self) -> bool:
        """Check if the indicator has completed its warmup period."""
        if not self.requires_warmup:
            return True
        return self._is_warmed_up

    def _process_warmup_kline(self, kline: Kline):
        """Process a kline during warmup period."""
        if not self.requires_warmup or self._is_warmed_up:
            return

        self._warmup_data_count += 1
        self.handle_kline(kline)

        if self._warmup_data_count >= self.warmup_period:
            self._is_warmed_up = True

    def reset_warmup(self):
        """Reset warmup state. Useful for backtesting or restarting indicators."""
        self._is_warmed_up = False
        self._warmup_data_count = 0


class IndicatorManager:
    def __init__(self, msgbus: MessageBus):
        self._bookl1_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._bookl2_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._kline_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._trade_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._warmup_pending: dict[str, list[Indicator]] = defaultdict(list)

        msgbus.subscribe(topic="bookl1", handler=self.on_bookl1)
        msgbus.subscribe(topic="bookl2", handler=self.on_bookl2)
        msgbus.subscribe(topic="kline", handler=self.on_kline)
        msgbus.subscribe(topic="trade", handler=self.on_trade)

    def add_bookl1_indicator(self, symbol: str, indicator: Indicator):
        self._bookl1_indicators[symbol].append(indicator)

    def add_bookl2_indicator(self, symbol: str, indicator: Indicator):
        self._bookl2_indicators[symbol].append(indicator)

    def add_kline_indicator(self, symbol: str, indicator: Indicator):
        if indicator.requires_warmup:
            self._warmup_pending[symbol].append(indicator)
        else:
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
        symbol = kline.symbol
        for indicator in self._kline_indicators[symbol]:
            indicator.handle_kline(kline)

        # Process warmup indicators and check if they're ready
        warmup_indicators = self._warmup_pending[symbol][:]
        for indicator in warmup_indicators:
            indicator._process_warmup_kline(kline)
            if indicator.is_warmed_up:
                self._warmup_pending[symbol].remove(indicator)
                self._kline_indicators[symbol].append(indicator)

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

    def get_warmup_requirements(
        self,
    ) -> dict[str, list[tuple[Indicator, int, KlineInterval]]]:
        """Get warmup requirements for all pending indicators by symbol."""
        requirements = defaultdict(list)
        for symbol, indicators in self._warmup_pending.items():
            for indicator in indicators:
                if indicator.requires_warmup:
                    requirements[symbol].append(
                        (indicator, indicator.warmup_period, indicator.warmup_interval)
                    )
        return dict(requirements)

    def has_warmup_pending(self, symbol: str = None) -> bool:
        """Check if there are indicators pending warmup."""
        if symbol:
            return len(self._warmup_pending[symbol]) > 0
        return any(len(indicators) > 0 for indicators in self._warmup_pending.values())

    def warmup_pending_symbols(self) -> list[str]:
        """Get list of symbols with indicators pending warmup."""
        return [
            symbol for symbol, indicators in self._warmup_pending.items() if indicators
        ]
