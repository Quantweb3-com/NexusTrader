"""
Public and Private connectors for Bybit TradeFi (MT5).

PublicConnector
    Provides market data (BookL1, Trade, Kline, historical klines, tickers)
    by polling the MT5 terminal via a dedicated single-threaded executor.
    There is no WebSocket; all data is obtained by periodic polling.

PrivateConnector
    Handles MT5 terminal initialisation, login, market loading, and delegates
    all order operations to BybitTradeFiOrderManagementSystem.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Set, Tuple

from nexustrader.aggregation import TimeKlineAggregator, VolumeKlineAggregator
from nexustrader.constants import (
    BookLevel,
    ExchangeType,
    KlineInterval,
    OrderSide,
)
from nexustrader.core.cache import AsyncCache
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock, Logger, MessageBus
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.bybit_tradfi.constants import (
    BybitTradeFiAccountType,
    kline_interval_to_mt5_timeframe,
)
from nexustrader.exchange.bybit_tradfi.exchange import BybitTradeFiExchangeManager
from nexustrader.exchange.bybit_tradfi.oms import BybitTradeFiOrderManagementSystem
from nexustrader.schema import (
    BookL1,
    Kline,
    KlineList,
    Ticker,
    Trade,
)


# ---------------------------------------------------------------------------
# Public Connector
# ---------------------------------------------------------------------------


class BybitTradeFiPublicConnector:
    """
    Market-data connector backed by MT5 polling.

    Implements the interface expected by Strategy / SSubscriptionManagementSystem.
    No WebSocket or REST client is used.
    """

    # Default polling intervals (seconds)
    TICK_POLL_INTERVAL = 0.1    # BookL1 / Trade polling
    KLINE_POLL_INTERVAL = 0.5   # Kline polling

    def __init__(
        self,
        account_type: BybitTradeFiAccountType,
        exchange: BybitTradeFiExchangeManager,
        msgbus: MessageBus,
        clock: LiveClock,
        task_manager: TaskManager,
        tick_poll_interval: float = TICK_POLL_INTERVAL,
        kline_poll_interval: float = KLINE_POLL_INTERVAL,
    ) -> None:
        self._log = Logger(name=type(self).__name__)
        self._account_type = account_type
        self._exchange = exchange
        self._executor = exchange._executor
        self._market = exchange.market
        self._market_id = exchange.market_id
        self._exchange_id = ExchangeType.BYBIT_TRADFI
        self._msgbus = msgbus
        self._clock = clock
        self._task_manager = task_manager
        self._tick_poll_interval = tick_poll_interval
        self._kline_poll_interval = kline_poll_interval

        # Subscription tracking
        self._bookl1_subs: Set[str] = set()   # nexus symbols
        self._trade_subs: Set[str] = set()
        self._kline_subs: Set[Tuple[str, KlineInterval]] = set()

        # Aggregator support (mirrors PublicConnector base)
        self._aggregators: Dict[str, list] = {}
        self._msgbus.subscribe(
            topic="trade", handler=self._handle_trade_for_aggregators
        )

    @property
    def account_type(self):
        return self._account_type

    # ------------------------------------------------------------------
    # BookL1 subscription
    # ------------------------------------------------------------------

    async def subscribe_bookl1(self, symbol: str | List[str]) -> None:
        symbols = [symbol] if isinstance(symbol, str) else symbol
        for sym in symbols:
            if sym not in self._bookl1_subs:
                self._bookl1_subs.add(sym)
                self._task_manager.create_task(
                    self._poll_bookl1(sym), name=f"mt5_bookl1_{sym}"
                )
                self._log.info(f"Subscribed to BookL1: {sym}")

    async def unsubscribe_bookl1(self, symbol: str | List[str]) -> None:
        symbols = [symbol] if isinstance(symbol, str) else symbol
        for sym in symbols:
            self._bookl1_subs.discard(sym)

    async def _poll_bookl1(self, nexus_symbol: str) -> None:
        mt5_symbol = self._nexus_to_mt5(nexus_symbol)
        if not mt5_symbol:
            self._log.error(f"Unknown symbol for BookL1 polling: {nexus_symbol}")
            return

        last_bid = last_ask = 0.0
        while nexus_symbol in self._bookl1_subs:
            try:
                tick = await self._get_tick(mt5_symbol)
                if tick and (tick.bid != last_bid or tick.ask != last_ask):
                    last_bid, last_ask = tick.bid, tick.ask
                    book = BookL1(
                        exchange=self._exchange_id,
                        symbol=nexus_symbol,
                        bid=tick.bid,
                        ask=tick.ask,
                        bid_size=0.0,
                        ask_size=0.0,
                        timestamp=int(tick.time_msc),
                    )
                    self._msgbus.publish(topic="bookl1", msg=book)
            except Exception as exc:
                self._log.error(f"BookL1 poll error ({nexus_symbol}): {exc}")
            await asyncio.sleep(self._tick_poll_interval)

    # ------------------------------------------------------------------
    # Trade subscription
    # ------------------------------------------------------------------

    async def subscribe_trade(self, symbol: str | List[str]) -> None:
        symbols = [symbol] if isinstance(symbol, str) else symbol
        for sym in symbols:
            if sym not in self._trade_subs:
                self._trade_subs.add(sym)
                self._task_manager.create_task(
                    self._poll_trade(sym), name=f"mt5_trade_{sym}"
                )
                self._log.info(f"Subscribed to Trade: {sym}")

    async def unsubscribe_trade(self, symbol: str | List[str]) -> None:
        symbols = [symbol] if isinstance(symbol, str) else symbol
        for sym in symbols:
            self._trade_subs.discard(sym)

    async def _poll_trade(self, nexus_symbol: str) -> None:
        mt5_symbol = self._nexus_to_mt5(nexus_symbol)
        if not mt5_symbol:
            self._log.error(f"Unknown symbol for Trade polling: {nexus_symbol}")
            return

        last_time_msc: int = 0
        while nexus_symbol in self._trade_subs:
            try:
                tick = await self._get_tick(mt5_symbol)
                if tick and tick.time_msc != last_time_msc:
                    last_time_msc = tick.time_msc
                    # Use tick flags to determine direction (2=buy, 4=sell)
                    side = (
                        OrderSide.BUY
                        if getattr(tick, "flags", 0) & 2
                        else OrderSide.SELL
                    )
                    trade = Trade(
                        exchange=self._exchange_id,
                        symbol=nexus_symbol,
                        side=side,
                        price=tick.last if tick.last else tick.bid,
                        size=0.0,
                        timestamp=int(tick.time_msc),
                    )
                    self._msgbus.publish(topic="trade", msg=trade)
            except Exception as exc:
                self._log.error(f"Trade poll error ({nexus_symbol}): {exc}")
            await asyncio.sleep(self._tick_poll_interval)

    # ------------------------------------------------------------------
    # Kline subscription
    # ------------------------------------------------------------------

    async def subscribe_kline(
        self, symbol: str | List[str], interval: KlineInterval
    ) -> None:
        symbols = [symbol] if isinstance(symbol, str) else symbol
        for sym in symbols:
            key = (sym, interval)
            if key not in self._kline_subs:
                self._kline_subs.add(key)
                self._task_manager.create_task(
                    self._poll_kline(sym, interval),
                    name=f"mt5_kline_{sym}_{interval.value}",
                )
                self._log.info(f"Subscribed to Kline: {sym} {interval.value}")

    async def unsubscribe_kline(
        self, symbol: str | List[str], interval: KlineInterval
    ) -> None:
        symbols = [symbol] if isinstance(symbol, str) else symbol
        for sym in symbols:
            self._kline_subs.discard((sym, interval))

    async def _poll_kline(self, nexus_symbol: str, interval: KlineInterval) -> None:
        mt5_symbol = self._nexus_to_mt5(nexus_symbol)
        if not mt5_symbol:
            self._log.error(f"Unknown symbol for Kline polling: {nexus_symbol}")
            return

        tf = kline_interval_to_mt5_timeframe(interval)
        last_bar_time: int = 0
        last_bar_close: float = 0.0

        while (nexus_symbol, interval) in self._kline_subs:
            try:
                bar = await self._get_latest_bar(mt5_symbol, tf)
                if bar is None:
                    await asyncio.sleep(self._kline_poll_interval)
                    continue

                if bar["time"] != last_bar_time:
                    if last_bar_time != 0:
                        # Previous bar just closed — emit confirmed
                        prev_bar = await self._get_bar_at(mt5_symbol, tf, 1)
                        if prev_bar:
                            self._msgbus.publish(
                                topic="kline",
                                msg=self._bar_to_kline(prev_bar, nexus_symbol, interval, confirmed=True),
                            )
                    last_bar_time = bar["time"]
                    last_bar_close = bar["close"]
                    # Emit the new unconfirmed bar on open
                    self._msgbus.publish(
                        topic="kline",
                        msg=self._bar_to_kline(bar, nexus_symbol, interval, confirmed=False),
                    )
                elif bar["close"] != last_bar_close:
                    # Price changed within the current bar — emit updated unconfirmed bar
                    last_bar_close = bar["close"]
                    self._msgbus.publish(
                        topic="kline",
                        msg=self._bar_to_kline(bar, nexus_symbol, interval, confirmed=False),
                    )
            except Exception as exc:
                self._log.error(f"Kline poll error ({nexus_symbol}/{interval.value}): {exc}")
            await asyncio.sleep(self._kline_poll_interval)

    # ------------------------------------------------------------------
    # Historical klines (synchronous interface, called before event loop)
    # ------------------------------------------------------------------

    def request_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        # Called synchronously from on_start() which runs inside the event loop.
        # Using run_sync() here causes a deadlock because run_sync() blocks the
        # event loop thread while waiting for a coroutine that needs that same
        # thread to execute.  Submit directly to the executor instead.
        mt5_symbol = self._nexus_to_mt5(symbol)
        if not mt5_symbol:
            return KlineList(klines=[])

        tf = kline_interval_to_mt5_timeframe(interval)
        future = self._executor.submit(
            self._mt5_copy_rates, mt5_symbol, tf, limit, start_time, end_time
        )
        rates = future.result()
        if rates is None:
            return KlineList(klines=[])

        klines = [
            self._bar_to_kline(
                {
                    "time": int(r[0]),
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "tick_volume": float(r[5]),
                },
                symbol,
                interval,
                confirmed=True,
            )
            for r in rates
        ]
        return KlineList(klines=klines)

    def request_ticker(self, symbol: str) -> Ticker:
        mt5_symbol = self._nexus_to_mt5(symbol)
        future = self._executor.submit(self._mt5_symbol_info_tick, mt5_symbol)
        tick = future.result()
        price = tick.last if (tick and tick.last) else (tick.bid if tick else 0.0)
        return Ticker(
            exchange=self._exchange_id,
            symbol=symbol,
            last_price=price,
            timestamp=int(tick.time_msc) if tick else self._clock.timestamp_ms(),
            volume=0.0,
            volumeCcy=0.0,
        )

    def request_all_tickers(self) -> Dict[str, Ticker]:
        result: Dict[str, Ticker] = {}
        for nexus_symbol in list(self._market.keys()):
            try:
                result[nexus_symbol] = self.request_ticker(nexus_symbol)
            except Exception:
                pass
        return result

    def request_index_klines(self, symbol: str, interval: KlineInterval, **_) -> KlineList:
        # MT5 TradeFi has no separate index price – return spot klines
        return self.request_klines(symbol, interval)

    # ------------------------------------------------------------------
    # Unsupported subscriptions (no-ops with a warning)
    # ------------------------------------------------------------------

    async def subscribe_bookl2(self, symbol, level: BookLevel) -> None:
        self._log.warning("BookL2 data is not available via MetaTrader5.")

    async def unsubscribe_bookl2(self, symbol, level: BookLevel) -> None:
        pass

    async def subscribe_funding_rate(self, symbol) -> None:
        self._log.warning("Funding rate is not applicable to MT5 TradeFi instruments.")

    async def unsubscribe_funding_rate(self, symbol) -> None:
        pass

    async def subscribe_index_price(self, symbol) -> None:
        self._log.warning("Index price is not separately available via MetaTrader5.")

    async def unsubscribe_index_price(self, symbol) -> None:
        pass

    async def subscribe_mark_price(self, symbol) -> None:
        self._log.warning("Mark price is not separately available via MetaTrader5.")

    async def unsubscribe_mark_price(self, symbol) -> None:
        pass

    # ------------------------------------------------------------------
    # Aggregator support (mirrors PublicConnector base)
    # ------------------------------------------------------------------

    async def subscribe_kline_aggregator(
        self, symbol: str, interval: KlineInterval, build_with_no_updates: bool
    ) -> None:
        await self.subscribe_trade(symbol)
        aggregator = TimeKlineAggregator(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            msgbus=self._msgbus,
            clock=self._clock,
            build_with_no_updates=build_with_no_updates,
        )
        self._aggregators.setdefault(symbol, []).append(aggregator)

    async def subscribe_volume_kline_aggregator(
        self, symbol: str, volume_threshold: float, volume_type: str
    ) -> None:
        await self.subscribe_trade(symbol)
        aggregator = VolumeKlineAggregator(
            exchange=self._exchange_id,
            symbol=symbol,
            msgbus=self._msgbus,
            volume_threshold=volume_threshold,
            volume_type=volume_type,
        )
        self._aggregators.setdefault(symbol, []).append(aggregator)

    def _handle_trade_for_aggregators(self, trade: Trade) -> None:
        for aggregator in self._aggregators.get(trade.symbol, []):
            aggregator.handle_trade(trade)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def disconnect(self) -> None:
        self._bookl1_subs.clear()
        self._trade_subs.clear()
        self._kline_subs.clear()
        for aggregators in self._aggregators.values():
            for agg in aggregators:
                if hasattr(agg, "stop"):
                    agg.stop()
        self._aggregators.clear()

    # ------------------------------------------------------------------
    # Internal MT5 helpers (all run via executor)
    # ------------------------------------------------------------------

    async def _get_tick(self, mt5_symbol: str):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._mt5_symbol_info_tick(mt5_symbol),
        )

    async def _get_latest_bar(self, mt5_symbol: str, tf: int) -> dict | None:
        loop = asyncio.get_event_loop()
        rates = await loop.run_in_executor(
            self._executor,
            lambda: self._mt5_copy_rates_from_pos(mt5_symbol, tf, 0, 1),
        )
        if rates is None or len(rates) == 0:
            return None
        r = rates[0]
        return {
            "time": int(r[0]),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "tick_volume": float(r[5]),
        }

    async def _get_bar_at(self, mt5_symbol: str, tf: int, pos: int) -> dict | None:
        loop = asyncio.get_event_loop()
        rates = await loop.run_in_executor(
            self._executor,
            lambda: self._mt5_copy_rates_from_pos(mt5_symbol, tf, pos, 1),
        )
        if not rates or len(rates) == 0:
            return None
        r = rates[0]
        return {
            "time": int(r[0]),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "tick_volume": float(r[5]),
        }

    @staticmethod
    def _mt5_symbol_info_tick(mt5_symbol: str):
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        return get_mt5().symbol_info_tick(mt5_symbol)

    @staticmethod
    def _mt5_copy_rates_from_pos(mt5_symbol: str, tf: int, pos: int, count: int):
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        return get_mt5().copy_rates_from_pos(mt5_symbol, tf, pos, count)

    @staticmethod
    def _mt5_copy_rates(
        mt5_symbol: str,
        tf: int,
        limit: int | None,
        start_time: int | None,
        end_time: int | None,
    ):
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5
        import datetime

        mt5 = get_mt5()
        if start_time and end_time:
            return mt5.copy_rates_range(
                mt5_symbol,
                tf,
                datetime.datetime.fromtimestamp(start_time / 1000),
                datetime.datetime.fromtimestamp(end_time / 1000),
            )
        count = limit or 500
        return mt5.copy_rates_from_pos(mt5_symbol, tf, 0, count)

    def _bar_to_kline(
        self,
        bar: dict,
        nexus_symbol: str,
        interval: KlineInterval,
        confirmed: bool,
    ) -> Kline:
        bar_ts_ms = bar["time"] * 1000
        return Kline(
            exchange=self._exchange_id,
            symbol=nexus_symbol,
            interval=interval,
            open=bar["open"],
            high=bar["high"],
            low=bar["low"],
            close=bar["close"],
            volume=bar["tick_volume"],
            start=bar_ts_ms,
            timestamp=self._clock.timestamp_ms(),
            confirm=confirmed,
        )

    def _nexus_to_mt5(self, nexus_symbol: str) -> str | None:
        market = self._market.get(nexus_symbol)
        return market.id if market else None


# ---------------------------------------------------------------------------
# Private Connector
# ---------------------------------------------------------------------------


class BybitTradeFiPrivateConnector:
    """
    Initialises the MT5 terminal, logs in, loads markets, and hosts the OMS.
    """

    def __init__(
        self,
        account_type: BybitTradeFiAccountType,
        exchange: BybitTradeFiExchangeManager,
        cache: AsyncCache,
        registry: OrderRegistry,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
    ) -> None:
        self._log = Logger(name=type(self).__name__)
        self._account_type = account_type
        self._exchange = exchange
        self._executor = exchange._executor
        self._cache = cache
        self._registry = registry
        self._clock = clock
        self._msgbus = msgbus
        self._task_manager = task_manager

        # OMS is constructed here but cannot call _init_account_balance /
        # _init_position yet because MT5 is not connected.
        # We defer those calls to connect().
        self._oms = BybitTradeFiOrderManagementSystem(
            account_type=account_type,
            exchange=exchange,
            registry=registry,
            cache=cache,
            clock=clock,
            msgbus=msgbus,
            task_manager=task_manager,
        )
        self._mt5_connected = False

    @property
    def account_type(self):
        return self._account_type

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """
        Full MT5 startup sequence:
        1. Platform / package check
        2. mt5.initialize()
        3. mt5.login()
        4. Terminal connected check
        5. Load markets from MT5
        6. Initialise OMS (balance + positions)
        7. Start order-status polling
        """
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import (
            check_terminal_connected,
            mt5_initialize,
            mt5_login,
        )

        self._log.info(
            f"Connecting to MT5 (account={self._exchange._login}, "
            f"server={self._exchange._server!r}, "
            f"demo={self._account_type.is_demo}) ..."
        )

        loop = asyncio.get_event_loop()

        # Step 1: initialize (runs in executor to keep MT5 in the worker thread)
        try:
            ok, err = await loop.run_in_executor(
                self._executor,
                lambda: mt5_initialize(self._exchange._terminal_path),
            )
        except ImportError as exc:
            raise SystemExit(f"\n{exc}") from None
        if not ok:
            raise RuntimeError(f"MT5 initialization failed: {err}")
        self._log.info("MT5 terminal initialised.")

        # Step 2: login
        ok, err = await loop.run_in_executor(
            self._executor,
            lambda: mt5_login(
                self._exchange._login,
                self._exchange._password,
                self._exchange._server,
            ),
        )
        if not ok:
            raise RuntimeError(f"MT5 login failed: {err}")
        self._log.info(f"MT5 logged in (account={self._exchange._login}).")

        # Step 3: verify terminal is connected to broker
        ok, err = await loop.run_in_executor(
            self._executor, check_terminal_connected
        )
        if not ok:
            raise RuntimeError(f"MT5 terminal not connected: {err}")
        self._log.info("MT5 terminal connected to broker.")

        # Step 4: load markets (must run in executor for MT5 thread safety)
        await loop.run_in_executor(
            self._executor, self._exchange.load_markets_from_mt5
        )
        self._log.info(
            f"MT5 markets ready: {len(self._exchange.market)} symbols."
        )

        # Step 5: initialise OMS (balance + positions)
        await self._oms._async_init_balance()
        await self._oms._async_init_position()

        self._mt5_connected = True

        # Step 6: start background order-status polling
        self._task_manager.create_task(
            self._oms.start_order_polling(), name="mt5_order_polling"
        )

        self._log.info("BybitTradeFi private connector ready.")

    async def disconnect(self) -> None:
        if not self._mt5_connected:
            return
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import mt5_shutdown

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, mt5_shutdown)
        self._exchange.close()
        self._mt5_connected = False
        self._log.info("MT5 connection closed.")
