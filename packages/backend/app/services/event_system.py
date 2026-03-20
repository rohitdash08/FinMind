"""
Event-Driven Financial Activity System.

Provides in-process event bus for financial domain events:
- expense_added, expense_updated, expense_deleted
- bill_paid, bill_overdue
- budget_exceeded
- anomaly_detected

Events are stored in a FinancialEvent log table (audit history) and
dispatched to registered synchronous handlers.

Note: This is an in-process event bus backed by DB persistence.
For true async (Celery/RQ), handlers can be replaced with task enqueuing.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from datetime import datetime
from enum import Enum
import json
import threading

from .. import db


# ──────────────────────────────────────────────────────────────────────
# Event types
# ──────────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    EXPENSE_ADDED = "expense_added"
    EXPENSE_UPDATED = "expense_updated"
    EXPENSE_DELETED = "expense_deleted"
    BILL_PAID = "bill_paid"
    BILL_OVERDUE = "bill_overdue"
    BUDGET_EXCEEDED = "budget_exceeded"
    ANOMALY_DETECTED = "anomaly_detected"


@dataclass
class FinancialEvent:
    """Domain event payload."""
    event_type: str
    user_id: int
    payload: dict
    occurred_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    event_id: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────
# SQLAlchemy model for audit log
# (Uses raw SQL so we don't need to modify models.py import chain)
# ──────────────────────────────────────────────────────────────────────

def _ensure_events_table():
    """Create financial_events audit table if it doesn't exist."""
    db.session.execute(db.text("""
        CREATE TABLE IF NOT EXISTS financial_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type VARCHAR(64) NOT NULL,
            user_id INTEGER NOT NULL,
            payload TEXT NOT NULL,
            occurred_at VARCHAR(32) NOT NULL,
            processed BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.commit()


def _persist_event(event: FinancialEvent) -> int:
    """Persist event to audit log. Returns event DB id."""
    try:
        _ensure_events_table()
        result = db.session.execute(
            db.text("""
                INSERT INTO financial_events (event_type, user_id, payload, occurred_at)
                VALUES (:event_type, :user_id, :payload, :occurred_at)
            """),
            {
                "event_type": event.event_type,
                "user_id": event.user_id,
                "payload": json.dumps(event.payload),
                "occurred_at": event.occurred_at,
            }
        )
        db.session.commit()
        return result.lastrowid
    except Exception:
        db.session.rollback()
        return 0


# ──────────────────────────────────────────────────────────────────────
# In-process event bus
# ──────────────────────────────────────────────────────────────────────

_handlers: dict[str, list[Callable]] = {}
_lock = threading.Lock()


def subscribe(event_type: str, handler: Callable[[FinancialEvent], None]) -> None:
    """Register a handler for an event type."""
    with _lock:
        if event_type not in _handlers:
            _handlers[event_type] = []
        _handlers[event_type].append(handler)


def unsubscribe(event_type: str, handler: Callable) -> None:
    """Remove a handler."""
    with _lock:
        if event_type in _handlers:
            _handlers[event_type] = [h for h in _handlers[event_type] if h != handler]


def emit(event: FinancialEvent) -> int:
    """
    Emit an event: persist to audit log + call all registered handlers.
    Returns the DB id of the persisted event.
    """
    event_id = _persist_event(event)
    event.event_id = str(event_id)

    with _lock:
        handlers = list(_handlers.get(event.event_type, []))
        # Also call wildcard handlers
        handlers += list(_handlers.get("*", []))

    for handler in handlers:
        try:
            handler(event)
        except Exception:
            pass  # Don't let a failing handler break the emit chain

    return event_id


# ──────────────────────────────────────────────────────────────────────
# Built-in handlers
# ──────────────────────────────────────────────────────────────────────

def _handle_budget_exceeded(event: FinancialEvent) -> None:
    """Log budget exceeded events (placeholder for notifications)."""
    # In a real system: enqueue notification, update badge count, etc.
    pass


def _handle_anomaly_detected(event: FinancialEvent) -> None:
    """Log anomaly events (placeholder for alerts)."""
    pass


# Register built-in handlers
subscribe(EventType.BUDGET_EXCEEDED, _handle_budget_exceeded)
subscribe(EventType.ANOMALY_DETECTED, _handle_anomaly_detected)


# ──────────────────────────────────────────────────────────────────────
# Query functions
# ──────────────────────────────────────────────────────────────────────

def get_event_history(
    user_id: int,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """
    Retrieve audit history for a user.

    Args:
        user_id: Filter by user
        event_type: Optional event type filter
        limit: Max records to return
        offset: Pagination offset

    Returns:
        List of event dicts sorted by occurred_at desc.
    """
    try:
        _ensure_events_table()
        if event_type:
            rows = db.session.execute(
                db.text("""
                    SELECT id, event_type, user_id, payload, occurred_at, processed
                    FROM financial_events
                    WHERE user_id = :user_id AND event_type = :event_type
                    ORDER BY id DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"user_id": user_id, "event_type": event_type, "limit": limit, "offset": offset}
            ).fetchall()
        else:
            rows = db.session.execute(
                db.text("""
                    SELECT id, event_type, user_id, payload, occurred_at, processed
                    FROM financial_events
                    WHERE user_id = :user_id
                    ORDER BY id DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"user_id": user_id, "limit": limit, "offset": offset}
            ).fetchall()

        return [
            {
                "id": row[0],
                "event_type": row[1],
                "user_id": row[2],
                "payload": json.loads(row[3]) if row[3] else {},
                "occurred_at": row[4],
                "processed": bool(row[5]),
            }
            for row in rows
        ]
    except Exception:
        return []


def get_event_stats(user_id: int) -> dict:
    """Return event counts by type for a user."""
    try:
        _ensure_events_table()
        rows = db.session.execute(
            db.text("""
                SELECT event_type, COUNT(*) as cnt
                FROM financial_events
                WHERE user_id = :user_id
                GROUP BY event_type
            """),
            {"user_id": user_id}
        ).fetchall()
        return {row[0]: row[1] for row in rows}
    except Exception:
        return {}


# ──────────────────────────────────────────────────────────────────────
# Convenience emitters
# ──────────────────────────────────────────────────────────────────────

def emit_expense_added(user_id: int, expense_id: int, amount: float, description: str) -> int:
    return emit(FinancialEvent(
        event_type=EventType.EXPENSE_ADDED,
        user_id=user_id,
        payload={"expense_id": expense_id, "amount": amount, "description": description},
    ))


def emit_bill_paid(user_id: int, bill_id: int, amount: float) -> int:
    return emit(FinancialEvent(
        event_type=EventType.BILL_PAID,
        user_id=user_id,
        payload={"bill_id": bill_id, "amount": amount},
    ))


def emit_budget_exceeded(user_id: int, category: str, budget: float, actual: float) -> int:
    return emit(FinancialEvent(
        event_type=EventType.BUDGET_EXCEEDED,
        user_id=user_id,
        payload={"category": category, "budget": budget, "actual": actual, "overage": round(actual - budget, 2)},
    ))


def emit_anomaly_detected(user_id: int, expense_id: int, reason: str, amount: float) -> int:
    return emit(FinancialEvent(
        event_type=EventType.ANOMALY_DETECTED,
        user_id=user_id,
        payload={"expense_id": expense_id, "reason": reason, "amount": amount},
    ))