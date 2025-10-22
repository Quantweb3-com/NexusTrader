from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
    LogConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange import BinanceAccountType
from nexustrader.engine import Engine


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        self.schedule(
            func=self.on_tick,
            trigger="interval",
            seconds=3,
        )

        # Set a parameter in Redis backend
        self.param(
            name="mode",
            value="normal",
            backend="redis",
        )

        self.param(
            name="signal",
            value={"BTCUSDT-PERP": 0.01, "ETHUSDT-PERP": -0.02},
            backend="redis",
        )

    def on_tick(self):
        # Get the parameter from Redis backend
        mode = self.param("mode", backend="redis")
        self.log.info(f"mode: {mode}")

        signal = self.param("signal", backend="redis")
        self.log.info(f"signal: {signal}")


config = Config(
    strategy_id="set_params",
    user_id="test_user",
    strategy=Demo(),
    log_config=LogConfig(level_stdout="INFO"),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.BINANCE: [
            PublicConnectorConfig(
                account_type=BinanceAccountType.SPOT,
                enable_rate_limit=True,
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
