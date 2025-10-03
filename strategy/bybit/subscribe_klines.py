from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, KlineInterval
from nexustrader.exchange import BybitAccountType
from nexustrader.schema import Kline
from nexustrader.engine import Engine


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        self.subscribe_kline(
            "BTCUSDT-PERP.BYBIT", interval=KlineInterval.SECOND_1, use_aggregator=True
        )

    def on_kline(self, kline: Kline):
        self.log.info(str(kline))


config = Config(
    strategy_id="bybit_subscribe_klines",
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
