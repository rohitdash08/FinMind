"""Mock bank connector for testing and development."""

from datetime import date, timedelta
from decimal import Decimal
import random

from .bank_connector import (
    BankConnector,
    BankAccountInfo,
    BankTransactionData,
    ConnectorRegistry,
)


@ConnectorRegistry.register
class MockBankConnector(BankConnector):
    """Mock connector that generates realistic sample data.

    Useful for testing the bank sync pipeline without real credentials.
    """

    @property
    def provider_name(self) -> str:
        return "mock"

    def authenticate(self, credentials: dict) -> dict:
        """Mock authentication — always succeeds."""
        return {
            "provider": "mock",
            "authenticated": True,
            "mock_user": credentials.get("username", "demo_user"),
        }

    def list_accounts(self, connection_data: dict) -> list[BankAccountInfo]:
        """Return two mock accounts."""
        return [
            BankAccountInfo(
                external_id="mock-checking-001",
                name="Mock Checking Account",
                account_type="checking",
                currency="USD",
                balance=Decimal("4523.67"),
            ),
            BankAccountInfo(
                external_id="mock-savings-001",
                name="Mock Savings Account",
                account_type="savings",
                currency="USD",
                balance=Decimal("12750.00"),
            ),
        ]

    def fetch_transactions(
        self,
        connection_data: dict,
        account_id: str,
        from_date: date,
        to_date: date,
    ) -> list[BankTransactionData]:
        """Generate deterministic mock transactions for the date range."""
        categories = [
            ("Groceries", -50, -150),
            ("Restaurant", -15, -80),
            ("Gas Station", -30, -70),
            ("Online Shopping", -20, -200),
            ("Subscription", -10, -30),
            ("Salary", 3000, 5000),
            ("Transfer", -100, -500),
            ("Utilities", -50, -200),
        ]

        transactions = []
        current = from_date
        seed = hash(f"{account_id}-{from_date}")
        rng = random.Random(seed)

        while current <= to_date:
            # 1-3 transactions per day
            num_tx = rng.randint(1, 3)
            for i in range(num_tx):
                cat_name, min_amt, max_amt = rng.choice(categories)
                amount = Decimal(str(round(rng.uniform(min_amt, max_amt), 2)))

                transactions.append(
                    BankTransactionData(
                        external_id=f"mock-tx-{account_id}-{current}-{i}",
                        amount=amount,
                        currency="USD",
                        description=f"{cat_name} - Mock Transaction",
                        category=cat_name,
                        transaction_date=current,
                    )
                )
            current += timedelta(days=1)

        return transactions

    def refresh_connection(self, connection_data: dict) -> dict:
        """Mock refresh — returns the same data."""
        return connection_data
