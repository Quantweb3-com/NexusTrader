from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange.binance import BinanceAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog
from nexustrader.constants import KlineInterval

SpdLog.initialize(level="INFO", file_name="tp_sl_order", production_mode=True)

BINANCE_API_KEY = settings.BINANCE.FUTURE.TESTNET_1.API_KEY
BINANCE_SECRET = settings.BINANCE.FUTURE.TESTNET_1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True
        self.order_id = None

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BINANCE"])

        end_time = self.clock.timestamp_ms()
        klines = self.request_klines(
            symbol="BTCUSDT-PERP.BINANCE",
            account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
            interval=KlineInterval.MINUTE_15,
            limit=24 * 60 / 15,
            end_time=end_time,
        )
        close_price = [kline.close for kline in klines]
        print(f"max: {max(close_price)}, min: {min(close_price)}")

    def query_order(self):
        if self.order_id:
            order = self.cache.get_order(self.order_id).unwrap()
            print(order, "\n")

    def on_canceled_order(self, order: Order):
        print(order, "\n")

    def on_failed_order(self, order: Order):
        print(order, "\n")

    def on_partially_filled_order(self, order: Order):
        print(order, "\n")

    def on_pending_order(self, order: Order):
        print(order, "\n")

    def on_accepted_order(self, order: Order):
        print(order, "\n")

    def on_filled_order(self, order: Order):
        print(order, "\n")

    def on_bookl1(self, bookl1: BookL1):
        print(bookl1, "\n")


config = Config(
    strategy_id="tp_sl_order",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
            api_key=BINANCE_API_KEY,
            secret=BINANCE_SECRET,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.BINANCE: [
            PublicConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
            )
        ]
    },
    private_conn_config={
        ExchangeType.BINANCE: [
            PrivateConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
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
