"""
Bank Sync Connector Architecture
=================================
Pluggable architecture for bank integrations.

Provides:
  - Abstract connector interface (BaseBankConnector)
  - Connector registry for dynamic provider lookup
  - Import & refresh support for transactions
  - Mock connector for development/testing
"""

from .base import BaseBankConnector
from .registry import ConnectorRegistry, get_connector, register_connector
from .mock import MockBankConnector

__all__ = [
    "BaseBankConnector",
    "ConnectorRegistry",
    "get_connector",
    "register_connector",
    "MockBankConnector",
]
