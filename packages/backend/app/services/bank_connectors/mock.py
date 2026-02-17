"""Mock Bank Connector for testing.

This module provides a mock implementation of the BankConnector interface
for testing without real bank credentials.
"""

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

from ..bank_connector import (
    BankAccount,
    BankConnector,
    BankConnectionStatus,
    BankTransaction,
)


class MockBankConnector(BankConnector):
    """Mock bank connector for testing.
    
    Simulates a bank API without making real network calls.
    Generates realistic test data.
    
    Example:
        >>> config = {"seed": 12345, "account_count": 3}
        >>> connector = MockBankConnector("mock", "Mock Bank", config)
        >>> connector.authenticate({"api_key": "test"})
        True
        >>> accounts = connector.fetch_accounts()
        >>> len(accounts)
        3
    """
    
    def __init__(self, connector_id: str, name: str, config: dict):
        super().__init__(connector_id, name, config)
        self._seed = config.get("seed", 42)
        self._account_count = config.get("account_count", 3)
        self._transaction_count = config.get("transaction_count", 50)
        self._accounts: list[BankAccount] = []
        self._transactions: dict[str, list[BankTransaction]] = {}
        self._status = BankConnectionStatus.DISCONNECTED
        self._random = random.Random(self._seed)
    
    def authenticate(self, credentials: dict) -> bool:
        """Authenticate with mock credentials.
        
        Any non-empty api_key is accepted.
        """
        api_key = credentials.get("api_key", "")
        if not api_key:
            return False
        
        self._authenticated = True
        self._status = BankConnectionStatus.ACTIVE
        self._generate_accounts()
        return True
    
    def fetch_accounts(self) -> list[BankAccount]:
        """Fetch mock accounts."""
        if not self._authenticated:
            raise ValueError("Not authenticated")
        return self._accounts.copy()
    
    def fetch_transactions(
        self,
        account_id: str,
        start_date: date | None = None,
        end_date: date | None = None
    ) -> list[BankTransaction]:
        """Fetch mock transactions for an account."""
        if not self._authenticated:
            raise ValueError("Not authenticated")
        
        if account_id not in [a.id for a in self._accounts]:
            raise ValueError(f"Account {account_id} not found")
        
        if account_id not in self._transactions:
            self._generate_transactions(account_id)
        
        transactions = self._transactions[account_id]
        
        # Filter by date if specified
        if start_date:
            transactions = [t for t in transactions if t.date >= start_date]
        if end_date:
            transactions = [t for t in transactions if t.date <= end_date]
        
        return transactions
    
    def refresh(self) -> bool:
        """Mock refresh - always succeeds if authenticated."""
        if not self._authenticated:
            return False
        self._status = BankConnectionStatus.ACTIVE
        return True
    
    def disconnect(self) -> bool:
        """Mock disconnect."""
        self._authenticated = False
        self._status = BankConnectionStatus.DISCONNECTED
        self._accounts = []
        self._transactions = {}
        return True
    
    def get_connection_status(self) -> BankConnectionStatus:
        """Get current connection status."""
        return self._status
    
    def health_check(self) -> dict:
        """Mock health check."""
        return {
            "status": "healthy" if self._authenticated else "not_authenticated",
            "latency_ms": self._random.randint(10, 100),
            "api_version": "v1.0.0-mock",
        }
    
    def _generate_accounts(self) -> None:
        """Generate mock bank accounts."""
        account_types = ["CHECKING", "SAVINGS", "CREDIT_CARD"]
        currencies = ["USD", "EUR", "GBP", "INR"]
        
        for i in range(self._account_count):
            acc_type = self._random.choice(account_types)
            currency = self._random.choice(currencies)
            
            # Generate realistic balance
            if acc_type == "CREDIT_CARD":
                balance = Decimal(str(self._random.uniform(-5000, 0)))
            else:
                balance = Decimal(str(self._random.uniform(1000, 50000)))
            
            account = BankAccount(
                id=f"mock_acc_{i}",
                name=f"{acc_type.title()} Account {i+1}",
                account_type=acc_type,
                currency=currency,
                balance=balance.quantize(Decimal("0.01")),
                account_number_masked=f"****{self._random.randint(1000, 9999)}",
                institution_name="Mock Bank",
            )
            self._accounts.append(account)
    
    def _generate_transactions(self, account_id: str) -> None:
        """Generate mock transactions for an account."""
        transactions = []
        
        # Get account currency
        account = next((a for a in self._accounts if a.id == account_id), None)
        currency = account.currency if account else "USD"
        
        # Merchant names for realistic descriptions
        merchants = [
            "Grocery Store", "Gas Station", "Coffee Shop", "Restaurant",
            "Online Retailer", "Utility Company", "Phone Company",
            "Streaming Service", "Gym Membership", "Pharmacy",
            "Bookstore", "Electronics Store", "Department Store",
            "Freelance Payment", "Salary Deposit", "Interest Earned",
        ]
        
        # Generate transactions over last 90 days
        end_date = date.today()
        
        for _ in range(self._transaction_count):
            merchant = self._random.choice(merchants)
            
            # Determine if income or expense based on merchant
            is_income = any(keyword in merchant.lower() 
                          for keyword in ["payment", "salary", "interest", "deposit"])
            
            if is_income:
                amount = Decimal(str(self._random.uniform(100, 5000)))
            else:
                amount = -Decimal(str(self._random.uniform(5, 500)))
            
            # Random date within range
            days_ago = self._random.randint(0, 90)
            tx_date = end_date - timedelta(days=days_ago)
            
            transaction = BankTransaction(
                id=f"mock_tx_{uuid.uuid4().hex[:8]}",
                account_id=account_id,
                date=tx_date,
                amount=amount.quantize(Decimal("0.01")),
                description=merchant,
                currency=currency,
                merchant_name=merchant if not is_income else None,
                pending=self._random.random() < 0.1,  # 10% pending
                metadata={"mock": True, "source": "mock_connector"},
            )
            transactions.append(transaction)
        
        # Sort by date descending
        transactions.sort(key=lambda x: x.date, reverse=True)
        self._transactions[account_id] = transactions
