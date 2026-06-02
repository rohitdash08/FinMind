"""Bank Connector Registry."""

from typing import Dict, Type, List, Any, Optional

try:
    from .base import BankConnector
    from .mock import MockBankConnector
    from .plaid import PlaidConnector
except ImportError:
    from base import BankConnector
    from mock import MockBankConnector
    from plaid import PlaidConnector

# Third-party connector availability
CONNECTOR_AVAILABILITY = {
    "mock_bank": True,
    "plaid": True,  # Available if plaid-python installed
}


class ConnectorRegistry:
    """Registry for bank connectors."""
    
    _connectors: Dict[str, Type[BankConnector]] = {}
    
    @classmethod
    def register(cls, connector_class: Type[BankConnector]) -> None:
        """Register a connector class."""
        cls._connectors[connector_class.name] = connector_class
    
    @classmethod
    def get(cls, name: str) -> Optional[Type[BankConnector]]:
        """Get a connector class by name."""
        return cls._connectors.get(name)
    
    @classmethod
    def list_connectors(cls) -> List[Dict[str, Any]]:
        """List all available connectors."""
        result = []
        for name, connector_class in cls._connectors.items():
            result.append({
                "id": name,
                "name": connector_class.name,
                "display_name": connector_class.display_name,
                "description": connector_class.description,
                "supported_countries": connector_class.supported_countries,
                "features": connector_class.features,
            })
        return result
    
    @classmethod
    def create_connector(cls, name: str, config: Optional[Dict] = None) -> BankConnector:
        """Create a connector instance."""
        connector_class = cls.get(name)
        if not connector_class:
            raise ValueError(f"Unknown connector: {name}")
        return connector_class(config)


# Register built-in connectors
ConnectorRegistry.register(MockBankConnector)

# Register third-party connectors (may require additional setup)
try:
    # Check if Plaid SDK is available
    import plaid
    ConnectorRegistry.register(PlaidConnector)
except ImportError:
    pass  # Plaid not installed, skip registration


# Convenience functions
def list_connectors() -> List[Dict[str, Any]]:
    """List all available connectors."""
    return ConnectorRegistry.list_connectors()


def get_connector(name: str) -> Optional[BankConnector]:
    """Get a connector instance by name."""
    try:
        return ConnectorRegistry.create_connector(name)
    except ValueError:
        return None
