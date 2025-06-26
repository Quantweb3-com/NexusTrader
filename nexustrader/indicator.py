from collections import defaultdict
from typing import Dict
import re
from nexustrader.schema import (
    BookL1,
    BookL2,
    Kline,
    Trade,
    IndexPrice,
    FundingRate,
    MarkPrice,
)
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.constants import KlineInterval


def _validate_indicator_name(name: str) -> bool:
    """
    Validate indicator name for use with getattr access pattern.

    Rules:
    - Must be a valid Python identifier
    - Cannot start with underscore (reserved for private attributes)
    - Cannot be a Python keyword
    - Must contain only alphanumeric characters and underscores
    - Must start with a letter or underscore (but not underscore per rule above)

    Args:
        name: The indicator name to validate

    Returns:
        bool: True if name is valid, False otherwise
    """
    import keyword

    if not name:
        return False

    # Check if it's a valid Python identifier
    if not name.isidentifier():
        return False

    # Cannot start with underscore (reserved for internal use)
    if name.startswith("_"):
        return False

    # Cannot be a Python keyword
    if keyword.iskeyword(name):
        return False

    # Additional check: must match pattern for safe attribute access
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", name):
        return False

    return True


class Indicator:
    def __init__(
        self,
        params: dict | None = None,
        name: str | None = None,
        warmup_period: int | None = None,
        warmup_interval: KlineInterval | None = None,
    ):
        indicator_name = name or type(self).__name__

        # Validate the indicator name for getattr access
        if not _validate_indicator_name(indicator_name):
            raise ValueError(
                f"Invalid indicator name '{indicator_name}'. "
                f"Name must be a valid Python identifier, cannot start with underscore, "
                f"cannot be a Python keyword, and must contain only alphanumeric characters and underscores."
            )

        self.name = indicator_name
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

    def handle_index_price(self, index_price: IndexPrice):
        """Handle index price updates if applicable."""
        raise NotImplementedError

    def handle_funding_rate(self, funding_rate: FundingRate):
        """Handle funding rate updates if applicable."""
        raise NotImplementedError

    def handle_mark_price(self, mark_price: MarkPrice):
        """Handle mark price updates if applicable."""
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

    @property
    def value(self):
        """Get the current value of the indicator."""
        raise NotImplementedError(
            "Subclasses must implement the 'value' property to return the indicator's value."
        )


class IndicatorManager:
    def __init__(self, msgbus: MessageBus):
        self._bookl1_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._bookl2_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._kline_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._trade_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._index_price_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._funding_rate_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._mark_price_indicators: dict[str, list[Indicator]] = defaultdict(list)
        self._warmup_pending: dict[str, list[Indicator]] = defaultdict(list)

        msgbus.subscribe(topic="bookl1", handler=self.on_bookl1)
        msgbus.subscribe(topic="bookl2", handler=self.on_bookl2)
        msgbus.subscribe(topic="kline", handler=self.on_kline)
        msgbus.subscribe(topic="trade", handler=self.on_trade)
        msgbus.subscribe(topic="index_price", handler=self.on_index_price)
        msgbus.subscribe(topic="funding_rate", handler=self.on_funding_rate)
        msgbus.subscribe(topic="mark_price", handler=self.on_mark_price)

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

    def add_index_price_indicator(self, symbol: str, indicator: Indicator):
        self._index_price_indicators[symbol].append(indicator)

    def add_funding_rate_indicator(self, symbol: str, indicator: Indicator):
        self._funding_rate_indicators[symbol].append(indicator)

    def add_mark_price_indicator(self, symbol: str, indicator: Indicator):
        self._mark_price_indicators[symbol].append(indicator)

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

    def on_index_price(self, index_price: IndexPrice):
        symbol = index_price.symbol
        for indicator in self._index_price_indicators[symbol]:
            indicator.handle_index_price(index_price)

    def on_funding_rate(self, funding_rate: FundingRate):
        symbol = funding_rate.symbol
        for indicator in self._funding_rate_indicators[symbol]:
            indicator.handle_funding_rate(funding_rate)

    def on_mark_price(self, mark_price: MarkPrice):
        symbol = mark_price.symbol
        for indicator in self._mark_price_indicators[symbol]:
            indicator.handle_mark_price(mark_price)

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

    @property
    def index_price_subscribed_symbols(self):
        return list(self._index_price_indicators.keys())

    @property
    def funding_rate_subscribed_symbols(self):
        return list(self._funding_rate_indicators.keys())

    @property
    def mark_price_subscribed_symbols(self):
        return list(self._mark_price_indicators.keys())

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


class IndicatorContainer:
    """Container for accessing indicators by symbol."""

    def __init__(self):
        self._indicators: Dict[str, Indicator] = {}

    def __getitem__(self, symbol: str):
        """Get indicator for specific symbol."""
        return self._indicators.get(symbol)

    def __setitem__(self, symbol: str, indicator: Indicator):
        """Set indicator for specific symbol."""
        self._indicators[symbol] = indicator

    def __contains__(self, symbol: str):
        """Check if symbol has an indicator."""
        return symbol in self._indicators

    def get(self, symbol: str, default=None):
        """Get indicator for symbol with default value."""
        return self._indicators.get(symbol, default)

    def symbols(self):
        """Get all symbols with indicators."""
        return list(self._indicators.keys())


class IndicatorProxy:
    """Proxy for accessing per-symbol indicator instances."""

    def __init__(self):
        self._containers: Dict[str, IndicatorContainer] = {}

    def __getattr__(self, name):
        """Get indicator container by name."""
        if name not in self._containers:
            self._containers[name] = IndicatorContainer()
        return self._containers[name]

    def register_indicator(self, name: str, symbol: str, indicator: Indicator):
        """Register an indicator instance for a specific symbol."""
        container = getattr(self, name)
        container[symbol] = indicator
