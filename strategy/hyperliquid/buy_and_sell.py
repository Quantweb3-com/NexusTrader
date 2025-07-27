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
from nexustrader.schema import BookL1, Order
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

    def on_bookl1(self, bookl1: BookL1):
        if self.signal:
            symbol = "BTCUSDC-PERP.HYPERLIQUID"
            self.create_order(
                symbol=symbol,
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                price=self.price_to_precision(symbol, bookl1.ask + 20),
                amount=Decimal("0.001"),
            )
            self.create_order(
                symbol=symbol,
                side=OrderSide.SELL,
                type=OrderType.LIMIT,
                amount=Decimal("0.001"),
                price=self.price_to_precision(symbol,bookl1.bid - 20),
            )
            self.signal = False

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

    