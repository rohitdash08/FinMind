"""
Connector registry for dynamic provider lookup.

Supports registering connectors by name and instantiating them
with provider-specific configuration.
"""

from typing import Dict, Optional, Type

from .base import BaseBankConnector


class ConnectorRegistry:
    """
    Registry for bank connector implementations.

    Usage:
        registry = ConnectorRegistry()
        registry.register("mock", MockBankConnector)
        connector = registry.get("mock", config={...})
    """

    def __init__(self):
        self._connectors: Dict[str, Type[BaseBankConnector]] = {}

    def register(self, name: str, connector_class: Type[BaseBankConnector]) -> None:
        """
        Register a connector class by provider name.

        Args:
            name: Provider name (e.g., 'plaid', 'mock').
            connector_class: The connector class to register.

        Raises:
            TypeError: If connector_class doesn't extend BaseBankConnector.
        """
        if not issubclass(connector_class, BaseBankConnector):
            raise TypeError(
                f"{connector_class.__name__} must extend BaseBankConnector"
            )
        self._connectors[name.lower()] = connector_class

    def get(
        self, name: str, config: Optional[dict] = None
    ) -> Optional[BaseBankConnector]:
        """
        Get an instance of a registered connector.

        Args:
            name: Provider name.
            config: Optional configuration to pass to the constructor.

        Returns:
            Connector instance, or None if not registered.
        """
        connector_class = self._connectors.get(name.lower())
        if connector_class is None:
            return None
        return connector_class(**(config or {}))

    def list_providers(self) -> list:
        """List all registered provider names."""
        return list(self._connectors.keys())

    def is_registered(self, name: str) -> bool:
        """Check if a provider is registered."""
        return name.lower() in self._connectors


# Global registry instance
_global_registry = ConnectorRegistry()


def register_connector(name: str, connector_class: Type[BaseBankConnector]) -> None:
    """Register a connector in the global registry."""
    _global_registry.register(name, connector_class)


def get_connector(
    name: str, config: Optional[dict] = None
) -> Optional[BaseBankConnector]:
    """Get a connector from the global registry."""
    return _global_registry.get(name, config)


def list_providers() -> list:
    """List all registered providers."""
    return _global_registry.list_providers()
