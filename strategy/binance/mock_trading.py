from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
    MockConnectorConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange import BinanceAccountType
from nexustrader.engine import Engine

from nexustrader.constants import OrderSide, OrderType
from decimal import Decimal


BINANCE_API_KEY = settings.BINANCE.LIVE.ACCOUNT1.API_KEY
BINANCE_SECRET = settings.BINANCE.LIVE.ACCOUNT1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BINANCE"])
        self.schedule(func=self.signal, trigger="interval", seconds=10)

    def signal(self):
        self.create_order(
            symbol="BTCUSDT-PERP.BINANCE",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=Decimal("0.001"),
        )


config = Config(
    strategy_id="subscribe_klines_binance",
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
            MockConnectorConfig(
                account_type=BinanceAccountType.LINEAR_MOCK,
                initial_balance={"USDT": 10_000},
                quote_currency="USDT",
                update_interval=20,
                overwrite_balance=True,
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
