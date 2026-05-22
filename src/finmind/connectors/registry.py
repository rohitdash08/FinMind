from typing import Dict, Type
from .base import BaseBankConnector


class ConnectorRegistry:
    """Registry for managing bank connector implementations."""

    _connectors: Dict[str, Type[BaseBankConnector]] = {}

    @classmethod
    def register(cls, name: str, connector_class: Type[BaseBankConnector]) -> None:
        """Register a new bank connector."""
        if not issubclass(connector_class, BaseBankConnector):
            raise ValueError(f"{connector_class} must inherit from BaseBankConnector")
        cls._connectors[name] = connector_class

    @classmethod
    def get(cls, name: str) -> Type[BaseBankConnector]:
        """Get a connector class by name."""
        if name not in cls._connectors:
            raise KeyError(f"Connector '{name}' not found. Available: {list(cls._connectors.keys())}")
        return cls._connectors[name]

    @classmethod
    def list(cls) -> Dict[str, Type[BaseBankConnector]]:
        """List all registered connectors."""
        return cls._connectors.copy()

    @classmethod
    def unregister(cls, name: str) -> None:
        """Unregister a connector."""
        cls._connectors.pop(name, None)