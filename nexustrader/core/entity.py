import signal
import asyncio
import socket
from typing import Callable, Coroutine, Any, TypeVar, Literal, Union
from typing import Dict, List
import warnings
from collections import deque
from statistics import median, mean
import redis
import time

from dataclasses import dataclass
from nexustrader.constants import get_redis_config
from nexustrader.core.nautilius_core import LiveClock, Logger
from nexustrader.schema import (
    Kline,
    BookL1,
    Trade,
    FundingRate,
    BookL2,
    IndexPrice,
    MarkPrice,
)

T = TypeVar("T")
InputDataType = Union[
    Kline, BookL1, Trade, FundingRate, BookL2, IndexPrice, IndexPrice, MarkPrice
]


def is_redis_available() -> bool:
    """Check if Redis dependencies and server are available"""
    try:
        # Check if Redis Python packages are installed
        import redis
        import socket
        from nexustrader.constants import get_redis_config

        # Check if Redis server is accessible
        try:
            # Detect if running in Docker
            in_docker = False
            try:
                socket.gethostbyname("redis")
                in_docker = True
            except socket.gaierror:
                pass

            # Get Redis config and test connection
            redis_config = get_redis_config(in_docker)
            client = redis.Redis(**redis_config)
            client.ping()  # This will raise an exception if Redis is not accessible
            client.close()
            return True
        except (redis.ConnectionError, redis.TimeoutError, socket.error, Exception):
            return False

    except ImportError:
        return False


def get_redis_client_if_available():
    """Get Redis client if available, otherwise return None"""
    if not is_redis_available():
        return None

    try:
        import socket
        from nexustrader.constants import get_redis_config

        # Detect if running in Docker
        in_docker = False
        try:
            socket.gethostbyname("redis")
            in_docker = True
        except socket.gaierror:
            pass

        redis_config = get_redis_config(in_docker)
        return redis.Redis(**redis_config)
    except Exception:
        return None


@dataclass
class RateLimit:
    """
    max_rate: Allow up to max_rate / time_period acquisitions before blocking.
    time_period: Time period in seconds.
    """

    max_rate: float
    time_period: float = 60


class TaskManager:
    def __init__(
        self, loop: asyncio.AbstractEventLoop, enable_signal_handlers: bool = True
    ):
        self._log = Logger(name=type(self).__name__)
        self._tasks: Dict[str, asyncio.Task] = {}
        self._shutdown_event = asyncio.Event()
        self._loop = loop
        if enable_signal_handlers:
            self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                self._loop.add_signal_handler(
                    sig, lambda: self.create_task(self._shutdown())
                )
        except NotImplementedError:
            warnings.warn("Signal handlers not supported on this platform")

    async def _shutdown(self):
        self._shutdown_event.set()
        self._log.debug("Shutdown signal received, cleaning up...")

    def create_task(self, coro: asyncio.coroutines, name: str = None) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._tasks[task.get_name()] = task
        task.add_done_callback(self._handle_task_done)
        return task

    def run_sync(self, coro: Coroutine[Any, Any, T]) -> T:
        """
        Run an async coroutine in a synchronous context.

        Args:
            coro: The coroutine to run

        Returns:
            The result of the coroutine

        Raises:
            RuntimeError: If the event loop is not running and cannot be started
            Exception: Any exception raised by the coroutine
        """
        try:
            if self._loop.is_running():
                future = asyncio.run_coroutine_threadsafe(coro, self._loop)
                return future.result()
            else:
                if self._loop.is_closed():
                    raise RuntimeError("Event loop is closed")
                return self._loop.run_until_complete(coro)
        except asyncio.CancelledError:
            raise RuntimeError("Coroutine was cancelled")
        except Exception as e:
            self._log.error(f"Error running coroutine: {e}")
            raise

    def cancel_task(self, name: str) -> bool:
        if name in self._tasks:
            self._tasks[name].cancel()
            return True
        return False

    def _handle_task_done(self, task: asyncio.Task):
        try:
            name = task.get_name()
            self._tasks.pop(name, None)
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._log.error(f"Error during task done: {e}")
            raise

    async def wait(self):
        try:
            if self._tasks:
                await self._shutdown_event.wait()
        except Exception as e:
            self._log.error(f"Error during wait: {e}")
            raise

    async def cancel(self):
        try:
            for task in self._tasks.values():
                if not task.done():
                    task.cancel()

            if self._tasks:
                results = await asyncio.gather(
                    *self._tasks.values(), return_exceptions=True
                )

                for result in results:
                    if isinstance(result, Exception) and not isinstance(
                        result, asyncio.CancelledError
                    ):
                        self._log.error(f"Task failed during cancellation: {result}")

        except Exception as e:
            self._log.error(f"Error during cancellation: {e}")
            raise
        finally:
            self._tasks.clear()


