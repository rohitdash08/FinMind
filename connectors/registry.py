"""Connector registry and factory pattern for plugin discovery."""

from __future__ import annotations

import logging
from typing import Dict, Optional, Type

from connectors.base import BankConnector, ConnectorError

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """Registry for discovering and instantiating bank connectors.

    Supports both explicit registration and auto-discovery of built-in
    connectors. Acts as a factory for creating connector instances.

    Usage:
        registry = ConnectorRegistry()
        registry.auto_register()  # loads built-in connectors

        # Or register manually
        registry.register("custom", MyCustomConnector)

        # Create instances
        connector = registry.create("mock", connector_id="test-1", config={})
    """

    def __init__(self) -> None:
        self._connectors: Dict[str, Type[BankConnector]] = {}

    @property
    def available_types(self) -> list[str]:
        """List all registered connector type names."""
        return sorted(self._connectors.keys())

    def register(self, connector_type: str, cls: Type[BankConnector]) -> None:
        """Register a connector class under a type name.

        Args:
            connector_type: Unique type identifier (e.g., 'plaid').
            cls: The connector class (must subclass BankConnector).

        Raises:
            TypeError: If cls is not a BankConnector subclass.
        """
        if not (isinstance(cls, type) and issubclass(cls, BankConnector)):
            raise TypeError(f"{cls!r} is not a BankConnector subclass.")

        if connector_type in self._connectors:
            logger.warning("Overwriting connector type %r with %s", connector_type, cls.__name__)

        self._connectors[connector_type] = cls
        logger.debug("Registered connector: %s -> %s", connector_type, cls.__name__)

    def unregister(self, connector_type: str) -> bool:
        """Remove a connector type from the registry.

        Returns:
            True if removed, False if not found.
        """
        if connector_type in self._connectors:
            del self._connectors[connector_type]
            return True
        return False

    def get_class(self, connector_type: str) -> Type[BankConnector]:
        """Get the connector class for a given type.

        Raises:
            ConnectorError: If type is not registered.
        """
        if connector_type not in self._connectors:
            raise ConnectorError(
                f"Unknown connector type: {connector_type!r}. "
                f"Available: {self.available_types}"
            )
        return self._connectors[connector_type]

    def create(
        self,
        connector_type: str,
        connector_id: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> BankConnector:
        """Create a new connector instance.

        Args:
            connector_type: Registered type name.
            connector_id: Unique instance ID (defaults to type name).
            config: Configuration dict passed to the connector.

        Returns:
            A new BankConnector instance (not yet connected).
        """
        cls = self.get_class(connector_type)
        cid = connector_id or f"{connector_type}-auto"
        instance = cls(connector_id=cid, config=config or {})
        logger.info("Created connector: %s (type=%s)", cid, connector_type)
        return instance

    def auto_register(self) -> None:
        """Auto-register all built-in connectors."""
        from connectors.mock import MockConnector
        from connectors.plaid import PlaidConnector
        from connectors.csv_import import CSVConnector

        builtins = {
            "mock": MockConnector,
            "plaid": PlaidConnector,
            "csv": CSVConnector,
        }
        for ctype, cls in builtins.items():
            if ctype not in self._connectors:
                self.register(ctype, cls)

        logger.info("Auto-registered %d built-in connectors.", len(builtins))

    def __contains__(self, connector_type: str) -> bool:
        return connector_type in self._connectors

    def __len__(self) -> int:
        return len(self._connectors)

    def __repr__(self) -> str:
        return f"<ConnectorRegistry types={self.available_types}>"


# Module-level default registry
_default_registry: Optional[ConnectorRegistry] = None


def get_registry() -> ConnectorRegistry:
    """Get or create the default global registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ConnectorRegistry()
        _default_registry.auto_register()
    return _default_registry
