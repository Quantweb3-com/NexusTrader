"""
Kline aggregation for live trading.

This module provides kline (candlestick) aggregation from trade data.
"""

from typing import Optional
from datetime import timedelta, datetime, timezone
from nexustrader.schema import Trade, Kline
from nexustrader.constants import KlineInterval, ExchangeType
from nexustrader.core.nautilius_core import LiveClock, TimeEvent, Logger, MessageBus


class KlineBuilder:
    """
    Kline builder for aggregating trade data into OHLCV klines.

    Parameters
    ----------
    exchange : ExchangeType
        The exchange for the klines
    symbol : str
        The symbol for the klines
    interval : KlineInterval
        The kline interval
    """

    def __init__(
        self,
        exchange: ExchangeType,
        symbol: str,
        interval: KlineInterval,
    ):
        self.exchange = exchange
        self.symbol = symbol
        self.interval = interval

        # OHLCV data as member variables
        self._open = None
        self._high = None
        self._low = None
        self._close = None
        self._volume = 0.0
        self._last_close = None

        self.initialized = False
        self.ts_last = 0
        self.count = 0

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"{self.exchange.value}, "
            f"{self.symbol}, "
            f"{self.interval.value}, "
            f"open={self._open}, "
            f"high={self._high}, "
            f"low={self._low}, "
            f"close={self._close}, "
            f"volume={self._volume})"
        )

    def update(self, trade: Trade) -> None:
        """
        Update the kline builder with a new trade.

        Parameters
        ----------
        trade : Trade
            The trade data to update with
        """
        if trade.timestamp < self.ts_last:
            return

        if trade.price <= 0:
            return

        if self._open is None:
            self._open = trade.price
            self._high = trade.price
            self._low = trade.price
            self.initialized = True
        elif trade.price > self._high:
            self._high = trade.price
        elif trade.price < self._low:
            self._low = trade.price

        self._close = trade.price
        self._volume += trade.size
        self.count += 1
        self.ts_last = trade.timestamp

    def reset(self) -> None:
        """Reset the builder to initial state."""
        self._open = None
        self._high = None
        self._low = None
        self._volume = 0.0
        self.count = 0

    def build(self, start: int, timestamp: int) -> Optional[Kline]:
        """
        Build a kline from the current state and reset.

        Returns None if no trades were received (not initialized).

        Parameters
        ----------
        ts_event : int
            Timestamp (nanoseconds) for the kline event
        ts_init : int
            Timestamp (nanoseconds) for the kline initialization

        Returns
        -------
        Kline | None
            The built kline, or None if no trades received
        """
        # If no trades received, don't emit a kline
        if not self.initialized:
            return None

        if self._open is None:
            self._open = self._last_close
            self._high = self._last_close
            self._low = self._last_close
            self._close = self._last_close

        self._low = min(self._low, self._close)
        self._high = max(self._high, self._close)

        kline = Kline(
            exchange=self.exchange,
            symbol=self.symbol,
            interval=self.interval,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
            start=start,
            timestamp=timestamp,
            confirm=True,
        )

        self._last_close = self._close
        self.reset()
        return kline

    def build_now(self) -> Optional[Kline]:
        """
        Build a kline with current timestamp and reset.

        Returns None if no trades were received.

        Returns
        -------
        Kline | None
            The built kline, or None if no trades received
        """
        return self.build(self.ts_last, self.ts_last)


class KlineAggregator:
    """
    Base class for kline aggregation from trade data.

    Parameters
    ----------
    exchange : ExchangeType
        The exchange for the aggregator
    symbol : str
        The symbol for the aggregator
    interval : KlineInterval
        The kline interval
    msgbus : MessageBus
        The message bus for publishing klines
    """

    def __init__(
        self,
        exchange: ExchangeType,
        symbol: str,
        msgbus: MessageBus,
        interval: KlineInterval | None = None,
    ):
        self.exchange = exchange
        self.symbol = symbol
        self.interval = interval
        self._msgbus = msgbus
        self._log = Logger(name=type(self).__name__)

        self._builder = KlineBuilder(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
        )
        self.is_running = False
        self._msgbus.subscribe(topic="trade", handler=self.handle_trade)

    def handle_trade(self, trade: Trade) -> None:
        """
        Handle incoming trade data.

        Parameters
        ----------
        trade : Trade
            The trade to process
        """
        self._apply_update(trade)

    def _apply_update(self, trade: Trade) -> None:
        """
        Apply trade update to the aggregator.

        Must be implemented by subclasses.

        Parameters
        ----------
        trade : Trade
            The trade to process
        """
        raise NotImplementedError(
            "method `_apply_update` must be implemented in the subclass"
        )

    def _build_now_and_send(self) -> None:
        """Build kline with current timestamp and publish to msgbus if kline was built."""
        kline = self._builder.build_now()
        if kline is not None:
            self._msgbus.publish(topic="kline", msg=kline)

    def _build_and_send(self, start: int, timestamp: int) -> None:
        """Build kline with specified timestamps and publish to msgbus if kline was built."""
        kline = self._builder.build(start, timestamp)
        if kline is not None:
            self._msgbus.publish(topic="kline", msg=kline)


