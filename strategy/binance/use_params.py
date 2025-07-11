from decimal import Decimal

from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange import BinanceAccountType
from nexustrader.engine import Engine


BINANCE_API_KEY = settings.BINANCE.FUTURE.TESTNET_1.API_KEY
BINANCE_SECRET = settings.BINANCE.FUTURE.TESTNET_1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.reset_param: bool = False  # Flag to reset parameters

    def on_start(self):
        if self.reset_param:
            self.clear_param("pos")  # Clear all parameters if flag is set

        pos = self.param("pos")
        if not pos:
            self.log.info("pos is not set, setting...")
            self.param(
                "pos",
                {
                    "BTCUSDT-PERP.BINANCE": Decimal("0.01"),
                },
            )  # can set any value here
            self.log.info("pos is set to 0.01")
        else:
            self.log.info(f"pos is set: {str(pos)}")


config = Config(
    strategy_id="demo_param_usage",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
            api_key=BINANCE_API_KEY,
            secret=BINANCE_SECRET,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.BINANCE: [
            PublicConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
                enable_rate_limit=True,
            )
        ]
    },
    private_conn_config={
        ExchangeType.BINANCE: [
            PrivateConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
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
