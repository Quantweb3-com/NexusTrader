from nexustrader.exchange.kucoin.constants import KucoinAccountType
from nexustrader.exchange.kucoin.exchange import KuCoinExchangeManager
from nexustrader.exchange.kucoin.connector import (
	KucoinPublicConnector,
	KucoinPrivateConnector,
)
from nexustrader.exchange.kucoin.rest_api import KucoinApiClient
from nexustrader.exchange.kucoin.ems import KucoinExecutionManagementSystem
from nexustrader.exchange.kucoin.oms import KucoinOrderManagementSystem
from nexustrader.exchange.kucoin.factory import KucoinFactory

# Auto-register factory on import
try:
	from nexustrader.exchange.registry import register_factory

	register_factory(KucoinFactory())
except ImportError:
	# Registry not available yet during bootstrap
	pass

__all__ = [
	"KucoinAccountType",
	"KuCoinExchangeManager",
	"KucoinPublicConnector",
	"KucoinPrivateConnector",
	"KucoinApiClient",
	"KucoinExecutionManagementSystem",
	"KucoinOrderManagementSystem",
	"KucoinFactory",
]

