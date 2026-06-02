"""
Mock Bank Connector

A fully functional connector that simulates a bank API.
Used for development, testing, and demo purposes.
Includes realistic transaction data across multiple account types.
"""

import random
from datetime import date, timedelta
from typing import Dict, List, Optional

from .base import (
    AccountInfo,
    BankConnector,
    ConnectionStatus,
    SyncResult,
    TransactionRecord,
)

# --- Seed transaction data (realistic mock) ---

MERCHANTS_BY_CATEGORY = {
    "groceries": [
        ("Whole Foods", -87.43),
        ("Trader Joe's", -52.18),
        ("Costco", -143.67),
        ("Safeway", -34.92),
    ],
    "dining": [
        ("Starbucks", -5.75),
        ("Chipotle", -12.30),
        ("Local Bistro", -68.50),
        ("Uber Eats", -24.99),
    ],
    "transport": [
        ("Shell Gas", -54.20),
        ("Uber", -18.75),
        ("Metro Transit", -2.75),
        ("Tesla Charging", -12.50),
    ],
    "shopping": [
        ("Amazon", -45.99),
        ("Target", -78.34),
        ("Apple Store", -299.00),
        ("Nike", -129.95),
    ],
    "bills": [
        ("Electric Company", -142.50),
        ("Internet Provider", -79.99),
        ("Phone Bill", -55.00),
        ("Netflix", -15.99),
    ],
    "income": [
        ("Acme Corp Payroll", 4250.00),
        ("Freelance Payment", 800.00),
        ("Tax Refund", 1200.00),
        ("Interest Credit", 3.42),
    ],
}

ACCOUNTS = [
    AccountInfo(
        account_id="mock-checking-001",
        name="Primary Checking",
        type="checking",
        balance=5432.18,
        currency="USD",
        masked_number="****4521",
    ),
    AccountInfo(
        account_id="mock-savings-002",
        name="High-Yield Savings",
        type="savings",
        balance=12750.00,
        currency="USD",
        masked_number="****7893",
    ),
    AccountInfo(
        account_id="mock-credit-003",
        name="Rewards Credit Card",
        type="credit",
        balance=-1247.33,
        currency="USD",
        masked_number="****3156",
    ),
]


def _generate_transactions(
    start_date: date, end_date: date, seed: int = 42
) -> List[TransactionRecord]:
    """Generate realistic mock transactions for a date range."""
    rng = random.Random(seed)
    transactions: List[TransactionRecord] = []
    current = start_date
    txn_id = 1000

    while current <= end_date:
        # Weekdays: more transactions
        if current.weekday() < 5:
            num_txn = rng.randint(1, 4)
        else:
            num_txn = rng.randint(0, 2)

        for _ in range(num_txn):
            category = rng.choice(list(MERCHANTS_BY_CATEGORY.keys()))
            merchant, amount = rng.choice(MERCHANTS_BY_CATEGORY[category])

            # Add some randomness to amount
            jitter = rng.uniform(-3, 3)
            final_amount = round(amount + jitter, 2)

            txn_id += 1
            transactions.append(
                TransactionRecord(
                    transaction_id=f"mock-txn-{txn_id}",
                    date=current,
                    amount=final_amount,
                    description=f"{merchant} — {category.title()}",
                    category_id=None,  # Will be categorized by FinMind
                    currency="USD",
                    merchant=merchant,
                    raw_data={
                        "category": category,
                        "posted_at": current.isoformat(),
                        "pending": rng.random() < 0.05,  # 5% pending
                    },
                )
            )

        current += timedelta(days=1)

    # Sort by date descending (most recent first)
    transactions.sort(key=lambda t: t.date, reverse=True)
    return transactions


class MockConnector(BankConnector):
    """
    Mock bank connector with realistic transaction data.

    Simulates a US bank with checking, savings, and credit card accounts.
    Generates consistent transactions based on date range (same range = same data).

    Usage:
        connector = MockConnector()
        await connector.connect()
        result = await connector.import_transactions("mock-checking-001")
    """

    provider_name = "mock"
    description = "Mock Bank — realistic test data for development"

    def __init__(self, credentials: dict | None = None):
        super().__init__(credentials)
        self._last_sync: dict[str, date] = {}

    async def connect(self) -> ConnectionStatus:
        """Simulate connection to mock bank."""
        self.connected = True
        return ConnectionStatus.CONNECTED

    async def disconnect(self) -> bool:
        """Simulate disconnection."""
        self.connected = False
        return True

    async def import_transactions(
        self,
        account_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> SyncResult:
        """Import transactions for the given date range."""
        if not self.connected:
            await self.connect()

        # Defaults: 90 days
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=90)

        # Generate transactions with consistent seed based on account
        seed = hash(account_id) % 10000
        transactions = _generate_transactions(start_date, end_date, seed=seed)

        # Record last sync date
        self._last_sync[account_id] = end_date

        return SyncResult(
            provider=self.provider_name,
            status="success",
            transactions_imported=len(transactions),
            transactions_skipped=0,
        )

    async def refresh(
        self,
        account_id: str,
        since: Optional[date] = None,
    ) -> SyncResult:
        """Refresh — fetch transactions since last sync or given date."""
        if not self.connected:
            await self.connect()

        # Use last sync date, or default to 7 days ago
        if since is None:
            since = self._last_sync.get(account_id)
            if since is None:
                since = date.today() - timedelta(days=7)

        end_date = date.today()
        seed = hash(account_id) % 10000
        transactions = _generate_transactions(since, end_date, seed=seed)

        self._last_sync[account_id] = end_date

        return SyncResult(
            provider=self.provider_name,
            status="success",
            transactions_imported=len(transactions),
            transactions_skipped=0,
        )

    async def get_accounts(self) -> List[AccountInfo]:
        """Return mock accounts."""
        return list(ACCOUNTS)
