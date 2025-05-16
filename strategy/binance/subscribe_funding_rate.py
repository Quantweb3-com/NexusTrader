from nexustrader.constants import settings
from nexustrader.config import Config, PublicConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange.binance import BinanceAccountType
from nexustrader.schema import FundingRate, IndexPrice, MarkPrice
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog

SpdLog.initialize(level="DEBUG", production_mode=True)


BINANCE_API_KEY = settings.BINANCE.LIVE.ACCOUNT1.API_KEY
BINANCE_SECRET = settings.BINANCE.LIVE.ACCOUNT1.SECRET

latency_list = []


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        symbols = ["BTCUSDT-PERP.BINANCE"]
        # in binance, you need to subscribe to one of the following: funding rate, index price and mark price
        # the other two will be automatically subscribed to
        self.subscribe_funding_rate(symbols=symbols)

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
