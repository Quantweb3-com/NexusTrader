import warnings
import ccxt
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from nexustrader.schema import BaseMarket, InstrumentId
from nexustrader.constants import ExchangeType, AccountType
from nexustrader.core.nautilius_core import Logger


class ExchangeManager(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = config.get("apiKey", None)
        self.secret = config.get("secret", None)
        self.exchange_id = ExchangeType(config["exchange_id"])
        self.api = self._init_exchange()
        self._log = Logger(name=type(self).__name__)
        self.is_testnet = config.get("sandbox", False)
        self.market: Dict[str, BaseMarket] = {}
        self.market_id: Dict[str, str] = {}

        if not self.api_key or not self.secret:
            warnings.warn(
                "API Key and Secret not provided, So some features related to trading will not work"
            )
        self.load_markets()

    def _init_exchange(self) -> ccxt.Exchange:
        """
        Initialize the exchange
        """
        try:
            exchange_class = getattr(ccxt, self.config["exchange_id"])
        except AttributeError:
            raise AttributeError(
                f"Exchange {self.config['exchange_id']} is not supported"
            )

        api = exchange_class(self.config)
        api.set_sandbox_mode(
            self.config.get("sandbox", False)
        )  # Set sandbox mode if demo trade is enabled
        return api

    def _parse_symbol(self, mkt: BaseMarket, exchange_suffix: str) -> str:
        """
        Parse the symbol for the exchange
        """
        if mkt.spot:
            return f"{mkt.base}{mkt.quote}.{exchange_suffix}"
        elif mkt.option:
            symbol = mkt.symbol
            parts = symbol.split("-")
            expiry = parts[1]
            strike = parts[2]
            option_type = parts[3]
            return f"{mkt.base}{mkt.quote}-{expiry}-{strike}-{option_type}.{exchange_suffix}"
        elif mkt.future:
            symbol = mkt.symbol
            expiry_suffix = symbol.split("-")[-1]
            return f"{mkt.base}{mkt.quote}-{expiry_suffix}.{exchange_suffix}"
        elif mkt.linear:
            return f"{mkt.base}{mkt.quote}-PERP.{exchange_suffix}"
        elif mkt.inverse:
            return f"{mkt.base}{mkt.quote}-PERP.{exchange_suffix}"

    @abstractmethod
    def load_markets(self):
        pass

    def linear(
        self,
        base: str | None = None,
        quote: str | None = None,
        exclude: List[str] | None = None,
    ) -> List[str]:
        symbols = []
        for symbol, market in self.market.items():
            if not (
                market.linear
                and market.active
                and not market.future
                and not market.option
            ):
                continue

            base_match = base is None or market.base == base
            quote_match = quote is None or market.quote == quote

            if (
                base_match
                and quote_match
                and (exclude is None or symbol not in exclude)
            ):
                symbols.append(symbol)
        return symbols

    def inverse(
        self,
        base: str | None = None,
        quote: str | None = None,
        exclude: List[str] | None = None,
    ) -> List[str]:
        symbols = []
        for symbol, market in self.market.items():
            if not (
                market.inverse
                and market.active
                and not market.future
                and not market.option
            ):
                continue

            base_match = base is None or market.base == base
            quote_match = quote is None or market.quote == quote

            if (
                base_match
                and quote_match
                and (exclude is None or symbol not in exclude)
            ):
                symbols.append(symbol)
        return symbols

    def spot(
        self,
        base: str | None = None,
        quote: str | None = None,
        exclude: List[str] | None = None,
    ) -> List[str]:
        symbols = []
        for symbol, market in self.market.items():
            if not (market.spot and market.active and not market.option):
                continue

            base_match = base is None or market.base == base
            quote_match = quote is None or market.quote == quote

            if (
                base_match
                and quote_match
                and (exclude is None or symbol not in exclude)
            ):
                symbols.append(symbol)
        return symbols

    def future(
        self,
        base: str | None = None,
        quote: str | None = None,
        exclude: List[str] | None = None,
    ) -> List[str]:
        symbols = []
        for symbol, market in self.market.items():
            if not (market.future and market.active and not market.option):
                continue

            base_match = base is None or market.base == base
            quote_match = quote is None or market.quote == quote

            if (
                base_match
                and quote_match
                and (exclude is None or symbol not in exclude)
            ):
                symbols.append(symbol)
        return symbols

    def option(
        self,
        base: str | None = None,
        quote: str | None = None,
        exclude: List[str] | None = None,
    ) -> List[str]:
        symbols = []
        for symbol, market in self.market.items():
            if not market.active:
                continue

            base_match = base is None or market.base == base
            quote_match = quote is None or market.quote == quote

            if (
                base_match
                and quote_match
                and (exclude is None or symbol not in exclude)
            ):
                symbols.append(symbol)
        return symbols

    @abstractmethod
    def validate_public_connector_config(
        self, account_type: AccountType, basic_config: Any
    ) -> None:
        """Validate public connector configuration for this exchange"""
        pass

    @abstractmethod
    def validate_public_connector_limits(
        self, existing_connectors: Dict[AccountType, Any]
    ) -> None:
        """Validate public connector limits for this exchange"""
        pass

    @abstractmethod
    def instrument_id_to_account_type(self, instrument_id: InstrumentId) -> AccountType:
        """Convert an instrument ID to the appropriate account type for this exchange"""
        pass
