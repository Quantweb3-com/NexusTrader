from collections import deque
from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, KlineInterval, DataType, LogColor
from nexustrader.exchange import BybitAccountType
from nexustrader.engine import Engine

from nexustrader.indicator import Indicator
from nexustrader.schema import Kline, BookL1, BookL2, Trade

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
        # Multi-symbol example
        self.symbols = [
            "BTCUSDT-PERP.BYBIT",
            "ETHUSDT-PERP.BYBIT",
            "UNIUSDT-PERP.BYBIT",
        ]
        self.ma_20 = MovingAverageIndicator(period=20)
        self.ma_50 = MovingAverageIndicator(period=50)

    def on_start(self):
        # Subscribe to kline data for multiple symbols
        self.subscribe_kline(
            symbols=self.symbols,
            interval=KlineInterval.MINUTE_1,
        )

        # Register indicators for multiple symbols - each symbol gets its own indicator instance
        self.register_indicator(
            symbols=self.symbols,
            indicator=self.ma_20,
            data_type=DataType.KLINE,
            account_type=BybitAccountType.LINEAR,
        )

        self.register_indicator(
            symbols=self.symbols,
            indicator=self.ma_50,
            data_type=DataType.KLINE,
            account_type=BybitAccountType.LINEAR,
        )

    def on_kline(self, kline: Kline):
        symbol = kline.symbol

        # Access per-symbol indicators using the new proxy
        ma_20_for_symbol = self.indicator.MA_20[symbol]
        ma_50_for_symbol = self.indicator.MA_50[symbol]

        if not ma_20_for_symbol or not ma_50_for_symbol:
            return

        if not ma_20_for_symbol.is_warmed_up or not ma_50_for_symbol.is_warmed_up:
            self.log.info(
                f"Indicators for {symbol} still warming up...", color=LogColor.BLUE
            )
            return

        if not kline.confirm:
            return

        if ma_20_for_symbol.value and ma_50_for_symbol.value:
            self.log.info(
                f"{symbol} - MA20: {ma_20_for_symbol.value:.4f}, MA50: {ma_50_for_symbol.value:.4f}, "
                f"Current Price: {kline.close:.4f}",
                color=LogColor.BLUE,
            )

            # Simple golden cross strategy signal per symbol
            if ma_20_for_symbol.value > ma_50_for_symbol.value:
                self.log.info(
                    f"{symbol} - Golden Cross - Bullish signal!", color=LogColor.BLUE
                )
            elif ma_20_for_symbol.value < ma_50_for_symbol.value:
                self.log.info(
                    f"{symbol} - Death Cross - Bearish signal!", color=LogColor.BLUE
                )


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
