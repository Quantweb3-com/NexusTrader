from nexustrader.constants import settings
from nexustrader.config import Config, PublicConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, KlineInterval
from nexustrader.exchange import BinanceAccountType
from nexustrader.schema import Kline
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog
import numpy as np

SpdLog.initialize(level="DEBUG", std_level="ERROR", production_mode=True)


BINANCE_API_KEY = settings.BINANCE.LIVE.ACCOUNT1.API_KEY
BINANCE_SECRET = settings.BINANCE.LIVE.ACCOUNT1.SECRET

latency_list = []


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        symbols = self.linear_info(exchange=ExchangeType.BINANCE, quote="USDT")
        self.subscribe_kline(symbols=symbols, interval=KlineInterval.HOUR_1)
        # self.subscribe_bookl1(symbols=symbols)

    def on_kline(self, kline: Kline):
        local = self.clock.timestamp_ms()
        latency_list.append(local - kline.timestamp)

        if len(latency_list) >= 300:
            mean = np.mean(latency_list)
            median = np.median(latency_list)
            percentile95 = np.percentile(latency_list, 95)
            percentile99 = np.percentile(latency_list, 99)
            print(
                f"mean: {mean:.4f} ms, median: {median:.4f} ms, 95 percentile: {percentile95:.4f} ms, 99 percentile: {percentile99:.4f} ms"
            )
            latency_list.clear()


config = Config(
    strategy_id="subscribe_klines_binance",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
            api_key=BINANCE_API_KEY,
            secret=BINANCE_SECRET,
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.BINANCE: [
            PublicConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE,
                custom_url="ws://127.0.0.1:9001/linear",
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
