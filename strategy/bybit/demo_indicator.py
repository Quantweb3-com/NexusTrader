from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange import BybitAccountType
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog
from nexustrader.indicator import Indicator
from nexustrader.constants import DataType
from nexustrader.schema import Kline, BookL1, BookL2, Trade

SpdLog.initialize(level="INFO", std_level="ERROR")

BYBIT_API_KEY = settings.BYBIT.LIVE.ACCOUNT1.API_KEY
BYBIT_SECRET = settings.BYBIT.LIVE.ACCOUNT1.SECRET


class MicroPriceIndicator(Indicator):
    def __init__(self):
        self.value = None

    def handle_kline(self, kline: Kline):
        pass

    def handle_bookl1(self, bookl1: BookL1):
        self.value = bookl1.weighted_mid

    def handle_bookl2(self, bookl2: BookL2):
        pass

    def handle_trade(self, trade: Trade):
        pass


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True
        self.symbol = "UNIUSDT-PERP.BYBIT"
        self.micro_price_indicator = MicroPriceIndicator()

    def on_start(self):
        self.subscribe_bookl1(
            symbols=self.symbol,
        )
        self.register_indicator(
            symbols=self.symbol,
            indicator=self.micro_price_indicator,
            data_type=DataType.BOOKL1,
        )

    def on_bookl1(self, bookl1: BookL1):
        if not self.micro_price_indicator.value:
            return
        self.log.info(
            f"micro_price: {self.micro_price_indicator.value:.4f}, bookl1: {bookl1.mid:.4f}"
        )


config = Config(
    strategy_id="bybit_demo_indicator",
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
