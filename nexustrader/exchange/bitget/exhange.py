import ccxt
import msgspec
from typing import Any, Dict
from nexustrader.base import ExchangeManager
from nexustrader.constants import ExchangeType, AccountType, ConfigType
from nexustrader.exchange.bitget.schema import BitgetMarket
from nexustrader.schema import InstrumentId


class BitgetExchangeManager(ExchangeManager):
    api: ccxt.bitget
    market: Dict[str, BitgetMarket]
    market_id: Dict[str, str]

    def __init__(self, config: ConfigType | None = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "bitget")
        super().__init__(config)

    def load_markets(self):
        market = self.api.load_markets()
        for symbol, mkt in market.items():
            try:
                mkt_json = msgspec.json.encode(mkt)
                mkt = msgspec.json.decode(mkt_json, type=BitgetMarket)

                if (
                    mkt.spot or mkt.linear or mkt.inverse or mkt.future
                ) and not mkt.option:
                    symbol = self._parse_symbol(mkt, exchange_suffix="BITGET")
                    mkt.symbol = symbol
                    self.market[symbol] = mkt
                    if mkt.type.value == "spot":
                        self.market_id[f"{mkt.id}_spot"] = symbol
                    elif mkt.linear:
                        self.market_id[f"{mkt.id}_linear"] = symbol
                    elif mkt.inverse:
                        self.market_id[f"{mkt.id}_inverse"] = symbol

            except Exception as e:
                print(f"Error: {e}, {symbol}, {mkt}")
                continue

    def validate_public_connector_config(
        self, account_type: AccountType, basic_config: Any
    ) -> None:
        """Validate public connector configuration for this exchange"""
        pass


    def validate_public_connector_limits(
        self, existing_connectors: Dict[AccountType, Any]
    ) -> None:
        """Validate public connector limits for this exchange"""
        pass


    def instrument_id_to_account_type(self, instrument_id: InstrumentId) -> AccountType:
        """Convert an instrument ID to the appropriate account type for this exchange"""
        pass

def main():
    # Example usage
    exchange = BitgetExchangeManager(config={
        "sandbox": True,
    })
    print(exchange.market)

if __name__ == "__main__":
    main()
