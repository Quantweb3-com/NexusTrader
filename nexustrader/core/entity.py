import signal
import asyncio
import socket
from typing import Callable, Coroutine, Any, TypeVar, Literal
from typing import Dict, List
import warnings
from collections import deque
from statistics import median, mean
import redis
import time

from dataclasses import dataclass
from nexustrader.constants import get_redis_config
from nexustrader.core.log import SpdLog
from nexustrader.core.nautilius_core import LiveClock
from nexustrader.schema import Kline, BookL1, Trade

T = TypeVar('T')

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
        self._log = SpdLog.get_logger(type(self).__name__, level="DEBUG", flush=True)
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
            self._log.warn("Signal handlers not supported on this platform")

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


class DataReady:
    def __init__(self, symbols: List[str], timeout: int = 60):
        """
        Initialize DataReady class

        Args:
            symbols: symbols list need to monitor
            timeout: timeout in seconds
        """
        self._log = SpdLog.get_logger(type(self).__name__, level="DEBUG", flush=True)
        self._symbols = {symbol: False for symbol in symbols}
        self._timeout = timeout
        self._clock = LiveClock()
        self._first_data_time: int | None = None

    def input(self, data: Kline | BookL1 | Trade) -> None:
        """
        Input data, update the status of the corresponding symbol

        Args:
            data: data object with symbol attribute
        """

        if not self.ready:
            symbol = data.symbol

            if self._first_data_time is None:
                self._first_data_time = self._clock.timestamp_ms()

            if symbol in self._symbols:
                self._symbols[symbol] = True

    @property
    def ready(self) -> bool:
        """
        Check if all data is ready or if it has timed out

        Returns:
            bool: if all data is ready or timed out, return True
        """
        if self._first_data_time is None:
            return False

        if self._clock.timestamp_ms() - self._first_data_time > self._timeout * 1000:
            not_ready = [symbol for symbol, ready in self._symbols.items() if not ready]
            if not_ready:
                warnings.warn(
                    f"Data receiving timed out. The following symbols are not ready: {', '.join(not_ready)}"
                )
            return True

        # check if all data is ready
        return all(self._symbols.values())


class MovingAverage:
    """
    Calculate moving median or mean using a sliding window.
    
    Args:
        length: Length of the sliding window
        method: 'median' or 'mean' calculation method
    """
    def __init__(self, length: int, method: Literal['median', 'mean'] = 'mean'):
        if method not in ['median', 'mean']:
            raise ValueError("method must be either 'median' or 'mean'")
            
        self._length = length
        self._method = method
        self._window = deque(maxlen=length)
        self._calc_func = median if method == 'median' else mean

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
