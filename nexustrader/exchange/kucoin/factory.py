"""
KuCoin exchange factory implementation.
"""

from nexustrader.constants import ExchangeType, AccountType
from nexustrader.config import (
	PublicConnectorConfig,
	PrivateConnectorConfig,
	BasicConfig,
)
from nexustrader.exchange.base_factory import ExchangeFactory, BuildContext
from nexustrader.base import (
	ExchangeManager,
	PublicConnector,
	PrivateConnector,
	ExecutionManagementSystem,
)

from .exchange import KuCoinExchangeManager
from .connector import KucoinPublicConnector
from .ems import KucoinExecutionManagementSystem

# Private connector is implemented in kucoin/connector.py
from .connector import KucoinPrivateConnector  # type: ignore


class KucoinFactory(ExchangeFactory):
	"""Factory for creating KuCoin exchange components."""

	@property
	def exchange_type(self) -> ExchangeType:
		return ExchangeType.KUCOIN

	def create_manager(self, basic_config: BasicConfig) -> ExchangeManager:
		"""Create KuCoinExchangeManager."""
		ccxt_config = {
			"apiKey": basic_config.api_key,
			"secret": basic_config.secret,
			"sandbox": basic_config.testnet,
		}
		if basic_config.passphrase:
			ccxt_config["password"] = basic_config.passphrase

		return KuCoinExchangeManager(ccxt_config)

	def create_public_connector(
		self,
		config: PublicConnectorConfig,
		exchange: ExchangeManager,
		context: BuildContext,
	) -> PublicConnector:
		"""Create KucoinPublicConnector."""
		connector = KucoinPublicConnector(
			account_type=config.account_type,
			exchange=exchange,  # type: ignore[arg-type]
			msgbus=context.msgbus,
			clock=context.clock,
			task_manager=context.task_manager,
			enable_rate_limit=config.enable_rate_limit,
			custom_url=config.custom_url,
		)

		# Post-creation setup if exchange supports it
		if hasattr(exchange, "set_public_connector_account_type"):
			exchange.set_public_connector_account_type(config.account_type)  # type: ignore[attr-defined]
		return connector

	def create_private_connector(
		self,
		config: PrivateConnectorConfig,
		exchange: ExchangeManager,
		context: BuildContext,
		account_type: AccountType = None,
	) -> PrivateConnector:
		"""Create KucoinPrivateConnector."""
		final_account_type = account_type or config.account_type

		return KucoinPrivateConnector(
			exchange=exchange,  # type: ignore[arg-type]
			account_type=final_account_type,  # type: ignore[arg-type]
			cache=context.cache,
			registry=context.registry,
			clock=context.clock,
			msgbus=context.msgbus,
			task_manager=context.task_manager,
			enable_rate_limit=config.enable_rate_limit,
			max_retries=config.max_retries,
			delay_initial_ms=config.delay_initial_ms,
			delay_max_ms=config.delay_max_ms,
			backoff_factor=config.backoff_factor,
		)

	def create_ems(
		self, exchange: ExchangeManager, context: BuildContext
	) -> ExecutionManagementSystem:
		"""Create KucoinExecutionManagementSystem."""
		return KucoinExecutionManagementSystem(
			market=exchange.market,
			cache=context.cache,
			msgbus=context.msgbus,
			clock=context.clock,
			task_manager=context.task_manager,
			registry=context.registry,
			is_mock=context.is_mock,
		)

	def setup_public_connector(
		self,
		exchange: ExchangeManager,
		connector: PublicConnector,
		account_type: AccountType,
	) -> None:
		"""Setup public connector account type if exchange supports it."""
		if hasattr(exchange, "set_public_connector_account_type"):
			exchange.set_public_connector_account_type(account_type)  # type: ignore[attr-defined]

