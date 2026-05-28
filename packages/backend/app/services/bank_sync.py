"""Bank Account Sync Simulation.

Simulate bank account synchronization:
- Multi-account support (checking, savings, credit)
- Transaction import and deduplication
- Balance reconciliation
- Sync scheduling (incremental vs full)
- Conflict resolution (duplicate handling)
- Sync status tracking and audit log
"""

import logging
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.banksync")


class SyncStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT = "credit"
    INVESTMENT = "investment"


class SyncTransaction:
    def __init__(self, tx_id, date, amount, description, merchant=None,
                 category=None, reference=None):
        self.tx_id = tx_id
        self.date = date
        self.amount = amount
        self.description = description
        self.merchant = merchant
        self.category = category
        self.reference = reference
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Create dedup hash from amount + date + description."""
        raw = f"{self.amount}:{self.date}:{self.description}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self):
        return {
            "tx_id": self.tx_id,
            "date": self.date,
            "amount": self.amount,
            "description": self.description,
            "merchant": self.merchant,
            "category": self.category,
            "reference": self.reference,
            "hash": self.hash,
        }


class BankAccount:
    def __init__(self, account_id: str, account_type: str, institution: str,
                 balance: float = 0, currency: str = "USD"):
        self.account_id = account_id
        self.account_type = account_type
        self.institution = institution
        self.balance = balance
        self.currency = currency
        self.last_sync = None
        self.transactions = []

    def to_dict(self):
        return {
            "account_id": self.account_id,
            "account_type": self.account_type,
            "institution": self.institution,
            "balance": round(self.balance, 2),
            "currency": self.currency,
            "last_sync": self.last_sync,
            "transaction_count": len(self.transactions),
        }


class SyncResult:
    def __init__(self, sync_id: str):
        self.sync_id = sync_id
        self.status = SyncStatus.PENDING
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.completed_at = None
        self.new_transactions = 0
        self.duplicates_skipped = 0
        self.updated_balances = 0
        self.errors = []
        self.account_results = {}

    def to_dict(self):
        return {
            "sync_id": self.sync_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "new_transactions": self.new_transactions,
            "duplicates_skipped": self.duplicates_skipped,
            "updated_balances": self.updated_balances,
            "errors": self.errors,
            "account_results": self.account_results,
        }


class BankSyncService:
    """Simulate bank account synchronization."""

    def __init__(self):
        self.accounts = {}
        self.existing_hashes = set()
        self.sync_history = []

    def register_account(self, account_id: str, account_type: str,
                          institution: str, balance: float = 0) -> dict:
        """Register a bank account."""
        account = BankAccount(account_id, account_type, institution, balance)
        self.accounts[account_id] = account
        return {"status": "registered", "account": account.to_dict()}

    def _simulate_fetch(self, account_id: str, since: str = None) -> list[dict]:
        """Simulate fetching transactions from bank API."""
        # In production, this would call Plaid/Yodlee/etc
        # For simulation, return empty list (real data comes from API)
        return []

    def _deduplicate(self, new_txs: list[dict]) -> tuple[list, int]:
        """Remove duplicate transactions using hash comparison."""
        unique = []
        dupes = 0
        for tx in new_txs:
            raw = f"{tx.get('amount', 0)}:{str(tx.get('date', ''))[:10]}:{tx.get('description', '')}"
            h = hashlib.md5(raw.encode()).hexdigest()[:12]
            if h not in self.existing_hashes:
                self.existing_hashes.add(h)
                unique.append(tx)
            else:
                dupes += 1
        return unique, dupes

    def _reconcile_balance(self, account: BankAccount,
                           transactions: list[dict],
                           reported_balance: float) -> dict:
        """Reconcile calculated balance with bank-reported balance."""
        calculated = account.balance
        for tx in transactions:
            calculated += float(tx.get("amount", 0))

        discrepancy = reported_balance - calculated

        return {
            "calculated_balance": round(calculated, 2),
            "reported_balance": round(reported_balance, 2),
            "discrepancy": round(discrepancy, 2),
            "reconciled": abs(discrepancy) < 0.01,
        }

    def sync_account(self, account_id: str,
                      bank_transactions: list[dict] = None,
                      reported_balance: float = None) -> dict:
        """Sync a single account with bank data."""
        if account_id not in self.accounts:
            return {"error": "Account not found", "account_id": account_id}

        sync_id = str(uuid4())[:8]
        result = SyncResult(sync_id)
        result.status = SyncStatus.IN_PROGRESS

        try:
            account = self.accounts[account_id]
            txs = bank_transactions or self._simulate_fetch(account_id)

            # Deduplicate
            unique, dupes = self._deduplicate(txs)
            result.duplicates_skipped = dupes

            # Add to account
            for tx in unique:
                account.transactions.append(tx)
            result.new_transactions = len(unique)

            # Reconcile balance
            if reported_balance is not None:
                recon = self._reconcile_balance(account, unique, reported_balance)
                result.updated_balances = 1
                if recon["reconciled"]:
                    account.balance = reported_balance
                result.account_results = {
                    "balance_reconciliation": recon,
                }

            account.last_sync = datetime.now(timezone.utc).isoformat()
            result.status = SyncStatus.COMPLETED

        except Exception as e:
            result.status = SyncStatus.FAILED
            result.errors.append(str(e))

        result.completed_at = datetime.now(timezone.utc).isoformat()
        self.sync_history.append(result.to_dict())

        return result.to_dict()

    def sync_all(self, bank_data: dict = None) -> dict:
        """Sync all registered accounts."""
        sync_id = str(uuid4())[:8]
        results = {}

        bank_data = bank_data or {}
        total_new = 0
        total_dupes = 0

        for account_id in self.accounts:
            acct_data = bank_data.get(account_id, {})
            r = self.sync_account(
                account_id,
                bank_transactions=acct_data.get("transactions", []),
                reported_balance=acct_data.get("balance"),
            )
            results[account_id] = r
            total_new += r.get("new_transactions", 0)
            total_dupes += r.get("duplicates_skipped", 0)

        return {
            "sync_id": sync_id,
            "accounts_synced": len(results),
            "total_new_transactions": total_new,
            "total_duplicates_skipped": total_dupes,
            "results": results,
        }

    def get_accounts(self) -> list[dict]:
        """List all registered accounts."""
        return [a.to_dict() for a in self.accounts.values()]

    def get_sync_history(self, limit: int = 10) -> list[dict]:
        """Get recent sync history."""
        return self.sync_history[-limit:]