class RedisClient:
    _params = None

    @classmethod
    def _is_in_docker(cls) -> bool:
        try:
            socket.gethostbyname("redis")
            return True
        except socket.gaierror:
            return False

    @classmethod
    def _get_params(cls) -> dict:
        if cls._params is None:
            in_docker = cls._is_in_docker()
            cls._params = get_redis_config(in_docker)
        return cls._params

    @classmethod
    def get_client(cls) -> redis.Redis:
        return redis.Redis(**cls._get_params())

    @classmethod
    def get_async_client(cls) -> redis.asyncio.Redis:
        return redis.asyncio.Redis(**cls._get_params())


class Clock:
    def __init__(self, tick_size: float = 1.0):
        """
        :param tick_size_s: Time interval of each tick in seconds (supports sub-second precision).
        """
        self._tick_size = tick_size  # Tick size in seconds
        self._current_tick = (time.time() // self._tick_size) * self._tick_size
        self._clock = LiveClock()
        self._tick_callbacks: List[Callable[[float], None]] = []
        self._started = False

    @property
    def tick_size(self) -> float:
        return self._tick_size

    @property
    def current_timestamp(self) -> float:
        return self._clock.timestamp()

    def add_tick_callback(self, callback: Callable[[float], None]):
        """
        Register a callback to be called on each tick.
        :param callback: Function to be called with current_tick as argument.
        """
        self._tick_callbacks.append(callback)

    async def run(self):
        if self._started:
            raise RuntimeError("Clock is already running.")
        self._started = True
        while True:
            now = time.time()
            next_tick_time = self._current_tick + self._tick_size
            sleep_duration = next_tick_time - now
            if sleep_duration > 0:
                await asyncio.sleep(sleep_duration)
            else:
                # If we're behind schedule, skip to the next tick to prevent drift
                next_tick_time = now
            self._current_tick = next_tick_time
            for callback in self._tick_callbacks:
                if asyncio.iscoroutinefunction(callback):
                    await callback(self.current_timestamp)
                else:
                    callback(self.current_timestamp)


class ZeroMQSignalRecv:
    def __init__(self, config, callback: Callable, task_manager: TaskManager):
        self._socket = config.socket
        self._callback = callback
        self._task_manager = task_manager

    async def _recv(self):
        while True:
            date = await self._socket.recv()
            if asyncio.iscoroutinefunction(self._callback):
                await self._callback(date)
            else:
                self._callback(date)

    async def start(self):
        self._task_manager.create_task(self._recv())


class MovingAverage:
    """
    Calculate moving median or mean using a sliding window.

    Args:
        length: Length of the sliding window
        method: 'median' or 'mean' calculation method
    """

    def __init__(self, length: int, method: Literal["median", "mean"] = "mean"):
        if method not in ["median", "mean"]:
            raise ValueError("method must be either 'median' or 'mean'")

        self._length = length
        self._method = method
        self._window = deque(maxlen=length)
        self._calc_func = median if method == "median" else mean

    def input(self, value: float) -> float | None:
        """
        Input a new value and return the current median/mean.

        Args:
            value: New value to add to sliding window

        Returns:
            Current median/mean value, or None if window not filled
        """
        self._window.append(value)

        if len(self._window) < self._length:
            return None

        return self._calc_func(self._window)


class DataReady:
    def __init__(
        self,
        symbols: List[str],
        name: str,
        timeout: int = 60,
        permanently_ready: bool = False,
    ):
        """
        Initialize DataReady class

        Args:
            symbols: symbols list need to monitor
            timeout: timeout in seconds
        """
        self._log = Logger(name=type(self).__name__)

        # Optimization: Store symbols as a set for faster lookups if needed,
        # but dict is fine for tracking status.
        self._symbols_status = {symbol: False for symbol in symbols}
        self._total_symbols = len(symbols)
        self._ready_symbols_count = 0

        self._timeout_ms = timeout * 1000  # Store timeout in ms
        self._clock = LiveClock()
        self._first_data_time: int | None = None
        self._name = name
        # Optimization: A flag to indicate that the "ready" state is final
        # (either all symbols received or timed out).
        self._is_permanently_ready: bool = permanently_ready

        if not symbols:  # If no symbols to monitor, it's ready immediately (or upon first data for timestamp)
            # We'll consider it ready once _first_data_time is set, which requires at least one input call
            # Or, we can decide it's ready right away if that's the desired behavior.
            # For now, let's assume if symbols is empty, it becomes ready when `ready` is first checked
            # after _first_data_time is set, or on timeout.
            # Alternatively, one could set self._is_permanently_ready = True here.
            # The current logic for _ready_symbols_count == _total_symbols (0 == 0) will handle this.
            self._is_permanently_ready = True

    def input(self, data: InputDataType) -> None:
        """
        Input data, update the status of the corresponding symbol

        Args:
            data: data object with symbol attribute
        """
        # Optimization: If already permanently ready, do nothing.
        if self._is_permanently_ready:
            return

        symbol = data.symbol

        if self._first_data_time is None:
            self._first_data_time = self._clock.timestamp_ms()

        # Process only if the symbol is one we are monitoring and it's not yet marked ready.
        if symbol in self._symbols_status and not self._symbols_status[symbol]:
            self._symbols_status[symbol] = True
            self._ready_symbols_count += 1

            # Optimization: Check if all symbols are now ready.
            if self._ready_symbols_count == self._total_symbols:
                self._log.debug(
                    f"All {self._total_symbols} symbols received. {self._name} is ready."
                )
                self._is_permanently_ready = True
                # No need to call self.ready here, the flag is enough.

    @property
    def ready(self) -> bool:
        """
        Check if all data is ready or if it has timed out

        Returns:
            bool: if all data is ready or timed out, return True
        """
        # Optimization: If already determined to be permanently ready, return True.
        if self._is_permanently_ready:
            return True

        if self._first_data_time is None:
            # No data received yet, so not ready (unless symbols list was empty and we decided that's ready from init)
            return False  # Or handle empty symbols list case from __init__

        # Check if all symbols have been received (could have been set by input)
        if self._ready_symbols_count == self._total_symbols:
            # This ensures that even if input didn't set _is_permanently_ready
            # (e.g. if ready is called before next input after last symbol arrived),
            # it's correctly identified.
            if (
                not self._is_permanently_ready
            ):  # To avoid repeated logging if already logged by input
                self._log.debug(
                    f"All {self._total_symbols} symbols confirmed ready by property access."
                )
            self._is_permanently_ready = True
            return True

        # Check for timeout
        if self._clock.timestamp_ms() - self._first_data_time > self._timeout_ms:
            # Only issue warning if not all symbols were ready before timeout
            if self._ready_symbols_count < self._total_symbols:
                not_ready_symbols = [
                    symbol
                    for symbol, status in self._symbols_status.items()
                    if not status
                ]
                if not_ready_symbols:  # Should always be true if count < total
                    warnings.warn(
                        f"Data receiving timed out. Timeout: {self._timeout_ms / 1000}s. "
                        f"Received {self._ready_symbols_count}/{self._total_symbols} symbols. "
                        f"The following symbols are not ready: {', '.join(not_ready_symbols)}"
                    )
            else:  # All symbols were received, but timeout check ran.
                self._log.debug(
                    f"Timeout checked, but all symbols were already received. {self._name} is ready."
                )

            self._is_permanently_ready = True  # Timed out, so state is now final.
            return True

        return False  # Not all symbols ready and not timed out yet.
