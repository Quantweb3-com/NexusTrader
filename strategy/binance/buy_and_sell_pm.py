##################################################################################################
## Buy and sell USDC on Binance Portfolio Margin                                                ##
##                                                                                              ##
## This strategy is used to buy and sell USDC on Binance Portfolio Margin.                      ##
## It uses the Binance Portfolio Margin account to buy and sell USDC.                           ##
##                                                                                              ##
## Author: @river                                                                               ##
##################################################################################################
## ███    ██ ███████ ██   ██ ██    ██ ███████ ████████ ██████   █████  ██████   ███████ ██████  ##
## ████   ██ ██       ██ ██  ██    ██ ██         ██    ██   ██ ██   ██ ██   ██  ██      ██   ██ ##
## ██ ██  ██ █████     ███   ██    ██ ███████    ██    ██████  ███████ ██   ██  █████   ██████  ##
## ██  ██ ██ ██       ██ ██  ██    ██      ██    ██    ██   ██ ██   ██ ██   ██  ██      ██   ██ ##
## ██   ████ ███████ ██   ██  ██████  ███████    ██    ██   ██ ██   ██ ██████   ███████ ██   ██ ##
##################################################################################################

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
from nexustrader.exchange import BinanceAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine


BINANCE_API_KEY = settings.BINANCE.PM.ACCOUNT1.API_KEY
BINANCE_SECRET = settings.BINANCE.PM.ACCOUNT1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl1(symbols=["USDCUSDT-PERP.BINANCE"])

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
            self.create_order(
                symbol="USDCUSDT-PERP.BINANCE",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("10"),
            )
            self.create_order(
                symbol="USDCUSDT-PERP.BINANCE",
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                amount=Decimal("25"),
                reduce_only=True,
            )
            self.signal = False


config = Config(
    strategy_id="buy_and_sell_binance",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
            api_key=BINANCE_API_KEY,
            secret=BINANCE_SECRET,
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.BINANCE: [
            PublicConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE,
            )
        ]
    },
    private_conn_config={
        ExchangeType.BINANCE: [
            PrivateConnectorConfig(
                account_type=BinanceAccountType.PORTFOLIO_MARGIN,
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
