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
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.OKX"])

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
            self.create_tp_sl_order(
                symbol=symbol,
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.001"),
                tp_order_type=OrderType.MARKET,
                tp_trigger_price=self.price_to_precision(
                    symbol, price=bookl1.ask * 1.01
                ),
                sl_order_type=OrderType.MARKET,
                sl_trigger_price=self.price_to_precision(
                    symbol, price=bookl1.bid * 0.99
                ),
            )
            self.signal = False


config = Config(
    strategy_id="demo_tp_and_sl",
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
