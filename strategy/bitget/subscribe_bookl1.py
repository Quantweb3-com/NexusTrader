from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange import BitgetAccountType
from nexustrader.schema import BookL1
from nexustrader.engine import Engine


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BITGET"])

    def on_bookl1(self, bookl1: BookL1):
        self.log.info(str(bookl1))


config = Config(
    strategy_id="subscribe_bookl1_bitget",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BITGET: BasicConfig(
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.BITGET: [
            PublicConnectorConfig(
                account_type=BitgetAccountType.UTA,
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
