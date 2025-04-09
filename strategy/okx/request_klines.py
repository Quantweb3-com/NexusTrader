import pandas as pd
from nexustrader.core.entity import RateLimit
from nexustrader.constants import settings
from nexustrader.config import Config, PublicConnectorConfig, PrivateConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, KlineInterval
from nexustrader.exchange.okx import OkxAccountType
from nexustrader.engine import Engine
from nexustrader.schema import Kline
from nexustrader.core.log import SpdLog

SpdLog.initialize(level="INFO", std_level="ERROR", production_mode=True)

OKX_API_KEY = settings.OKX.DEMO_1.API_KEY
OKX_SECRET = settings.OKX.DEMO_1.SECRET
OKX_PASSPHRASE = settings.OKX.DEMO_1.PASSPHRASE



class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True
        
    def get_klines(self, symbol: str, interval: KlineInterval, limit: int):
        end = self.clock.timestamp_ms()
        klines: list[Kline] = self.request_klines(
            symbol=symbol,
            account_type=OkxAccountType.DEMO,
            interval=interval,
            limit=limit,
            end_time=end,
        )
        data = {
            "timestamp": [kline.start for kline in klines],
            "open": [kline.open for kline in klines],
            "high": [kline.high for kline in klines],
            "low": [kline.low for kline in klines],
            "close": [kline.close for kline in klines],
            "volume": [kline.volume for kline in klines],
        }
        df = pd.DataFrame(data)
        return df
        
    def iter(self):
        df = self.get_klines(symbol="BTCUSDT.OKX", interval=KlineInterval.MINUTE_1, limit=300)
        print(df)
        
    
    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT.OKX"])
        self.schedule(self.iter, trigger="interval", seconds=20)
        self.get_klines(symbol="BTCUSDT.OKX", interval=KlineInterval.MINUTE_1, limit=300)
        

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
                rate_limit=RateLimit(
                    max_rate=20,
                    time_period=1,
                )
            )
        ]
    },
    private_conn_config={
        ExchangeType.OKX: [
            PrivateConnectorConfig(
                account_type=OkxAccountType.DEMO,
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
