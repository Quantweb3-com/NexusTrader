import ccxt
import msgspec
from typing import Any, Dict
from nexustrader.base import ExchangeManager
from nexustrader.schema import InstrumentId
from nexustrader.error import EngineBuildError
from nexustrader.config import BasicConfig
from nexustrader.constants import AccountType, ConfigType
from nexustrader.exchange.bitget.schema import BitgetMarket
from nexustrader.exchange.bitget.constants import BitgetAccountType

class BitgetExchangeManager(ExchangeManager):
    api: ccxt.bitget
    market: Dict[str, BitgetMarket]
    market_id: Dict[str, str]

    def __init__(self, config: ConfigType | None = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "bitget")
        super().__init__(config)
        self.passphrase = config.get("password", None)

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
        self, account_type: AccountType, basic_config:  BasicConfig | None = None
    ) -> None:
        """Validate public connector configuration for this exchange"""
        if not isinstance(account_type, BitgetAccountType):
            raise EngineBuildError(f"Expected BitgetAccountType, got {type(account_type)}")

        if basic_config.testnet != account_type.is_testnet:
            raise EngineBuildError(
                f"The `testnet` setting of Bitget is not consistent with the public connector's account type `{account_type}`."
            )

    def validate_public_connector_limits(
        self, existing_connectors: Dict[AccountType, Any]
    ) -> None:
        """Validate public connector limits for this exchange"""
        bitget_connectors = [
            c
            for c in existing_connectors.values()
            if hasattr(c, "account_type") and isinstance(c.account_type, BitgetAccountType)
        ]
        if len(bitget_connectors) > 1:
            raise EngineBuildError(
                "Only one public connector is supported for Bitget, please remove the extra public connector config."
            )

    def set_public_connector_account_type(self, account_type: BitgetAccountType) -> None:
        """Set the account type for public connector configuration"""
        self._public_conn_account_type = account_type

    def instrument_id_to_account_type(self, instrument_id: InstrumentId) -> AccountType:
        """Convert an instrument ID to the appropriate account type for this exchange"""
        if self._public_conn_account_type is None:
            raise EngineBuildError(
                "Public connector account type not set for Bitget. Please add Bitget in public_conn_config."
            )
        return self._public_conn_account_type



def main():
    # Example usage
    exchange = BitgetExchangeManager(
        config={
            "sandbox": True,
        }
    )
    print(exchange.market)


if __name__ == "__main__":
    main()
