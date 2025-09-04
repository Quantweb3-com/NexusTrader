"""
Factory registry for exchange components.

This module provides a centralized registry for exchange factories with
auto-discovery capabilities.
"""

import importlib
import pkgutil
from typing import Dict, List
from nexustrader.constants import ExchangeType
from nexustrader.exchange.base_factory import ExchangeFactory


class ExchangeRegistry:
    """Registry for exchange factories with auto-discovery."""

    def __init__(self):
        self._factories: Dict[ExchangeType, ExchangeFactory] = {}
        self._auto_discovered = False

    def register(self, factory: ExchangeFactory) -> None:
        """
        Register an exchange factory.

        Args:
            factory: Factory instance to register

        Raises:
            ValueError: If exchange type is already registered
        """
        exchange_type = factory.exchange_type
        if exchange_type in self._factories:
            raise ValueError(f"Exchange {exchange_type} is already registered")

        self._factories[exchange_type] = factory

    def get(self, exchange_type: ExchangeType) -> ExchangeFactory:
        """
        Get factory for exchange type.

        Args:
            exchange_type: Type of exchange

        Returns:
            Factory instance

        Raises:
            ValueError: If exchange type is not registered
        """
        # Auto-discover if not done yet
        if not self._auto_discovered:
            self.discover_factories()

        if exchange_type not in self._factories:
            raise ValueError(f"Exchange {exchange_type} is not registered")

        return self._factories[exchange_type]

    def list_exchanges(self) -> List[ExchangeType]:
        """
        List all registered exchange types.

        Returns:
            List of registered exchange types
        """
        if not self._auto_discovered:
            self.discover_factories()

        return list(self._factories.keys())

    def is_registered(self, exchange_type: ExchangeType) -> bool:
        """
        Check if exchange type is registered.

        Args:
            exchange_type: Type of exchange to check

        Returns:
            True if registered, False otherwise
        """
        if not self._auto_discovered:
            self.discover_factories()

        return exchange_type in self._factories

    def discover_factories(self) -> None:
        """
        Auto-discover and register exchange factories.

        This method scans the nexustrader.exchange package for factory modules
        and automatically registers them.
        """
        if self._auto_discovered:
            return

        try:
            import nexustrader.exchange as exchange_package

            # Get the path of the exchange package
            package_path = exchange_package.__path__

            # Scan for subpackages (exchange implementations)
            for importer, modname, ispkg in pkgutil.iter_modules(package_path):
                if not ispkg or modname in ("__pycache__", "base_factory", "build"):
                    continue

                try:
                    # Try to import the factory module
                    factory_module_name = f"nexustrader.exchange.{modname}.factory"
                    factory_module = importlib.import_module(factory_module_name)

                    # Look for factory classes
                    for attr_name in dir(factory_module):
                        attr = getattr(factory_module, attr_name)

                        # Check if it's a factory class (not the base class)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, ExchangeFactory)
                            and attr is not ExchangeFactory
                        ):
                            # Instantiate and register
                            factory_instance = attr()
                            if factory_instance.exchange_type not in self._factories:
                                self._factories[factory_instance.exchange_type] = (
                                    factory_instance
                                )

                except ImportError:
                    # Skip exchanges that don't have factory modules
                    continue
                except Exception as e:
                    # Log but don't fail on individual exchange errors
                    print(f"Warning: Failed to register factory for {modname}: {e}")
                    continue

        except Exception as e:
            print(f"Warning: Factory auto-discovery failed: {e}")

        self._auto_discovered = True

    def clear(self) -> None:
        """Clear all registered factories (mainly for testing)."""
        self._factories.clear()
        self._auto_discovered = False


# Global registry instance
_registry = ExchangeRegistry()


def register_factory(factory: ExchangeFactory) -> None:
    """
    Register an exchange factory in the global registry.

    Args:
        factory: Factory instance to register
    """
    _registry.register(factory)


def get_factory(exchange_type: ExchangeType) -> ExchangeFactory:
    """
    Get factory for exchange type from the global registry.

    Args:
        exchange_type: Type of exchange

    Returns:
        Factory instance
    """
    return _registry.get(exchange_type)


def list_exchanges() -> List[ExchangeType]:
    """
    List all registered exchange types.

    Returns:
        List of registered exchange types
    """
    return _registry.list_exchanges()


def is_exchange_registered(exchange_type: ExchangeType) -> bool:
    """
    Check if exchange type is registered.

    Args:
        exchange_type: Type of exchange to check

    Returns:
        True if registered, False otherwise
    """
    return _registry.is_registered(exchange_type)


def discover_exchanges() -> None:
    """Force discovery of exchange factories."""
    _registry.discover_factories()
