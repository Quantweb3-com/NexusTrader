from decimal import Decimal

from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    LogConfig,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide, OrderType, KlineInterval
from nexustrader.exchange import BinanceAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine


BINANCE_API_KEY = settings.BINANCE.FUTURE.TESTNET_1.API_KEY
BINANCE_SECRET = settings.BINANCE.FUTURE.TESTNET_1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BINANCE"])
        self.subscribe_kline(
            symbols="BTCUSDT-PERP.BINANCE", interval=KlineInterval.MINUTE_1
        )

    def on_failed_order(self, order: Order):
        print(order)

    def on_pending_order(self, order: Order):
        print(order)

    def on_accepted_order(self, order: Order):
        print(order)

    def on_filled_order(self, order: Order):
        print(order)

    def on_bookl1(self, bookl1: BookL1):
        if self.signal:
            self.create_order(
                symbol="BTCUSDT-PERP.BINANCE",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.01"),
            )
            self.create_order(
                symbol="BTCUSDT-PERP.BINANCE",
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                amount=Decimal("0.01"),
                reduce_only=True,
            )
            self.signal = False


config = Config(
    strategy_id="buy_and_sell_binance",
    user_id="user_test",
    strategy=Demo(),
    log_config=LogConfig(
        level_stdout="INFO",
        level_file="INFO",
        directory=".log",
        file_name="trading.log",
    ),
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
