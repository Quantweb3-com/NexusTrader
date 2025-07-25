import ccxt
import msgspec
from typing import Any, Dict
from nexustrader.base import ExchangeManager
from nexustrader.exchange.hpyerliquid.schema import HpyerLiquidMarket


class HyperLiquidExchangeManager(ExchangeManager):
    api: ccxt.hyperliquid
    market: Dict[str, HpyerLiquidMarket]
    market_id: Dict[str, str]

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "hyperliquid")

        config["walletAddress"] = config.pop("apiKey", None)
        config["privateKey"] = config.pop("secret", None)

        super().__init__(config, require_api_key=False)

    def load_markets(self):
        market = self.api.load_markets()
        for symbol, mkt in market.items():
            try:
                mkt_json = msgspec.json.encode(mkt)
                mkt = msgspec.json.decode(mkt_json, type=HpyerLiquidMarket)

                if (
                    mkt.spot or mkt.linear or mkt.inverse or mkt.future
                ) and not mkt.option:
                    symbol = self._parse_symbol(mkt, exchange_suffix="HYPER")
                    mkt.symbol = symbol
                    self.market[symbol] = mkt
                    self.market_id[mkt.id] = symbol

            except Exception as e:
                print(f"Error: {e}, {symbol}, {mkt}")
                continue

    def validate_public_connector_config(self, account_type, basic_config):
        pass

    def validate_public_connector_limits(self, existing_connectors):
        pass

    def instrument_id_to_account_type(self, instrument_id):
        pass
