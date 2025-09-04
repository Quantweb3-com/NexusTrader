"""
Binance exchange factory implementation.
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

from nexustrader.exchange.binance.exchange import BinanceExchangeManager
from nexustrader.exchange.binance.connector import (
    BinancePublicConnector,
    BinancePrivateConnector,
)
from nexustrader.exchange.binance.ems import BinanceExecutionManagementSystem


class BinanceFactory(ExchangeFactory):
    """Factory for creating Binance exchange components."""

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.BINANCE

    def create_manager(self, basic_config: BasicConfig) -> ExchangeManager:
        """Create BinanceExchangeManager."""
        ccxt_config = {
            "apiKey": basic_config.api_key,
            "secret": basic_config.secret,
            "sandbox": basic_config.testnet,
        }
        if basic_config.passphrase:
            ccxt_config["password"] = basic_config.passphrase

        return BinanceExchangeManager(ccxt_config)

    def create_public_connector(
        self,
        config: PublicConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
    ) -> PublicConnector:
        """Create BinancePublicConnector."""
        return BinancePublicConnector(
            account_type=config.account_type,
            exchange=exchange,
            msgbus=context.msgbus,
            clock=context.clock,
            task_manager=context.task_manager,
            enable_rate_limit=config.enable_rate_limit,
            custom_url=config.custom_url,
        )

    def create_private_connector(
        self,
        config: PrivateConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
        account_type: AccountType = None,
    ) -> PrivateConnector:
        """Create BinancePrivateConnector."""
        # Use provided account_type or fall back to config
        final_account_type = account_type or config.account_type

        return BinancePrivateConnector(
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
        """Create BinanceExecutionManagementSystem."""
        return BinanceExecutionManagementSystem(
            market=exchange.market,
            cache=context.cache,
            msgbus=context.msgbus,
            clock=context.clock,
            task_manager=context.task_manager,
            registry=context.registry,
            is_mock=context.is_mock,
        )
