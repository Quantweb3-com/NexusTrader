from nexustrader.constants import settings
from nexustrader.config import Config, PublicConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.constants import KlineInterval
from nexustrader.exchange.okx import OkxAccountType
from nexustrader.schema import Kline
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog

SpdLog.initialize(level="DEBUG", std_level="ERROR", production_mode=True)

OKX_API_KEY = settings.OKX.LIVE.API_KEY
OKX_SECRET = settings.OKX.LIVE.SECRET
OKX_PASSPHRASE = settings.OKX.LIVE.PASSPHRASE

class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True
        
    def on_start(self):
        symbols = ["BTCUSDT-PERP.OKX"]
        missing_symbols = [
            symbol
            for symbol in symbols
            if symbol not in self.linear_info(exchange=ExchangeType.OKX, quote="USDT")
        ]
        if missing_symbols:
            raise ValueError(f"Symbols not found in OKX linear markets: {missing_symbols}")
        print(f"Subscribing OKX klines: {symbols}")
        self.subscribe_bookl1(symbols=symbols)
        self.subscribe_kline(symbols=symbols, interval=KlineInterval.MINUTE_1)
    
    def on_kline(self, kline: Kline):
        print(kline)
        

config = Config(
    strategy_id="okx_subscribe_klines",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.OKX: BasicConfig(
            api_key=OKX_API_KEY,
            secret=OKX_SECRET,
            passphrase=OKX_PASSPHRASE,
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.OKX: [
            PublicConnectorConfig(
                account_type=OkxAccountType.LIVE,
            )
        ]
    },
    private_conn_config={},
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
