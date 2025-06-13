import ccxt
import msgspec
from typing import Any, Dict
from nexustrader.base import ExchangeManager
from nexustrader.exchange.bybit.schema import BybitMarket
from nexustrader.exchange.bybit.constants import BybitAccountType
from nexustrader.constants import AccountType
from nexustrader.schema import InstrumentId
from nexustrader.error import EngineBuildError


class BybitExchangeManager(ExchangeManager):
    api: ccxt.bybit
    market = Dict[str, BybitMarket]
    market_id = Dict[str, str]

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "bybit")
        super().__init__(config)

    def load_markets(self):
        market = self.api.load_markets()
        for symbol, mkt in market.items():
            try:
                mkt_json = msgspec.json.encode(mkt)
                mkt = msgspec.json.decode(mkt_json, type=BybitMarket)
                if mkt.spot or mkt.linear or mkt.inverse or mkt.future:
                    symbol = self._parse_symbol(mkt, exchange_suffix="BYBIT")
                    mkt.symbol = symbol
                    self.market[symbol] = mkt
                    if mkt.type.value == "spot":
                        self.market_id[f"{mkt.id}_spot"] = symbol
                    elif mkt.option:
                        self.market_id[f"{mkt.id}_option"] = symbol
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
        """Validate public connector configuration for Bybit exchange"""
        if not isinstance(account_type, BybitAccountType):
            raise EngineBuildError(
                f"Expected BybitAccountType, got {type(account_type)}"
            )

        if (
            account_type == BybitAccountType.UNIFIED
            or account_type == BybitAccountType.UNIFIED_TESTNET
        ):
            raise EngineBuildError(
                f"{account_type} is not supported for public connector."
            )

        if basic_config.testnet != account_type.is_testnet:
            raise EngineBuildError(
                f"The `testnet` setting of Bybit is not consistent with the public connector's account type `{account_type}`."
            )

    def validate_public_connector_limits(
        self, existing_connectors: Dict[AccountType, Any]
    ) -> None:
        """Validate public connector limits for Bybit exchange"""
        # Bybit has no specific connector limits
        pass

    def instrument_id_to_account_type(self, instrument_id: InstrumentId) -> AccountType:
        """Convert an instrument ID to the appropriate account type for Bybit exchange"""
        if instrument_id.is_spot:
            return (
                BybitAccountType.SPOT_TESTNET
                if self.is_testnet
                else BybitAccountType.SPOT
            )
        elif instrument_id.is_linear:
            return (
                BybitAccountType.LINEAR_TESTNET
                if self.is_testnet
                else BybitAccountType.LINEAR
            )
        elif instrument_id.is_inverse:
            return (
                BybitAccountType.INVERSE_TESTNET
                if self.is_testnet
                else BybitAccountType.INVERSE
            )
        else:
            raise ValueError(f"Unsupported instrument type: {instrument_id.type}")


if __name__ == "__main__":
    exchange = BybitExchangeManager()
    exchange.load_markets()
    print(exchange.market)
    print(exchange.market_id)
