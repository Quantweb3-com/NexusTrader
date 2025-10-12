from nexustrader.config import Config, PublicConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, KlineInterval
from nexustrader.exchange import BinanceAccountType
from nexustrader.schema import Kline
from nexustrader.engine import Engine


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        self.subscribe_kline(
            ["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"],
            KlineInterval.SECOND_1,
            use_aggregator=True,
        )

        # self.subscribe_volume_kline(
        #     "BTCUSDT-PERP.BINANCE",
        #     volume_threshold=5,
        # )

    def on_kline(self, kline: Kline):
        self.log.info(str(kline))


config = Config(
    strategy_id="subscribe_klines_binance",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
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
