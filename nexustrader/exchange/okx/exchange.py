from typing import Any, Dict
from nexustrader.base import ExchangeManager
import ccxt
import orjson
import msgspec
from nexustrader.exchange.okx.schema import OkxMarket


class OkxExchangeManager(ExchangeManager):
    api: ccxt.okx
    market: Dict[str, OkxMarket]  # symbol -> okx market
    market_id: Dict[str, str]  # symbol -> exchange symbol id

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "okx")
        super().__init__(config)
        self.passphrase = config.get("password", None)

    def load_markets(self):
        market = self.api.load_markets()
        for symbol, mkt in market.items():
            try:
                mkt_json = orjson.dumps(mkt)
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
