"""
OKX exchange factory implementation.
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

from nexustrader.exchange.okx.exchange import OkxExchangeManager
from nexustrader.exchange.okx.connector import OkxPublicConnector, OkxPrivateConnector
from nexustrader.exchange.okx.ems import OkxExecutionManagementSystem
from nexustrader.exchange.okx.constants import OkxAccountType


class OkxFactory(ExchangeFactory):
    """Factory for creating OKX exchange components."""

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.OKX

    def create_manager(self, basic_config: BasicConfig) -> ExchangeManager:
        """Create OkxExchangeManager."""
        ccxt_config = {
            "apiKey": basic_config.api_key,
            "secret": basic_config.secret,
            "sandbox": basic_config.testnet,
        }
        if basic_config.passphrase:
            ccxt_config["password"] = basic_config.passphrase

        return OkxExchangeManager(ccxt_config)

    def create_public_connector(
        self,
        config: PublicConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
    ) -> PublicConnector:
        """Create OkxPublicConnector."""
        connector = OkxPublicConnector(
            account_type=config.account_type,
            exchange=exchange,
            msgbus=context.msgbus,
            clock=context.clock,
            task_manager=context.task_manager,
            enable_rate_limit=config.enable_rate_limit,
            custom_url=config.custom_url,
        )

        # OKX needs post-creation setup
        self.setup_public_connector(exchange, connector, config.account_type)
        return connector

    def create_private_connector(
        self,
        config: PrivateConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
        account_type: AccountType = None,
    ) -> PrivateConnector:
        """Create OkxPrivateConnector."""
        # Use provided account_type or determine from exchange testnet status
        if account_type:
            final_account_type = account_type
        else:
            final_account_type = self.get_private_account_type(exchange, config)

        return OkxPrivateConnector(
            exchange=exchange,
            account_type=final_account_type,
            cache=context.cache,
            clock=context.clock,
            msgbus=context.msgbus,
            registry=context.registry,
            enable_rate_limit=config.enable_rate_limit,
            task_manager=context.task_manager,
            max_retries=config.max_retries,
            delay_initial_ms=config.delay_initial_ms,
            delay_max_ms=config.delay_max_ms,
            backoff_factor=config.backoff_factor,
        )

    def create_ems(
        self, exchange: ExchangeManager, context: BuildContext
    ) -> ExecutionManagementSystem:
        """Create OkxExecutionManagementSystem."""
        return OkxExecutionManagementSystem(
            market=exchange.market,
            cache=context.cache,
            msgbus=context.msgbus,
            clock=context.clock,
            task_manager=context.task_manager,
            registry=context.registry,
            is_mock=context.is_mock,
        )

    def get_private_account_type(
        self, exchange: ExchangeManager, config: PrivateConnectorConfig
    ) -> AccountType:
        """Determine account type based on testnet status."""
        return OkxAccountType.DEMO if exchange.is_testnet else OkxAccountType.LIVE

    def setup_public_connector(
        self,
        exchange: ExchangeManager,
        connector: PublicConnector,
        account_type: AccountType,
    ) -> None:
        """Setup public connector account type."""
        exchange.set_public_connector_account_type(account_type)
