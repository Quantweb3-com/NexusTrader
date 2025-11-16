import ccxt
import msgspec
from typing import Any, Dict
from nexustrader.base import ExchangeManager
from nexustrader.config import BasicConfig
from nexustrader.constants import ConfigType

from nexustrader.constants import AccountType
from nexustrader.schema import InstrumentId
from nexustrader.error import EngineBuildError
from nexustrader.exchange.hyperliquid.schema import HyperLiquidMarket
from nexustrader.exchange.hyperliquid.constants import HyperLiquidAccountType


class HyperLiquidExchangeManager(ExchangeManager):
    api: ccxt.hyperliquid
    market: Dict[str, HyperLiquidMarket]
    market_id: Dict[str, str]

    def __init__(self, config: ConfigType | None = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "hyperliquid")

        config["walletAddress"] = config.get("apiKey", None)
        config["privateKey"] = config.get("secret", None)

        super().__init__(config)
        self._public_conn_account_type = None

    def load_markets(self):
        market = self.api.load_markets()
        mapping = self.api.options["spotCurrencyMapping"]
        for symbol, mkt in market.items():
            try:
                mkt_json = msgspec.json.encode(mkt)
                mkt = msgspec.json.decode(mkt_json, type=HyperLiquidMarket)

                if (
                    mkt.spot or mkt.linear or mkt.inverse or mkt.future
                ) and not mkt.option:
                    if mkt.spot and mkt.base in mapping:
                        continue

                    symbol = self._parse_symbol(mkt, exchange_suffix="HYPERLIQUID")
                    mkt.symbol = symbol
                    self.market[symbol] = mkt
                    self.market_id[mkt.baseName if mkt.swap else mkt.id] = symbol

            except msgspec.ValidationError as ve:
                self._log.warning(f"Symbol Format Error: {ve}, {symbol}, {mkt}")
                continue

    def validate_public_connector_config(
        self, account_type: AccountType, basic_config: BasicConfig | None = None
    ) -> None:
        if not isinstance(account_type, HyperLiquidAccountType):
            raise EngineBuildError(
                f"Expected HyperLiquidAccountType, got {type(account_type)}"
            )

        if basic_config.testnet != account_type.is_testnet:
            raise EngineBuildError(
                f"The `testnet` setting of HyperLiquid is not consistent with the public connector's account type `{account_type}`."
            )

    def validate_public_connector_limits(
        self, existing_connectors: Dict[AccountType, Any]
    ) -> None:
        hyperliquid_connectors = [
            c
            for c in existing_connectors.values()
            if hasattr(c, "account_type")
            and isinstance(c.account_type, HyperLiquidAccountType)
        ]
        if len(hyperliquid_connectors) > 1:
            raise EngineBuildError(
                "Only one public connector is supported for HyperLiquid, please remove the extra public connector config."
            )

    def set_public_connector_account_type(
        self, account_type: HyperLiquidAccountType
    ) -> None:
        """Set the account type for public connector configuration"""
        self._public_conn_account_type = account_type

    def instrument_id_to_account_type(self, instrument_id: InstrumentId) -> AccountType:
        if self._public_conn_account_type is None:
            raise EngineBuildError(
                "Public connector account type not set for HyperLiquid. Please add HyperLiquid in public_conn_config."
            )
        return self._public_conn_account_type


def main():
    exchange_manager = HyperLiquidExchangeManager()
    print("Markets loaded:", exchange_manager.market)


if __name__ == "__main__":
    main()
