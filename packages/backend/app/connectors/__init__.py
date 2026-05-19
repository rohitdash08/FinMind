"""Bank Sync Connectors — pluggable bank integration architecture.

Usage:
    from app.connectors import ConnectorManager
    from app.connectors.mock import MockBankConnector

    manager = ConnectorManager()
    manager.register(MockBankConnector())
    transactions = manager.import_transactions("mock", user_id=1)
    manager.refresh("mock", user_id=1)
"""

from app.connectors.base import BankConnector, BankTransaction
from app.connectors.manager import ConnectorManager
from app.connectors.mock import MockBankConnector

__all__ = [
    "BankConnector",
    "BankTransaction",
    "ConnectorManager",
    "MockBankConnector",
]
