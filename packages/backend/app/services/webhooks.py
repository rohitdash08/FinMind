"""Webhook delivery service with HMAC signing and retry logic."""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime

import requests

from ..extensions import db
from ..models import WebhookEndpoint, WebhookDelivery

logger = logging.getLogger("finmind.webhooks")

MAX_RETRIES = 3
RETRY_DELAYS = [10, 60, 300]  # seconds: 10s, 1m, 5m


def _sign_payload(payload: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature for the payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _deliver(delivery: WebhookDelivery, endpoint: WebhookEndpoint) -> bool:
    """Attempt to deliver a webhook. Returns True on success."""
    signature = _sign_payload(delivery.payload, endpoint.secret)
    headers = {
        "Content-Type": "application/json",
        "X-FinMind-Signature": f"sha256={signature}",
        "X-FinMind-Event": delivery.event_type,
        "X-FinMind-Delivery": str(delivery.id),
    }

    try:
        resp = requests.post(
            endpoint.url,
            data=delivery.payload,
            headers=headers,
            timeout=10,
        )
        delivery.response_status = resp.status_code
        delivery.success = 200 <= resp.status_code < 300
    except requests.RequestException as e:
        logger.warning("Webhook delivery failed endpoint=%s: %s", endpoint.id, e)
        delivery.response_status = None
        delivery.success = False

    delivery.attempts += 1
    delivery.last_attempt_at = datetime.utcnow()
    db.session.commit()
    return delivery.success


def emit_event(user_id: int, event_type: str, data: dict) -> list[int]:
    """Emit a webhook event to all matching endpoints for the user.

    Returns list of delivery IDs created.
    """
    endpoints = WebhookEndpoint.query.filter_by(
        user_id=user_id, is_active=True
    ).all()

    delivery_ids = []
    payload = json.dumps({
        "event": event_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "data": data,
    }, default=str)

    for ep in endpoints:
        # Check if endpoint subscribes to this event
        subscribed_events = json.loads(ep.events)
        if "*" not in subscribed_events and event_type not in subscribed_events:
            continue

        delivery = WebhookDelivery(
            endpoint_id=ep.id,
            event_type=event_type,
            payload=payload,
        )
        db.session.add(delivery)
        db.session.flush()
        delivery_ids.append(delivery.id)

        # First attempt (synchronous for simplicity; production would use a queue)
        _deliver(delivery, ep)

    db.session.commit()
    return delivery_ids


def retry_failed_deliveries() -> int:
    """Retry failed deliveries that haven't exceeded max retries.

    Returns count of retried deliveries.
    """
    failed = WebhookDelivery.query.filter(
        WebhookDelivery.success == False,
        WebhookDelivery.attempts < MAX_RETRIES,
    ).all()

    retried = 0
    for delivery in failed:
        endpoint = WebhookEndpoint.query.get(delivery.endpoint_id)
        if not endpoint or not endpoint.is_active:
            continue
        _deliver(delivery, endpoint)
        retried += 1

    return retried
