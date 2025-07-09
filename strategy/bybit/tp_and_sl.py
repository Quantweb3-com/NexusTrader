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
from nexustrader.exchange import BybitAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine


BYBIT_API_KEY = settings.BYBIT.ACCOUNT1.API_KEY
BYBIT_SECRET = settings.BYBIT.ACCOUNT1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BYBIT"])

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
            symbol = "BTCUSDT-PERP.BYBIT"
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
    strategy_id="bybit_tp_sl_order",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BYBIT: BasicConfig(
            api_key=BYBIT_API_KEY,
            secret=BYBIT_SECRET,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.BYBIT: [
            PublicConnectorConfig(
                account_type=BybitAccountType.LINEAR_TESTNET,
            ),
        ]
    },
    private_conn_config={
        ExchangeType.BYBIT: [
            PrivateConnectorConfig(
                account_type=BybitAccountType.UNIFIED_TESTNET,
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
