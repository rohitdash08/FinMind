"""Mock bank connector for development and testing."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from app.connectors.base import BankConnector, BankTransaction, TransactionType


class MockBankConnector(BankConnector):
    """Fake bank connector that returns synthetic transactions.

    Useful for testing the connector pipeline without real bank credentials.
    """

    name = "mock"
    display_name = "Mock Bank (Demo)"

    _sample_transactions = [
        ("GROCERY STORE PURCHASE     ", Decimal("45.50"), TransactionType.DEBIT, "Groceries"),
        ("SALARY CREDIT - ACME CORP  ", Decimal("5000.00"), TransactionType.CREDIT, "Salary"),
        ("UBER RIDE                   ", Decimal("12.75"), TransactionType.DEBIT, "Transport"),
        ("NETFLIX SUBSCRIPTION        ", Decimal("15.99"), TransactionType.DEBIT, "Entertainment"),
        ("INTEREST CREDIT             ", Decimal("3.20"), TransactionType.CREDIT, "Interest"),
        ("ELECTRICITY BILL PAYMENT    ", Decimal("89.00"), TransactionType.DEBIT, "Utilities"),
        ("AMAZON PURCHASE             ", Decimal("67.99"), TransactionType.DEBIT, "Shopping"),
        ("DIVIDEND RECEIVED           ", Decimal("150.00"), TransactionType.CREDIT, "Dividend"),
        ("RESTAURANT - ZOMATO         ", Decimal("28.50"), TransactionType.DEBIT, "Dining"),
        ("ATM WITHDRAWAL              ", Decimal("200.00"), TransactionType.DEBIT, "Cash"),
        ("MOBILE RECHARGE             ", Decimal("29.00"), TransactionType.DEBIT, "Utilities"),
        ("FREELANCE PAYMENT RECEIVED  ", Decimal("800.00"), TransactionType.CREDIT, "Freelance"),
    ]

    def __init__(self):
        self._connected = True
        self._last_sync: Optional[date] = None

    async def fetch_transactions(
        self,
        user_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        **credentials,
    ) -> list[BankTransaction]:
        """Return synthetic transactions spread over the last 30 days."""
        if from_date is None:
            from_date = date.today() - timedelta(days=30)
        if to_date is None:
            to_date = date.today()

        transactions = []
        total_days = (to_date - from_date).days or 1

        for i, (desc, amount, tx_type, category) in enumerate(self._sample_transactions):
            tx_date = from_date + timedelta(days=(i * total_days) // len(self._sample_transactions))
            transactions.append(
                BankTransaction(
                    date=tx_date,
                    amount=amount,
                    description=desc.strip(),
                    transaction_type=tx_type,
                    currency="INR",
                    reference_id=f"MOCK-{user_id}-{i:04d}",
                    category_hint=category,
                )
            )

        self._last_sync = date.today()
        return transactions

    async def refresh_connection(self, **credentials) -> bool:
        """Mock always returns healthy."""
        self._connected = True
        return True

    def get_connection_status(self) -> dict:
        return {
            "connector": self.name,
            "display_name": self.display_name,
            "connected": self._connected,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "note": "This is a demo connector — no real bank data is accessed.",
        }
