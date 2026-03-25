"""
NexusTrader core abstractions – nautilus-trader free implementation.

All components previously imported from nautilus_trader are now provided by
nexus_core (pure Python) and nexuslog (lightweight Rust-backed logging).
"""

from __future__ import annotations

import nexuslog as _nexuslog

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
# Logger shim
# ---------------------------------------------------------------------------
# Expose a Logger *callable* that behaves like nautilus Logger(name=...).
# Under the hood it just returns a nexuslog logger.

class Logger:
    """Thin shim around nexuslog that matches the nautilus Logger interface.

    Usage (same as before)::

        self._log = Logger(name=type(self).__name__)
        # or positionally:
        self._log = Logger(type(self).__name__)
    """

    def __init__(self, name: str = ""):
        self._logger = _nexuslog.getLogger(name=name)

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
        self._logger.error(msg)  # nexuslog may not have critical; map to error


# ---------------------------------------------------------------------------
# Setup helper
# ---------------------------------------------------------------------------

def setup_nautilus_core(
    trader_id: str,
    # nexuslog-style parameters (used by reference implementation)
    filename: str | None = None,
    level: str = "INFO",
    name_levels: dict[str | None, str] | None = None,
    unix_ts: bool = False,
    batch_size: int | None = None,
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
    ignored) *and* the new nexuslog-style parameters so that existing callers
    continue to work without changes.
    """
    # Resolve effective log level: prefer the explicit `level` kwarg; fall
    # back to `level_stdout` for callers that still use the old signature.
    effective_level = level if level != "INFO" else level_stdout

    # Map log level string to nexuslog constant
    level_map = {
        "TRACE": _nexuslog.TRACE,
        "DEBUG": _nexuslog.DEBUG,
        "INFO": _nexuslog.INFO,
        "WARNING": _nexuslog.WARNING,
        "ERROR": _nexuslog.ERROR,
        "OFF": _nexuslog.ERROR,  # "OFF" → suppress almost everything
    }
    log_level = level_map.get(effective_level.upper(), _nexuslog.INFO)

    _name_levels: dict[str | None, int] | None = None
    if name_levels:
        _name_levels = {
            name: level_map.get(lvl.upper(), _nexuslog.INFO)
            for name, lvl in name_levels.items()
        }
    elif component_levels:
        _name_levels = {
            name: level_map.get(lvl.upper(), _nexuslog.INFO)
            for name, lvl in component_levels.items()
        }

    # Resolve file path
    log_file: str | None = filename or (
        f"{directory}/{file_name}" if directory and file_name else file_name
    )

    kwargs: dict = dict(level=log_level)
    if log_file:
        kwargs["filename"] = log_file
    if _name_levels is not None:
        kwargs["name_levels"] = _name_levels
    if unix_ts:
        kwargs["unix_ts"] = unix_ts
    # Default batch_size=1 so logs are written immediately to stdout.
    # Callers can override with a larger value for file-logging performance.
    kwargs["batch_size"] = batch_size if batch_size is not None else 1

    _nexuslog.basicConfig(**kwargs)

    clock = LiveClock()
    msgbus = MessageBus(trader_id=TraderId(trader_id), clock=clock)
    return msgbus, clock


# Keep the old name as an alias so existing code doesn't need changing.
setup_nexus_core = setup_nautilus_core
