from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, KlineInterval
from nexustrader.exchange import BybitAccountType
from nexustrader.engine import Engine

from datetime import datetime, timedelta


BYBIT_API_KEY = settings.BYBIT.LIVE.ACCOUNT1.API_KEY
BYBIT_SECRET = settings.BYBIT.LIVE.ACCOUNT1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.symbol = "UNIUSDT-PERP.BYBIT"

    def on_start(self):
        res = self.request_klines(
            symbol=self.symbol,
            interval=KlineInterval.MINUTE_1,
            start_time=datetime.now() - timedelta(minutes=600),
            account_type=BybitAccountType.LINEAR,
        )
        print(res.df)


config = Config(
    strategy_id="bybit_request_klines",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BYBIT: BasicConfig(
            api_key=BYBIT_API_KEY,
            secret=BYBIT_SECRET,
        )
    },
    public_conn_config={
        ExchangeType.BYBIT: [
            PublicConnectorConfig(
                account_type=BybitAccountType.LINEAR,
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
