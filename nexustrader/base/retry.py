import asyncio
from typing import Callable, Awaitable, Generic, TypeVar
from random import randint

from nexustrader.core.nautilius_core import Logger

T = TypeVar("T")


def get_exponential_backoff(
    num_attempts: int,
    delay_initial_ms: int = 500,
    delay_max_ms: int = 2_000,
    backoff_factor: int = 2,
    jitter: bool = True,
) -> int:
    """
    Compute the backoff delay using exponential backoff and jitter.

    References: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
    """
    delay = min(delay_max_ms, delay_initial_ms * backoff_factor ** (num_attempts - 1))

    if jitter:
        return randint(delay_initial_ms, delay)  # noqa: S311

    return delay


class RetryManager(Generic[T]):
    """
    Provides retry state management for async operations with exponential backoff.

    Parameters
    ----------
    max_retries : int
        The maximum number of retries before failure.
    delay_initial_ms : int
        The initial delay (milliseconds) for retries.
    delay_max_ms : int
        The maximum delay (milliseconds) for exponential backoff.
    backoff_factor : int
        The exponential backoff factor for retry delays.
    exc_types : tuple[type[BaseException], ...]
        The exception types to handle for retries.
    retry_check : Callable[[BaseException], bool] | None
        A function that performs additional checks on the exception.
        If it returns False, a retry will not be attempted.
    """

    def __init__(
        self,
        max_retries: int,
        delay_initial_ms: int,
        delay_max_ms: int,
        backoff_factor: int,
        exc_types: tuple[type[BaseException], ...],
        retry_check: Callable[[BaseException], bool] | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.delay_initial_ms = delay_initial_ms
        self.delay_max_ms = delay_max_ms
        self.backoff_factor = backoff_factor
        self.exc_types = exc_types
        self.retry_check = retry_check
        self.cancel_event = asyncio.Event()
        self._log = Logger(name=type(self).__name__)

        self.name: str | None = None
        self.details: list[object] | None = None
        self.details_str: str | None = None
        self.result: bool = False
        self.message: str | None = None

    def __repr__(self) -> str:
        return f"<{type(self).__name__}(name='{self.name}', details={self.details}) at {hex(id(self))}>"

    async def run(
        self,
        name: str,
        func: Callable[..., Awaitable[T]],
        details: list[object] | None = None,
        jitter: bool = True,
        *args,
        **kwargs,
    ) -> T | None:
        """
        Execute the given `func` with retry management.

        If an exception in `self.exc_types` is raised, a warning is logged
        and the function is retried after a delay until the maximum retries
        are reached.
        """
        retries = 0
        self.name = name
        self.details = details

        try:
            while True:
                if self.cancel_event.is_set():
                    self._cancel()
                    return None

                try:
                    response = await func(*args, **kwargs)
                    self.result = True
                    return response
                except self.exc_types as e:
                    self._log.warning(repr(e))
                    if (
                        (self.retry_check and not self.retry_check(e))
                        or not self.max_retries
                        or retries >= self.max_retries
                    ):
                        self._log_error()
                        self.result = False
                        self.message = str(e)
                        raise

                    retries += 1
                    retry_delay_ms = get_exponential_backoff(
                        delay_initial_ms=self.delay_initial_ms,
                        delay_max_ms=self.delay_max_ms,
                        backoff_factor=self.backoff_factor,
                        num_attempts=retries,
                        jitter=jitter,
                    )
                    self._log_retry(retries, retry_delay_ms=retry_delay_ms)
                    await asyncio.sleep(retry_delay_ms / 1000)
        except asyncio.CancelledError:
            self._cancel()
            return None

    def cancel(self) -> None:
        self._log.debug(f"Canceling {self!r}")
        self.cancel_event.set()

    def clear(self) -> None:
        self.name = None
        self.details = None
        self.details_str = None
        self.result = False
        self.message = None

    def _cancel(self) -> None:
        self._log.warning(f"Canceled retry for '{self.name}'")
        self.result = False
        self.message = "Canceled retry"

    def _log_retry(self, retry: int, retry_delay_ms: int) -> None:
        self._log.warning(
            f"Retrying {retry}/{self.max_retries} for '{self.name}' "
            f"in {retry_delay_ms / 1000}s{self._details_str()}",
        )

    def _log_error(self) -> None:
        self._log.error(
            f"Failed on '{self.name}'{self._details_str()}",
        )

    def _details_str(self) -> str:
        if not self.details:
            return ""

        if not self.details_str:
            self.details_str = ": " + ", ".join([repr(x) for x in self.details])

        return self.details_str
