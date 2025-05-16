import ccxt
import orjson
import msgspec
from typing import Any, Dict
from nexustrader.base import ExchangeManager
from nexustrader.exchange.bybit.schema import BybitMarket


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
                mkt_json = orjson.dumps(mkt)
                mkt = msgspec.json.decode(mkt_json, type=BybitMarket)
                if (
                    mkt.spot or mkt.linear or mkt.inverse or mkt.future
                ) and not mkt.option:
                    symbol = self._parse_symbol(mkt, exchange_suffix="BYBIT")
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
