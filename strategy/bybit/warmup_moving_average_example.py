from collections import deque
from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, KlineInterval, DataType
from nexustrader.exchange.bybit import BybitAccountType
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog
from nexustrader.indicator import Indicator
from nexustrader.schema import Kline, BookL1, BookL2, Trade

SpdLog.initialize(level="INFO")

BYBIT_API_KEY = settings.BYBIT.LIVE.ACCOUNT1.API_KEY
BYBIT_SECRET = settings.BYBIT.LIVE.ACCOUNT1.SECRET


class MovingAverageIndicator(Indicator):
    def __init__(self, period: int = 20):
        super().__init__(
            params={"period": period},
            name=f"MA_{period}",
            warmup_period=period * 2,
            warmup_interval=KlineInterval.MINUTE_1,
        )
        self.period = period
        self.prices = deque(maxlen=period)
        self.current_ma = None

    def handle_kline(self, kline: Kline):
        if not kline.confirm:
            return

        self.prices.append(kline.close)

        # Calculate moving average if we have enough data
        if len(self.prices) >= self.period:
            self.current_ma = sum(self.prices) / len(self.prices)

    def handle_bookl1(self, bookl1: BookL1):
        pass

    def handle_bookl2(self, bookl2: BookL2):
        pass

    def handle_trade(self, trade: Trade):
        pass

    @property
    def value(self):
        return self.current_ma


class WarmupDemo(Strategy):
    def __init__(self):
        super().__init__()
        self.symbol = "UNIUSDT-PERP.BYBIT"
        self.ma_20 = MovingAverageIndicator(period=20)
        self.ma_50 = MovingAverageIndicator(period=50)

    def on_start(self):
        # Subscribe to kline data
        self.subscribe_kline(
            symbols=self.symbol,
            interval=KlineInterval.MINUTE_1,
        )

        # Register indicators with warmup - they will automatically fetch historical data
        self.register_indicator(
            symbols=self.symbol,
            indicator=self.ma_20,
            data_type=DataType.KLINE,
            account_type=BybitAccountType.LINEAR,
        )

        self.register_indicator(
            symbols=self.symbol,
            indicator=self.ma_50,
            data_type=DataType.KLINE,
            account_type=BybitAccountType.LINEAR,
        )

    def on_kline(self, kline: Kline):
        if not self.ma_20.is_warmed_up or not self.ma_50.is_warmed_up:
            self.log.info("Indicators still warming up...")
            return

        if not kline.confirm:
            return

        if self.ma_20.value and self.ma_50.value:
            self.log.info(
                f"MA20: {self.ma_20.value:.4f}, MA50: {self.ma_50.value:.4f}, "
                f"Current Price: {kline.close:.4f}"
            )

            # Simple golden cross strategy signal
            if self.ma_20.value > self.ma_50.value:
                self.log.info("Golden Cross - Bullish signal!")
            elif self.ma_20.value < self.ma_50.value:
                self.log.info("Death Cross - Bearish signal!")


config = Config(
    strategy_id="bybit_warmup_demo",
    user_id="user_test",
    strategy=WarmupDemo(),
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
