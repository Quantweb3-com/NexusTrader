"""
ExchangeManager for the Bybit TradeFi (MT5) connector.

Unlike all other ExchangeManager implementations this class does NOT use
ccxt.  Markets are loaded from the MT5 terminal after a successful login
(see ``BybitTradeFiPrivateConnector.connect()``).
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, Dict

from nexustrader.constants import AccountType, ExchangeType
from nexustrader.core.nautilius_core import Logger
from nexustrader.exchange.bybit_tradfi.constants import BybitTradeFiAccountType
from nexustrader.exchange.bybit_tradfi.schema import BybitTradeFiMarket
from nexustrader.schema import InstrumentId


class BybitTradeFiExchangeManager:
    """
    Manages MT5 symbol metadata for the Bybit TradeFi connector.

    Markets are populated lazily (after MT5 login) via ``load_markets_from_mt5()``.
    Until that point ``self.market`` and ``self.market_id`` are empty dicts which
    is intentional – no market data is needed during the build phase.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.exchange_id = ExchangeType.BYBIT_TRADFI
        self.is_testnet: bool = config.get("sandbox", False)

        # MT5 credentials stored for use in connect()
        self._login: int = config.get("login", 0)
        self._password: str = config.get("password", "")
        self._server: str = config.get("server", "")
        self._terminal_path: str | None = config.get("path", None)

        # Shared by EMS / OMS / Connectors
        self.market: Dict[str, BybitTradeFiMarket] = {}
        self.market_id: Dict[str, str] = {}  # mt5_symbol → nexus_symbol

        # Single-threaded executor ensures all MT5 calls run from the same thread
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="mt5_worker"
        )

        self._log = Logger(name=type(self).__name__)

    # ------------------------------------------------------------------
    # Market loading (called after MT5 is connected)
    # ------------------------------------------------------------------

    def load_markets(self) -> None:
        """No-op: markets are loaded after MT5 login via load_markets_from_mt5()."""
        pass

    def load_markets_from_mt5(self) -> None:
        """
        Populate ``self.market`` and ``self.market_id`` from the connected MT5 terminal.

        This must be called from the MT5 worker thread (i.e. inside a task
        submitted to ``self._executor``).
        """
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        mt5 = get_mt5()
        symbols = mt5.symbols_get()
        if symbols is None:
            self._log.warning("mt5.symbols_get() returned None – no markets loaded")
            return

        loaded = 0
        for sym in symbols:
            if not sym.visible:
                continue  # hidden symbols are not tradeable
            try:
                nexus_symbol = self._build_nexus_symbol(sym.name)
                base, quote = self._parse_base_quote(sym.name, sym)

                # price precision: digits → step size (e.g. 5 digits → 0.00001)
                price_step = 10 ** (-sym.digits) if sym.digits > 0 else 1.0

                market = BybitTradeFiMarket(
                    mt5_symbol=sym.name,
                    nexus_symbol=nexus_symbol,
                    base=base,
                    quote=quote,
                    price_precision=price_step,
                    volume_min=sym.volume_min,
                    volume_step=sym.volume_step,
                    contract_size=sym.trade_contract_size,
                )

                self.market[nexus_symbol] = market
                self.market_id[sym.name] = nexus_symbol
                loaded += 1
            except Exception as exc:
                self._log.debug(f"Skipping symbol {sym.name}: {exc}")

        self._log.info(f"MT5 markets loaded: {loaded} symbols")

    # ------------------------------------------------------------------
    # Symbol helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_nexus_symbol(mt5_symbol: str) -> str:
        """
        Convert an MT5 symbol name to the NexusTrader symbol format.

        Leading ``#`` / ``.`` prefixes are stripped (broker decoration).
        Internal dots are replaced with ``_`` so that the NexusTrader
        ``symbol.EXCHANGE`` convention is not broken.

        Examples
        --------
        "EURUSD"   → "EURUSD.BYBIT_TRADFI"
        "#AAPL"    → "AAPL.BYBIT_TRADFI"
        "XAUUSD.s" → "XAUUSD_s.BYBIT_TRADFI"
        "TSLA.s"   → "TSLA_s.BYBIT_TRADFI"
        """
        clean = mt5_symbol.lstrip("#").lstrip(".")
        clean = clean.replace(".", "_")
        return f"{clean}.BYBIT_TRADFI"

    @staticmethod
    def _parse_base_quote(mt5_symbol: str, sym_info: Any) -> tuple[str, str]:
        """
        Derive base / quote from an MT5 SymbolInfo object.

        MT5 exposes ``currency_base`` and ``currency_profit`` which are the
        most reliable source.  Fall back to a naive 3-char split for symbols
        that lack those fields.
        """
        base = getattr(sym_info, "currency_base", None)
        quote = getattr(sym_info, "currency_profit", None)
        if base and quote:
            return base, quote

        # Fallback: try to split the clean name at known positions
        clean = mt5_symbol.lstrip("#").lstrip(".")
        if len(clean) == 6:
            return clean[:3], clean[3:]
        # Cannot determine – use full symbol as base, empty quote
        return clean, ""

    # ------------------------------------------------------------------
    # Interface required by Engine / Factory (stubs – MT5 has no ccxt)
    # ------------------------------------------------------------------

    def validate_public_connector_config(
        self, account_type: AccountType, basic_config: Any
    ) -> None:
        if not isinstance(account_type, BybitTradeFiAccountType):
            from nexustrader.error import EngineBuildError

            raise EngineBuildError(
                f"Expected BybitTradeFiAccountType, got {type(account_type).__name__}."
            )

    def validate_public_connector_limits(
        self, existing_connectors: Dict[AccountType, Any]
    ) -> None:
        pass  # MT5 has no connector-level limits

    def instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> BybitTradeFiAccountType:
        return (
            BybitTradeFiAccountType.DEMO
            if self.is_testnet
            else BybitTradeFiAccountType.LIVE
        )

    # ------------------------------------------------------------------
    # Compatibility helpers used by ExchangeManager base helpers
    # ------------------------------------------------------------------

    def linear(self, **_):
        return []

    def inverse(self, **_):
        return []

    def spot(self, base=None, quote=None, exclude=None):
        result = []
        for symbol, mkt in self.market.items():
            if not mkt.active:
                continue
            if base is not None and mkt.base != base:
                continue
            if quote is not None and mkt.quote != quote:
                continue
            if exclude and symbol in exclude:
                continue
            result.append(symbol)
        return result

    def future(self, **_):
        return []

    def option(self, **_):
        return []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Shut down the MT5 worker thread pool."""
        self._executor.shutdown(wait=False)
