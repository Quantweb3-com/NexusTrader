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
from nexustrader.schema import BookL1, Order, BatchOrder
from nexustrader.engine import Engine


BINANCE_API_KEY = settings.BINANCE.FUTURE.TESTNET_1.API_KEY
BINANCE_SECRET = settings.BINANCE.FUTURE.TESTNET_1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BINANCE"])

    def on_failed_order(self, order: Order):
        self.log.info(str(order))

    def on_pending_order(self, order: Order):
        self.log.info(str(order))

    def on_accepted_order(self, order: Order):
        self.log.info(str(order))

    def on_filled_order(self, order: Order):
        self.log.info(str(order))

    def on_bookl1(self, bookl1: BookL1):
        if self.signal:
            symbol = "BTCUSDT-PERP.BINANCE"
            bid = bookl1.bid

            prices = [
                self.price_to_precision(symbol, bid),
                self.price_to_precision(symbol, bid * 0.999),
                self.price_to_precision(symbol, bid * 0.998),
                self.price_to_precision(symbol, bid * 0.997),
                self.price_to_precision(symbol, bid * 0.996),
                self.price_to_precision(symbol, bid * 0.995),
                self.price_to_precision(symbol, bid * 0.994),
            ]

            orders = [
                BatchOrder(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    amount=Decimal("0.01"),
                    price=price,
                )
                for price in prices
            ]

            self.create_batch_orders(
                orders=orders,
            )
            self.signal = False


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
