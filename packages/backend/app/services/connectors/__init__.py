"""
Bank Sync Connector Registry
Pluggable architecture for bank integrations.
"""

from typing import Dict, Type

from .base import BankConnector

_registry: Dict[str, Type["BankConnector"]] = {}


def register_connector(connector_cls: Type["BankConnector"]) -> Type["BankConnector"]:
    """Decorator to register a bank connector."""
    if not connector_cls.provider_name:
        raise ValueError(f"Connector {connector_cls.__name__} must define provider_name")
    _registry[connector_cls.provider_name.lower()] = connector_cls
    return connector_cls


def get_connector(provider: str) -> Type["BankConnector"]:
    """Get a registered connector by provider name."""
    key = provider.lower()
    if key not in _registry:
        available = ", ".join(_registry.keys())
        raise ValueError(
            f"Unknown provider '{provider}'. Available: {available}"
        )
    return _registry[key]


def list_connectors() -> Dict[str, str]:
    """List all registered connectors with their names and descriptions."""
    return {
        name: cls.description or name
        for name, cls in _registry.items()
    }


# Import connectors to register them
from .mock_connector import MockConnector  # noqa: E402, F401
