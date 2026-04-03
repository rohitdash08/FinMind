"""Webhook event system for FinMind.

Emits signed webhook deliveries for key application events.
Supports retry with exponential backoff and failure tracking.
"""
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

import requests
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..extensions import db

logger = logging.getLogger("finmind.webhooks")

# ---------------------------------------------------------------------------
# Event Types
# ---------------------------------------------------------------------------

class WebhookEventType(str, Enum):
    """Supported webhook event types."""
    EXPENSE_CREATED = "expense.created"
    EXPENSE_UPDATED = "expense.updated"
    EXPENSE_DELETED = "expense.deleted"
    BILL_CREATED = "bill.created"
    BILL_UPDATED = "bill.updated"
    BILL_PAID = "bill.paid"
    BUDGET_ALERT = "budget.alert"
    USER_REGISTERED = "user.registered"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class WebhookEndpoint(db.Model):
    """A registered webhook destination."""
    __tablename__ = "webhook_endpoints"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    secret = Column(String(128), nullable=False)  # whsec_... hex
    description = Column(String(255), nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    events = relationship("WebhookDelivery", back_populates="endpoint", cascade="all, delete-orphan")

    def sign_payload(self, payload: bytes, timestamp: int) -> str:
        """Compute HMAC-SHA256 signature: timestamp.payload"""
        message = f"{timestamp}.{payload.decode()}".encode()
        return hmac.new(self.secret.encode(), message, hashlib.sha256).hexdigest()


class WebhookDelivery(db.Model):
    """A single delivery attempt for a webhook event."""
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True)
    endpoint_id = Column(Integer, ForeignKey("webhook_endpoints.id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload = Column(Text, nullable=False)
    status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    success = Column(Boolean, default=False, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    last_attempt_at = Column(DateTime, nullable=True)
    next_retry_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    endpoint = relationship("WebhookEndpoint", back_populates="events")


# ---------------------------------------------------------------------------
# Retry Configuration
# ---------------------------------------------------------------------------

MAX_RETRIES = 5
RETRY_DELAYS = [10, 60, 300, 1800, 7200]  # seconds: 10s, 1m, 5m, 30m, 2h
DELIVERY_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------

def register_endpoint(user_id: int, url: str, description: str | None = None) -> WebhookEndpoint:
    """Create a new webhook endpoint for a user."""
    import secrets
    secret = f"whsec_{secrets.token_hex(32)}"
    endpoint = WebhookEndpoint(
        user_id=user_id,
        url=url,
        secret=secret,
        description=description,
    )
    db.session.add(endpoint)
    db.session.commit()
    logger.info("Webhook endpoint registered: user=%s url=%s", user_id, url)
    return endpoint


def delete_endpoint(user_id: int, endpoint_id: int) -> bool:
    """Remove a webhook endpoint."""
    ep = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=user_id).first()
    if not ep:
        return False
    db.session.delete(ep)
    db.session.commit()
    return True


def emit_event(event_type: WebhookEventType, data: dict, user_id: int | None = None):
    """Queue a webhook event for delivery to matching endpoints."""
    payload = json.dumps({
        "id": str(uuid.uuid4()),
        "type": event_type.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }, sort_keys=True)

    query = WebhookEndpoint.query.filter_by(active=True)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)

    for endpoint in query.all():
        delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            event_type=event_type.value,
            payload=payload,
        )
        db.session.add(delivery)

        # Attempt immediate delivery
        _deliver(delivery, endpoint)

    db.session.commit()


def process_retries():
    """Process pending retries. Call periodically (e.g., via cron)."""
    now = datetime.now(timezone.utc)
    pending = WebhookDelivery.query.filter(
        WebhookDelivery.success == False,  # noqa: E712
        WebhookDelivery.attempts <= MAX_RETRIES,
        WebhookDelivery.next_retry_at <= now,
    ).all()

    for delivery in pending:
        endpoint = WebhookEndpoint.query.get(delivery.endpoint_id)
        if endpoint and endpoint.active:
            _deliver(delivery, endpoint)

    db.session.commit()
    return len(pending)


def _deliver(delivery: WebhookDelivery, endpoint: WebhookEndpoint):
    """Execute a single delivery attempt."""
    timestamp = int(time.time())
    signature = endpoint.sign_payload(delivery.payload.encode(), timestamp)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-ID": str(delivery.id),
        "X-Webhook-Signature": f"t={timestamp},v1={signature}",
        "X-Webhook-Event": delivery.event_type,
    }

    delivery.attempts += 1
    delivery.last_attempt_at = datetime.now(timezone.utc)

    try:
        resp = requests.post(
            endpoint.url,
            data=delivery.payload,
            headers=headers,
            timeout=DELIVERY_TIMEOUT,
        )
        delivery.status_code = resp.status_code
        delivery.response_body = resp.text[:1000]  # Truncate large responses
        delivery.success = 200 <= resp.status_code < 300

        if delivery.success:
            logger.info("Webhook delivered: id=%s status=%s", delivery.id, resp.status_code)
        else:
            logger.warning("Webhook failed: id=%s status=%s", delivery.id, resp.status_code)

    except requests.RequestException as exc:
        delivery.status_code = 0
        delivery.response_body = str(exc)[:1000]
        delivery.success = False
        logger.warning("Webhook error: id=%s error=%s", delivery.id, exc)

    # Schedule retry if failed and retries remain
    if not delivery.success and delivery.attempts <= MAX_RETRIES:
        delay = RETRY_DELAYS[min(delivery.attempts - 1, len(RETRY_DELAYS) - 1)]
        delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
