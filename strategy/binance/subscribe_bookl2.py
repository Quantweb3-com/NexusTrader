from nexustrader.constants import settings
from nexustrader.config import Config, PublicConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, BookLevel
from nexustrader.exchange import BinanceAccountType
from nexustrader.schema import BookL2
from nexustrader.engine import Engine


BINANCE_API_KEY = settings.BINANCE.LIVE.ACCOUNT1.API_KEY
BINANCE_SECRET = settings.BINANCE.LIVE.ACCOUNT1.SECRET

latency_list = []


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        self.subscribe_bookl2(symbols="BTCUSDT-PERP.BINANCE", level=BookLevel.L10)
        # self.subscribe_bookl1(symbols=symbols)

    def on_bookl2(self, bookl2: BookL2):
        b_sum = bookl2.bids[0].price + bookl2.bids[1].price + bookl2.bids[2].price
        a_sum = bookl2.asks[0].price + bookl2.asks[1].price + bookl2.asks[2].price

        obi = (b_sum - a_sum) / (b_sum + a_sum)
        print(obi)


config = Config(
    strategy_id="subscribe_bookl2_binance",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
            api_key=BINANCE_API_KEY,
            secret=BINANCE_SECRET,
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.BINANCE: [
            PublicConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE,
            )
        ]
    },
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
