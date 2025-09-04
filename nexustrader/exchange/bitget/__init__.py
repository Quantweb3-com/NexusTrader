from nexustrader.exchange.bitget.exchange import BitgetExchangeManager
from nexustrader.exchange.bitget.connector import (
    BitgetPublicConnector,
    BitgetPrivateConnector,
)
from nexustrader.exchange.bitget.constants import BitgetAccountType
from nexustrader.exchange.bitget.ems import BitgetExecutionManagementSystem
from nexustrader.exchange.bitget.oms import BitgetOrderManagementSystem
from nexustrader.exchange.bitget.factory import BitgetFactory

# Auto-register factory on import
try:
    from nexustrader.exchange.registry import register_factory

    register_factory(BitgetFactory())
except ImportError:
    # Registry not available yet during bootstrap
    pass

__all__ = [
    "BitgetExchangeManager",
    "BitgetPublicConnector",
    "BitgetPrivateConnector",
    "BitgetAccountType",
    "BitgetExecutionManagementSystem",
    "BitgetOrderManagementSystem",
    "BitgetFactory",
]
