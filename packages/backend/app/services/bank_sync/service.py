"""
Bank sync service layer.

Bridges the connector interface with the FinMind database models.
Handles importing transactions from bank connectors into the
FinMind expense tracking system.
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from ...extensions import db
from ...models import Expense, Category
from .base import (
    BaseBankConnector,
    BankTransaction,
    SyncResult,
    TransactionType,
)
from .registry import get_connector


class BankSyncService:
    """
    Service that orchestrates bank sync operations.

    Connects bank connector output to FinMind's data model,
    converting bank transactions into expenses.
    """

    def __init__(self, user_id: int, provider: str, config: Optional[dict] = None):
        self.user_id = user_id
        self.provider = provider
        self.connector = get_connector(provider, config)
        if self.connector is None:
            raise ValueError(f"Unknown bank provider: {provider}")

    def connect(self, credentials: dict) -> dict:
        """Connect to the bank provider."""
        status = self.connector.connect(credentials)
        return {"status": status.value, "provider": self.provider}

    def disconnect(self) -> dict:
        """Disconnect from the bank provider."""
        success = self.connector.disconnect()
        return {"success": success}

    def list_accounts(self) -> List[dict]:
        """List linked bank accounts."""
        accounts = self.connector.list_accounts()
        return [
            {
                "account_id": a.account_id,
                "name": a.name,
                "institution": a.institution_name,
                "type": a.account_type,
                "currency": a.currency,
                "balance": a.balance,
                "available_balance": a.available_balance,
                "last_synced": a.last_synced.isoformat() if a.last_synced else None,
            }
            for a in accounts
        ]

    def import_and_save(
        self,
        account_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """
        Import transactions from a bank account and save as expenses.

        Returns:
            Summary of imported transactions.
        """
        if start_date is None:
            start_date = date.today() - timedelta(days=30)
        if end_date is None:
            end_date = date.today()

        transactions = self.connector.import_transactions(
            account_id, start_date, end_date
        )

        imported, skipped = self._save_transactions(transactions)

        return {
            "account_id": account_id,
            "transactions_found": len(transactions),
            "imported": imported,
            "skipped": skipped,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
        }

    def refresh(self, account_id: Optional[str] = None) -> dict:
        """
        Refresh account data and import new transactions.

        Args:
            account_id: Specific account or None for all accounts.

        Returns:
            Sync result summary.
        """
        result = self.connector.refresh(account_id)

        # After refresh, import any new transactions
        accounts = self.connector.list_accounts()
        if account_id:
            accounts = [a for a in accounts if a.account_id == account_id]

        total_imported = 0
        for account in accounts:
            # Import only last 3 days on refresh (incremental)
            start = date.today() - timedelta(days=3)
            transactions = self.connector.import_transactions(
                account.account_id, start_date=start
            )
            imported, _ = self._save_transactions(transactions)
            total_imported += imported

        return {
            "success": result.success,
            "accounts_synced": result.accounts_synced,
            "transactions_imported": total_imported,
            "errors": result.errors,
            "synced_at": result.synced_at.isoformat(),
        }

    def _save_transactions(
        self, transactions: List[BankTransaction]
    ) -> Tuple[int, int]:
        """
        Save bank transactions as FinMind expenses.

        Deduplicates by checking for existing transactions with
        the same external transaction ID.

        Returns:
            (imported_count, skipped_count)
        """
        imported = 0
        skipped = 0

        for txn in transactions:
            # Skip pending transactions
            if txn.pending:
                skipped += 1
                continue

            # Skip income/credits (only track expenses)
            if txn.transaction_type == TransactionType.CREDIT:
                skipped += 1
                continue

            # Deduplicate: check if transaction already imported
            existing = Expense.query.filter_by(
                user_id=self.user_id,
                notes=f"[bank-sync:{txn.transaction_id}]",
            ).first()

            if existing:
                skipped += 1
                continue

            # Find or create category
            category_id = self._resolve_category(txn.category)

            # Create expense
            expense = Expense(
                user_id=self.user_id,
                category_id=category_id,
                amount=txn.amount,
                currency=txn.currency,
                expense_type="EXPENSE",
                notes=f"[bank-sync:{txn.transaction_id}] {txn.description}",
                spent_at=txn.date,
            )
            db.session.add(expense)
            imported += 1

        if imported > 0:
            db.session.commit()

        return imported, skipped

    def _resolve_category(self, category_name: Optional[str]) -> Optional[int]:
        """
        Find or create a category by name for the current user.

        Returns:
            Category ID or None.
        """
        if not category_name:
            return None

        category = Category.query.filter_by(
            user_id=self.user_id,
            name=category_name,
        ).first()

        if not category:
            category = Category(user_id=self.user_id, name=category_name)
            db.session.add(category)
            db.session.flush()

        return category.id
