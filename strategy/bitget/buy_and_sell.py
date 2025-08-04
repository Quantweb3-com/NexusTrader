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
from nexustrader.exchange import BitgetAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine


API_KEY = settings.BITGET.DEMO1.API_KEY
SECRET = settings.BITGET.DEMO1.SECRET
PASSPHRASE = settings.BITGET.DEMO1.PASSPHRASE


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BITGET"])

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
            symbol = "BTCUSDT-PERP.BITGET"
            self.create_order(
                symbol=symbol,
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.001"),
            )
            self.create_order(
                symbol=symbol,
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                amount=Decimal("0.001"),
            )
            self.signal = False


config = Config(
    strategy_id="buy_and_sell_bitget",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BITGET: BasicConfig(
            api_key=API_KEY,
            secret=SECRET,
            passphrase=PASSPHRASE,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.BITGET: [
            PublicConnectorConfig(
                account_type=BitgetAccountType.UTA_DEMO,
                enable_rate_limit=True,
            )
        ]
    },
    private_conn_config={
        ExchangeType.BITGET: [
            PrivateConnectorConfig(
                account_type=BitgetAccountType.FUTURE_DEMO,
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
