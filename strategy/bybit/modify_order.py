from decimal import Decimal

from nexustrader.constants import settings
from nexustrader.config import Config, PublicConnectorConfig, PrivateConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide, OrderType
from nexustrader.exchange.bybit import BybitAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog

SpdLog.initialize(level="DEBUG", std_level="ERROR", production_mode=True, file_name="cancel_all.log")

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
    
    def on_canceled_order(self, order: Order):
        print(order)
    
    def on_bookl1(self, bookl1: BookL1):
        if self.signal:
            uuid = self.create_order(
                symbol="BTCUSDT-PERP.BYBIT",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                amount=Decimal("0.001"),
                price=Decimal("80000"),
            )
            self.modify_order(
                symbol="BTCUSDT-PERP.BYBIT",
                side=OrderSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("81000"),
                uuid=uuid,
            )
            self.signal = False

config = Config(
    strategy_id="bybit_buy_and_sell",
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
            )
        ]
    },
    private_conn_config={
        ExchangeType.BYBIT: [
            PrivateConnectorConfig(
                account_type=BybitAccountType.UNIFIED_TESTNET,
            )
        ]
    }
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
