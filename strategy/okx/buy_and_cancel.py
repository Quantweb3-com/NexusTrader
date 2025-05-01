from decimal import Decimal
from nexustrader.constants import settings
from nexustrader.config import Config, PublicConnectorConfig, PrivateConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide, OrderType
from nexustrader.exchange.okx import OkxAccountType 
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog

SpdLog.initialize(level="DEBUG", std_level="ERROR", production_mode=True, file_name="buy_and_cancel.log")

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
            self.create_order(
                symbol="BTCUSDT.OKX",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.1"),
            )
            self.create_order(
                symbol="BTCUSDT-PERP.OKX",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.1"),
            )  
            self.signal = False
        

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
    }
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
