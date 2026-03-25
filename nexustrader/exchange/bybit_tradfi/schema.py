"""
Data structures specific to the Bybit TradeFi (MT5) connector.

``BybitTradeFiMarket`` is intentionally kept as a plain Python class (not a
msgspec Struct) because MT5 symbol metadata does not map cleanly to the ccxt
BaseMarket schema, and we need mutable precision/limits fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _Precision:
    price: float   # e.g. 0.00001 (5 digits after decimal)
    amount: float  # e.g. 0.01


@dataclass
class _LimitMinMax:
    min: float | None = None
    max: float | None = None


@dataclass
class _Limits:
    amount: _LimitMinMax = field(default_factory=_LimitMinMax)
    price: _LimitMinMax = field(default_factory=_LimitMinMax)
    cost: _LimitMinMax = field(default_factory=_LimitMinMax)


class BybitTradeFiMarket:
    """
    Minimal market descriptor for an MT5 CFD/FX symbol.

    Attributes that the NexusTrader framework reads from a market object
    are all present here; everything else is stubbed to sensible defaults.
    """

    __slots__ = (
        "id",         # MT5 symbol name (e.g. "EURUSD")
        "symbol",     # NexusTrader symbol (e.g. "EURUSD.BYBIT_TRADFI")
        "base",       # base currency / asset  (e.g. "EUR")
        "quote",      # quote currency          (e.g. "USD")
        "precision",  # _Precision instance
        "limits",     # _Limits instance
        "active",
        # Instrument-type flags expected by ExchangeManager helpers
        "spot",
        "linear",
        "inverse",
        "swap",
        "future",
        "option",
        "margin",
        "contract",
        "taker",
        "maker",
        "contractSize",
    )

    def __init__(
        self,
        mt5_symbol: str,
        nexus_symbol: str,
        base: str,
        quote: str,
        price_precision: float,
        volume_min: float,
        volume_step: float,
        contract_size: float = 1.0,
        taker: float = 0.0,
        maker: float = 0.0,
    ) -> None:
        self.id = mt5_symbol
        self.symbol = nexus_symbol
        self.base = base
        self.quote = quote

        self.precision = _Precision(
            price=price_precision,
            amount=volume_step,
        )
        self.limits = _Limits(
            amount=_LimitMinMax(min=volume_min),
        )
        self.active = True

        # All MT5 CFD/FX instruments are treated as "spot-like" in NexusTrader
        self.spot = True
        self.linear = False
        self.inverse = False
        self.swap = False
        self.future = False
        self.option = False
        self.margin = False
        self.contract = False

        self.taker = taker
        self.maker = maker
        self.contractSize = contract_size

    def __repr__(self) -> str:
        return (
            f"BybitTradeFiMarket(id={self.id!r}, symbol={self.symbol!r}, "
            f"base={self.base!r}, quote={self.quote!r})"
        )
