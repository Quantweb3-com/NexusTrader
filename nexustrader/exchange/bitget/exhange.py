import ccxt
import msgspec
from typing import Any, Dict
from nexustrader.base import ExchangeManager
from nexustrader.exchange.bitget.schema import BitgetMarket
from nexustrader.schema import InstrumentId


class BitgetExchangeManager(ExchangeManager):
    api: ccxt.bitget
    market: Dict[str, BitgetMarket]
    market_id: Dict[str, str]

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "bitget")
        super().__init__(config)

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


def check():
    bgt = BitgetExchangeManager()
    market = bgt.market
    market_id = bgt.market_id

    for symbol, mkt in market.items():
        instrument_id = InstrumentId.from_str(symbol)
        if mkt.subType:
            assert instrument_id.type == mkt.subType
        else:
            assert instrument_id.type == mkt.type

    print("All checks passed")


if __name__ == "__main__":
    check()
