"""
NexusTrader core abstractions – nautilus-trader free implementation.

All components previously imported from nautilus_trader are now provided by
nexus_core (pure Python) and loguru (pure-Python high-performance logging
with built-in time-based log rotation).
"""

from __future__ import annotations

import sys
from loguru import logger as _loguru

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
# loguru level constants (kept as public names for API compatibility)
# ---------------------------------------------------------------------------
TRACE = 5       # loguru native TRACE level
DEBUG = 10
INFO = 20
WARNING = 30
ERROR = 40

# Set a default `component` extra so format strings never raise KeyError
# when logging is triggered outside the Logger shim (e.g. third-party code).
_loguru.configure(extra={"component": ""})

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_LEVEL_STR_MAP: dict[str, str] = {
    "TRACE":   "TRACE",
    "DEBUG":   "DEBUG",
    "INFO":    "INFO",
    "WARNING": "WARNING",
    "ERROR":   "ERROR",
    "OFF":     "ERROR",   # "OFF" → suppress almost everything
}

# Maps TimedRotatingFileHandler `when` values to loguru rotation strings
_ROTATION_WHEN_MAP: dict[str, str] = {
    "midnight": "00:00",
    "h":        "1 hour",
    "m":        "1 minute",
    "s":        "1 second",
    "w0":       "monday",
    "w1":       "tuesday",
    "w2":       "wednesday",
    "w3":       "thursday",
    "w4":       "friday",
    "w5":       "saturday",
    "w6":       "sunday",
}

_FMT_HUMAN = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} [{level:<7}] {extra[component]}: {message}"
)
_FMT_UNIX = "{time:X} [{level}] {extra[component]}: {message}"


def _make_filter(default_level: str, name_levels: dict[str, str]):
    """Return a loguru filter that applies per-component log levels."""
    # pre-compute numeric levels for speed
    _num: dict[str, int] = {
        "TRACE": TRACE, "DEBUG": DEBUG, "INFO": INFO,
        "WARNING": WARNING, "ERROR": ERROR,
    }
    default_no = _num.get(default_level.upper(), INFO)
    comp_map = {
        name: _num.get(lvl.upper(), INFO)
        for name, lvl in name_levels.items()
        if name is not None
    }

    def _filter(record: dict) -> bool:
        component = record["extra"].get("component", "")
        threshold = comp_map.get(component, default_no)
        return record["level"].no >= threshold

    return _filter


# ---------------------------------------------------------------------------
# Logger shim – same interface as the old nautilus Logger
# ---------------------------------------------------------------------------


class Logger:
    """Thin shim around loguru that matches the nautilus Logger interface.

    Usage (same as before)::

        self._log = Logger(name=type(self).__name__)
        # or positionally:
        self._log = Logger(type(self).__name__)
    """

    def __init__(self, name: str = "") -> None:
        # bind the component name so it appears in every log record
        self._logger = _loguru.bind(component=name)

    def trace(self, msg: str, **kwargs) -> None:
        self._logger.trace(msg)

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


def setup_nautilus_core(
    trader_id: str,
    # loguru-style parameters
    filename: str | None = None,
    level: str = "INFO",
    name_levels: dict[str | None, str] | None = None,
    unix_ts: bool = False,
    batch_size: int | None = None,   # kept for API compatibility, not used
    # Time-rotating file handler parameters
    rotation_when: str = "midnight",  # 'midnight', 'W0'–'W6', 'h', 'm', 's'
    rotation_interval: int = 1,       # kept for API compatibility
    rotation_backup_count: int = 30,  # keep N days of logs
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
        When *filename* is provided, loguru adds a time-rotating sink that
        rotates at ``rotation_when`` (default ``"midnight"``), retaining
        ``rotation_backup_count`` backup files (default 30 days).
    """
    # Resolve effective log level
    effective_level = level if level != "INFO" else level_stdout
    log_level = _LEVEL_STR_MAP.get(effective_level.upper(), "INFO")

    # Resolve file path (support both new and legacy parameter names)
    log_file: str | None = filename or (
        f"{directory}/{file_name}" if directory and file_name else file_name
    )

    # Build per-component filter
    merged_name_levels: dict[str, str] = {}
    if name_levels:
        merged_name_levels.update(
            {k: v for k, v in name_levels.items() if k is not None}
        )
    if component_levels:
        merged_name_levels.update(component_levels)
    log_filter = _make_filter(log_level, merged_name_levels)

    fmt = _FMT_UNIX if unix_ts else _FMT_HUMAN

    # Remove all existing handlers (re-entrant safety)
    _loguru.remove()

    # stdout handler (colorize only when stdout is a TTY)
    _loguru.add(
        sys.stdout,
        level=log_level,
        format=fmt,
        filter=log_filter,
        colorize=sys.stdout.isatty(),
    )

    # Optional time-rotating file handler
    if log_file:
        rotation = _ROTATION_WHEN_MAP.get(rotation_when.lower(), "00:00")
        _loguru.add(
            log_file,
            level=log_level,
            format=fmt,
            filter=log_filter,
            rotation=rotation,
            retention=f"{rotation_backup_count} days",
            encoding="utf-8",
            enqueue=True,   # async, non-blocking
        )

    clock = LiveClock()
    msgbus = MessageBus(trader_id=TraderId(trader_id), clock=clock)
    return msgbus, clock


# Keep the old name as an alias so existing code doesn't need changing.
setup_nexus_core = setup_nautilus_core
