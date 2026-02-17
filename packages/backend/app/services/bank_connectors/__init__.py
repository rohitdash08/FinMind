"""Bank Connectors package.

This package contains implementations of the BankConnector interface.
"""

from .mock import MockBankConnector
from ..bank_connector import ConnectorRegistry

# Register the mock connector
ConnectorRegistry.register("mock", MockBankConnector)

__all__ = ["MockBankConnector"]
