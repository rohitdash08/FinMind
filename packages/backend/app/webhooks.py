import hashlib
import hmac
import json
import logging
import time
import threading
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import secrets

import requests
from sqlalchemy import Enum as SAEnum

from .extensions import db

logger = logging.getLogger(__name__)


# ─────────────────────────── Event types ─────────────────────────────────────

class WebhookEvent(str, Enum):
    EXPENSE_CREATED = "expense.created"
    EXPENSE_UPDATED = "expense.updated"
    EXPENSE_DELETED = "expense.deleted"
    BILL_CREATED = "bill.created"
    BILL_PAID = "bill.paid"
    REMINDER_TRIGGERED = "reminder.triggered"
    BUDGET_EXCEEDED = "budget.exceeded"


# ─────────────────────────── Models ──────────────────────────────────────────

class WebhookSubscription(db.Model):
    __tablename__ = "webhook_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    secret = db.Column(db.String(64), nullable=False)
    events = db.Column(db.Text, nullable=False)  # JSON array of event names
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    consecutive_failures = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_events(self) -> list:
        return json.loads(self.events)

    def set_events(self, event_list: list):
        self.events = json.dumps(event_list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "events": self.get_events(),
            "is_active": self.is_active,
            "consecutive_failures": self.consecutive_failures,
            "created_at": self.created_at.isoformat(),
        }


class WebhookDelivery(db.Model):
    __tablename__ = "webhook_deliveries"
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("webhook_subscriptions.id"), nullable=False)
    event = db.Column(db.String(64), nullable=False)
    payload = db.Column(db.Text, nullable=False)  # JSON payload sent
    status_code = db.Column(db.Integer, nullable=True)
    attempt = db.Column(db.Integer, default=1, nullable=False)
    succeeded = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    correlation_id = db.Column(db.String(36), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subscription_id": self.subscription_id,
            "event": self.event,
            "status_code": self.status_code,
            "attempt": self.attempt,
            "succeeded": self.succeeded,
            "created_at": self.created_at.isoformat(),
            "correlation_id": self.correlation_id,
        }


# ─────────────────────────── Signature helpers ───────────────────────────────

MAX_CONSECUTIVE_FAILURES = 5
RETRY_DELAYS = [30, 120, 900, 3600]  # seconds: 30s, 2m, 15m, 1h


def _sign_payload(secret: str, timestamp: int, payload: bytes) -> str:
    """Compute HMAC-SHA256 signature: HEX(HMAC(secret, timestamp.payload))."""
    msg = f"{timestamp}.".encode() + payload
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _build_headers(secret: str, payload: bytes, correlation_id: str) -> dict:
    ts = int(time.time())
    sig = _sign_payload(secret, ts, payload)
    return {
        "Content-Type": "application/json",
        "X-FinMind-Signature": f"t={ts},v1={sig}",
        "X-FinMind-Correlation-Id": correlation_id,
        "User-Agent": "FinMind-Webhooks/1.0",
    }


# ─────────────────────────── Delivery engine ─────────────────────────────────

def _deliver(
    subscription: WebhookSubscription,
    event: str,
    payload_dict: dict,
    correlation_id: str,
    attempt: int = 1,
) -> bool:
    """Attempt to deliver a webhook. Returns True on success."""
    from .extensions import db as _db

    payload_bytes = json.dumps(payload_dict).encode()
    headers = _build_headers(subscription.secret, payload_bytes, correlation_id)
    delivery = WebhookDelivery(
        subscription_id=subscription.id,
        event=event,
        payload=json.dumps(payload_dict),
        attempt=attempt,
        correlation_id=correlation_id,
    )

    try:
        resp = requests.post(subscription.url, data=payload_bytes, headers=headers, timeout=10)
        delivery.status_code = resp.status_code
        delivery.succeeded = 200 <= resp.status_code < 300
    except Exception as exc:
        logger.warning("Webhook delivery failed for sub %s: %s", subscription.id, exc)
        delivery.succeeded = False

    _db.session.add(delivery)
    if delivery.succeeded:
        subscription.consecutive_failures = 0
    else:
        subscription.consecutive_failures = (subscription.consecutive_failures or 0) + 1
        if subscription.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            subscription.is_active = False
            logger.warning("Webhook subscription %s auto-disabled after %d failures", subscription.id, MAX_CONSECUTIVE_FAILURES)
    _db.session.commit()
    return delivery.succeeded


def _retry_worker(subscription_id: int, event: str, payload_dict: dict, correlation_id: str, attempt: int):
    """Background retry with exponential backoff."""
    from . import create_app as _create_app  # avoid circular import
    from .config import Settings

    app = _create_app(Settings())
    with app.app_context():
        from .extensions import db as _db
        sub = WebhookSubscription.query.get(subscription_id)
        if sub is None or not sub.is_active:
            return
        succeeded = _deliver(sub, event, payload_dict, correlation_id, attempt)
        if not succeeded and attempt <= len(RETRY_DELAYS):
            delay = RETRY_DELAYS[attempt - 1]
            timer = threading.Timer(
                delay, _retry_worker, args=(subscription_id, event, payload_dict, correlation_id, attempt + 1)
            )
            timer.daemon = True
            timer.start()


# ─────────────────────────── Public emit API ─────────────────────────────────

def emit(user_id: int, event: str, data: dict):
    """Emit a domain event to all matching active subscriptions for a user."""
    correlation_id = secrets.token_hex(16)
    payload = {
        "event": event,
        "data": data,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "correlation_id": correlation_id,
    }

    subscriptions = WebhookSubscription.query.filter_by(
        user_id=user_id, is_active=True
    ).all()

    for sub in subscriptions:
        if event not in sub.get_events():
            continue
        succeeded = _deliver(sub, event, payload, correlation_id, attempt=1)
        if not succeeded and sub.is_active:
            # Schedule retries in background
            timer = threading.Timer(
                RETRY_DELAYS[0],
                _retry_worker,
                args=(sub.id, event, payload, correlation_id, 2),
            )
            timer.daemon = True
            timer.start()
