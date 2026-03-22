"""Bank connector registry.

Usage::

    from app.services.bank_connectors import get_connector, list_connectors

    connector = get_connector("mock")
    accounts = connector.fetch_accounts({})
"""

from __future__ import annotations

from .base import BankAccount, BankConnector, BankTransaction, ImportResult
from .mock import MockBankConnector

__all__ = [
    "BankAccount",
    "BankConnector",
    "BankTransaction",
    "ImportResult",
    "get_connector",
    "list_connectors",
    "register_connector",
]

_registry: dict[str, BankConnector] = {}


def register_connector(connector: BankConnector) -> None:
    """Register a connector instance under its :attr:`~BankConnector.provider_id`."""
    _registry[connector.provider_id] = connector


def get_connector(provider_id: str) -> BankConnector | None:
    """Return the registered connector for *provider_id*, or ``None``."""
    return _registry.get(provider_id)


def list_connectors() -> list[BankConnector]:
    """Return all registered connectors."""
    return list(_registry.values())


# Register built-in connectors
register_connector(MockBankConnector())
