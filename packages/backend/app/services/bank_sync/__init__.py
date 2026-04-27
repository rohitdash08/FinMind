"""Pluggable bank sync connector architecture.

A connector is a class that implements :class:`BankConnector` and is
registered via :func:`register_connector`. Connectors expose two operations
needed for bank integration:

- ``connect``: validate credentials and return the linkable bank accounts
- ``fetch_transactions``: pull transactions for a linked account, optionally
  filtered by ``since`` for incremental refresh

Concrete connectors live in sibling modules (e.g. ``mock.py``). Importing
this package eagerly imports the bundled mock connector so it is always
available.
"""

from .base import (
    BankAccountInfo,
    BankConnector,
    BankTransaction,
    ConnectorError,
)
from .registry import (
    available_connectors,
    get_connector,
    list_connectors,
    register_connector,
)

# Eagerly import bundled connectors so they self-register.
from . import mock  # noqa: F401

__all__ = [
    "BankAccountInfo",
    "BankConnector",
    "BankTransaction",
    "ConnectorError",
    "available_connectors",
    "get_connector",
    "list_connectors",
    "register_connector",
]
