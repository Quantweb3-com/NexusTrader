"""Public interface for strategy web integration."""

from __future__ import annotations

from .app import StrategyFastAPI, create_strategy_app
from .server import StrategyWebServer

# Default app instance for convenience imports (``from nexustrader.web import app``)
app = create_strategy_app()

__all__ = [
    "StrategyFastAPI",
    "StrategyWebServer",
    "create_strategy_app",
    "app",
]
