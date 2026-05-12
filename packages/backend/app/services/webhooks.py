"""Webhook event system with signed delivery and retry."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime
from typing import Any

from ..extensions import db, redis_client
import logging
import requests

logger = logging.getLogger("finmind.webhooks")

WEBHOOK_SECRET_KEY = "webhooks:secret"
WEBHOOK_QUEUE_KEY = "webhooks:queue"
MAX_RETRIES = 3
RETRY_DELAYS = [10, 60, 300]  # seconds

# Supported event types
EVENT_TYPES = [
    "expense.created",
    "expense.updated",
    "expense.deleted",
    "bill.created",
    "bill.due",
    "goal.achieved",
    "login.anomaly",
]


class WebhookSubscription(db.Model):
    __tablename__ = "webhook_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    secret = db.Column(db.String(255), nullable=False)
    events = db.Column(db.String(500), nullable=False)  # comma-separated
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


def sign_payload(payload: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return hmac.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


def emit_event(user_id: int, event_type: str, data: dict[str, Any]):
    """Emit a webhook event to all matching subscriptions."""
    subscriptions = (
        db.session.query(WebhookSubscription)
        .filter_by(user_id=user_id, active=True)
        .all()
    )

    for sub in subscriptions:
        if event_type not in sub.events.split(","):
            continue

        delivery_id = str(uuid.uuid4())
        payload = json.dumps({
            "id": delivery_id,
            "event": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        })

        # Queue for delivery
        job = json.dumps({
            "delivery_id": delivery_id,
            "url": sub.url,
            "secret": sub.secret,
            "payload": payload,
            "attempt": 0,
        })
        redis_client.lpush(WEBHOOK_QUEUE_KEY, job)
        logger.info("Webhook queued: event=%s delivery=%s", event_type, delivery_id)


def deliver_next() -> bool:
    """Deliver the next webhook in queue. Returns True if delivered."""
    raw = redis_client.rpop(WEBHOOK_QUEUE_KEY)
    if not raw:
        return False

    job = json.loads(raw)
    delivery_id = job["delivery_id"]
    url = job["url"]
    secret = job["secret"]
    payload = job["payload"]
    attempt = job["attempt"]

    signature = hmac.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Delivery": delivery_id,
        "User-Agent": "FinMind-Webhooks/1.0",
    }

    try:
        resp = requests.post(url, data=payload, headers=headers, timeout=10)
        if resp.status_code < 300:
            logger.info("Webhook delivered: %s -> %s", delivery_id, url)
            return True
        raise Exception(f"HTTP {resp.status_code}")
    except Exception as e:
        attempt += 1
        if attempt < MAX_RETRIES:
            job["attempt"] = attempt
            # Re-queue with delay info
            redis_client.lpush(WEBHOOK_QUEUE_KEY, json.dumps(job))
            logger.warning(
                "Webhook failed, retry %d/%d: %s error=%s",
                attempt, MAX_RETRIES, delivery_id, str(e),
            )
        else:
            logger.error("Webhook exhausted retries: %s error=%s", delivery_id, str(e))
        return True
