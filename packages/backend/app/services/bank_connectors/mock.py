"""
Mock Bank Connector - For testing and development.

This connector provides simulated bank data without connecting
to any real banking APIs.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
import uuid

from app.services.bank_connectors import (
    BankConnector,
    BankAccount,
    Transaction,
    ConnectorType,
    register_connector,
)


@register_connector(ConnectorType.MOCK)
class MockBankConnector(BankConnector):
    """Mock connector that returns simulated data."""
    
    def __init__(self, api_key: str | None = None, **config):
        super().__init__(api_key, **config)
        self._accounts = self._generate_mock_accounts()
        self._transactions = self._generate_mock_transactions()
    
    @property
    def connector_type(self) -> ConnectorType:
        return ConnectorType.MOCK
    
    def _generate_mock_accounts(self) -> list[dict[str, Any]]:
        """Generate mock account data."""
        return [
            {
                "account_id": "mock_checking_001",
                "account_name": "Mock Checking Account",
                "account_type": "checking",
                "balance": Decimal("5234.56"),
                "currency": "USD",
                "institution_name": "Mock Bank",
            },
            {
                "account_id": "mock_savings_001",
                "account_name": "Mock Savings Account",
                "account_type": "savings",
                "balance": Decimal("15750.00"),
                "currency": "USD",
                "institution_name": "Mock Bank",
            },
            {
                "account_id": "mock_credit_001",
                "account_name": "Mock Credit Card",
                "account_type": "credit",
                "balance": Decimal("-1250.75"),
                "currency": "USD",
                "institution_name": "Mock Bank",
            },
        ]
    
    def _generate_mock_transactions(self) -> list[dict[str, Any]]:
        """Generate mock transaction data."""
        today = date.today()
        transactions = []
        
        # Sample transactions for the last 30 days
        sample_txns = [
            ("2026-03-04", "-45.99", "Grocery Store", "food"),
            ("2026-03-03", "-125.00", "Electric Bill", "utilities"),
            ("2026-03-02", "-2500.00", "Rent Payment", "housing"),
            ("2026-03-01", "5000.00", "Salary Deposit", "income"),
            ("2026-02-28", "-89.99", "Gas Station", "transport"),
            ("2026-02-27", "-15.99", "Netflix Subscription", "entertainment"),
            ("2026-02-26", "-234.50", "Restaurant", "food"),
            ("2026-02-25", "-56.78", "Pharmacy", "health"),
            ("2026-02-24", "-199.00", "Internet Bill", "utilities"),
            ("2026-02-23", "150.00", "Freelance Payment", "income"),
        ]
        
        for i, (tx_date_str, amount, desc, category) in enumerate(sample_txns):
            tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d").date()
            tx_uuid = str(uuid.uuid4())[:8]
            
            for acc in self._accounts:
                transactions.append({
                    "transaction_id": f"txn_{acc['account_id']}_{tx_uuid}_{i}",
                    "account_id": acc["account_id"],
                    "amount": Decimal(amount),
                    "currency": "USD",
                    "date": tx_date,
                    "description": desc,
                    "category": category,
                    "merchant_name": desc.split()[0] if desc else None,
                })
        
        return transactions
    
    def get_accounts(self) -> list[BankAccount]:
        """Return mock accounts."""
        return [
            BankAccount(
                account_id=acc["account_id"],
                account_name=acc["account_name"],
                account_type=acc["account_type"],
                balance=acc["balance"],
                currency=acc["currency"],
                institution_name=acc["institution_name"],
                last_updated=datetime.now(),
            )
            for acc in self._accounts
        ]
    
    def get_transactions(
        self,
        account_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Transaction]:
        """Return mock transactions for an account."""
        txns = [
            txn for txn in self._transactions
            if txn["account_id"] == account_id
        ]
        
        if start_date:
            txns = [t for t in txns if t["date"] >= start_date]
        if end_date:
            txns = [t for t in txns if t["date"] <= end_date]
        
        return [
            Transaction(
                transaction_id=t["transaction_id"],
                account_id=t["account_id"],
                amount=t["amount"],
                currency=t["currency"],
                date=t["date"],
                description=t["description"],
                category=t["category"],
                merchant_name=t["merchant_name"],
            )
            for t in txns
        ]
    
    def refresh_account(self, account_id: str) -> BankAccount:
        """Return the account (mock refresh just returns current data)."""
        accounts = self.get_accounts()
        for acc in accounts:
            if acc.account_id == account_id:
                return acc
        raise ValueError(f"Account {account_id} not found")