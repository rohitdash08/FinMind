"""Event-driven financial activity system.

Publish and subscribe to financial events (expense added, budget exceeded,
goal reached, etc.) with event log and webhook support.
"""

from datetime import datetime
from ..extensions import db


class FinancialEvent(db.Model):
    __tablename__ = "financial_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    source = db.Column(db.String(50), default="system")  # system, user, webhook
    payload = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class EventSubscription(db.Model):
    __tablename__ = "event_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)  # * for all
    webhook_url = db.Column(db.String(500), nullable=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


EVENT_TYPES = [
    "expense.created", "expense.updated", "expense.deleted",
    "budget.exceeded", "budget.warning",
    "goal.milestone", "goal.completed",
    "bill.due_soon", "bill.overdue",
    "anomaly.detected", "review.completed",
]

# In-memory handlers for this process
_handlers: dict[str, list] = {}


def publish(user_id: int, event_type: str, payload: dict | None = None, source: str = "system") -> dict:
    """Publish a financial event."""
    import json

    if event_type not in EVENT_TYPES and event_type != "*":
        raise ValueError(f"Unknown event type: {event_type}")

    event = FinancialEvent(
        user_id=user_id, event_type=event_type,
        payload=json.dumps(payload or {}), source=source,
    )
    db.session.add(event)
    db.session.commit()

    # Trigger in-memory handlers
    for handler in _handlers.get(event_type, []) + _handlers.get("*", []):
        try:
            handler(event_type, payload or {}, user_id)
        except Exception:
            pass

    return _serialize_event(event)


def get_events(user_id: int, event_type: str | None = None, limit: int = 50) -> list[dict]:
    q = FinancialEvent.query.filter_by(user_id=user_id)
    if event_type:
        q = q.filter_by(event_type=event_type)
    events = q.order_by(FinancialEvent.created_at.desc()).limit(limit).all()
    return [_serialize_event(e) for e in events]


def subscribe(user_id: int, event_type: str, webhook_url: str | None = None) -> dict:
    if event_type not in EVENT_TYPES and event_type != "*":
        raise ValueError(f"Unknown event type: {event_type}")

    sub = EventSubscription(
        user_id=user_id, event_type=event_type, webhook_url=webhook_url,
    )
    db.session.add(sub)
    db.session.commit()
    return _serialize_sub(sub)


def get_subscriptions(user_id: int) -> list[dict]:
    subs = EventSubscription.query.filter_by(user_id=user_id, active=True).all()
    return [_serialize_sub(s) for s in subs]


def unsubscribe(user_id: int, sub_id: int) -> bool:
    sub = EventSubscription.query.filter_by(id=sub_id, user_id=user_id).first()
    if not sub:
        return False
    sub.active = False
    db.session.commit()
    return True


def get_event_types() -> list[str]:
    return EVENT_TYPES


def register_handler(event_type: str, handler):
    """Register an in-memory event handler."""
    if event_type not in _handlers:
        _handlers[event_type] = []
    _handlers[event_type].append(handler)


def clear_handlers():
    _handlers.clear()


def _serialize_event(e: FinancialEvent) -> dict:
    import json
    return {
        "id": e.id, "event_type": e.event_type, "source": e.source,
        "payload": json.loads(e.payload), "created_at": e.created_at.isoformat(),
    }


def _serialize_sub(s: EventSubscription) -> dict:
    return {
        "id": s.id, "event_type": s.event_type,
        "webhook_url": s.webhook_url, "active": s.active,
        "created_at": s.created_at.isoformat(),
    }
