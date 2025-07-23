import ccxt
import msgspec
from typing import Any, Dict
from nexustrader.base import ExchangeManager
from nexustrader.exchange.hyperliquid.schema import HyperLiquidMarket
from nexustrader.constants import AccountType
from nexustrader.schema import InstrumentId


class HyperLiquidExchangeManager(ExchangeManager):
    api: ccxt.hyperliquid
    market: Dict[str, HyperLiquidMarket]
    market_id: Dict[str, str]

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "hyperliquid")
        super().__init__(config)

    def load_markets(self):
        market = self.api.load_markets()
        for symbol, mkt in market.items():
            try:
                mkt_json = msgspec.json.encode(mkt)
                mkt = msgspec.json.decode(mkt_json, type=HyperLiquidMarket)

                if (
                    mkt.spot or mkt.linear or mkt.inverse or mkt.future
                ) and not mkt.option:
                    symbol = self._parse_symbol(mkt, exchange_suffix="HYPERLIQUID")
                    mkt.symbol = symbol
                    self.market[symbol] = mkt
                    self.market_id[mkt.id] = symbol

            except Exception as e:
                print(f"Error: {e}, {symbol}, {mkt}")
                continue

    def validate_public_connector_config(
        self, account_type: AccountType, basic_config: Any
    ) -> None:
        """Validate public connector configuration for Hyperliquid"""
        # Hyperliquid doesn't require special validation for public connectors
        # All public data is accessible without authentication
        pass

    def validate_public_connector_limits(
        self, existing_connectors: Dict[AccountType, Any]
    ) -> None:
        """Validate public connector limits for Hyperliquid"""
        # Hyperliquid doesn't have strict limits on public connectors
        # Multiple public connectors can be created for different purposes
        pass

    def instrument_id_to_account_type(self, instrument_id: InstrumentId) -> AccountType:
        """Convert an instrument ID to the appropriate account type for Hyperliquid"""
        # Hyperliquid uses a unified account system
        # All instruments use the same account type
        from nexustrader.exchange.hyperliquid.constants import HyperLiquidAccountType
        if self.is_testnet:
            return HyperLiquidAccountType.TESTNET
        return HyperLiquidAccountType.MAINNET


if __name__ == "__main__":
    hpy = HyperLiquidExchangeManager()
    print(hpy.market)
    print(hpy.market_id)
