from datetime import datetime, timedelta
from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, KlineInterval
from nexustrader.exchange.okx import OkxAccountType
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog

SpdLog.initialize(level="INFO", std_level="ERROR", production_mode=True)

OKX_API_KEY = settings.OKX.DEMO_1.API_KEY
OKX_SECRET = settings.OKX.DEMO_1.SECRET
OKX_PASSPHRASE = settings.OKX.DEMO_1.PASSPHRASE


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def get_klines(self, symbol: str, interval: KlineInterval):
        res = self.request_index_klines(
            symbol=symbol,
            account_type=OkxAccountType.DEMO,
            interval=interval,
            start_time=datetime.now() - timedelta(days=5),
        )
        df = res.df
        print(df)

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT.OKX"])
        self.get_klines(symbol="BTCUSDT.OKX", interval=KlineInterval.MINUTE_1)


config = Config(
    strategy_id="okx_buy_and_sell",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.OKX: BasicConfig(
            api_key=OKX_API_KEY,
            secret=OKX_SECRET,
            passphrase=OKX_PASSPHRASE,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.OKX: [
            PublicConnectorConfig(
                account_type=OkxAccountType.DEMO,
                enable_rate_limit=True,
            )
        ]
    },
    private_conn_config={
        ExchangeType.OKX: [
            PrivateConnectorConfig(
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
