import math
from nexustrader.constants import settings
from nexustrader.config import Config, PublicConnectorConfig, PrivateConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide, OrderType
from nexustrader.exchange.bybit import BybitAccountType
from nexustrader.schema import Trade
from nexustrader.engine import Engine
from nexustrader.core.log import SpdLog

SpdLog.initialize(level="INFO", std_level="ERROR", production_mode=True)


BYBIT_API_KEY = settings.BYBIT.LIVE.ACCOUNT2.API_KEY
BYBIT_SECRET = settings.BYBIT.LIVE.ACCOUNT2.SECRET

BASE_AMOUNT = 321.843719 # SUI
QUOTE_AMOUNT = 952.7604 # USDT

class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True
        self.last_price = QUOTE_AMOUNT / BASE_AMOUNT
        self.hedge_threshold = 0.001
        self.liquidity_constant = math.sqrt(BASE_AMOUNT * QUOTE_AMOUNT)
    
    def on_start(self):
        self.symbol = "SUIUSDT-PERP.BYBIT"
        self.subscribe_trade(symbols=self.symbol)
        self.subscribe_bookl1(symbols=self.symbol)
        self.schedule(self.hedge_trade, trigger="cron", minute="*")
    
    def hedge_trade(self):
        price = self.cache.trade(symbol=self.symbol).price
        target = self.liquidity_constant / math.sqrt(price)
        price_change = abs(price / self.last_price - 1)
        
        if price_change < self.hedge_threshold:
            return
            
        min_order_amount = self.min_order_amount(self.symbol)
        curr_pos = self.cache.get_position(symbol=self.symbol).value_or(None)
        current_amount = float(curr_pos.amount) if curr_pos else 0
        
        diff = target - current_amount
        if abs(diff) < min_order_amount:
            return
            
        # Determine order side and amount
        side = OrderSide.SELL if diff > 0 else OrderSide.BUY
        amount = self.amount_to_precision(symbol=self.symbol, amount=abs(diff))
        
        self.log.info(f"Position adjustment: {current_amount} -> {target}, Price: {self.last_price} -> {price}")
        
        # Create order
        self.create_order(
            symbol=self.symbol,
            side=side,
            type=OrderType.MARKET,
            amount=amount,
        )
        self.log.info(f"[{side.name}]: {amount}")
        self.last_price = price

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
