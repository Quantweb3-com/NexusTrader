"""
Bybit TradeFi (MT5) — trading demo strategy.

Tests covered
-------------
1. Account balance check on startup
2. Open position check on startup
3. Place a LIMIT buy order (well below market so it stays pending)
4. Confirm ACCEPTED status callback
5. Cancel the pending order after 10 s
6. Confirm CANCELED status callback
7. Place a MARKET buy (small lot) and confirm FILLED
8. Print final balance / position summary

WARNING
-------
This strategy places REAL orders on the configured MT5 account.
Use a DEMO account (testnet=True) when testing.

Prerequisites
-------------
* Windows OS with MetaTrader5 terminal installed and logged in
* Fill in your credentials below
"""

from datetime import datetime, timedelta
from decimal import Decimal

from nexustrader.config import (
    BasicConfig,
    Config,
    LogConfig,
    PrivateConnectorConfig,
    PublicConnectorConfig,
)
from nexustrader.constants import ExchangeType, OrderSide, OrderType
from nexustrader.engine import Engine
from nexustrader.exchange.bybit_tradfi import BybitTradeFiAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.strategy import Strategy
from nexustrader.constants import settings

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
try:
    MT5_LOGIN    = settings.BYBIT_TRADFI.DEMO.API_KEY
    MT5_PASSWORD = settings.BYBIT_TRADFI.DEMO.SECRET
    MT5_SERVER   = settings.BYBIT_TRADFI.DEMO.PASSPHRASE
except AttributeError as e:
    raise SystemExit(
        "Missing BYBIT_TRADFI credentials. "
        "Please add the following to your .secrets.toml:\n\n"
        "  [BYBIT_TRADFI.DEMO]\n"
        "  API_KEY    = \"<MT5 login number>\"\n"
        "  SECRET     = \"<MT5 password>\"\n"
        "  PASSPHRASE = \"<MT5 broker server name>\"\n"
    ) from e

SYMBOL = "XAUUSD_s.BYBIT_TRADFI"

# Small lot size – adjust to the minimum allowed by your broker
LOT = Decimal("0.01")


