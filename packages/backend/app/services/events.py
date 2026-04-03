"""Event-Driven Financial Activity System for FinMind (#97)."""
import logging
from datetime import datetime, date
from typing import Optional, Callable
from enum import Enum

from ..extensions import db
from ..models import FinancialEvent

logger = logging.getLogger("finmind.events")


class EventType(str, Enum):
    EXPENSE_ADDED = "expense_added"
    EXPENSE_UPDATED = "expense_updated"
    EXPENSE_DELETED = "expense_deleted"
    INCOME_ADDED = "income_added"
    BILL_PAID = "bill_paid"
    BILL_OVERDUE = "bill_overdue"
    BUDGET_EXCEEDED = "budget_exceeded"
    ANOMALY_DETECTED = "anomaly_detected"
    RECURRING_TRIGGERED = "recurring_triggered"
    CATEGORY_CREATED = "category_created"
    SAVINGS_MILESTONE = "savings_milestone"


# In-memory event handlers registry
# Maps event_type -> list of handler functions
_handlers: dict[str, list[Callable]] = {}


def subscribe(event_type: str, handler: Callable) -> None:
    """Register a handler function for an event type."""
    if event_type not in _handlers:
        _handlers[event_type] = []
    _handlers[event_type].append(handler)
    logger.debug("Handler registered for event_type=%s", event_type)


def emit(
    uid: int,
    event_type: str,
    payload: dict,
    persist: bool = True,
) -> Optional["FinancialEvent"]:
    """
    Emit a financial event.

    1. Persists the event to the database (if persist=True)
    2. Executes all registered handlers asynchronously (sync in MVP)

    Args:
        uid: User ID
        event_type: One of EventType enum values
        payload: Dict with event-specific data
        persist: Whether to store in DB (default True)

    Returns:
        The created FinancialEvent record, or None if not persisted
    """
    import json

    event = None
    if persist:
        try:
            event = FinancialEvent(
                user_id=uid,
                event_type=event_type,
                payload=json.dumps(payload),
                occurred_at=datetime.utcnow(),
            )
            db.session.add(event)
            db.session.commit()
        except Exception as e:
            logger.error("Failed to persist event uid=%s type=%s: %s", uid, event_type, e)
            db.session.rollback()

    # Execute handlers
    handlers = _handlers.get(event_type, [])
    for handler in handlers:
        try:
            handler(uid, event_type, payload)
        except Exception as e:
            logger.error("Event handler error event_type=%s: %s", event_type, e)

    logger.info("Event emitted uid=%s type=%s handlers=%d", uid, event_type, len(handlers))
    return event


def get_activity_feed(
    uid: int,
    limit: int = 50,
    offset: int = 0,
    event_type: Optional[str] = None,
) -> dict:
    """
    Get the user's financial activity feed (event history).

    Returns:
        {
            "events": [...],
            "total": int,
            "limit": int,
            "offset": int
        }
    """
    import json

    q = db.session.query(FinancialEvent).filter_by(user_id=uid)
    if event_type:
        q = q.filter(FinancialEvent.event_type == event_type)

    total = q.count()
    events = (
        q.order_by(FinancialEvent.occurred_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "payload": json.loads(e.payload) if e.payload else {},
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in events
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_activity_summary(uid: int, days: int = 30) -> dict:
    """
    Get summary statistics of financial activity for the past N days.
    """
    from datetime import timedelta
    from sqlalchemy import func, extract

    cutoff = datetime.utcnow() - timedelta(days=days)
    counts = (
        db.session.query(
            FinancialEvent.event_type,
            func.count(FinancialEvent.id).label("count")
        )
        .filter(
            FinancialEvent.user_id == uid,
            FinancialEvent.occurred_at >= cutoff,
        )
        .group_by(FinancialEvent.event_type)
        .all()
    )

    by_type = {row.event_type: row.count for row in counts}
    total = sum(by_type.values())

    return {
        "period_days": days,
        "total_events": total,
        "by_type": by_type,
        "most_active_type": max(by_type, key=by_type.__getitem__) if by_type else None,
    }


# Built-in event handlers

def _handle_budget_alert(uid: int, event_type: str, payload: dict) -> None:
    """Log budget exceeded events for dashboard display."""
    if event_type == EventType.BUDGET_EXCEEDED:
        logger.warning(
            "Budget exceeded uid=%s category=%s amount=%.2f",
            uid,
            payload.get("category_name", "unknown"),
            payload.get("total_spent", 0),
        )


def _handle_anomaly_alert(uid: int, event_type: str, payload: dict) -> None:
    """Log anomaly events."""
    if event_type == EventType.ANOMALY_DETECTED:
        logger.warning(
            "Anomaly detected uid=%s type=%s details=%s",
            uid,
            payload.get("anomaly_type", "unknown"),
            str(payload)[:200],
        )


# Register built-in handlers on module load
subscribe(EventType.BUDGET_EXCEEDED, _handle_budget_alert)
subscribe(EventType.ANOMALY_DETECTED, _handle_anomaly_alert)

