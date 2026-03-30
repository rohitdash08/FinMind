"""
Bank Connector Factory

Factory pattern for creating and managing bank connector instances.
"""

from typing import Type
from .base import BaseBankConnector, ConnectorConfig
import logging

logger = logging.getLogger("finmind.bank_connectors")

_CONNECTOR_REGISTRY: dict[str, Type[BaseBankConnector]] = {}


def register_connector(connector_class: Type[BaseBankConnector]) -> Type[BaseBankConnector]:
    """
    Decorator to register a bank connector class.
    
    Usage:
        @register_connector
        class MyBankConnector(BaseBankConnector):
            ...
    """
    # Create a temporary instance to get the institution_id
    try:
        temp_instance = connector_class()
        inst_id = temp_instance.institution_id
    except Exception:
        # If instantiation fails, try to get from class attribute
        inst_id = getattr(connector_class, "INSTITUTION_ID", None)
        if inst_id is None:
            raise ValueError(
                f"Connector class {connector_class.__name__} must define "
                "institution_id property or INSTITUTION_ID class attribute"
            )
    _CONNECTOR_REGISTRY[inst_id] = connector_class
    logger.info(f"Registered bank connector: {inst_id}")
    return connector_class


def get_connector(
    institution_id: str,
    config: ConnectorConfig | None = None,
) -> BaseBankConnector | None:
    """
    Get a bank connector instance by institution ID.
    
    Args:
        institution_id: The unique identifier for the institution
        config: Optional configuration for the connector
        
    Returns:
        An instance of the requested connector, or None if not found
    """
    connector_class = _CONNECTOR_REGISTRY.get(institution_id)
    if connector_class is None:
        logger.warning(f"No connector found for institution: {institution_id}")
        return None
    
    return connector_class(config)


def list_available_connectors() -> list[dict[str, str]]:
    """
    List all available bank connectors.
    
    Returns:
        List of dictionaries with institution_id and institution_name
    """
    result = []
    for inst_id, connector_class in _CONNECTOR_REGISTRY.items():
        try:
            temp_instance = connector_class()
            result.append({
                "institution_id": inst_id,
                "institution_name": temp_instance.institution_name,
                "supports_oauth": temp_instance.supports_oauth,
                "supports_refresh": temp_instance.supports_refresh,
            })
        except Exception:
            # Try class attributes
            result.append({
                "institution_id": inst_id,
                "institution_name": getattr(connector_class, "INSTITUTION_NAME", inst_id),
                "supports_oauth": getattr(connector_class, "SUPPORTS_OAUTH", True),
                "supports_refresh": getattr(connector_class, "SUPPORTS_REFRESH", True),
            })
    return result


def get_connector_class(institution_id: str) -> Type[BaseBankConnector] | None:
    """Get a connector class by institution ID."""
    return _CONNECTOR_REGISTRY.get(institution_id)


def clear_registry() -> None:
    """Clear the connector registry (mainly for testing)."""
    _CONNECTOR_REGISTRY.clear()
    logger.info("Cleared bank connector registry")
