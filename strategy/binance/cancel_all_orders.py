from decimal import Decimal

from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide, OrderType
from nexustrader.exchange import BinanceAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog

SpdLog.initialize(level="DEBUG", std_level="ERROR", production_mode=True)


BINANCE_API_KEY = settings.BINANCE.FUTURE.TESTNET_1.API_KEY
BINANCE_SECRET = settings.BINANCE.FUTURE.TESTNET_1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True
        self.canceled = False

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BINANCE"])

    def on_failed_order(self, order: Order):
        print(order)

    def on_pending_order(self, order: Order):
        print(order)

    def on_accepted_order(self, order: Order):
        print(order)

    def on_filled_order(self, order: Order):
        print(order)

    def on_canceled_order(self, order: Order):
        print(order)

    def on_bookl1(self, bookl1: BookL1):
        if self.signal:
            self.create_order(
                symbol="BTCUSDT-PERP.BINANCE",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.002"),
                price=Decimal("90000"),
            )
            self.create_order(
                symbol="BTCUSDT-PERP.BINANCE",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.002"),
                price=Decimal("89000"),
            )
            self.create_order(
                symbol="BTCUSDT-PERP.BINANCE",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.002"),
                price=Decimal("88000"),
            )
            self.signal = False

        if not self.signal and not self.canceled:
            self.cancel_all_orders(symbol="BTCUSDT-PERP.BINANCE")
            self.canceled = True


config = Config(
    strategy_id="buy_and_sell_binance",
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
