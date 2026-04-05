"""
Mock Bank Connector

A mock connector for testing and development purposes.
Simulates bank API responses without making actual network calls.
"""

import random
from datetime import date, datetime, timedelta
from typing import Any

from .bank_connector import (
    BankAccount,
    BankConnector,
    BankTransaction,
    ConnectorConfig,
    ConnectorRegistry,
    TransactionType,
    register_connector,
)


@register_connector
class MockBankConnector(BankConnector):
    """
    Mock bank connector for testing.
    
    Simulates a bank API with configurable responses.
    """
    
    # Sample transaction descriptions for realistic mock data
    SAMPLE_MERCHANTS = [
        "Amazon.com",
        "Walmart",
        "Target",
        "Starbucks",
        "Netflix",
        "Spotify",
        "Uber",
        "Lyft",
        "Whole Foods",
        "Costco",
        "Shell Gas Station",
        "Chevron",
        "CVS Pharmacy",
        "Walgreens",
        "Apple Store",
        "Best Buy",
        "Home Depot",
        "Lowes",
        "McDonald's",
        "Chipotle",
    ]
    
    SAMPLE_INCOME = [
        "Payroll Deposit",
        "Direct Deposit - Employer",
        "ACH Credit",
        "Wire Transfer Received",
        "Refund - Amazon",
        "Dividend Payment",
        "Interest Payment",
    ]
    
    def __init__(self):
        self._connected = False
        self._config: ConnectorConfig | None = None
        self._accounts: list[BankAccount] = []
        self._transactions: dict[str, list[BankTransaction]] = {}
        self._seed = random.randint(0, 99999)
    
    @property
    def connector_type(self) -> str:
        return "mock"
    
    @property
    def display_name(self) -> str:
        return "Mock Bank (Development)"
    
    @property
    def supported_features(self) -> list[str]:
        return ["import", "refresh", "accounts"]
    
    def connect(self, config: ConnectorConfig) -> bool:
        """Simulate connecting to the mock bank."""
        self._config = config
        self._connected = True
        
        # Generate mock accounts
        self._accounts = self._generate_mock_accounts()
        
        # Generate mock transactions for each account
        self._transactions = {}
        for account in self._accounts:
            self._transactions[account.account_id] = self._generate_mock_transactions(
                account.account_id
            )
        
        return True
    
    def disconnect(self) -> bool:
        """Simulate disconnecting from the mock bank."""
        self._connected = False
        self._config = None
        self._accounts = []
        self._transactions = {}
        return True
    
    def _generate_mock_accounts(self) -> list[BankAccount]:
        """Generate mock bank accounts."""
        return [
            BankAccount(
                account_id=f"ACC{random.randint(1000, 9999)}",
                account_name="Primary Checking",
                account_type="checking",
                currency="USD",
                current_balance=random.uniform(1000, 15000),
                available_balance=random.uniform(1000, 15000),
            ),
            BankAccount(
                account_id=f"ACC{random.randint(1000, 9999)}",
                account_name="Savings Account",
                account_type="savings",
                currency="USD",
                current_balance=random.uniform(5000, 50000),
                available_balance=random.uniform(5000, 50000),
            ),
            BankAccount(
                account_id=f"ACC{random.randint(1000, 9999)}",
                account_name="Credit Card",
                account_type="credit",
                currency="USD",
                current_balance=random.uniform(-5000, -100),
            ),
        ]
    
    def _generate_mock_transactions(
        self,
        account_id: str,
        days_back: int = 90,
    ) -> list[BankTransaction]:
        """Generate mock transactions."""
        transactions = []
        today = date.today()
        
        # Generate 30-50 transactions
        num_transactions = random.randint(30, 50)
        
        for i in range(num_transactions):
            # Random date within the past N days
            days_ago = random.randint(0, days_back)
            tx_date = today - timedelta(days=days_ago)
            
            # Determine if income or expense
            is_income = random.random() < 0.2  # 20% income
            
            if is_income:
                amount = random.uniform(500, 5000)
                description = random.choice(self.SAMPLE_INCOME)
                tx_type = TransactionType.INCOME
            else:
                amount = random.uniform(5, 500)
                description = random.choice(self.SAMPLE_MERCHANTS)
                tx_type = TransactionType.EXPENSE
            
            transactions.append(
                BankTransaction(
                    date=tx_date,
                    amount=amount,
                    description=description,
                    transaction_type=tx_type,
                    currency="USD",
                    external_id=f"{account_id}-TX{i:04d}",
                )
            )
        
        # Sort by date descending
        transactions.sort(key=lambda t: t.date, reverse=True)
        return transactions
    
    def get_accounts(self) -> list[BankAccount]:
        """Get mock accounts."""
        if not self._connected:
            return []
        return self._accounts
    
    def get_transactions(
        self,
        account_id: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[BankTransaction]:
        """Get mock transactions with optional date filtering."""
        if not self._connected:
            return []
        
        transactions = self._transactions.get(account_id, [])
        
        filtered = []
        for tx in transactions:
            if from_date and tx.date < from_date:
                continue
            if to_date and tx.date > to_date:
                continue
            filtered.append(tx)
        
        return filtered
    
    def refresh_transactions(
        self,
        account_id: str,
        since: datetime,
    ) -> list[BankTransaction]:
        """Get new transactions since the given datetime."""
        if not self._connected:
            return []
        
        # Generate a few new transactions to simulate recent activity
        new_transactions = []
        today = date.today()
        
        for i in range(random.randint(1, 5)):
            days_ago = random.randint(0, 7)
            tx_date = today - timedelta(days=days_ago)
            
            is_income = random.random() < 0.15
            if is_income:
                amount = random.uniform(500, 3000)
                description = random.choice(self.SAMPLE_INCOME)
                tx_type = TransactionType.INCOME
            else:
                amount = random.uniform(10, 200)
                description = random.choice(self.SAMPLE_MERCHANTS)
                tx_type = TransactionType.EXPENSE
            
            new_transactions.append(
                BankTransaction(
                    date=tx_date,
                    amount=amount,
                    description=description,
                    transaction_type=tx_type,
                    currency="USD",
                    external_id=f"{account_id}-NEW{i:04d}",
                )
            )
        
        return new_transactions
    
    def get_connection_status(self) -> dict[str, Any]:
        """Get mock connection status."""
        return {
            "connected": self._connected,
            "connector_type": self.connector_type,
            "display_name": self.display_name,
            "num_accounts": len(self._accounts),
        }
    
    def set_mock_data(
        self,
        accounts: list[BankAccount] | None = None,
        transactions: dict[str, list[BankTransaction]] | None = None,
    ) -> None:
        """
        Set custom mock data for testing.
        
        Args:
            accounts: Custom accounts to use
            transactions: Custom transactions keyed by account_id
        """
        if accounts is not None:
            self._accounts = accounts
        if transactions is not None:
            self._transactions = transactions


# Auto-register the mock connector
ConnectorRegistry.register(MockBankConnector)