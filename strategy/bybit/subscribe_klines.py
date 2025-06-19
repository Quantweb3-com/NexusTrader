from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, KlineInterval
from nexustrader.exchange import BybitAccountType
from nexustrader.schema import Kline
from nexustrader.engine import Engine


BYBIT_API_KEY = settings.BYBIT.ACCOUNT1.API_KEY
BYBIT_SECRET = settings.BYBIT.ACCOUNT1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        symbols = self.linear_info(ExchangeType.BYBIT)
        self.subscribe_kline(symbols=symbols, interval=KlineInterval.MINUTE_1)

    def on_kline(self, kline: Kline):
        print(kline)


config = Config(
    strategy_id="bybit_subscribe_klines",
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
