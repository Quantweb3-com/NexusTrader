from decimal import Decimal
import math
from nexustrader.constants import settings
from nexustrader.config import Config, PublicConnectorConfig, PrivateConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide, OrderType
from nexustrader.exchange.bybit import BybitAccountType
from nexustrader.schema import Trade, Order
from nexustrader.engine import Engine



BYBIT_API_KEY = settings.BYBIT.LIVE.ACCOUNT1.API_KEY
BYBIT_SECRET = settings.BYBIT.LIVE.ACCOUNT1.SECRET

BASE_AMOUNT = 1 # SOL
QUOTE_AMOUNT = 138.1530 # USDT

class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True
        self.last_price = QUOTE_AMOUNT / BASE_AMOUNT
        self.hedge_threshold = 0.001
        self.liquidity_constant = math.sqrt(BASE_AMOUNT * QUOTE_AMOUNT)
    
    def on_start(self):
        self.symbol = "SOLUSDT-PERP.BYBIT"
        self.subscribe_trade(symbols=self.symbol)
        self.subscribe_bookl1(symbols=self.symbol)
    
    def on_trade(self, trade: Trade):
        target = self.liquidity_constant / math.sqrt(trade.price)
        price_change = abs(trade.price / self.last_price - 1)
        if price_change >= self.hedge_threshold:
            print(f"Target: {target}, Last Price: {self.last_price}, Current Price: {trade.price}")
            self.last_price = trade.price
            
            min_order_amount = self.min_order_amount(self.symbol)
            
            curr_pos = self.cache.get_position(symbol=self.symbol).value_or(None)
            if curr_pos is None:
                target = self.amount_to_precision(symbol=self.symbol, amount=target)
                
                if target >= min_order_amount:   
                    self.create_order(
                        symbol=self.symbol,
                        side=OrderSide.SELL,
                        type=OrderType.MARKET,
                        amount=target,
                    )
            else:
                diff = target - float(curr_pos.amount)
                if diff > 0:
                    amount = self.amount_to_precision(symbol=self.symbol, amount=diff)
                    if amount >= min_order_amount:
                        self.create_order(
                            symbol=self.symbol,
                            side=OrderSide.SELL,
                            type=OrderType.MARKET,
                            amount=amount,
                        )
                elif diff < 0:
                    amount = self.amount_to_precision(symbol=self.symbol, amount=abs(diff))
                    if amount >= min_order_amount:
                        self.create_order(
                            symbol=self.symbol,
                            side=OrderSide.BUY,
                            type=OrderType.MARKET,
                            amount=amount,
                        )

config = Config(
    strategy_id="bybit_lp_hedge",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BYBIT: BasicConfig(
            api_key=BYBIT_API_KEY,
            secret=BYBIT_SECRET,
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.BYBIT: [
            PublicConnectorConfig(
                account_type=BybitAccountType.LINEAR,
            )
        ]
    },
    private_conn_config={
        ExchangeType.BYBIT: [
            PrivateConnectorConfig(
                account_type=BybitAccountType.UNIFIED,
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
