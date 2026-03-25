"""
Gold Arbitrage — Market Data Monitor
=====================================
Simultaneously subscribes to:
  * XAUUSDT-PERP.BYBIT       — Bybit linear perpetual (WebSocket)
  * XAUUSD.BYBIT_TRADFI       — Bybit TradeFi MT5 spot (polling)

No orders are placed.  The strategy logs a spread summary every 3 seconds
so you can verify that both feeds are stable and in sync.

Spread definition
-----------------
  spread       = bybit_mid - mt5_mid   (positive → perp premium)
  spread_pct   = spread / mt5_mid * 100

Prerequisites
-------------
* Windows OS with MetaTrader5 terminal installed and connected
* Fill in credentials in .keys/.secrets.toml:
    [BYBIT_TRADFI.DEMO]
    API_KEY    = "<MT5 login number>"
    SECRET     = "<MT5 password>"
    PASSPHRASE = "<broker server name, e.g. BybitBroker-Demo>"
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
from nexustrader.exchange import BybitAccountType
from nexustrader.exchange.bybit_tradfi import BybitTradeFiAccountType
from nexustrader.schema import BookL1, Kline
from nexustrader.strategy import Strategy

# ---------------------------------------------------------------------------
# Credentials (MT5 side only; Bybit public feed needs no API key)
# ---------------------------------------------------------------------------
MT5_LOGIN    = settings.BYBIT_TRADFI.DEMO.API_KEY
MT5_PASSWORD = settings.BYBIT_TRADFI.DEMO.SECRET
MT5_SERVER   = settings.BYBIT_TRADFI.DEMO.PASSPHRASE

# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------
BYBIT_SYMBOL = "XAUUSDT-PERP.BYBIT"    # Bybit linear perpetual (USDT-margined)
MT5_SYMBOL   = "XAUUSD_s.BYBIT_TRADFI"   # MT5 spot gold (broker symbol: XAUUSD)

SUMMARY_INTERVAL = 3   # seconds between spread logs
RUN_SECONDS      = 300 # auto-stop after this many seconds (0 = run forever)


class XauArbMonitor(Strategy):
    """
    Dual-feed market data monitor for XAU arbitrage research.

    Tracks the real-time spread between Bybit's XAUUSDT perpetual
    and the MT5 XAUUSD spot price, printing a summary every few seconds.
    """

    def __init__(self):
        super().__init__()
        # latest mid prices
        self._bybit_mid: float | None = None
        self._mt5_mid:   float | None = None
        # tick counters
        self._bybit_ticks: int = 0
        self._mt5_ticks:   int = 0
        # spread stats (session)
        self._spread_samples: list[float] = []

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def on_start(self):
        self.log.info("=== XAU Arb Monitor starting ===")
        self.log.info(f"  Bybit feed : {BYBIT_SYMBOL}")
        self.log.info(f"  MT5 feed   : {MT5_SYMBOL}")

        # Bybit perpetual — BookL1 (real-time WebSocket)
        self.subscribe_bookl1(symbols=BYBIT_SYMBOL)

        # MT5 spot — BookL1 (polling via executor)
        self.subscribe_bookl1(symbols=MT5_SYMBOL, ready=False)

        # Kline subscriptions for context (M1 bars)
        self.subscribe_kline(
            symbols=BYBIT_SYMBOL,
            interval=KlineInterval.MINUTE_1,
        )
        self.subscribe_kline(
            symbols=MT5_SYMBOL,
            interval=KlineInterval.MINUTE_1,
            ready=False,
        )

        # Periodic summary
        self.schedule(self._log_summary, trigger="interval", seconds=SUMMARY_INTERVAL)

        # Auto-stop (skip if RUN_SECONDS == 0)
        if RUN_SECONDS > 0:
            self.schedule(self._auto_stop, trigger="interval", seconds=RUN_SECONDS)

    # ── Market data callbacks ────────────────────────────────────────────────

    def on_bookl1(self, bookl1: BookL1):
        if bookl1.symbol == BYBIT_SYMBOL:
            self._bybit_mid = bookl1.mid
            self._bybit_ticks += 1
        elif bookl1.symbol == MT5_SYMBOL:
            self._mt5_mid = bookl1.mid
            self._mt5_ticks += 1

        # Record spread whenever both sides are available
        if self._bybit_mid is not None and self._mt5_mid is not None:
            self._spread_samples.append(self._bybit_mid - self._mt5_mid)

    def on_kline(self, kline: Kline):
        if not kline.confirm:
            return
        tag = "BYBIT" if kline.symbol == BYBIT_SYMBOL else "MT5  "
        self.log.info(
            f"[BAR CLOSED] {tag} {kline.symbol}  "
            f"O={kline.open:.3f}  H={kline.high:.3f}  "
            f"L={kline.low:.3f}  C={kline.close:.3f}"
        )

    # ── Scheduled helpers ────────────────────────────────────────────────────

    def _log_summary(self):
        bybit = f"{self._bybit_mid:.3f}" if self._bybit_mid else "---"
        mt5   = f"{self._mt5_mid:.3f}"   if self._mt5_mid   else "---"

        if self._bybit_mid is not None and self._mt5_mid is not None:
            spread     = self._bybit_mid - self._mt5_mid
            spread_pct = spread / self._mt5_mid * 100

            # rolling stats from session samples
            n = len(self._spread_samples)
            avg = sum(self._spread_samples) / n if n else 0.0
            hi  = max(self._spread_samples) if n else 0.0
            lo  = min(self._spread_samples) if n else 0.0

            self.log.info(
                f"[SPREAD]  "
                f"Bybit={bybit}  MT5={mt5}  "
                f"spread={spread:+.3f} ({spread_pct:+.4f}%)  "
                f"| session avg={avg:+.3f}  hi={hi:+.3f}  lo={lo:+.3f}  "
                f"| ticks bybit={self._bybit_ticks}  mt5={self._mt5_ticks}"
            )
        else:
            self.log.info(
                f"[SPREAD]  Bybit={bybit}  MT5={mt5}  "
                f"(waiting for both feeds…)  "
                f"ticks bybit={self._bybit_ticks}  mt5={self._mt5_ticks}"
            )

    def _auto_stop(self):
        n = len(self._spread_samples)
        if n:
            avg = sum(self._spread_samples) / n
            hi  = max(self._spread_samples)
            lo  = min(self._spread_samples)
            self.log.info(
                f"=== Session complete ({n} samples) ===\n"
                f"  spread  avg={avg:+.4f}  hi={hi:+.4f}  lo={lo:+.4f}\n"
                f"  ticks   bybit={self._bybit_ticks}  mt5={self._mt5_ticks}"
            )
        self.stop()


# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------

config = Config(
    strategy_id="xau_arb_monitor",
    user_id="user_test",
    strategy=XauArbMonitor(),
    log_config=LogConfig(level_stdout="INFO"),
    basic_config={
        # Bybit public feed — no API key required
        ExchangeType.BYBIT: BasicConfig(
            testnet=False,
        ),
        # MT5 TradeFi — credentials from .keys/.secrets.toml
        ExchangeType.BYBIT_TRADFI: BasicConfig(
            api_key=MT5_LOGIN,
            secret=MT5_PASSWORD,
            passphrase=MT5_SERVER,
            testnet=True,   # True → DEMO account
        ),
    },
    public_conn_config={
        ExchangeType.BYBIT: [
            PublicConnectorConfig(
                account_type=BybitAccountType.LINEAR,
            )
        ],
        ExchangeType.BYBIT_TRADFI: [
            PublicConnectorConfig(
                account_type=BybitTradeFiAccountType.DEMO,
            )
        ],
    },
    private_conn_config={
        # MT5 private connector is required for the polling executor to start
        ExchangeType.BYBIT_TRADFI: [
            PrivateConnectorConfig(
                account_type=BybitTradeFiAccountType.DEMO,
            )
        ],
    },
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
