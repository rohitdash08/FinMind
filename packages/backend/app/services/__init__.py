"""Services package."""

from .ai import generate_insights, suggest_budget
from .cache import cache_delete_patterns, monthly_summary_key
from .reminders import check_and_send_reminders
from .expense_import import extract_transactions_from_statement, normalize_import_rows
from .bank_connector import (
    BankAccount,
    BankConnector,
    BankConnectionStatus,
    BankTransaction,
    ConnectorRegistry,
    SyncResult,
)
from .bank_sync import BankSyncService
from .bank_connectors.mock import MockBankConnector

__all__ = [
    # AI services
    "generate_insights",
    "suggest_budget",
    # Cache services
    "cache_delete_patterns",
    "monthly_summary_key",
    # Reminder services
    "check_and_send_reminders",
    # Expense import
    "extract_transactions_from_statement",
    "normalize_import_rows",
    # Bank connector base
    "BankAccount",
    "BankConnector",
    "BankConnectionStatus",
    "BankTransaction",
    "ConnectorRegistry",
    "SyncResult",
    # Bank sync service
    "BankSyncService",
    # Bank connectors
    "MockBankConnector",
]
