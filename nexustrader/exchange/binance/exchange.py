import ccxt
import msgspec
from typing import Any, Dict, List
from nexustrader.base import ExchangeManager
from nexustrader.exchange.binance.schema import BinanceMarket
from nexustrader.exchange.binance.constants import BinanceAccountType
from nexustrader.schema import InstrumentId
from nexustrader.constants import AccountType
from nexustrader.error import EngineBuildError


class BinanceExchangeManager(ExchangeManager):
    api: ccxt.binance
    market: Dict[str, BinanceMarket]
    market_id: Dict[str, str]

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "binance")
        super().__init__(config)

    def load_markets(self):
        market = self.api.load_markets()
        for symbol, mkt in market.items():
            try:
                mkt_json = msgspec.json.encode(mkt)
                mkt = msgspec.json.decode(mkt_json, type=BinanceMarket)

                if (
                    mkt.spot or mkt.linear or mkt.inverse or mkt.future
                ) and not mkt.option:
                    symbol = self._parse_symbol(mkt, exchange_suffix="BINANCE")
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

    def option(
        self,
        base: str | None = None,
        quote: str | None = None,
        exclude: List[str] | None = None,
    ) -> List[str]:
        raise NotImplementedError("Option is not supported for Binance")

    def validate_public_connector_config(
        self, account_type: AccountType, basic_config: Any
    ) -> None:
        """Validate public connector configuration for Binance exchange"""
        if not isinstance(account_type, BinanceAccountType):
            raise EngineBuildError(
                f"Expected BinanceAccountType, got {type(account_type)}"
            )

        if (
            account_type.is_isolated_margin_or_margin
            or account_type.is_portfolio_margin
        ):
            raise EngineBuildError(
                f"{account_type} is not supported for public connector."
            )

        if basic_config.testnet != account_type.is_testnet:
            raise EngineBuildError(
                f"The `testnet` setting of Binance is not consistent with the public connector's account type `{account_type}`."
            )

    def validate_public_connector_limits(
        self, existing_connectors: Dict[AccountType, Any]
    ) -> None:
        """Validate public connector limits for Binance exchange"""
        # Binance has no specific connector limits
        pass

    def instrument_id_to_account_type(self, instrument_id: InstrumentId) -> AccountType:
        """Convert an instrument ID to the appropriate account type for Binance exchange"""
        if instrument_id.is_spot:
            return (
                BinanceAccountType.SPOT_TESTNET
                if self.is_testnet
                else BinanceAccountType.SPOT
            )
        elif instrument_id.is_linear:
            return (
                BinanceAccountType.USD_M_FUTURE_TESTNET
                if self.is_testnet
                else BinanceAccountType.USD_M_FUTURE
            )
        elif instrument_id.is_inverse:
            return (
                BinanceAccountType.COIN_M_FUTURE_TESTNET
                if self.is_testnet
                else BinanceAccountType.COIN_M_FUTURE
            )
        else:
            raise ValueError(f"Unsupported instrument type: {instrument_id.type}")


def check():
    bnc = BinanceExchangeManager()
    market = bnc.market
    market_id = bnc.market_id  # noqa: F841

    for symbol, mkt in market.items():
        instrument_id = InstrumentId.from_str(symbol)
        if mkt.subType:
            assert instrument_id.type == mkt.subType
        else:
            assert instrument_id.type == mkt.type

    print("All checks passed")


if __name__ == "__main__":
    check()
