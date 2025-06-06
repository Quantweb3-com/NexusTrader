from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange import BybitAccountType
from nexustrader.schema import FundingRate, IndexPrice, MarkPrice
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog


SpdLog.initialize(level="DEBUG", production_mode=True)

BYBIT_API_KEY = settings.BYBIT.ACCOUNT1.API_KEY
BYBIT_SECRET = settings.BYBIT.ACCOUNT1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        self.subscribe_funding_rate(symbols=["BTCUSDT-PERP.BYBIT"])
        self.subscribe_index_price(symbols=["BTCUSDT-PERP.BYBIT"])
        self.subscribe_mark_price(symbols=["BTCUSDT-PERP.BYBIT"])

    def on_funding_rate(self, funding_rate: FundingRate):
        print(funding_rate)

    def on_index_price(self, index_price: IndexPrice):
        print(index_price)

    def on_mark_price(self, mark_price: MarkPrice):
        print(mark_price)


config = Config(
    strategy_id="bybit_subscribe_funding_rate",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BYBIT: BasicConfig(
            api_key=BYBIT_API_KEY,
            secret=BYBIT_SECRET,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.BYBIT: [
            PublicConnectorConfig(
                account_type=BybitAccountType.LINEAR_TESTNET,
            )
        ]
    },
    private_conn_config={
        ExchangeType.BYBIT: [
            PrivateConnectorConfig(
                account_type=BybitAccountType.UNIFIED_TESTNET,
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
