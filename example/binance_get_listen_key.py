import asyncio

from tradebot.constants import CONFIG
from tradebot.exchange.binance import BinanceRestApi
from tradebot.constants import BinanceAccountType


BINANCE_API_KEY = CONFIG['binance_future_testnet']['API_KEY']
BINANCE_API_SECRET = CONFIG['binance_future_testnet']['SECRET']


async def main():
    try:
        rest_api = BinanceRestApi(
            api_key=BINANCE_API_KEY,
            secret=BINANCE_API_SECRET,
            account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
        )
        
        res = await rest_api.start_user_data_stream()
        listen_key = res['listenKey']
        print(listen_key)
        res = await rest_api.keep_alive_user_data_stream(listen_key)
        print(res)
        
        res = await rest_api.new_order("BTCUSDT", "BUY", "MARKET", quantity=0.01)
        print(res)
        res = await rest_api.new_order("BTCUSDT", "BUY", "MARKET", quantity=0.01)
        print(res)
        
        
    finally:
        await rest_api.close_session()
    


if __name__ == "__main__":
    asyncio.run(main())
    


