"""
MetaTrader5 lazy-import bridge.

All MT5 API calls must go through this module.  The ``MetaTrader5``
package is only imported when first accessed so that users who do not use
the Bybit TradeFi connector are not affected in any way.
"""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import MetaTrader5 as _Mt5Module  # noqa: F401 – type hint only

_mt5_module = None

# MT5 integer constants that the official __init__.py normally exports but
# _core.pyd does not.  We patch these onto the module object when missing.
_MT5_CONSTANTS = {
    # Trade actions
    "TRADE_ACTION_DEAL": 1,
    "TRADE_ACTION_PENDING": 5,
    "TRADE_ACTION_SLTP": 6,
    "TRADE_ACTION_MODIFY": 7,
    "TRADE_ACTION_REMOVE": 8,
    "TRADE_ACTION_CLOSE_BY": 10,
    # Order types
    "ORDER_TYPE_BUY": 0,
    "ORDER_TYPE_SELL": 1,
    "ORDER_TYPE_BUY_LIMIT": 2,
    "ORDER_TYPE_SELL_LIMIT": 3,
    "ORDER_TYPE_BUY_STOP": 4,
    "ORDER_TYPE_SELL_STOP": 5,
    "ORDER_TYPE_BUY_STOP_LIMIT": 6,
    "ORDER_TYPE_SELL_STOP_LIMIT": 7,
    "ORDER_TYPE_CLOSE_BY": 8,
    # Order filling
    "ORDER_FILLING_FOK": 0,
    "ORDER_FILLING_IOC": 1,
    "ORDER_FILLING_RETURN": 2,
    # Order time
    "ORDER_TIME_GTC": 0,
    "ORDER_TIME_DAY": 1,
    "ORDER_TIME_SPECIFIED": 2,
    "ORDER_TIME_SPECIFIED_DAY": 3,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_platform() -> None:
    """Raise SystemExit when not running on Windows."""
    if platform.system() != "Windows":
        raise SystemExit(
            f"Bybit TradeFi (MT5) requires Windows, but current platform is "
            f"{platform.system()}.\n"
            "MetaTrader5 does not support Linux/macOS. "
            "Please run this strategy on a Windows machine with MT5 installed."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_mt5():
    """
    Return the MetaTrader5 module, importing it lazily on first call.

    Raises
    ------
    RuntimeError
        If the current platform is not Windows.
    ImportError
        If the ``MetaTrader5`` package is not installed.
    """
    global _mt5_module
    if _mt5_module is None:
        _check_platform()
        try:
            # Try the standard top-level package first (works when __init__.py
            # is present).  If the package was installed without __init__.py
            # (a known PyPI packaging quirk), fall back to importing _core
            # directly so that all MT5 functions are still available.
            try:
                import MetaTrader5 as mt5  # noqa: PLC0415

                if not hasattr(mt5, "initialize"):
                    from MetaTrader5 import _core as mt5  # noqa: PLC0415
            except ImportError:
                from MetaTrader5 import _core as mt5  # noqa: PLC0415
            _mt5_module = mt5
            # Patch any missing constants (absent when __init__.py is not installed)
            for _name, _value in _MT5_CONSTANTS.items():
                if not hasattr(_mt5_module, _name):
                    setattr(_mt5_module, _name, _value)
        except ImportError:
            raise ImportError(
                "MetaTrader5 package is required for Bybit TradeFi integration.\n"
                "Install it with:\n"
                "  uv add MetaTrader5          # if using uv (recommended)\n"
                "  pip install MetaTrader5     # if using pip\n"
                "Note: MetaTrader5 is only supported on Windows."
            ) from None
    return _mt5_module


def check_terminal_connected() -> tuple[bool, str]:
    """
    Verify that the MT5 terminal is running and connected to a broker.

    Returns
    -------
    (success, error_message)
    """
    mt5 = get_mt5()
    terminal_info = mt5.terminal_info()
    if terminal_info is None:
        err = mt5.last_error()
        return False, f"MT5 terminal not found or not running: {err}"
    if not terminal_info.connected:
        return False, (
            "MT5 terminal is running but NOT connected to the broker server. "
            "Please log in to the terminal manually and ensure the connection icon "
            "is green before starting NexusTrader."
        )
    return True, ""


def mt5_initialize(path: str | None = None) -> tuple[bool, str]:
    """
    Call ``mt5.initialize()``.

    Parameters
    ----------
    path:
        Optional filesystem path to the MT5 terminal executable.

    Returns
    -------
    (success, error_message)
    """
    mt5 = get_mt5()
    kwargs: dict = {}
    if path:
        kwargs["path"] = path
    if not mt5.initialize(**kwargs):
        err = mt5.last_error()
        return False, f"mt5.initialize() failed: {err}"
    return True, ""


def mt5_login(login: int, password: str, server: str) -> tuple[bool, str]:
    """
    Authenticate with the broker via the MT5 terminal.

    Parameters
    ----------
    login:
        MT5 account number.
    password:
        MT5 account password.
    server:
        Broker server name (e.g. ``"BybitBroker-Demo"``).

    Returns
    -------
    (success, error_message)
    """
    mt5 = get_mt5()
    if not mt5.login(login=login, password=password, server=server):
        err = mt5.last_error()
        return False, (
            f"mt5.login() failed (login={login}, server={server}): {err}. "
            "Please verify your credentials and that the MT5 terminal is open."
        )
    return True, ""


def mt5_shutdown() -> None:
    """Gracefully shut down the MT5 connection (if active)."""
    global _mt5_module
    if _mt5_module is not None:
        try:
            _mt5_module.shutdown()
        except Exception:
            pass
