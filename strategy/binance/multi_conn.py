##################################################################################################
## Buy and sell USDC on Binance Spot and Future                                                 ##
##                                                                                              ##
## This strategy is used to buy and sell USDC on Binance Spot and Future.                       ##
## It uses the Binance Spot and Future account to buy and sell USDC.                            ##
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
from nexustrader.core.log import SpdLog

SpdLog.initialize(level="INFO", production_mode=True)


BINANCE_API_KEY = settings.BINANCE.LIVE.ACCOUNT1.API_KEY
BINANCE_SECRET = settings.BINANCE.LIVE.ACCOUNT1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl1(symbols=["USDCUSDT-PERP.BINANCE", "USDCUSDT.BINANCE"])

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
                symbol="USDCUSDT.BINANCE",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("6"),
            )
            self.create_order(
                symbol="USDCUSDT.BINANCE",
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                amount=Decimal("6"),
            )
            self.create_order(
                symbol="USDCUSDT-PERP.BINANCE",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("6"),
            )
            self.create_order(
                symbol="USDCUSDT-PERP.BINANCE",
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                amount=Decimal("6"),
                reduce_only=True,
            )
            self.signal = False


config = Config(
    strategy_id="multi_conn_binance",
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
            ),
            PublicConnectorConfig(
                account_type=BinanceAccountType.SPOT,
            ),
        ]
    },
    private_conn_config={
        ExchangeType.BINANCE: [
            PrivateConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE,
            ),
            PrivateConnectorConfig(
                account_type=BinanceAccountType.SPOT,
            ),
        ]
    },
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
