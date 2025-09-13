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
from nexustrader.exchange import OkxAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine


OKX_API_KEY = settings.OKX.DEMO_1.API_KEY
OKX_SECRET = settings.OKX.DEMO_1.SECRET
OKX_PASSPHRASE = settings.OKX.DEMO_1.PASSPHRASE


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT.OKX", "BTCUSDT-PERP.OKX"])

    def on_cancel_failed_order(self, order: Order):
        print(order)

    def on_canceled_order(self, order: Order):
        print(order)

    def on_failed_order(self, order: Order):
        print(order)

    def on_pending_order(self, order: Order):
        print(order)

    def on_accepted_order(self, order: Order):
        print(order)

    def on_partially_filled_order(self, order: Order):
        print(order)

    def on_filled_order(self, order: Order):
        print(order)

    def on_bookl1(self, bookl1: BookL1):
        if self.signal:
            symbol = "BTCUSDT-PERP.OKX"
            bid = bookl1.bid

            prices = [
                # self.price_to_precision(symbol, bid),
                self.price_to_precision(symbol, bid * 0.999),
                self.price_to_precision(symbol, bid * 0.998),
                self.price_to_precision(symbol, bid * 0.997),
                self.price_to_precision(symbol, bid * 0.996),
            ]

            for price in prices:
                self.create_order_ws(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    type=OrderType.POST_ONLY,
                    amount=Decimal("0.001"),
                    price=price,
                )
            self.signal = False

        open_orders = self.cache.get_open_orders(symbol="BTCUSDT-PERP.OKX")
        for oid in open_orders:
            self.cancel_order_ws(symbol="BTCUSDT-PERP.OKX", oid=oid)


config = Config(
    strategy_id="demo_buy_and_cancel",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.OKX: BasicConfig(
            api_key=OKX_API_KEY,
            secret=OKX_SECRET,
            passphrase=OKX_PASSPHRASE,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.OKX: [
            PublicConnectorConfig(
                account_type=OkxAccountType.DEMO,
            )
        ]
    },
    private_conn_config={
        ExchangeType.OKX: [
            PrivateConnectorConfig(
                account_type=OkxAccountType.DEMO,
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
