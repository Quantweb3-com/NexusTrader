"""
HyperLiquid exchange factory implementation.
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

from nexustrader.exchange.hyperliquid.exchange import HyperLiquidExchangeManager
from nexustrader.exchange.hyperliquid.connector import (
    HyperLiquidPublicConnector,
    HyperLiquidPrivateConnector,
)
from nexustrader.exchange.hyperliquid.ems import HyperLiquidExecutionManagementSystem


class HyperLiquidFactory(ExchangeFactory):
    """Factory for creating HyperLiquid exchange components."""

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.HYPERLIQUID

    def create_manager(self, basic_config: BasicConfig) -> ExchangeManager:
        """Create HyperLiquidExchangeManager."""
        ccxt_config = {
            "apiKey": basic_config.api_key,
            "secret": basic_config.secret,
            "sandbox": basic_config.testnet,
        }
        if basic_config.passphrase:
            ccxt_config["password"] = basic_config.passphrase

        return HyperLiquidExchangeManager(ccxt_config)

    def create_public_connector(
        self,
        config: PublicConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
    ) -> PublicConnector:
        """Create HyperLiquidPublicConnector."""
        connector = HyperLiquidPublicConnector(
            account_type=config.account_type,
            exchange=exchange,
            msgbus=context.msgbus,
            clock=context.clock,
            task_manager=context.task_manager,
            enable_rate_limit=config.enable_rate_limit,
            custom_url=config.custom_url,
        )

        # HyperLiquid needs post-creation setup
        self.setup_public_connector(exchange, connector, config.account_type)
        return connector

    def create_private_connector(
        self,
        config: PrivateConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
        account_type: AccountType = None,
    ) -> PrivateConnector:
        """Create HyperLiquidPrivateConnector."""
        # Use provided account_type or fall back to config
        final_account_type = account_type or config.account_type

        return HyperLiquidPrivateConnector(
            exchange=exchange,
            account_type=final_account_type,
            cache=context.cache,
            clock=context.clock,
            msgbus=context.msgbus,
            registry=context.registry,
            enable_rate_limit=config.enable_rate_limit,
            task_manager=context.task_manager,
            max_slippage=config.max_slippage,
        )

    def create_ems(
        self, exchange: ExchangeManager, context: BuildContext
    ) -> ExecutionManagementSystem:
        """Create HyperLiquidExecutionManagementSystem."""
        return HyperLiquidExecutionManagementSystem(
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
        """Setup public connector account type."""
        exchange.set_public_connector_account_type(account_type)
