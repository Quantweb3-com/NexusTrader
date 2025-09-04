from nexustrader.exchange.binance.constants import BinanceAccountType
from nexustrader.exchange.binance.exchange import BinanceExchangeManager
from nexustrader.exchange.binance.connector import (
    BinancePublicConnector,
    BinancePrivateConnector,
)
from nexustrader.exchange.binance.rest_api import BinanceApiClient
from nexustrader.exchange.binance.ems import BinanceExecutionManagementSystem
from nexustrader.exchange.binance.oms import BinanceOrderManagementSystem
from nexustrader.exchange.binance.factory import BinanceFactory

# Auto-register factory on import
try:
    from nexustrader.exchange.registry import register_factory

    register_factory(BinanceFactory())
except ImportError:
    # Registry not available yet during bootstrap
    pass

__all__ = [
    "BinanceAccountType",
    "BinanceExchangeManager",
    "BinancePublicConnector",
    "BinancePrivateConnector",
    "BinanceHttpClient",
    "BinanceApiClient",
    "BinanceExecutionManagementSystem",
    "BinanceOrderManagementSystem",
    "BinanceFactory",
]
