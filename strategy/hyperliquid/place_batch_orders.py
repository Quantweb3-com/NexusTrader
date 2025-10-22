from nexustrader.constants import settings
from decimal import Decimal
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide, OrderType
from nexustrader.exchange import HyperLiquidAccountType
from nexustrader.schema import BookL1, Order, BatchOrder
from nexustrader.engine import Engine


HYPER_API_KEY = settings.HYPER.TESTNET.API_KEY
HYPER_SECRET = settings.HYPER.TESTNET.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDC-PERP.HYPERLIQUID"])

    def on_failed_order(self, order: Order):
        self.log.info(str(order))

    def on_pending_order(self, order: Order):
        self.log.info(str(order))

    def on_accepted_order(self, order: Order):
        self.log.info(str(order))

    def on_filled_order(self, order: Order):
        self.log.info(str(order))

    def on_canceled_order(self, order):
        self.log.info(str(order))

    def on_bookl1(self, bookl1: BookL1):
        symbol = "BTCUSDC-PERP.HYPERLIQUID"
        if self.signal:
            bid = bookl1.bid

            prices = [
                self.price_to_precision(symbol, bid * 0.999),
                self.price_to_precision(symbol, bid * 0.998),
                self.price_to_precision(symbol, bid * 0.997),
                self.price_to_precision(symbol, bid * 0.996),
                self.price_to_precision(symbol, bid * 0.995),
                self.price_to_precision(symbol, bid * 0.994),
            ]

            self.create_batch_orders(
                orders=[
                    BatchOrder(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        type=OrderType.LIMIT,
                        amount=Decimal("0.01"),
                        price=px,
                    )
                    for px in prices
                ]
            )
            self.signal = False

        for oid in self.cache.get_open_orders(symbol):
            self.cancel_order(
                symbol=symbol,
                oid=oid,
            )


config = Config(
    strategy_id="buy_and_sell_hyperliquid",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.HYPERLIQUID: BasicConfig(
            api_key=HYPER_API_KEY,
            secret=HYPER_SECRET,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.HYPERLIQUID: [
            PublicConnectorConfig(
                account_type=HyperLiquidAccountType.TESTNET,
                enable_rate_limit=True,
            )
        ]
    },
    private_conn_config={
        ExchangeType.HYPERLIQUID: [
            PrivateConnectorConfig(
                account_type=HyperLiquidAccountType.TESTNET,
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