class Mt5TradingDemo(Strategy):
    """
    Step-by-step order lifecycle test via MT5.

    Timeline (approximate):
      t=0   startup – print balance & positions, subscribe BookL1
      t=5s  place a LIMIT buy 2% below mid (should stay pending)
      t=15s cancel the pending limit order
      t=20s place a MARKET buy (minimum lot)
      t=40s exit
    """

    def __init__(self):
        super().__init__()
        self._pending_oid: str | None = None
        self._market_oid: str | None = None
        self._bookl1_ready = False

    def on_start(self):
        self.log.info("=== MT5 Trading Demo starting ===")

        # ── Print account state ──────────────────────────────────────────
        balance = self.cache.get_balance(BybitTradeFiAccountType.DEMO)
        if balance:
            self.log.info(f"Account balance: {balance}")
        else:
            self.log.warning("Balance not yet available (will be populated after connect)")

        positions = self.cache.get_all_positions(ExchangeType.BYBIT_TRADFI)
        if positions:
            self.log.info(f"Open positions: {positions}")
        else:
            self.log.info("No open positions.")

        # ── Subscribe BookL1 – needed to get a reference price ───────────
        self.subscribe_bookl1(symbols=SYMBOL, ready=False)

        # ── Schedule order tests (each fires exactly once via trigger="date") ──
        now = datetime.now()
        self.schedule(self._place_limit_order,  trigger="date", run_date=now + timedelta(seconds=5))
        self.schedule(self._cancel_limit_order, trigger="date", run_date=now + timedelta(seconds=15))
        self.schedule(self._place_market_order, trigger="date", run_date=now + timedelta(seconds=20))
        self.schedule(self._finish,             trigger="date", run_date=now + timedelta(seconds=40))

    # ── BookL1 callback ──────────────────────────────────────────────────

    def on_bookl1(self, bookl1: BookL1):
        if not self._bookl1_ready:
            self._bookl1_ready = True
            self.log.info(
                f"[BookL1] {bookl1.symbol}  "
                f"bid={bookl1.bid:.5f}  ask={bookl1.ask:.5f}  "
                f"spread={bookl1.spread:.5f}"
            )

    # ── Order status callbacks ───────────────────────────────────────────

    def on_pending_order(self, order: Order):
        self.log.info(f"[ORDER PENDING]   oid={order.oid}  {order.side.value} {order.amount} @ {order.price}")

    def on_accepted_order(self, order: Order):
        self.log.info(f"[ORDER ACCEPTED]  oid={order.oid}  {order.side.value} {order.amount} @ {order.price}")

    def on_filled_order(self, order: Order):
        self.log.info(
            f"[ORDER FILLED]    oid={order.oid}  {order.side.value} {order.amount}"
            f"  avg={order.average}"
        )
        pos = self.cache.get_position(SYMBOL)
        if pos:
            self.log.info(
                f"  → Position: {pos.side.value if pos.side else 'FLAT'}  "
                f"amount={pos.amount}  entry={pos.entry_price:.5f}  "
                f"uPnL={pos.unrealized_pnl:.2f}"
            )

    def on_canceled_order(self, order: Order):
        self.log.info(f"[ORDER CANCELED]  oid={order.oid}")

    def on_failed_order(self, order: Order):
        self.log.error(f"[ORDER FAILED]    oid={order.oid}  symbol={order.symbol}")

    def on_cancel_failed_order(self, order: Order):
        self.log.error(f"[CANCEL FAILED]   oid={order.oid}")

    # ── Scheduled steps ──────────────────────────────────────────────────

    def _place_limit_order(self):
        book = self.cache.bookl1(SYMBOL)
        if book is None:
            self.log.warning("BookL1 not ready yet – skipping limit order placement")
            return

        # Place limit 2% below current bid (very unlikely to fill)
        limit_price = self.price_to_precision(SYMBOL, book.bid * 0.98)
        self.log.info(f"Placing LIMIT BUY  {LOT} {SYMBOL} @ {limit_price}")

        self._pending_oid = self.create_order(
            symbol=SYMBOL,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=LOT,
            price=limit_price,
        )
        self.log.info(f"  → oid={self._pending_oid}")

    def _cancel_limit_order(self):
        if self._pending_oid is None:
            self.log.warning("No pending order to cancel")
            return
        open_orders = self.cache.get_open_orders(SYMBOL)
        if self._pending_oid not in open_orders:
            self.log.info("Limit order already closed – nothing to cancel")
            return
        self.log.info(f"Canceling limit order oid={self._pending_oid}")
        self.cancel_order(symbol=SYMBOL, oid=self._pending_oid)

    def _place_market_order(self):
        book = self.cache.bookl1(SYMBOL)
        if book is None:
            self.log.warning("BookL1 not ready – skipping market order")
            return
        self.log.info(f"Placing MARKET BUY {LOT} {SYMBOL}")
        
        self._market_oid = self.create_order(
            symbol=SYMBOL,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            amount=LOT,
        )
        
        self.log.info(f"  → oid={self._market_oid}")

    def _finish(self):
        balance = self.cache.get_balance(BybitTradeFiAccountType.DEMO)
        self.log.info(f"Final balance: {balance}")
        pos = self.cache.get_position(SYMBOL)
        if pos and pos.is_opened:
            self.log.info(
                f"Final position: {pos.side.value}  amount={pos.amount}  "
                f"entry={pos.entry_price:.5f}  uPnL={pos.unrealized_pnl:.2f}"
            )
        self.log.info("=== MT5 Trading Demo finished ===")
        self.stop()


# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------

config = Config(
    strategy_id="mt5_trading_demo",
    user_id="user_test",
    strategy=Mt5TradingDemo(),
    log_config=LogConfig(level_stdout="INFO"),
    basic_config={
        ExchangeType.BYBIT_TRADFI: BasicConfig(
            api_key=MT5_LOGIN,
            secret=MT5_PASSWORD,
            passphrase=MT5_SERVER,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.BYBIT_TRADFI: [
            PublicConnectorConfig(
                account_type=BybitTradeFiAccountType.DEMO,
            )
        ]
    },
    private_conn_config={
        ExchangeType.BYBIT_TRADFI: [
            PrivateConnectorConfig(
                account_type=BybitTradeFiAccountType.DEMO,
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
