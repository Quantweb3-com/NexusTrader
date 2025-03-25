import ccxt
import json


def get_meta_data(exchange_id: str):
    exchange: ccxt.Exchange = getattr(ccxt, exchange_id)
    market = exchange().load_markets()
    with open(f"./test/test_data/{exchange_id}_mkt_meta.json", "w") as f:
        json.dump(market, f, indent=4)


if __name__ == "__main__":
    get_meta_data("binance")
    get_meta_data("bybit")
    get_meta_data("okx")
