from typing import Any, Dict
from nexustrader.base import ExchangeManager
import ccxt
import msgspec
from nexustrader.config import BasicConfig
from nexustrader.exchange.kucoin.schema import KucoinSpotMarket, KucoinFuturesMarket
from nexustrader.exchange.kucoin.constants import KucoinAccountType

# from nexustrader.exchange.kucoin.constants import KucoinAccountType
from nexustrader.constants import AccountType, ConfigType
from nexustrader.schema import InstrumentId
from nexustrader.error import EngineBuildError


class KuCoinExchangeManager(ExchangeManager):
    api: ccxt.kucoin
    market: Dict[str, KucoinSpotMarket | KucoinFuturesMarket]  # symbol -> kucoin market
    market_id: Dict[str, str]  # symbol -> exchange symbol id

    def __init__(self, config: ConfigType | None = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "kucoin")
        super().__init__(config)
        self._public_conn_account_type = None

    def _parse_market(self, mkt: dict, typ: KucoinSpotMarket | KucoinFuturesMarket):
        for symbol, mkt in mkt.items():
            try:
                mkt_json = msgspec.json.encode(mkt)
                mkt = msgspec.json.decode(mkt_json, type=typ)

                if (
                    mkt.spot or mkt.linear or mkt.inverse or mkt.future
                ) and not mkt.option:
                    symbol = self._parse_symbol(mkt, exchange_suffix="KUCOIN")
                    mkt.symbol = symbol
                    self.market[symbol] = mkt
                    self.market_id[mkt.id] = (
                        symbol  # since kucoin symbol id is identical, no need to distinguish spot, linear, inverse
                    )
            except msgspec.ValidationError as ve:
                self._log.warning(f"Symbol Format Error: {ve}, {symbol}, {mkt}")
                continue

    def load_markets(self):
        spot_market = self.api.load_markets()
        future_market = ccxt.kucoinfutures().load_markets()

        self._parse_market(spot_market, KucoinSpotMarket)
        self._parse_market(future_market, KucoinFuturesMarket)

    def validate_public_connector_config(
        self, account_type: AccountType, basic_config: Any
    ) -> None:
        """Validate public connector configuration for this exchange"""
        if not isinstance(account_type, KucoinAccountType):
            raise EngineBuildError(
                f"Expected KucoinAccountType, got {type(account_type)}"
            )
        # For KuCoin, testnet is handled via CCXT sandbox; no strict coupling needed here.

    def validate_public_connector_limits(
        self, existing_connectors: Dict[AccountType, Any]
    ) -> None:
        """Validate public connector limits for this exchange"""
        kucoin_connectors = [
            c
            for c in existing_connectors.values()
            if hasattr(c, "account_type") and isinstance(c.account_type, KucoinAccountType)
        ]
        if len(kucoin_connectors) > 1:
            raise EngineBuildError(
                "Only one public connector is supported for KuCoin; remove extras."
            )

    def set_public_connector_account_type(self, account_type: KucoinAccountType) -> None:
        """Set the account type for public connector configuration."""
        self._public_conn_account_type = account_type

    def instrument_id_to_account_type(self, instrument_id: InstrumentId) -> AccountType:
        """Convert an instrument ID to the appropriate account type for this exchange"""
        if self._public_conn_account_type is None:
            raise EngineBuildError(
                "Public connector account type not set for KuCoin. Please add KuCoin in public_conn_config."
            )
        return self._public_conn_account_type
