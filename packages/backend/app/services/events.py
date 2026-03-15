"""Event-Driven Financial Activity Service.

Provides event emission, subscription management, replay,
and analytics for FinMind's financial activity system.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, and_, desc

from ..extensions import db
from ..models import (
    FinancialEvent,
    EventSubscription,
    EventType,
    EntityType,
    CallbackType,
)


# ── Event Emission ───────────────────────────────────────

def emit_event(
    user_id: int,
    event_type: str,
    entity_type: str,
    entity_id: int | None = None,
    payload: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    """Emit a financial event. This is the core event producer.

    Events are persisted immediately and can be replayed later.
    """
    event = FinancialEvent(
        user_id=user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
        metadata_=metadata or {},
    )
    db.session.add(event)
    db.session.commit()
    return _event_to_dict(event)


def emit_expense_created(user_id: int, expense_id: int, amount, currency: str, category: str | None = None) -> dict:
    """Convenience: emit expense.created event."""
    return emit_event(
        user_id=user_id,
        event_type=EventType.EXPENSE_CREATED.value,
        entity_type=EntityType.EXPENSE.value,
        entity_id=expense_id,
        payload={
            "amount": str(amount),
            "currency": currency,
            "category": category,
        },
    )


def emit_expense_updated(user_id: int, expense_id: int, changes: dict) -> dict:
    """Convenience: emit expense.updated event."""
    return emit_event(
        user_id=user_id,
        event_type=EventType.EXPENSE_UPDATED.value,
        entity_type=EntityType.EXPENSE.value,
        entity_id=expense_id,
        payload={"changes": changes},
    )


def emit_expense_deleted(user_id: int, expense_id: int, amount, currency: str) -> dict:
    """Convenience: emit expense.deleted event."""
    return emit_event(
        user_id=user_id,
        event_type=EventType.EXPENSE_DELETED.value,
        entity_type=EntityType.EXPENSE.value,
        entity_id=expense_id,
        payload={"amount": str(amount), "currency": currency},
    )


def emit_bill_event(user_id: int, event_type: str, bill_id: int, payload: dict | None = None) -> dict:
    """Emit a bill-related event."""
    return emit_event(
        user_id=user_id,
        event_type=event_type,
        entity_type=EntityType.BILL.value,
        entity_id=bill_id,
        payload=payload or {},
    )


def emit_anomaly(user_id: int, entity_type: str, entity_id: int, description: str, severity: str = "medium") -> dict:
    """Emit an anomaly detection event."""
    return emit_event(
        user_id=user_id,
        event_type=EventType.ANOMALY_DETECTED.value,
        entity_type=entity_type,
        entity_id=entity_id,
        payload={"description": description, "severity": severity},
    )


# ── Event Querying ───────────────────────────────────────

def get_events(
    user_id: int,
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Query events with rich filtering."""
    q = FinancialEvent.query.filter_by(user_id=user_id)

    if event_type:
        q = q.filter_by(event_type=event_type)
    if entity_type:
        q = q.filter_by(entity_type=entity_type)
    if entity_id is not None:
        q = q.filter_by(entity_id=entity_id)
    if since:
        q = q.filter(FinancialEvent.created_at >= since)
    if until:
        q = q.filter(FinancialEvent.created_at <= until)

    total = q.count()
    events = (
        q.order_by(desc(FinancialEvent.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "events": [_event_to_dict(e) for e in events],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_event_by_id(user_id: int, event_id: int) -> dict | None:
    """Get a single event by ID."""
    e = FinancialEvent.query.filter_by(id=event_id, user_id=user_id).first()
    return _event_to_dict(e) if e else None


def replay_events(
    user_id: int,
    entity_type: str | None = None,
    entity_id: int | None = None,
    since: datetime | None = None,
) -> list[dict]:
    """Replay events in chronological order (oldest first)."""
    q = FinancialEvent.query.filter_by(user_id=user_id)
    if entity_type:
        q = q.filter_by(entity_type=entity_type)
    if entity_id is not None:
        q = q.filter_by(entity_id=entity_id)
    if since:
        q = q.filter(FinancialEvent.created_at >= since)

    events = q.order_by(FinancialEvent.created_at.asc()).all()
    return [_event_to_dict(e) for e in events]


# ── Event Analytics ──────────────────────────────────────

def event_stats(user_id: int, days: int = 30) -> dict:
    """Get event statistics for a user."""
    cutoff = datetime.utcnow() - timedelta(days=int(days))
    q = FinancialEvent.query.filter(
        FinancialEvent.user_id == user_id,
        FinancialEvent.created_at >= cutoff,
    )

    total = q.count()

    # Breakdown by event type
    by_type = (
        db.session.query(
            FinancialEvent.event_type,
            func.count(FinancialEvent.id),
        )
        .filter(
            FinancialEvent.user_id == user_id,
            FinancialEvent.created_at >= cutoff,
        )
        .group_by(FinancialEvent.event_type)
        .all()
    )

    # Breakdown by entity type
    by_entity = (
        db.session.query(
            FinancialEvent.entity_type,
            func.count(FinancialEvent.id),
        )
        .filter(
            FinancialEvent.user_id == user_id,
            FinancialEvent.created_at >= cutoff,
        )
        .group_by(FinancialEvent.entity_type)
        .all()
    )

    # Daily activity
    daily = (
        db.session.query(
            func.date(FinancialEvent.created_at).label("day"),
            func.count(FinancialEvent.id),
        )
        .filter(
            FinancialEvent.user_id == user_id,
            FinancialEvent.created_at >= cutoff,
        )
        .group_by(func.date(FinancialEvent.created_at))
        .order_by(func.date(FinancialEvent.created_at))
        .all()
    )

    return {
        "total_events": total,
        "period_days": days,
        "by_event_type": {t: c for t, c in by_type},
        "by_entity_type": {t: c for t, c in by_entity},
        "daily_activity": [{"date": str(d), "count": c} for d, c in daily],
    }


# ── Subscriptions ────────────────────────────────────────

def subscribe(
    user_id: int,
    event_type: str,
    callback_type: str = "internal",
    callback_url: str | None = None,
) -> dict:
    """Subscribe to an event type."""
    existing = EventSubscription.query.filter_by(
        user_id=user_id,
        event_type=event_type,
        callback_type=callback_type,
    ).first()

    if existing:
        existing.is_active = True
        existing.callback_url = callback_url
    else:
        existing = EventSubscription(
            user_id=user_id,
            event_type=event_type,
            callback_type=callback_type,
            callback_url=callback_url,
        )
        db.session.add(existing)

    db.session.commit()
    return _sub_to_dict(existing)


def unsubscribe(user_id: int, subscription_id: int) -> bool:
    """Deactivate a subscription."""
    sub = EventSubscription.query.filter_by(
        id=subscription_id, user_id=user_id
    ).first()
    if not sub:
        return False
    sub.is_active = False
    db.session.commit()
    return True


def list_subscriptions(user_id: int, active_only: bool = True) -> list[dict]:
    """List user's event subscriptions."""
    q = EventSubscription.query.filter_by(user_id=user_id)
    if active_only:
        q = q.filter_by(is_active=True)
    return [_sub_to_dict(s) for s in q.all()]


# ── Available Event Types ────────────────────────────────

def available_event_types() -> list[dict]:
    """Return all available event types with descriptions."""
    descriptions = {
        "expense.created": "Fired when a new expense is recorded",
        "expense.updated": "Fired when an expense is modified",
        "expense.deleted": "Fired when an expense is removed",
        "bill.created": "Fired when a new bill is added",
        "bill.paid": "Fired when a bill is marked as paid",
        "bill.overdue": "Fired when a bill passes its due date",
        "bill.updated": "Fired when a bill is modified",
        "bill.deleted": "Fired when a bill is removed",
        "budget.exceeded": "Fired when spending exceeds budget limit",
        "budget.warning": "Fired when spending approaches budget limit",
        "category.created": "Fired when a new category is created",
        "category.deleted": "Fired when a category is removed",
        "anomaly.detected": "Fired when unusual financial activity is detected",
        "account.login": "Fired on successful login",
        "account.settings_changed": "Fired when account settings are updated",
    }
    return [
        {"event_type": et.value, "description": descriptions.get(et.value, "")}
        for et in EventType
    ]


# ── Helpers ──────────────────────────────────────────────

def _event_to_dict(e: FinancialEvent) -> dict:
    return {
        "id": e.id,
        "user_id": e.user_id,
        "event_type": e.event_type,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "payload": e.payload,
        "metadata": e.metadata_,
        "created_at": e.created_at.isoformat(),
    }


def _sub_to_dict(s: EventSubscription) -> dict:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "event_type": s.event_type,
        "callback_type": s.callback_type,
        "callback_url": s.callback_url,
        "is_active": s.is_active,
        "created_at": s.created_at.isoformat(),
    }
