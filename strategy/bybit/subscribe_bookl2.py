from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, BookLevel
from nexustrader.exchange import BybitAccountType
from nexustrader.schema import BookL2
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog


SpdLog.initialize(level="DEBUG", std_level="ERROR", production_mode=True)

BYBIT_API_KEY = settings.BYBIT.ACCOUNT1.API_KEY
BYBIT_SECRET = settings.BYBIT.ACCOUNT1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        self.subscribe_bookl2(symbols="BTCUSDT-PERP.BYBIT", level=BookLevel.L50)

    def on_bookl2(self, bookl2: BookL2):
        print(bookl2)


config = Config(
    strategy_id="bybit_subscribe_bookl2",
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
