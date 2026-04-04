"""
NexusTrader core abstractions – nautilus-trader free implementation.

All components previously imported from nautilus_trader are now provided by
nexus_core (pure Python) and picologging (high-performance C-extension logging
with TimedRotatingFileHandler for daily log rotation).
"""

from __future__ import annotations

import sys
import time
import picologging as logging
from picologging.handlers import TimedRotatingFileHandler

from nexustrader.core.nexus_core import (  # noqa: F401
    MessageBus,
    LiveClock,
    TimeEvent,
    TraderId,
    UUID4,
    hmac_signature,
    rsa_signature,
    ed25519_signature,
)

# ---------------------------------------------------------------------------
# TRACE level – picologging does not support addLevelName / custom levels,
# so TRACE is mapped to DEBUG (numeric alias kept for API compatibility).
# ---------------------------------------------------------------------------
TRACE = logging.DEBUG

# ---------------------------------------------------------------------------
# Log formatter
# picologging does not interpolate %(msecs)03d or %-alignment in format
# strings, so we subclass Formatter to inject milliseconds manually.
# ---------------------------------------------------------------------------
_DATEFMT = "%Y-%m-%d %H:%M:%S"


class _MsFormatter(logging.Formatter):
    """Formatter that appends milliseconds: 2024-01-01 12:00:00.123 [INFO] name: msg

    picologging's C-extension bypasses Python-level formatTime overrides, so
    we override format() directly instead.
    """

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        ts = time.strftime(_DATEFMT, time.localtime(record.created))
        ms = int((record.created % 1) * 1000)
        return f"{ts}.{ms:03d} [{record.levelname}] {record.name}: {record.getMessage()}"


class _UnixTsFormatter(logging.Formatter):
    """Formatter that uses Unix timestamp instead of human-readable datetime."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        return f"{record.created:.6f} [{record.levelname}] {record.name}: {record.getMessage()}"


def _make_formatter(unix_ts: bool) -> logging.Formatter:
    return _UnixTsFormatter() if unix_ts else _MsFormatter()

# ---------------------------------------------------------------------------
# Logger shim – same interface as the old nautilus Logger
# ---------------------------------------------------------------------------


class Logger:
    """Thin shim around picologging that matches the nautilus Logger interface.

    Usage (same as before)::

        self._log = Logger(name=type(self).__name__)
        # or positionally:
        self._log = Logger(type(self).__name__)
    """

    def __init__(self, name: str = "") -> None:
        self._logger: logging.Logger = logging.getLogger(name)

    def trace(self, msg: str, **kwargs) -> None:
        self._logger.debug(msg)  # picologging has no TRACE; mapped to DEBUG

    def debug(self, msg: str, **kwargs) -> None:
        self._logger.debug(msg)

    def info(self, msg: str, **kwargs) -> None:
        self._logger.info(msg)

    def warning(self, msg: str, **kwargs) -> None:
        self._logger.warning(msg)

    def error(self, msg: str, **kwargs) -> None:
        self._logger.error(msg)

    def critical(self, msg: str, **kwargs) -> None:
        self._logger.critical(msg)


# ---------------------------------------------------------------------------
# Setup helper
# ---------------------------------------------------------------------------

_LEVEL_MAP: dict[str, int] = {
    "TRACE": TRACE,
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "OFF": logging.ERROR,  # "OFF" → suppress almost everything
}


def setup_nautilus_core(
    trader_id: str,
    # picologging-style parameters
    filename: str | None = None,
    level: str = "INFO",
    name_levels: dict[str | None, str] | None = None,
    unix_ts: bool = False,
    batch_size: int | None = None,  # kept for API compatibility, not used
    # Time-rotating file handler parameters
    rotation_when: str = "midnight",   # 'midnight', 'W0'–'W6', 'h', 'm', 's'
    rotation_interval: int = 1,
    rotation_backup_count: int = 30,   # keep 30 days of logs
    # Legacy nautilus-style parameters (ignored – kept for signature compat)
    level_stdout: str = "INFO",
    level_file: str | None = None,
    directory: str | None = None,
    file_name: str | None = None,
    file_format: str | None = None,
    is_colored: bool | None = None,
    print_config: bool | None = None,
    component_levels: dict[str, str] | None = None,
    file_rotate: tuple[int, int] | None = None,
    is_bypassed: bool | None = None,
    log_components_only: bool | None = None,
) -> tuple[MessageBus, LiveClock]:
    """Initialise logging and return (msgbus, clock).

    Accepts both the old nautilus-style keyword arguments (which are silently
    ignored) *and* the new parameters so that existing callers continue to
    work without changes.

    Log rotation:
        When *filename* is provided a ``TimedRotatingFileHandler`` is added
        that rotates at ``rotation_when`` (default ``"midnight"``), keeping
        ``rotation_backup_count`` backup files (default 30 days).
    """
    # Resolve effective log level: prefer explicit `level`; fall back to
    # `level_stdout` for callers still using the old signature.
    effective_level = level if level != "INFO" else level_stdout
    log_level = _LEVEL_MAP.get(effective_level.upper(), logging.INFO)

    # Resolve log file path (support both new and legacy parameter names)
    log_file: str | None = filename or (
        f"{directory}/{file_name}" if directory and file_name else file_name
    )

    formatter = _make_formatter(unix_ts)

    # Root logger
    root = logging.getLogger()
    root.setLevel(log_level)

    # Remove any handlers added by a previous call (re-entrant safety)
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()

    # stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)
    stdout_handler.setFormatter(formatter)
    root.addHandler(stdout_handler)

    # Optional time-rotating file handler
    if log_file:
        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when=rotation_when,
            interval=rotation_interval,
            backupCount=rotation_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # Per-component log levels
    effective_name_levels = name_levels or component_levels or {}
    for name, lvl in effective_name_levels.items():
        if name is not None:
            logging.getLogger(name).setLevel(
                _LEVEL_MAP.get(lvl.upper(), logging.INFO)
            )

    clock = LiveClock()
    msgbus = MessageBus(trader_id=TraderId(trader_id), clock=clock)
    return msgbus, clock


# Keep the old name as an alias so existing code doesn't need changing.
setup_nexus_core = setup_nautilus_core
