from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.constants import KlineInterval
from nexustrader.exchange import OkxAccountType
from nexustrader.schema import Kline
from nexustrader.engine import Engine


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_kline(
            "BTCUSDT-PERP.OKX", interval=KlineInterval.SECOND_1, use_aggregator=True
        )

    def on_kline(self, kline: Kline):
        self.log.info(str(kline))


config = Config(
    strategy_id="okx_subscribe_klines",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.OKX: BasicConfig(
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.OKX: [
            PublicConnectorConfig(
                account_type=OkxAccountType.DEMO,
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
