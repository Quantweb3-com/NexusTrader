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
        super().__init__(config)

    def load_markets(self):
        market = self.api.load_markets()
        for symbol, mkt in market.items():
            try:
                mkt_json = msgspec.json.encode(mkt)
                mkt = msgspec.json.decode(mkt_json, type=HpyerLiquidMarket)

                if (
                    mkt.spot or mkt.linear or mkt.inverse or mkt.future
                ) and not mkt.option:
                    symbol = self._parse_symbol(mkt, exchange_suffix="HYPERLIQUID")
                    mkt.symbol = symbol
                    self.market[symbol] = mkt
                    self.market_id[mkt.id] = symbol

            except Exception as e:
                print(f"Error: {e}, {symbol}, {mkt}")
                continue


if __name__ == "__main__":
    hpy = HyperLiquidExchangeManager()
    print(hpy.market)
    print(hpy.market_id)
