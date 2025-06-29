from nexustrader.constants import settings
from nexustrader.config import Config, PublicConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange import BinanceAccountType
from nexustrader.schema import FundingRate, IndexPrice, MarkPrice
from nexustrader.engine import Engine


BINANCE_API_KEY = settings.BINANCE.LIVE.ACCOUNT1.API_KEY
BINANCE_SECRET = settings.BINANCE.LIVE.ACCOUNT1.SECRET

latency_list = []


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        symbols = ["BTCUSDT-PERP.BINANCE"]
        self.subscribe_funding_rate(symbols=symbols)
        self.subscribe_index_price(symbols=symbols)
        self.subscribe_mark_price(symbols=symbols)

    def on_funding_rate(self, funding_rate: FundingRate):
        print(funding_rate)

    def on_index_price(self, index_price: IndexPrice):
        print(index_price)

    def on_mark_price(self, mark_price: MarkPrice):
        print(mark_price)


config = Config(
    strategy_id="subscribe_funding_rate_binance",
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
