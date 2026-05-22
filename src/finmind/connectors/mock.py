import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any
from .base import BaseBankConnector, Transaction


class MockBankConnector(BaseBankConnector):
    """Mock bank connector for testing and development."""

    def __init__(self):
        self._authenticated = False
        self._accounts = [
            {
                "account_id": "mock_acc_1",
                "account_name": "Checking Account",
                "account_type": "checking",
                "balance": 2500.75,
                "currency": "USD",
            },
            {
                "account_id": "mock_acc_2",
                "account_name": "Savings Account",
                "account_type": "savings",
                "balance": 15000.0,
                "currency": "USD",
            },
        ]

    def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """Mock authentication - accepts any credentials."""
        self._authenticated = True
        return True

    def import_transactions(self, account_id: str, from_date: datetime, to_date: datetime) -> List[Transaction]:
        """Generate mock transactions for the given account and date range."""
        if not self._authenticated:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        transactions = []
        current_date = from_date

        while current_date <= to_date:
            # Generate 1-3 transactions per day
            for i in range(1, 4):
                if current_date > to_date:
                    break

                amount = round((i * 10.5) * (1 if i % 2 == 0 else -1), 2)
                transaction = Transaction(
                    transaction_id=str(uuid.uuid4()),
                    amount=amount,
                    description=f"Mock transaction {i} on {current_date.strftime('%Y-%m-%d')}",
                    date=current_date,
                    account_id=account_id,
                    category="mock",
                )
                transactions.append(transaction)

            current_date += timedelta(days=1)

        return transactions

    def refresh_accounts(self) -> List[Dict[str, Any]]:
        """Return mock accounts with slightly updated balances."""
        if not self._authenticated:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        # Simulate balance changes
        for account in self._accounts:
            account["balance"] += round((hash(account["account_id"]) % 100) * 0.01 - 0.5, 2)

        return self._accounts