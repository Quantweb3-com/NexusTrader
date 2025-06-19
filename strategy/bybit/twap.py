from decimal import Decimal

from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide
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

    def on_canceled_order(self, order: Order):
        print(f"canceled: {order.uuid}")

    def on_accepted_order(self, order: Order):
        print(f"accepted: {order.uuid}")

    def on_partial_filled_order(self, order: Order):
        print(f"partial filled: {order.uuid}")

    def on_filled_order(self, order: Order):
        print(f"filled: {order.uuid}")

    def on_bookl1(self, bookl1: BookL1):
        if self.signal:
            self.create_twap(
                symbol="BTCUSDT-PERP.BYBIT",
                side=OrderSide.BUY,
                amount=Decimal("0.3"),
                duration=60 * 5,
                wait=3,
            )
            self.signal = False
        position = self.cache.get_position("BTCUSDT-PERP.BYBIT")
        print(f"position: {position}")


config = Config(
    strategy_id="bybit_twap",
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
            PublicConnectorConfig(
                account_type=BybitAccountType.SPOT_TESTNET,
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
