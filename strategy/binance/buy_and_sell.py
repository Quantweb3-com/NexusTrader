from decimal import Decimal

from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
    LogConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide, OrderType
from nexustrader.exchange import BinanceAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine


BINANCE_API_KEY = settings.BINANCE.DEMO.API_KEY
BINANCE_SECRET = settings.BINANCE.DEMO.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True
        self.symbol = "BTCUSDT.BINANCE"

    def on_start(self):
        self.subscribe_bookl1(symbols=[self.symbol])

    def on_failed_order(self, order: Order):
        self.log.info(str(order))

    def on_pending_order(self, order: Order):
        self.log.info(str(order))

    def on_accepted_order(self, order: Order):
        self.log.info(str(order))

    def on_filled_order(self, order: Order):
        self.log.info(str(order))

    def on_canceled_order(self, order: Order):
        self.log.info(str(order))

    def on_bookl1(self, bookl1: BookL1):
        if self.signal:
            symbol = self.symbol
            bid = bookl1.bid

            prices = [
                # self.price_to_precision(symbol, bid),
                self.price_to_precision(symbol, bid * 0.999),
                self.price_to_precision(symbol, bid * 0.998),
                self.price_to_precision(symbol, bid * 0.997),
                self.price_to_precision(symbol, bid * 0.996),
            ]

            for price in prices:
                self.create_order(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    type=OrderType.POST_ONLY,
                    amount=Decimal("0.001"),
                    price=price,
                )
            self.signal = False

        open_orders = self.cache.get_open_orders(symbol=self.symbol)
        for oid in open_orders:
            self.cancel_order(
                symbol=self.symbol,
                oid=oid,
                account_type=BinanceAccountType.SPOT_TESTNET,
            )


config = Config(
    strategy_id="buy_and_sell_binance",
    user_id="user_test",
    strategy=Demo(),
    log_config=LogConfig(level_stdout="INFO"),
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
                account_type=BinanceAccountType.SPOT_TESTNET,
                enable_rate_limit=True,
            )
        ]
    },
    private_conn_config={
        ExchangeType.BINANCE: [
            PrivateConnectorConfig(
                account_type=BinanceAccountType.SPOT_TESTNET,
                enable_rate_limit=True,
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
