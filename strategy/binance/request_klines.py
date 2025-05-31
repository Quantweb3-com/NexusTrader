from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, KlineInterval
from nexustrader.exchange.binance import BinanceAccountType
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog
from datetime import datetime, timedelta

SpdLog.initialize(level="INFO", production_mode=True)

BINANCE_API_KEY = settings.BINANCE.LIVE.ACCOUNT1.API_KEY
BINANCE_SECRET = settings.BINANCE.LIVE.ACCOUNT1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def get_klines(self, symbol: str, interval: KlineInterval):
        res = self.request_klines(
            symbol=symbol,
            account_type=BinanceAccountType.USD_M_FUTURE,
            interval=interval,
            start_time=datetime.now() - timedelta(hours=100),
        )

        return res.df

    def on_start(self):
        df = self.get_klines(
            symbol="BTCUSDT-PERP.BINANCE", interval=KlineInterval.HOUR_1
        )
        print(df)


config = Config(
    strategy_id="binance_request_klines",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
            api_key=BINANCE_API_KEY,
            secret=BINANCE_SECRET,
        )
    },
    public_conn_config={
        ExchangeType.BINANCE: [
            PublicConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE,
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