class VolumeKlineAggregator(KlineAggregator):
    """
    Volume-based kline aggregator.

    Creates klines when cumulative trade volume reaches the threshold.
    Large trades are split across multiple klines.

    Parameters
    ----------
    exchange : ExchangeType
        The exchange for the aggregator
    symbol : str
        The symbol for the aggregator
    interval : KlineInterval
        The kline interval (used for metadata only)
    msgbus : MessageBus
        The message bus for publishing klines
    volume_threshold : float
        Volume threshold for creating new klines
    """

    def __init__(
        self,
        exchange: ExchangeType,
        symbol: str,
        msgbus: MessageBus,
        volume_threshold: float,
    ):
        super().__init__(exchange, symbol, msgbus, interval=KlineInterval.VOLUME)
        self.volume_threshold = volume_threshold

    def _apply_update(self, trade: Trade) -> None:
        """
        Apply trade update with volume-based aggregation.

        Parameters
        ----------
        trade : Trade
            The trade to process
        """
        size_update = trade.size

        while size_update > 0:
            current_volume = self._builder._volume

            if current_volume + size_update < self.volume_threshold:
                # Update and break
                partial_trade = Trade(
                    exchange=trade.exchange,
                    symbol=trade.symbol,
                    price=trade.price,
                    size=size_update,
                    timestamp=trade.timestamp,
                )
                self._builder.update(partial_trade)
                break

            # Calculate size needed to reach threshold
            size_diff = self.volume_threshold - current_volume

            # Update builder to threshold
            partial_trade = Trade(
                exchange=trade.exchange,
                symbol=trade.symbol,
                price=trade.price,
                size=size_diff,
                timestamp=trade.timestamp,
            )
            self._builder.update(partial_trade)
            self._build_now_and_send()

            # Decrement remaining size
            size_update -= size_diff


class TimeKlineAggregator(KlineAggregator):
    """
    Time-based kline aggregator using LiveClock.

    Creates klines at regular time intervals (1s to 1w).

    Parameters
    ----------
    exchange : ExchangeType
        The exchange for the aggregator
    symbol : str
        The symbol for the aggregator
    interval : KlineInterval
        The kline interval
    msgbus : MessageBus
        The message bus for publishing klines
    clock : LiveClock
        The clock for timing
    """

    def __init__(
        self,
        exchange: ExchangeType,
        symbol: str,
        interval: KlineInterval,
        msgbus: MessageBus,
        clock: LiveClock,
    ):
        super().__init__(exchange, symbol, msgbus, interval)
        self._clock = clock
        self._timer_name = f"{exchange.value}_{symbol}_{interval.value}"

        self.interval_ms = interval.milliseconds
        self.interval_ns = interval.nanoseconds

        # Set up the timer
        self._set_build_timer()

    def _set_build_timer(self) -> None:
        """Set up the clock timer for kline building."""
        start_time = self._get_start_time()

        # Calculate interval timedelta
        interval_td = timedelta(milliseconds=self.interval_ms)

        self._clock.set_timer(
            name=self._timer_name,
            interval=interval_td,
            start_time=start_time,
            stop_time=None,
            callback=self._build_bar,
        )
        self._log.debug(
            f"Timer set: {self._timer_name}, start={start_time}, interval={interval_td}"
        )

    def _get_start_time(self):
        """
        Calculate the start time for the next kline interval.

        Uses the same logic as Nautilus TimeBarAggregator:
        - Find the floor time (closest smaller time aligned to interval)
        - Always schedule for the NEXT interval boundary
        """
        timestamp = self._clock.timestamp_ms()
        interval_ms = self.interval_ms
        floored_timestamp = (timestamp // interval_ms) * interval_ms
        start_time = datetime.fromtimestamp(floored_timestamp / 1000, tz=timezone.utc)

        # Always start at the NEXT interval boundary
        return start_time + timedelta(milliseconds=interval_ms)

    def stop(self) -> None:
        """Stop the aggregator and cancel the timer."""
        self._clock.cancel_timer(self._timer_name)

    def _apply_update(self, trade: Trade) -> None:
        """
        Apply trade update with time-based aggregation.

        Parameters
        ----------
        trade : Trade
            The trade to process
        """
        self._builder.update(trade)

    def _build_bar(self, event: TimeEvent) -> None:
        """
        Build and emit kline on timer event.

        Parameters
        ----------
        event : TimeEvent
            The timer event
        """
        ts_event = event.ts_event // 1_000_000  # Convert ns to ms
        ts_init = event.ts_init // 1_000_000  # Convert ns to ms

        # # Build and send kline (only if trades were received)
        self._build_and_send(ts_event, ts_init)
        self._log.debug(f"Kline built: ts_event={ts_event}, ts_init={ts_init}")
