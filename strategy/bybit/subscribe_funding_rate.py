from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange import BybitAccountType
from nexustrader.schema import FundingRate, IndexPrice, MarkPrice
from nexustrader.engine import Engine

class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        self.subscribe_funding_rate(symbols=["BTCUSDT-PERP.BYBIT"])
        self.subscribe_index_price(symbols=["BTCUSDT-PERP.BYBIT"])
        self.subscribe_mark_price(symbols=["BTCUSDT-PERP.BYBIT"])

    def on_funding_rate(self, funding_rate: FundingRate):
        self.log.info(str(funding_rate))

    def on_index_price(self, index_price: IndexPrice):
        self.log.info(str(index_price))

    def on_mark_price(self, mark_price: MarkPrice):
        self.log.info(str(mark_price))


config = Config(
    strategy_id="bybit_subscribe_funding_rate",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BYBIT: BasicConfig(
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.BYBIT: [
            PublicConnectorConfig(
                account_type=BybitAccountType.LINEAR,
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
