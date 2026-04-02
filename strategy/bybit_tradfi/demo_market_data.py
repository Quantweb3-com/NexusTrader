"""
Bybit TradeFi (MT5) — market data demo strategy.

Tests covered
-------------
1. Historical klines via request_klines()
2. Real-time BookL1 subscription (bid/ask polling)
3. Real-time Kline subscription (bar polling)
4. Real-time Trade subscription (tick-as-trade)

Prerequisites
-------------
* Windows OS with MetaTrader5 terminal installed
* MT5 terminal must be open and connected to the broker
* Fill in your credentials below (or use .keys/.secrets.toml)

Symbol notes
------------
MT5 symbol names vary by broker.  Common Bybit TradeFi symbols:
  EURUSD, GBPUSD, USDJPY, XAUUSD (Gold), US500 (S&P 500), BTCUSD
The NexusTrader symbol appends ".BYBIT_TRADFI":
  EURUSD.BYBIT_TRADFI  /  XAUUSD.BYBIT_TRADFI
"""


from nexustrader.config import (
    BasicConfig,
    Config,
    LogConfig,
    PrivateConnectorConfig,
    PublicConnectorConfig,
)
from nexustrader.constants import ExchangeType, KlineInterval, settings
from nexustrader.engine import Engine
from nexustrader.exchange.bybit_tradfi import BybitTradeFiAccountType
from nexustrader.schema import BookL1, Kline, Trade
from nexustrader.strategy import Strategy

# ---------------------------------------------------------------------------
# Credentials are loaded from .keys/.secrets.toml:
#   [BYBIT_TRADFI.DEMO]
#   API_KEY    = "12345678"        # MT5 login number
#   SECRET     = "your_password"  # MT5 password
#   PASSPHRASE = "BybitBroker-Demo"# MT5 broker server name
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

SYMBOL = "EURUSD.BYBIT_TRADFI"


class Mt5MarketDataDemo(Strategy):
    """
    Subscribes to BookL1, Kline (M1), and Trade for EURUSD.
    Also fetches the last 100 historical M1 bars at startup and prints a
    5-row summary.
    Runs for ~60 seconds then exits automatically.
    """

    def __init__(self):
        super().__init__()
        self._bookl1_count = 0
        self._kline_count = 0
        self._trade_count = 0
        self._stop_after = 250  # seconds

    def on_start(self):
        self.log.info("=== MT5 Market Data Demo starting ===")

        # ── 1. Historical klines ────────────────────────────────────────
        self.log.info(f"Requesting last 100 M1 bars for {SYMBOL} ...")
        klines = self.request_klines(
            symbol=SYMBOL,
            interval=KlineInterval.MINUTE_1,
            limit=100,
            account_type=BybitTradeFiAccountType.DEMO,
        )
        if klines:
            df = klines.df
            self.log.info(f"Historical klines received: {len(klines)} bars")
            self.log.info(f"\n{df.tail(5).to_string()}")
        else:
            self.log.warning("No historical klines returned (is MT5 connected?)")

        # ── 2. Live subscriptions ────────────────────────────────────────
        self.subscribe_bookl1(symbols=SYMBOL, ready=False)
        self.subscribe_trade(symbols=SYMBOL, ready=False)
        self.subscribe_kline(
            symbols=SYMBOL,
            interval=KlineInterval.MINUTE_1,
            ready=False,
        )

        self.log.info(f"Subscribed to BookL1 / Trade / Kline(M1) for {SYMBOL}")

        # Schedule auto-stop
        self.schedule(self._auto_stop, trigger="interval", seconds=self._stop_after)

    # ── Market data callbacks ────────────────────────────────────────────

    def on_bookl1(self, bookl1: BookL1):
        self._bookl1_count += 1
        if self._bookl1_count % 2 == 1:   # print every 50th update
            self.log.info(
                f"[BookL1] {bookl1.symbol}  "
                f"bid={bookl1.bid:.5f}  ask={bookl1.ask:.5f}  "
                f"spread={bookl1.spread:.5f}  (#{self._bookl1_count})"
            )

    def on_trade(self, trade: Trade):
        self._trade_count += 1
        if self._trade_count % 20 == 1:    # print every 20th tick
            self.log.info(
                f"[Trade]  {trade.symbol}  "
                f"price={trade.price:.5f}  side={trade.side.value}  "
                f"(#{self._trade_count})"
            )

    def on_kline(self, kline: Kline):
        self._kline_count += 1
        status = "CLOSED" if kline.confirm else "open"
        if status == "CLOSED":
            self.log.info(
                f"[Kline]  {kline.symbol} {kline.interval.value}  "
                f"O={kline.open:.5f}  H={kline.high:.5f}  "
                f"L={kline.low:.5f}  C={kline.close:.5f}  [{status}]  "
                f"(#{self._kline_count})"
            )

    # ── Auto-stop ────────────────────────────────────────────────────────

    def _auto_stop(self):
        self.log.info(
            f"=== Demo finished. "
            f"bookl1={self._bookl1_count}  "
            f"trades={self._trade_count}  "
            f"klines={self._kline_count} ==="
        )
        self.stop()


# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------

config = Config(
    strategy_id="mt5_market_data_demo",
    user_id="user_test",
    strategy=Mt5MarketDataDemo(),
    log_config=LogConfig(level_stdout="INFO"),
    basic_config={
        ExchangeType.BYBIT_TRADFI: BasicConfig(
            api_key=MT5_LOGIN,
            secret=MT5_PASSWORD,
            passphrase=MT5_SERVER,
            testnet=True,   # True = DEMO account
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
