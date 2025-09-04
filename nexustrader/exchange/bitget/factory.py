"""
Bitget exchange factory implementation.
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

from nexustrader.exchange.bitget.exchange import BitgetExchangeManager
from nexustrader.exchange.bitget.connector import (
    BitgetPublicConnector,
    BitgetPrivateConnector,
)
from nexustrader.exchange.bitget.ems import BitgetExecutionManagementSystem


class BitgetFactory(ExchangeFactory):
    """Factory for creating Bitget exchange components."""

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.BITGET

    def create_manager(self, basic_config: BasicConfig) -> ExchangeManager:
        """Create BitgetExchangeManager."""
        ccxt_config = {
            "apiKey": basic_config.api_key,
            "secret": basic_config.secret,
            "sandbox": basic_config.testnet,
        }
        if basic_config.passphrase:
            ccxt_config["password"] = basic_config.passphrase

        return BitgetExchangeManager(ccxt_config)

    def create_public_connector(
        self,
        config: PublicConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
    ) -> PublicConnector:
        """Create BitgetPublicConnector."""
        connector = BitgetPublicConnector(
            account_type=config.account_type,
            exchange=exchange,
            msgbus=context.msgbus,
            clock=context.clock,
            task_manager=context.task_manager,
            enable_rate_limit=config.enable_rate_limit,
            custom_url=config.custom_url,
        )

        # Bitget needs post-creation setup
        self.setup_public_connector(exchange, connector, config.account_type)
        return connector

    def create_private_connector(
        self,
        config: PrivateConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
        account_type: AccountType = None,
    ) -> PrivateConnector:
        """Create BitgetPrivateConnector."""
        # Use provided account_type or fall back to config
        final_account_type = account_type or config.account_type

        return BitgetPrivateConnector(
            exchange=exchange,
            account_type=final_account_type,
            cache=context.cache,
            msgbus=context.msgbus,
            clock=context.clock,
            registry=context.registry,
            enable_rate_limit=config.enable_rate_limit,
            task_manager=context.task_manager,
            max_retries=config.max_retries,
            delay_initial_ms=config.delay_initial_ms,
            delay_max_ms=config.delay_max_ms,
            backoff_factor=config.backoff_factor,
            max_slippage=config.max_slippage,
        )

    def create_ems(
        self, exchange: ExchangeManager, context: BuildContext
    ) -> ExecutionManagementSystem:
        """Create BitgetExecutionManagementSystem."""
        return BitgetExecutionManagementSystem(
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
        exchange: BitgetExchangeManager,
        connector: PublicConnector,
        account_type: AccountType,
    ) -> None:
        """Setup public connector account type."""
        exchange.set_public_connector_account_type(account_type)
