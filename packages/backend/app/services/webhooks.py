"""Webhook event dispatcher with HMAC-SHA256 signing and retry logic.

Handles:
  - Event emission to registered webhooks
  - HMAC-SHA256 signed payloads
  - Exponential-backoff retries (1s, 5s, 30s, 2min, 10min)
  - Automatic disable after 10 consecutive failures
"""

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import requests as http_requests

from ..extensions import db
from ..models import Webhook, WebhookDelivery, DeliveryStatus

logger = logging.getLogger("finmind.webhooks")

# Retry backoff schedule in seconds
RETRY_DELAYS = [1, 5, 30, 120, 600]

# Auto-disable threshold
MAX_CONSECUTIVE_FAILURES = 10


def sign_payload(secret: str, payload_bytes: bytes) -> str:
    """Generate HMAC-SHA256 signature for the payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def verify_signature(secret: str, payload_bytes: bytes, signature: str) -> bool:
    """Verify an HMAC-SHA256 signature."""
    expected = sign_payload(secret, payload_bytes)
    return hmac.compare_digest(expected, signature)


def emit_event(user_id: int, event_type: str, data: dict[str, Any]) -> list[int]:
    """Dispatch an event to all matching active webhooks for a user.

    Returns a list of WebhookDelivery IDs created.
    """
    webhooks = (
        db.session.query(Webhook)
        .filter_by(user_id=user_id, active=True)
        .all()
    )

    delivery_ids: list[int] = []
    for wh in webhooks:
        subscribed = json.loads(wh.events) if wh.events else []
        if "*" not in subscribed and event_type not in subscribed:
            continue

        delivery = _create_delivery(wh, event_type, data)
        delivery_ids.append(delivery.id)
        _attempt_delivery(wh, delivery)

    return delivery_ids


def retry_pending_deliveries() -> int:
    """Process deliveries that are due for retry. Returns count processed."""
    now = datetime.utcnow()
    pending = (
        db.session.query(WebhookDelivery)
        .filter(
            WebhookDelivery.status == DeliveryStatus.PENDING.value,
            WebhookDelivery.next_retry_at <= now,
            WebhookDelivery.attempts < WebhookDelivery.max_retries,
        )
        .limit(50)
        .all()
    )

    count = 0
    for delivery in pending:
        wh = db.session.get(Webhook, delivery.webhook_id)
        if not wh or not wh.active:
            delivery.status = DeliveryStatus.DEAD.value
            db.session.commit()
            continue
        _attempt_delivery(wh, delivery)
        count += 1

    return count


def _create_delivery(
    wh: Webhook, event_type: str, data: dict[str, Any]
) -> WebhookDelivery:
    """Create a WebhookDelivery record."""
    delivery_id = str(uuid.uuid4())
    payload = json.dumps(
        {
            "event_type": event_type,
            "delivery_id": delivery_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": data,
        },
        default=str,
    )

    delivery = WebhookDelivery(
        webhook_id=wh.id,
        delivery_id=delivery_id,
        event_type=event_type,
        payload=payload,
        status=DeliveryStatus.PENDING.value,
        attempts=0,
        max_retries=5,
    )
    db.session.add(delivery)
    db.session.commit()
    return delivery


def _attempt_delivery(wh: Webhook, delivery: WebhookDelivery) -> bool:
    """Send the webhook payload. Returns True on success."""
    payload_bytes = delivery.payload.encode("utf-8")
    signature = sign_payload(wh.secret, payload_bytes)

    headers = {
        "Content-Type": "application/json",
        "X-FinMind-Signature": f"sha256={signature}",
        "X-FinMind-Delivery": delivery.delivery_id,
        "X-FinMind-Event": delivery.event_type,
    }

    delivery.attempts += 1
    start = time.monotonic()

    try:
        resp = http_requests.post(
            wh.url,
            data=payload_bytes,
            headers=headers,
            timeout=10,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        delivery.last_status_code = resp.status_code
        delivery.last_response_ms = elapsed_ms

        if 200 <= resp.status_code < 300:
            delivery.status = DeliveryStatus.SUCCESS.value
            delivery.completed_at = datetime.utcnow()
            wh.failure_count = 0
            db.session.commit()
            logger.info(
                "Webhook delivered id=%s event=%s status=%s ms=%s",
                delivery.delivery_id, delivery.event_type,
                resp.status_code, elapsed_ms,
            )
            return True
        else:
            delivery.last_error = f"HTTP {resp.status_code}: {resp.text[:500]}"
            logger.warning(
                "Webhook delivery failed id=%s status=%s",
                delivery.delivery_id, resp.status_code,
            )

    except http_requests.RequestException as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        delivery.last_response_ms = elapsed_ms
        delivery.last_error = str(exc)[:500]
        logger.warning(
            "Webhook delivery error id=%s error=%s",
            delivery.delivery_id, str(exc)[:200],
        )

    # Handle failure: schedule retry or mark dead
    _handle_failure(wh, delivery)
    return False


def _handle_failure(wh: Webhook, delivery: WebhookDelivery):
    """Schedule a retry or mark as dead."""
    wh.failure_count += 1

    if delivery.attempts >= delivery.max_retries:
        delivery.status = DeliveryStatus.DEAD.value
        delivery.completed_at = datetime.utcnow()
        logger.warning(
            "Webhook delivery dead id=%s after %s attempts",
            delivery.delivery_id, delivery.attempts,
        )
    else:
        delay_idx = min(delivery.attempts - 1, len(RETRY_DELAYS) - 1)
        delay = RETRY_DELAYS[delay_idx]
        delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
        logger.info(
            "Webhook delivery retry scheduled id=%s attempt=%s delay=%ss",
            delivery.delivery_id, delivery.attempts, delay,
        )

    # Auto-disable webhook after too many consecutive failures
    if wh.failure_count >= MAX_CONSECUTIVE_FAILURES:
        wh.active = False
        logger.warning(
            "Webhook auto-disabled id=%s after %s consecutive failures",
            wh.id, wh.failure_count,
        )

    db.session.commit()
