"""
Bank connector service.

This module provides a service layer for interacting with bank connectors.
"""
import logging
from typing import Any

from flask import current_app

from app.connectors import (
    BaseConnector,
    ConnectorRegistry,
    ConnectorType,
    Transaction,
    Account,
)

logger = logging.getLogger("finmind.connectors")


def get_connector() -> BaseConnector:
    """
    Get the configured connector instance.

    Returns:
        An instance of the configured connector
    """
    from app.config import Settings

    settings = current_app.config.get("settings")
    if settings is None:
        # Fallback for when app context is not available
        settings = Settings()

    connector_type = settings.get_connector_type()
    api_key = settings.connector_api_keys.get(connector_type.value)

    logger.info("Creating connector of type: %s", connector_type)

    return ConnectorRegistry.get_connector(
        connector_type,
        api_key=api_key,
    )


def import_transactions(
    user_id: int,
    account_id: str | None = None,
    from_date: Any = None,
    to_date: Any = None,
) -> list[Transaction]:
    """
    Import transactions using the configured connector.

    Args:
        user_id: The user ID to import transactions for
        account_id: Optional specific account to import from
        from_date: Optional start date for transaction import
        to_date: Optional end date for transaction import

    Returns:
        List of Transaction objects
    """
    connector = get_connector()
    return connector.import_transactions(
        user_id=user_id,
        account_id=account_id,
        from_date=from_date,
        to_date=to_date,
    )


def refresh_connector(user_id: int) -> dict[str, Any]:
    """
    Refresh account data using the configured connector.

    Args:
        user_id: The user ID to refresh data for

    Returns:
        Dictionary containing refresh status and any new transactions
    """
    connector = get_connector()
    return connector.refresh(user_id=user_id)


def get_connector_accounts(user_id: int) -> list[Account]:
    """
    Get all accounts linked to the connector for a user.

    Args:
        user_id: The user ID to get accounts for

    Returns:
        List of Account objects
    """
    connector = get_connector()
    return connector.get_accounts(user_id=user_id)


def validate_connector_credentials() -> bool:
    """
    Validate the connector credentials.

    Returns:
        True if credentials are valid, False otherwise
    """
    connector = get_connector()
    return connector.validate_credentials()


def list_available_connectors() -> list[ConnectorType]:
    """
    List all available connector types.

    Returns:
        List of registered ConnectorType values
    """
    return ConnectorRegistry.list_connectors()
