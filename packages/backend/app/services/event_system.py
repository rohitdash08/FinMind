"""Event-Driven Financial Activity System.

Pub/sub event bus for financial activities:
- Transaction events (created, updated, deleted, threshold exceeded)
- Budget events (limit reached, goal achieved)
- Account events (balance changed, linked, unlinked)
- Async event processing with handlers
- Event persistence and replay
"""

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional
from uuid import uuid4

logger = logging.getLogger("finmind.events")


class EventType(str, Enum):
    # Transaction events
    TRANSACTION_CREATED = "transaction.created"
    TRANSACTION_UPDATED = "transaction.updated"
    TRANSACTION_DELETED = "transaction.deleted"
    TRANSACTION_THRESHOLD = "transaction.threshold_exceeded"
    TRANSACTION_LARGE = "transaction.large_detected"

    # Budget events
    BUDGET_CREATED = "budget.created"
    BUDGET_LIMIT_REACHED = "budget.limit_reached"
    BUDGET_LIMIT_WARNING = "budget.limit_warning"  # 80% threshold
    BUDGET_GOAL_ACHIEVED = "budget.goal_achieved"

    # Account events
    ACCOUNT_LINKED = "account.linked"
    ACCOUNT_UNLINKED = "account.unlinked"
    ACCOUNT_BALANCE_CHANGED = "account.balance_changed"
    ACCOUNT_LOW_BALANCE = "account.low_balance"

    # Bill events
    BILL_DUE_SOON = "bill.due_soon"
    BILL_OVERDUE = "bill.overdue"
    BILL_PAID = "bill.paid"

    # System events
    USER_LOGIN = "user.login"
    USER_ANOMALY = "user.anomaly_detected"


class Event:
    """Immutable event object."""

    def __init__(self, event_type: EventType, payload: dict = None,
                 user_id: str = "", source: str = ""):
        self.event_id = str(uuid4())
        self.event_type = event_type if isinstance(event_type, str) else event_type.value
        self.payload = payload or {}
        self.user_id = user_id
        self.source = source
        self.timestamp = time.time()
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "user_id": self.user_id,
            "source": self.source,
            "timestamp": self.timestamp,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        evt = cls(
            event_type=data.get("event_type", ""),
            payload=data.get("payload", {}),
            user_id=data.get("user_id", ""),
            source=data.get("source", ""),
        )
        evt.event_id = data.get("event_id", evt.event_id)
        evt.timestamp = data.get("timestamp", evt.timestamp)
        evt.created_at = data.get("created_at", evt.created_at)
        return evt


class EventHandler:
    """Wrapper for event handler functions."""

    def __init__(self, handler: Callable, name: str = "", priority: int = 0):
        self.handler = handler
        self.name = name or handler.__name__
        self.priority = priority  # Lower = higher priority

    async def __call__(self, event: Event):
        return self.handler(event)


class EventBus:
    """Central event bus for publish/subscribe pattern."""

    def __init__(self):
        self._handlers = defaultdict(list)  # event_type -> [EventHandler]
        self._wildcard_handlers = []  # Subscribe to all events
        self._event_log = []  # Event persistence
        self._max_log_size = 10000

    def subscribe(self, event_type: str, handler: Callable, name: str = "", priority: int = 0):
        """Subscribe to a specific event type."""
        eh = EventHandler(handler, name, priority)
        self._handlers[event_type].append(eh)
        self._handlers[event_type].sort(key=lambda h: h.priority)
        logger.info(f"Subscribed {eh.name} to {event_type}")

    def subscribe_all(self, handler: Callable, name: str = ""):
        """Subscribe to all events (wildcard)."""
        eh = EventHandler(handler, name)
        self._wildcard_handlers.append(eh)

    def unsubscribe(self, event_type: str, handler_name: str):
        """Unsubscribe a handler by name."""
        self._handlers[event_type] = [
            h for h in self._handlers[event_type] if h.name != handler_name
        ]

    def publish(self, event: Event) -> dict:
        """Publish an event to all subscribers."""
        # Log the event
        self._event_log.append(event.to_dict())
        if len(self._event_log) > self._max_log_size:
            self._event_log = self._event_log[-self._max_log_size:]

        # Notify specific handlers
        handlers = self._handlers.get(event.event_type, [])
        results = []

        for eh in handlers:
            try:
                result = eh.handler(event)
                results.append({"handler": eh.name, "status": "ok", "result": result})
            except Exception as e:
                logger.error(f"Handler {eh.name} failed: {e}")
                results.append({"handler": eh.name, "status": "error", "error": str(e)})

        # Notify wildcard handlers
        for eh in self._wildcard_handlers:
            try:
                eh.handler(event)
            except Exception as e:
                logger.error(f"Wildcard handler {eh.name} failed: {e}")

        return {
            "event_id": event.event_id,
            "notified": len(handlers) + len(self._wildcard_handlers),
            "results": results,
        }

    def get_event_log(self, event_type: str = None, user_id: str = None,
                      limit: int = 100) -> list[dict]:
        """Get event log with optional filtering."""
        events = self._event_log

        if event_type:
            events = [e for e in events if e.get("event_type") == event_type]
        if user_id:
            events = [e for e in events if e.get("user_id") == user_id]

        return events[-limit:]

    def replay(self, event_type: str = None, user_id: str = None):
        """Replay events through handlers."""
        events = self.get_event_log(event_type, user_id)
        results = []
        for evt_data in events:
            event = Event.from_dict(evt_data)
            result = self.publish(event)
            results.append(result)
        return {"replayed": len(results), "results": results}


# Global event bus instance
event_bus = EventBus()


# ===========================================
# Built-in event handlers
# ===========================================

def handle_transaction_threshold(event: Event) -> dict:
    """Alert when transaction exceeds threshold."""
    amount = event.payload.get("amount", 0)
    threshold = event.payload.get("threshold", 1000)
    return {
        "alert": amount > threshold,
        "amount": amount,
        "message": f"Transaction ${amount} exceeds threshold ${threshold}",
    }


def handle_budget_warning(event: Event) -> dict:
    """Send warning when budget approaching limit."""
    usage_pct = event.payload.get("usage_percent", 0)
    return {
        "warning_level": "critical" if usage_pct > 90 else "warning",
        "message": f"Budget at {usage_pct}% usage",
    }


def handle_large_transaction(event: Event) -> dict:
    """Flag unusually large transactions."""
    amount = event.payload.get("amount", 0)
    avg_amount = event.payload.get("average_amount", 0)

    if avg_amount > 0 and amount > avg_amount * 3:
        return {
            "flagged": True,
            "reason": f"${amount} is {amount/avg_amount:.1f}x average ${avg_amount}",
        }
    return {"flagged": False}


# Register built-in handlers
event_bus.subscribe("transaction.threshold_exceeded", handle_transaction_threshold, "threshold_checker")
event_bus.subscribe("budget.limit_warning", handle_budget_warning, "budget_warner")
event_bus.subscribe("transaction.large_detected", handle_large_transaction, "large_tx_detector")
