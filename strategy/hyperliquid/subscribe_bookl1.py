from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange import HyperLiquidAccountType
from nexustrader.schema import BookL1
from nexustrader.engine import Engine


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDC-PERP.HYPERLIQUID"])

    def on_bookl1(self, bookl1: BookL1):
        self.log.info(str(bookl1))


config = Config(
    strategy_id="subscribe_bookl1_hyperliquid",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.HYPERLIQUID: BasicConfig(
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.HYPERLIQUID: [
            PublicConnectorConfig(
                account_type=HyperLiquidAccountType.MAINNET,
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
