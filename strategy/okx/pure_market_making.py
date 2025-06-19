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
from nexustrader.exchange import OkxAccountType
from nexustrader.schema import BookL1, Order, AccountBalance
from nexustrader.engine import Engine
from nexustrader.core.nautilius_core import LiveClock


OKX_API_KEY = settings.OKX.DEMO_1.api_key
OKX_SECRET = settings.OKX.DEMO_1.secret
OKX_PASSPHRASE = settings.OKX.DEMO_1.passphrase


class PureMarketMaking(Strategy):
    def __init__(self):
        super().__init__()
        self.clock = LiveClock()
        # 配置交易对

        # 基础策略参数
        self.bid_spread = 0.001  # 买单价差 0.1%
        self.ask_spread = 0.001  # 卖单价差 0.1%
        self.order_amount = 0.001  # 订单基础数量
        self.min_spread = 0.0002  # 最小价差 0.02%
        self.order_refresh_time = 60  # 订单刷新时间(秒)

        # 库存管理参数
        self.inventory_target_base_pct = 0.5  # 目标基础资产占比 50%
        self.inventory_range_multiplier = 0.5  # 库存范围乘数
        self.inventory_skew_enabled = True  # 是否启用库存偏移

        # 状态变量
        self.last_order_refresh_timestamp = 0
        self.active_orders = set()  # 追踪活跃订单

        # store balance
        self.balance: dict[str, Decimal] = {}

    def on_start(self):
        self.subscribe_bookl1(symbols=["BTCUSDT.OKX"])

    def on_balance(self, balance: AccountBalance):
        self.balance = balance.balance_total

    def get_balance(self, sym_base: str) -> float:
        return float(str(self.balance.get(sym_base, Decimal("0"))))

    def get_inventory_ratios(self, mid_price: float) -> tuple[float, float]:
        """计算当前库存比例和目标偏差"""
        # 获取账户余额
        base_balance = self.get_balance("BTC")
        quote_balance = self.get_balance("USDT")

        # 计算总资产价值(以USDT计价)
        total_value = base_balance * mid_price + quote_balance
        if total_value == 0:
            return 0.5, 0.5

        # 计算当前基础资产占比
        current_base_ratio = (base_balance * mid_price) / total_value

        # 计算库存范围
        target_base_ratio = self.inventory_target_base_pct
        inventory_range = (
            self.order_amount
            * mid_price
            * self.inventory_range_multiplier
            / total_value
        )

        # 较大的 inventory_range（通过增加 inventory_range_multiplier）会使调整更加温和
        # 较小的 inventory_range 会使调整更加激进

        # 根据当前位置计算买卖订单比例 （在偏离目标时，通过调整买卖单的数量来逐步回归目标配比）
        if current_base_ratio < target_base_ratio:
            bid_ratio = 1
            ask_ratio = 1 - (target_base_ratio - current_base_ratio) / inventory_range
            ask_ratio = max(0, min(ask_ratio, 1))
        else:
            ask_ratio = 1
            bid_ratio = 1 - (current_base_ratio - target_base_ratio) / inventory_range
            bid_ratio = max(0, min(bid_ratio, 1))

        return bid_ratio, ask_ratio

    def get_adjusted_amounts(self, mid_price: float) -> tuple[float, float]:
        """根据库存情况调整买卖订单数量"""
        if not self.inventory_skew_enabled:
            return self.order_amount, self.order_amount

        bid_ratio, ask_ratio = self.get_inventory_ratios(mid_price)
        bid_amount = self.order_amount * bid_ratio
        ask_amount = self.order_amount * ask_ratio

        # 确保订单数量符合交易所最小交易量要求
        min_amount = self.market("BTCUSDT.OKX").limits.amount.min
        bid_amount = max(bid_amount, min_amount)
        ask_amount = max(ask_amount, min_amount)

        return bid_amount, ask_amount

    def on_failed_order(self, order: Order):
        self.active_orders.discard(order.id)
        print(f"Order failed: {order}")

    def on_pending_order(self, order: Order):
        print(f"Order pending: {order}")

    def on_accepted_order(self, order: Order):
        self.active_orders.add(order.id)
        print(f"Order accepted: {order}")

    def on_filled_order(self, order: Order):
        self.active_orders.discard(order.id)
        print(f"Order filled: {order}")

    def on_canceled_order(self, order: Order):
        self.active_orders.discard(order.id)
        print(f"Order canceled: {order}")

    def on_bookl1(self, bookl1: BookL1):
        current_timestamp = self.clock.timestamp_ms()

        # 检查是否需要刷新订单
        if (
            current_timestamp - self.last_order_refresh_timestamp
            < self.order_refresh_time
        ):
            return

        # 取消现有订单
        for order_id in list(self.active_orders):
            self.cancel_order(symbol="BTCUSDT.OKX", order_id=order_id)

        # 计算买卖价格
        mid_price = (bookl1.bid + bookl1.ask) / 2
        bid_price = mid_price * (1 - self.bid_spread)
        ask_price = mid_price * (1 + self.ask_spread)

        # 检查价差是否满足最小要求
        current_spread = (ask_price - bid_price) / mid_price
        if current_spread < self.min_spread:
            return

        # 获取考虑库存因素后的订单数量
        bid_amount, ask_amount = self.get_adjusted_amounts(mid_price)

        # 创建新的买卖订单
        if bid_amount > 0:
            self.create_order(
                symbol="BTCUSDT.OKX",
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                price=self.price_to_precision("BTCUSDT.OKX", bid_price),
                amount=self.amount_to_precision("BTCUSDT.OKX", bid_amount),
            )

        if ask_amount > 0:
            self.create_order(
                symbol="BTCUSDT.OKX",
                side=OrderSide.SELL,
                type=OrderType.LIMIT,
                price=self.price_to_precision("BTCUSDT.OKX", ask_price),
                amount=self.amount_to_precision("BTCUSDT.OKX", ask_amount),
            )

        self.last_order_refresh_timestamp = current_timestamp


config = Config(
    strategy_id="okx_pure_market_making",
    user_id="user_test",
    strategy=PureMarketMaking(),
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
    },
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
