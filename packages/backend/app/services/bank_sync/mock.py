"""
Mock bank connector for development and testing.

Generates realistic-looking fake data for testing the bank sync
architecture without requiring real bank credentials.
"""

import random
from datetime import date, datetime, timedelta
from typing import List, Optional

from .base import (
    BankAccount,
    BankTransaction,
    BaseBankConnector,
    ConnectionStatus,
    SyncResult,
    TransactionType,
)


# Sample data for realistic mock transactions
MERCHANTS = [
    ("Whole Foods Market", "Groceries"),
    ("Shell Gas Station", "Transportation"),
    ("Netflix", "Entertainment"),
    ("Starbucks", "Food & Drink"),
    ("Amazon.com", "Shopping"),
    ("Uber", "Transportation"),
    ("Spotify", "Entertainment"),
    ("Walmart", "Shopping"),
    ("CVS Pharmacy", "Health"),
    ("Target", "Shopping"),
    ("Chipotle", "Food & Drink"),
    ("Electric Company", "Utilities"),
    ("Water Authority", "Utilities"),
    ("Internet Provider", "Utilities"),
    ("Gym Membership", "Health"),
    ("Costco", "Shopping"),
    ("DoorDash", "Food & Drink"),
    ("Gas & Electric", "Utilities"),
    ("Phone Bill", "Utilities"),
    ("Rent Payment", "Housing"),
]

INCOME_SOURCES = [
    ("Direct Deposit - Employer", "Income"),
    ("Freelance Payment", "Income"),
    ("Interest Payment", "Income"),
    ("Refund - Amazon", "Refund"),
    ("Cashback Reward", "Income"),
]


class MockBankConnector(BaseBankConnector):
    """
    Mock bank connector for testing.

    Generates realistic fake accounts and transactions.
    Useful for development, testing, and demo purposes.

    Usage:
        connector = MockBankConnector(num_accounts=2, seed=42)
        connector.connect({})
        accounts = connector.list_accounts()
        transactions = connector.import_transactions(accounts[0].account_id)
    """

    def __init__(self, num_accounts: int = 2, seed: Optional[int] = None):
        self._num_accounts = num_accounts
        self._seed = seed
        self._rng = random.Random(seed)
        self._status = ConnectionStatus.DISCONNECTED
        self._accounts: List[BankAccount] = []
        self._transactions: dict = {}  # account_id -> List[BankTransaction]

    @property
    def provider_name(self) -> str:
        return "mock"

    def connect(self, credentials: dict) -> ConnectionStatus:
        """Connect (always succeeds for mock)."""
        self._status = ConnectionStatus.CONNECTED
        self._generate_accounts()
        return self._status

    def disconnect(self) -> bool:
        self._status = ConnectionStatus.DISCONNECTED
        self._accounts = []
        self._transactions = {}
        return True

    def get_status(self) -> ConnectionStatus:
        return self._status

    def list_accounts(self) -> List[BankAccount]:
        if self._status != ConnectionStatus.CONNECTED:
            return []
        return self._accounts

    def import_transactions(
        self,
        account_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[BankTransaction]:
        if self._status != ConnectionStatus.CONNECTED:
            return []

        if account_id not in self._transactions:
            self._generate_transactions(account_id)

        transactions = self._transactions.get(account_id, [])

        # Filter by date range
        if start_date:
            transactions = [t for t in transactions if t.date >= start_date]
        if end_date:
            transactions = [t for t in transactions if t.date <= end_date]

        return transactions

    def refresh(self, account_id: Optional[str] = None) -> SyncResult:
        if self._status != ConnectionStatus.CONNECTED:
            return SyncResult(
                success=False,
                errors=["Not connected. Call connect() first."],
            )

        accounts_to_sync = (
            [a for a in self._accounts if a.account_id == account_id]
            if account_id
            else self._accounts
        )

        total_imported = 0
        for account in accounts_to_sync:
            # Add a few new transactions on refresh
            new_txns = self._generate_recent_transactions(account.account_id, count=3)
            existing = self._transactions.get(account.account_id, [])
            self._transactions[account.account_id] = existing + new_txns
            total_imported += len(new_txns)
            account.last_synced = datetime.utcnow()

        return SyncResult(
            success=True,
            accounts_synced=len(accounts_to_sync),
            transactions_imported=total_imported,
        )

    # --- Private helpers ---

    def _generate_accounts(self):
        """Generate mock bank accounts."""
        account_types = [
            ("checking", "Main Checking", 2500.00),
            ("savings", "Emergency Savings", 8500.00),
            ("credit_card", "Rewards Credit Card", -1200.00),
        ]
        self._accounts = []
        for i in range(min(self._num_accounts, len(account_types))):
            atype, name, balance = account_types[i]
            self._accounts.append(
                BankAccount(
                    account_id=f"mock-acct-{i+1:04d}",
                    name=name,
                    institution_name="Mock National Bank",
                    account_type=atype,
                    currency="USD",
                    balance=balance + self._rng.uniform(-500, 500),
                    available_balance=balance + self._rng.uniform(-100, 100),
                    last_synced=datetime.utcnow(),
                )
            )

    def _generate_transactions(self, account_id: str, days: int = 30):
        """Generate mock transactions for the last N days."""
        transactions = []
        today = date.today()

        for day_offset in range(days):
            txn_date = today - timedelta(days=day_offset)
            # 1-4 transactions per day
            num_txns = self._rng.randint(1, 4)

            for _ in range(num_txns):
                # 85% expenses, 15% income
                if self._rng.random() < 0.85:
                    merchant, category = self._rng.choice(MERCHANTS)
                    amount = round(self._rng.uniform(3.50, 150.00), 2)
                    if merchant == "Rent Payment":
                        amount = round(self._rng.uniform(1200, 2200), 2)
                    txn_type = TransactionType.DEBIT
                else:
                    merchant, category = self._rng.choice(INCOME_SOURCES)
                    amount = round(self._rng.uniform(50, 3500), 2)
                    txn_type = TransactionType.CREDIT

                txn_id = f"mock-txn-{account_id}-{day_offset}-{self._rng.randint(1000, 9999)}"
                transactions.append(
                    BankTransaction(
                        transaction_id=txn_id,
                        account_id=account_id,
                        amount=amount,
                        currency="USD",
                        description=f"{merchant} - {'Purchase' if txn_type == TransactionType.DEBIT else 'Payment'}",
                        category=category,
                        transaction_type=txn_type,
                        date=txn_date,
                        pending=(day_offset == 0 and self._rng.random() < 0.3),
                        merchant_name=merchant,
                    )
                )

        self._transactions[account_id] = sorted(
            transactions, key=lambda t: t.date, reverse=True
        )

    def _generate_recent_transactions(
        self, account_id: str, count: int = 3
    ) -> List[BankTransaction]:
        """Generate a few new recent transactions (for refresh)."""
        transactions = []
        today = date.today()

        for i in range(count):
            merchant, category = self._rng.choice(MERCHANTS)
            amount = round(self._rng.uniform(5.00, 80.00), 2)
            txn_id = f"mock-txn-{account_id}-new-{self._rng.randint(10000, 99999)}"
            transactions.append(
                BankTransaction(
                    transaction_id=txn_id,
                    account_id=account_id,
                    amount=amount,
                    currency="USD",
                    description=f"{merchant} - Purchase",
                    category=category,
                    transaction_type=TransactionType.DEBIT,
                    date=today,
                    merchant_name=merchant,
                )
            )

        return transactions
