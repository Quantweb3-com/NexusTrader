"""
Base factory interface for exchange components.

This module defines the abstract base class and context for creating exchange-specific
components in a standardized way.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
from nexustrader.constants import ExchangeType, AccountType
from nexustrader.base import (
    ExchangeManager,
    PublicConnector,
    PrivateConnector,
    ExecutionManagementSystem,
)
from nexustrader.config import (
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
)


@dataclass
class BuildContext:
    """Context object containing shared components for factory methods."""

    msgbus: Any
    clock: Any
    task_manager: Any
    cache: Any
    registry: Any  # OrderRegistry
    is_mock: bool


class ExchangeFactory(ABC):
    """
    Abstract base class for creating exchange-specific components.

    Each exchange should implement this factory to provide standardized
    creation methods for all its components.
    """

    @property
    @abstractmethod
    def exchange_type(self) -> ExchangeType:
        """Return the exchange type this factory handles."""
        pass

    @abstractmethod
    def create_manager(self, basic_config: BasicConfig) -> ExchangeManager:
        """
        Create an ExchangeManager instance.

        Args:
            basic_config: Basic configuration containing API credentials

        Returns:
            Configured ExchangeManager instance
        """
        pass

    @abstractmethod
    def create_public_connector(
        self,
        config: PublicConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
    ) -> PublicConnector:
        """
        Create a PublicConnector instance.

        Args:
            config: Public connector configuration
            exchange: Exchange manager instance
            context: Build context with shared components

        Returns:
            Configured PublicConnector instance
        """
        pass

    @abstractmethod
    def create_private_connector(
        self,
        config: PrivateConnectorConfig,
        exchange: ExchangeManager,
        context: BuildContext,
        account_type: Optional[AccountType] = None,
    ) -> PrivateConnector:
        """
        Create a PrivateConnector instance.

        Args:
            config: Private connector configuration
            exchange: Exchange manager instance
            context: Build context with shared components
            account_type: Override account type (for testnet handling)

        Returns:
            Configured PrivateConnector instance
        """
        pass

    @abstractmethod
    def create_ems(
        self, exchange: ExchangeManager, context: BuildContext
    ) -> ExecutionManagementSystem:
        """
        Create an ExecutionManagementSystem instance.

        Args:
            exchange: Exchange manager instance
            context: Build context with shared components

        Returns:
            Configured ExecutionManagementSystem instance
        """
        pass

    def validate_config(self, basic_config: BasicConfig) -> None:
        """
        Validate exchange-specific configuration.

        Args:
            basic_config: Basic configuration to validate

        Raises:
            ValueError: If configuration is invalid
        """
        # Default implementation - exchanges can override
        pass

    def get_private_account_type(
        self, exchange: ExchangeManager, config: PrivateConnectorConfig
    ) -> AccountType:
        """
        Determine the account type for private connector.

        Some exchanges (like Bybit, OKX) map testnet to different account types.

        Args:
            exchange: Exchange manager instance
            config: Private connector configuration

        Returns:
            Account type to use
        """
        return config.account_type

    def setup_public_connector(
        self,
        exchange: ExchangeManager,
        connector: PublicConnector,
        account_type: AccountType,
    ) -> None:
        """
        Perform any post-creation setup for public connector.

        Some exchanges (like Bitget) need additional setup after creation.

        Args:
            exchange: Exchange manager instance
            connector: Created public connector
            account_type: Account type being used
        """
        # Default implementation - exchanges can override
        pass
