```diff
--- /dev/null
+++ b/backend/app/connectors/__init__.py
@@ -0,0 +1,5 @@
+from .base import BankConnector, Transaction, AccountBalance
+from .registry import ConnectorRegistry
+
+__all__ = ["BankConnector", "Transaction", "AccountBalance", "ConnectorRegistry"]
+
--- /dev/null
+++	b/backend/app/connectors/base.py
@@ -0,0 +1,85 @@
+from abc import ABC, abstractmethod
+from dataclasses import dataclass
+from datetime import datetime
+from decimal import Decimal
+from typing import List, Optional
+
+
+@dataclass
+class Transaction:
+    """Represents a bank transaction."""
+    transaction_id: str
+    account_id: str
+    date: datetime
+    description: str
+    amount: Decimal
+    currency: str = "USD"
+    category: Optional[str] = None
+    merchant_name: Optional[str] = None
+    pending: bool = False
+    raw_data: Optional[dict] = None
+
+
+@dataclass
+class AccountBalance:
+    """Represents an account balance."""
+    account_id: str
+    account_name: str
+    account_type: str  # e.g., checking, savings, credit_card
+    balance: Decimal
+    available_balance: Optional[Decimal] = None
+    currency: str = "USD"
+    last_updated: Optional[datetime] = None
+
+
+class BankConnector(ABC):
+    """
+    Abstract base class for bank integration connectors.
+    
+    All bank connectors must inherit from this class and implement
+    the required methods for account listing, transaction fetching,
+    and balance retrieval.
+    """
+    
+    def __init__(self, credentials: dict):
+        """
+        Initialize the connector with user-provided credentials.
+        
+        Args:
+            credentials: Dict containing authentication details.
+                        e.g., {'api_key': '...', 'api_secret': '...'}
+        """
+        self.credentials = credentials
+    
+    @abstractmethod
+    def authenticate(self) -> bool:
+        """Authenticate with the bank API. Returns True on success."""
+        pass
+    
+    @abstractmethod
+    def list_accounts(self) -> List[AccountBalance]:
+        """List all accounts accessible with the current credentials."""
+        pass
+    
+    @abstractmethod
+    def get_transactions(
+        self,
+        account_id: str,
+        start_date: Optional[datetime] = None,
+        end_date: Optional[datetime] = None
+    ) -> List[Transaction]:
+        """
+        Fetch transactions for a given account.
+        
+        Args:
+            account_id: The account to fetch transactions for.
+            start_date: Optional filter for transactions after this date.
+            end_date: Optional filter for transactions before this date.
+        """
+        pass
+    
+    @abstractmethod
+    def get_balance(self, account_id: str) -> AccountBalance:
+        """Get current balance for the specified account."""
+        pass
+
--- /dev/null
+++	b/backend/app/connectors/registry.py
@@ -0,0 +1,56 @@
+import importlib
+from typing import Dict, Type, Optional
+from .base import BankConnector
+
+
+class ConnectorRegistry:
+    """
+    Registry for bank connector plugins.
+    
+    Connectors can be registered explicitly or auto-discovered
+    from a specified module path.
+    """
+    
+    _connectors: Dict[str, Type[BankConnector]] = {}
+    
+    @classmethod
+    def register(cls, name: str, connector_class: Type[BankConnector]) -> None:
+        """Register a connector class under the given name."""
+        if not issubclass(connector_class, BankConnector):
+            raise ValueError(f"Connector must inherit from BankConnector: {connector_class}")
+        cls._connectors[name] = connector_class
+    
+    @classmethod
+    def get(cls, name: str) -> Optional[Type[BankConnector]]:
+        """Get a connector class by name."""
+        return cls._connectors.get(name)
+    
+    @classmethod
+    def list_connectors(cls) -> Dict[str, Type[BankConnector]]:
+        """Return a copy of all registered connectors."""
+        return cls._connectors.copy()
+    
+    @classmethod
+    def create(cls, name: str, credentials: dict) -> BankConnector:
+        """
+        Instantiate a connector by name with the given credentials.
+        
+        Raises:
+            KeyError: If connector name is not registered.
+        """
+        connector_class = cls._connectors[name]
+        return connector_class(credentials)
+    
+    @classmethod
+    def auto_discover(cls, module_path: str = "backend.app.connectors.plugins") -> None:
+        """
+        Auto-discover and register connectors from a module path.
+        
+        Expects modules in the path to register themselves on import.
+        """
+        try:
+            importlib.import_module(module_path)
+        except ImportError:
+            pass
+    
+    @classmethod
+    def clear(cls) -> None:
+        """Clear all registered connectors. Useful for testing."""
+        cls._connectors.clear()
+
--- /dev/null
+++	b/backend/app/connectors/plugins/__init__.py
@@ -0,0 +1,3 @@
+from .mock import MockBankConnector
+
+__all__ = ["MockBankConnector"]
+
--- /dev/null
+++	b/backend/app/connectors/plugins/mock.py
@@ -0,0 +1,118 @@
+from datetime import datetime, timedelta
+from decimal import Decimal
+from typing import List, Optional
+import uuid
+
+from ..base import BankConnector, Transaction, AccountBalance
+from ..registry import ConnectorRegistry
+
+
+class MockBankConnector(BankConnector):
+    """
+    Mock bank connector for development and testing.
+    
+    Simulates a bank with predefined accounts and generates
+    synthetic transactions.
+    """
+    
+    def __init__(self, credentials: dict):
+        super().__init__(credentials)
+        self._authenticated = False
+        self._accounts = [
+            {
+                "account_id": "mock-checking-001",
+                "account_name": "Mock Checking",
+                "account_type": "checking",
+                "balance": Decimal("2543.87"),
+                "available_balance": Decimal("2543.87"),
+            },
+            {
+                "account_id": "mock-savings-001",
+                "account_name": "Mock Savings",
+                "account_type": "savings",
+                "balance": Decimal("15000.00"),
+                "