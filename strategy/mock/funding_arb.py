"""
long bnc short okx

funding_diff bnc - okx < 0
px_diff bnc - okx < 0

edge = -funding_diff - px_diff
"""

from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    BasicConfig,
    PrivateConnectorConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType
from nexustrader.exchange.binance import BinanceAccountType
from nexustrader.exchange.okx import OkxAccountType
from nexustrader.schema import BookL1, Order, OrderSide, OrderType, FundingRate, Trade
from nexustrader.core.entity import DataReady, RateLimit, MovingAverage
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog
from nexustrader.exchange.okx.schema import OkxMarket
from decimal import Decimal
from datetime import datetime, timedelta

SpdLog.initialize(
    level="INFO",
    std_level="ERROR",
    production_mode=True,
    file_name="funding_rate_order.log",
)


BINANCE_API_KEY = settings.BINANCE.LIVE.ACCOUNT3.API_KEY
BINANCE_SECRET = settings.BINANCE.LIVE.ACCOUNT3.SECRET
OKX_API_KEY = settings.OKX.LIVE3.API_KEY
OKX_SECRET = settings.OKX.LIVE3.SECRET
OKX_PASSPHRASE = settings.OKX.LIVE3.PASSPHRASE


class Demo(Strategy):
    def __init__(self, args=None):
        super().__init__()
        self.symbol = "SWELLUSDT-PERP"
        
        self.okx_symbol = f"{self.symbol}.OKX"
        self.bnc_symbol = f"{self.symbol}.BINANCE"
        
        self.trade_ready = DataReady(symbols=[self.okx_symbol, self.bnc_symbol])
        self.funding_ready = DataReady(symbols=[self.okx_symbol, self.bnc_symbol])
        self.book_ready = DataReady(symbols=[self.okx_symbol, self.bnc_symbol])
        
        self.avg = MovingAverage(length=30, method='median')

    def on_start(self):
        self.subscribe_bookl1(symbols=[self.okx_symbol, self.bnc_symbol])
        self.subscribe_funding_rate(symbols=[self.okx_symbol, self.bnc_symbol])
        self.subscribe_trade(symbols=[self.okx_symbol, self.bnc_symbol])
        # Option 1: Using next_run_time to specify when the first run happens
        next_run = datetime.now() + timedelta(seconds=15)  # Run after 1 minute
        self.schedule(
            func=self.cal_edge,
            trigger="interval",
            seconds=1,
            next_run_time=next_run,
        )
    
    def on_bookl1(self, book: BookL1):
        self.book_ready.input(book)
    
    def on_funding_rate(self, funding_rate: FundingRate):
        self.funding_ready.input(funding_rate)
    
    def on_trade(self, trade: Trade):
        self.trade_ready.input(trade)
        
        
    def _get_funding_diff(self):
        bnc_funding = self.cache.funding_rate(self.bnc_symbol)
        okx_funding = self.cache.funding_rate(self.okx_symbol)
        if bnc_funding.next_funding_time > okx_funding.next_funding_time:
            return 0 - okx_funding.rate
        elif bnc_funding.next_funding_time < okx_funding.next_funding_time:
            return bnc_funding.rate - 0
        else:
            return bnc_funding.rate - okx_funding.rate
    
    def _get_px_diff(self):
        bnc_px = self.cache.trade(self.bnc_symbol).price
        okx_px = self.cache.trade(self.okx_symbol).price
        
        return bnc_px - okx_px
        
    
    def cal_edge(self):
        if not self.funding_ready.ready or not self.trade_ready.ready:
            return
        funding_diff = self._get_funding_diff()
        px_diff = self._get_px_diff()
        edge = -funding_diff - px_diff
        
        avg = self.avg.input(edge)
        if avg:
            print(f"funding_diff: {funding_diff}, px_diff: {px_diff}, edge: {edge}, avg: {avg}")
        


if __name__ == "__main__":
    config = Config(
        strategy_id="funding_arb",
        user_id="user_test",
        strategy=Demo(),
        basic_config={
            ExchangeType.BINANCE: BasicConfig(
                api_key=BINANCE_API_KEY,
                secret=BINANCE_SECRET,
                testnet=False,
            ),
            ExchangeType.OKX: BasicConfig(
                api_key=OKX_API_KEY,
                secret=OKX_SECRET,
                passphrase=OKX_PASSPHRASE,
                testnet=False,
            ),
        },
        public_conn_config={
            ExchangeType.BINANCE: [
                PublicConnectorConfig(
                    account_type=BinanceAccountType.USD_M_FUTURE,
                )
            ],
            ExchangeType.OKX: [
                PublicConnectorConfig(
                    account_type=OkxAccountType.LIVE,
                )
            ],
        },
        private_conn_config={
            ExchangeType.BINANCE: [
                PrivateConnectorConfig(
                    account_type=BinanceAccountType.USD_M_FUTURE,
                    rate_limit=RateLimit(
                        max_rate=20,
                        time_period=1,
                    ),
                )
            ],
            ExchangeType.OKX: [
                PrivateConnectorConfig(
                    account_type=OkxAccountType.LIVE,
                    rate_limit=RateLimit(
                        max_rate=20,
                        time_period=1,
                    ),
                )
            ],
        },
    )

    engine = Engine(config)

    try:
        engine.start()
    finally:
        engine.dispose()
