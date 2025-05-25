import ccxt
import msgspec
from typing import Any, Dict
from nexustrader.base import ExchangeManager
from nexustrader.exchange.binance.schema import BinanceMarket
from nexustrader.schema import InstrumentId
import pickle
from typing import List


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


def check():
    bnc = BinanceExchangeManager()
    market = bnc.market
    market_id = bnc.market_id

    for symbol, mkt in market.items():
        instrument_id = InstrumentId.from_str(symbol)
        if mkt.subType:
            assert instrument_id.type == mkt.subType
        else:
            assert instrument_id.type == mkt.type

    print("All checks passed")

    with open("./test/test_data/market.pkl", "wb") as f:
        pickle.dump(market, f)

    with open("./test/test_data/market_id.pkl", "wb") as f:
        pickle.dump(market_id, f)


if __name__ == "__main__":
    check()
