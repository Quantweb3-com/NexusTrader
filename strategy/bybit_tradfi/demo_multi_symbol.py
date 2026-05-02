"""
Bybit TradeFi (MT5) — multi-symbol market data demo.

Subscribes to BookL1 for EURUSD, XAUUSD (Gold), and BTCUSD simultaneously,
logs mid-price every 5 seconds for each symbol, and exits after 60 s.

Demonstrates that multiple MT5 symbols can be polled concurrently via the
single-threaded executor without blocking each other.
"""

from nexustrader.config import (
    BasicConfig,
    Config,
    LogConfig,
    PrivateConnectorConfig,
    PublicConnectorConfig,
)
from nexustrader.constants import ExchangeType, KlineInterval
from nexustrader.engine import Engine
from nexustrader.exchange.bybit_tradfi import BybitTradeFiAccountType
from nexustrader.schema import BookL1, Kline
from nexustrader.strategy import Strategy

from nexustrader.constants import settings

try:
    MT5_LOGIN = settings.BYBIT_TRADFI.DEMO.API_KEY
    MT5_PASSWORD = settings.BYBIT_TRADFI.DEMO.SECRET
    MT5_SERVER = settings.BYBIT_TRADFI.DEMO.PASSPHRASE
except AttributeError as e:
    raise SystemExit(
        "Missing BYBIT_TRADFI credentials. "
        "Please add the following to your .secrets.toml:\n\n"
        "  [BYBIT_TRADFI.DEMO]\n"
        '  API_KEY    = "<MT5 login number>"\n'
        '  SECRET     = "<MT5 password>"\n'
        '  PASSPHRASE = "<MT5 broker server name>"\n'
    ) from e

SYMBOLS = [
    "EURUSD.BYBIT_TRADFI",
    "XAUUSD_s.BYBIT_TRADFI",
    "TSLA_s.BYBIT_TRADFI",
]


class Mt5MultiSymbolDemo(Strategy):
    def __init__(self):
        super().__init__()
        self._last_mid: dict[str, float] = {}
        self._tick: int = 0

    def on_start(self):
        self.log.info(f"Subscribing to {len(SYMBOLS)} symbols ...")
        self.subscribe_bookl1(symbols=SYMBOLS, ready=False)
        self.subscribe_kline(
            symbols=SYMBOLS,
            interval=KlineInterval.MINUTE_1,
            ready=False,
        )
        # Print summary every 5 seconds
        self.schedule(self._print_summary, trigger="interval", seconds=5)
        # Stop after 60 seconds
        self.schedule(self._stop, trigger="interval", seconds=60)

    def on_bookl1(self, bookl1: BookL1):
        self._last_mid[bookl1.symbol] = bookl1.mid

    def on_kline(self, kline: Kline):
        if kline.confirm:
            self.log.info(
                f"[BAR CLOSED] {kline.symbol}  "
                f"O={kline.open}  H={kline.high}  L={kline.low}  C={kline.close}"
            )

    def _print_summary(self):
        self._tick += 1
        lines = [f"── Tick #{self._tick} ──────────────────"]
        for sym in SYMBOLS:
            mid = self._last_mid.get(sym)
            if mid:
                lines.append(f"  {sym:<30}  mid={mid:.5f}")
            else:
                lines.append(f"  {sym:<30}  (no data yet)")
        self.log.info("\n".join(lines))

    def _stop(self):
        self.log.info("Demo complete.")
        self.stop()


config = Config(
    strategy_id="mt5_multi_symbol_demo",
    user_id="user_test",
    strategy=Mt5MultiSymbolDemo(),
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
            PublicConnectorConfig(account_type=BybitTradeFiAccountType.DEMO)
        ]
    },
    private_conn_config={
        ExchangeType.BYBIT_TRADFI: [
            PrivateConnectorConfig(account_type=BybitTradeFiAccountType.DEMO)
        ]
    },
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
