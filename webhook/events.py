"""Webhook event type definitions for FinMind.

Defines all supported event types emitted by the system. Each event type
follows a `resource.action` naming convention.
"""

from enum import Enum


class EventType(str, Enum):
    """Supported webhook event types.

    Naming convention: ``resource.action``

    Categories:
        - **Transaction** – lifecycle of financial transactions
        - **Account** – connection and sync status changes
        - **Budget** – threshold alerts
        - **Anomaly** – fraud / unusual-activity detection
        - **Export** – data-export completion
    """

    # Transaction events
    TRANSACTION_CREATED = "transaction.created"
    TRANSACTION_UPDATED = "transaction.updated"
    TRANSACTION_DELETED = "transaction.deleted"

    # Account events
    ACCOUNT_CONNECTED = "account.connected"
    ACCOUNT_DISCONNECTED = "account.disconnected"
    ACCOUNT_SYNCED = "account.synced"

    # Budget events
    BUDGET_EXCEEDED = "budget.exceeded"
    BUDGET_WARNING = "budget.warning"

    # Anomaly events
    ANOMALY_DETECTED = "anomaly.detected"

    # Export events
    EXPORT_COMPLETED = "export.completed"


# Convenient groupings for filtering / subscription
TRANSACTION_EVENTS = {
    EventType.TRANSACTION_CREATED,
    EventType.TRANSACTION_UPDATED,
    EventType.TRANSACTION_DELETED,
}

ACCOUNT_EVENTS = {
    EventType.ACCOUNT_CONNECTED,
    EventType.ACCOUNT_DISCONNECTED,
    EventType.ACCOUNT_SYNCED,
}

BUDGET_EVENTS = {
    EventType.BUDGET_EXCEEDED,
    EventType.BUDGET_WARNING,
}

ALL_EVENTS = set(EventType)
