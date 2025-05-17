import pandas as pd
from nexustrader.core.entity import RateLimit
from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, KlineInterval
from nexustrader.exchange.bybit import BybitAccountType
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog
from datetime import datetime, timedelta

SpdLog.initialize(level="INFO", std_level="ERROR", production_mode=True)

BYBIT_API_KEY = settings.BYBIT.LIVE.ACCOUNT1.API_KEY
BYBIT_SECRET = settings.BYBIT.LIVE.ACCOUNT1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def get_klines(self, symbol: str, interval: KlineInterval):
        res = self.request_klines(
            symbol=symbol,
            account_type=BybitAccountType.LINEAR,
            interval=interval,
            start_time=datetime.now() - timedelta(hours=100),
        )

        return res.df

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BYBIT"])
        df = self.get_klines(
            symbol="BTCUSDT-PERP.BYBIT", interval=KlineInterval.HOUR_1
        )
        print(df)


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
                rate_limit=RateLimit(
                    max_rate=20,
                    time_period=1,
                ),
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
