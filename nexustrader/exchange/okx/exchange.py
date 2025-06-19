from typing import Any, Dict, List
from nexustrader.base import ExchangeManager
import ccxt
import msgspec
from nexustrader.exchange.okx.schema import OkxMarket
from nexustrader.exchange.okx.constants import OkxAccountType
from nexustrader.constants import AccountType
from nexustrader.schema import InstrumentId
from nexustrader.error import EngineBuildError


class OkxExchangeManager(ExchangeManager):
    api: ccxt.okx
    market: Dict[str, OkxMarket]  # symbol -> okx market
    market_id: Dict[str, str]  # symbol -> exchange symbol id

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "okx")
        super().__init__(config)
        self.passphrase = config.get("password", None)
        self._public_conn_account_type = None

    def load_markets(self):
        market = self.api.load_markets()
        for symbol, mkt in market.items():
            try:
                mkt_json = msgspec.json.encode(mkt)
                mkt = msgspec.json.decode(mkt_json, type=OkxMarket)

                if (
                    mkt.spot or mkt.linear or mkt.inverse or mkt.future
                ) and not mkt.option:
                    symbol = self._parse_symbol(mkt, exchange_suffix="OKX")
                    mkt.symbol = symbol
                    self.market[symbol] = mkt
                    self.market_id[mkt.id] = (
                        symbol  # since okx symbol id is identical, no need to distinguish spot, linear, inverse
                    )

            except Exception as e:
                print(f"Error: {e}, {symbol}, {mkt}")
                continue

    def option(
        self,
        base: str | None = None,
        quote: str | None = None,
        exclude: List[str] | None = None,
    ) -> List[str]:
        raise NotImplementedError("Option is not supported for OKX")

    def validate_public_connector_config(
        self, account_type: AccountType, basic_config: Any
    ) -> None:
        """Validate public connector configuration for OKX exchange"""
        if not isinstance(account_type, OkxAccountType):
            raise EngineBuildError(f"Expected OkxAccountType, got {type(account_type)}")

        if basic_config.testnet != account_type.is_testnet:
            raise EngineBuildError(
                f"The `testnet` setting of OKX is not consistent with the public connector's account type `{account_type}`."
            )

    def validate_public_connector_limits(
        self, existing_connectors: Dict[AccountType, Any]
    ) -> None:
        """Validate public connector limits for OKX exchange"""
        okx_connectors = [
            c
            for c in existing_connectors.values()
            if hasattr(c, "account_type") and isinstance(c.account_type, OkxAccountType)
        ]
        if len(okx_connectors) > 1:
            raise EngineBuildError(
                "Only one public connector is supported for OKX, please remove the extra public connector config."
            )

    def set_public_connector_account_type(self, account_type: OkxAccountType) -> None:
        """Set the account type for public connector configuration"""
        self._public_conn_account_type = account_type

    def instrument_id_to_account_type(self, instrument_id: InstrumentId) -> AccountType:
        """Convert an instrument ID to the appropriate account type for OKX exchange"""
        if self._public_conn_account_type is None:
            raise EngineBuildError(
                "Public connector account type not set for OKX. Please add OKX in public_conn_config."
            )
        return self._public_conn_account_type
