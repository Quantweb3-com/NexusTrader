from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.constants import BookLevel
from nexustrader.exchange import OkxAccountType
from nexustrader.schema import BookL2
from nexustrader.engine import Engine


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl2(symbols="BTCUSDT-PERP.OKX", level=BookLevel.L5)

    def on_bookl2(self, bookl2: BookL2):
        print(bookl2)


config = Config(
    strategy_id="okx_subscribe_bookl2",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.OKX: BasicConfig(
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.OKX: [
            PublicConnectorConfig(
                account_type=OkxAccountType.LIVE,
            )
        ]
    }
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
