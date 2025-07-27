import asyncio
from decimal import Decimal

from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
    LogConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide, OrderType, KlineInterval
from nexustrader.exchange import HyperLiquidAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine


HYPERLIQUID_API_KEY = settings.HYPERLIQUID.FUTURE.TESTNET_1.API_KEY
HYPERLIQUID_SECRET = settings.HYPERLIQUID.FUTURE.TESTNET_1.SECRET


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.HYPERLIQUID"])
        self.subscribe_kline(
            symbols="BTCUSDT-PERP.HYPERLIQUID", interval=KlineInterval.MINUTE_1
        )

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
            symbol = "BTCUSDT-PERP.HYPERLIQUID"
            bid = bookl1.bid

            prices = [
                self.price_to_precision(symbol, bid),
                self.price_to_precision(symbol, bid * 0.999),
                self.price_to_precision(symbol, bid * 0.998),
                self.price_to_precision(symbol, bid * 0.997),
                self.price_to_precision(symbol, bid * 0.996),
            ]

            for price in prices:
                self.create_order(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    type=OrderType.POST_ONLY,
                    amount=Decimal("0.001"),
                    price=price,
                )
            self.signal = False


log_config = LogConfig(level_stdout="DEBUG")

config = Config(
    strategy_id="buy_and_sell_hyperliquid",
    user_id="user_test",
    log_config=log_config,
    strategy=Demo(),
    basic_config={
        ExchangeType.HYPERLIQUID: BasicConfig(
            api_key=HYPERLIQUID_API_KEY,
            secret=HYPERLIQUID_SECRET,
            privateKey=HYPERLIQUID_SECRET,
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
    # try:
    #     engine.start()
    # finally:
    #     engine.dispose()

    engine._build()
    exchange = engine._exchanges[ExchangeType.HYPERLIQUID]
    exchange.load_markets()

    loop = asyncio.get_event_loop()
    connector = engine._private_connectors[HyperLiquidAccountType.TESTNET]

    # create and cancel order
    order = loop.run_until_complete(
        connector.create_order(
            symbol="ETHUSDC-PERP.HYPERLIQUID",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0.2"),
            price=Decimal("1000"),
        )
    )
    print(order)

    res = loop.run_until_complete(
        connector.cancel_order(
            symbol="ETHUSDC-PERP.HYPERLIQUID",
            oid=int(order.id),
        )
    )
    print(res)

    ## cancel all orders
    # orders = connector._api_client.get_open_orders("0x24D6E187493E4DbfFeBD16a2953d4b45B9B67a56")
    # for order in orders:
    #     print(order)
    #     res = loop.run_until_complete(connector.cancel_order(
    #         symbol="ETHUSDC-PERP.HYPERLIQUID",
    #         oid=order.oid,
    #     ))
    #     print(res)

    # Rest API testing
    user_perps_summary = connector._api_client.get_user_perps_summary(
        "0x24D6E187493E4DbfFeBD16a2953d4b45B9B67a56"
    )
    print(user_perps_summary)

    user_spot_summary = connector._api_client.get_user_spot_summary(
        "0x24D6E187493E4DbfFeBD16a2953d4b45B9B67a56"
    )
    print(user_spot_summary)

    user_active_assets = connector._api_client.get_user_active_assets(
        "0x24D6E187493E4DbfFeBD16a2953d4b45B9B67a56",
        exchange.market["ETHUSDC-PERP.HYPERLIQUID"].info.name,
    )
    print(user_active_assets)

    pass
