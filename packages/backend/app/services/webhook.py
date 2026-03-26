"""
Signed Webhook Service

Provides secure webhook delivery with HMAC-SHA256 signatures and retry support.

Event Types:
    - expense.created  : Fired when a new expense is created
    - expense.updated  : Fired when an expense is modified
    - expense.deleted  : Fired when an expense is deleted
    - bill.due         : Fired when a bill is due
    - reminder.sent    : Fired when a reminder is sent

Signature Verification:
    Each webhook includes:
    - X-Webhook-Signature: HMAC-SHA256(timestamp + "." + payload, secret)
    - X-Webhook-Timestamp: Unix timestamp of when the webhook was sent

    Recipients should verify:
    1. Timestamp is recent (within 5 minutes) to prevent replay attacks
    2. Signature matches the expected HMAC value

Retry Policy:
    Failed deliveries (non-2xx or timeout) are retried up to 3 times
    with exponential backoff: 1min, 5min, 15min
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from threading import Thread
from typing import Any

import requests
from requests.exceptions import RequestException

from ..extensions import db
from ..models import WebhookDelivery, WebhookEvent, WebhookSubscription

logger = logging.getLogger("finmind.webhook")

MAX_RETRIES = 3
RETRY_DELAYS = [60, 300, 900]  # 1min, 5min, 15min in seconds
TIMEOUT_SECONDS = 10
SIGNATURE_TOLERANCE_SECONDS = 300  # 5 minutes


def _sign_payload(timestamp: str, payload: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    message = f"{timestamp}.{payload}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _build_headers(
    payload: str,
    secret: str,
    event_type: str,
    delivery_id: int | None = None,
) -> dict[str, str]:
    """Build signed webhook headers."""
    timestamp = str(int(time.time()))
    signature = _sign_payload(timestamp, payload, secret)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event_type,
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": f"sha256={signature}",
    }
    if delivery_id is not None:
        headers["X-Webhook-Delivery-ID"] = str(delivery_id)
    return headers


def _deliver_webhook_sync(
    url: str,
    payload: str,
    headers: dict[str, str],
) -> tuple[int, str]:
    """Send webhook and return (http_status, response_body)."""
    try:
        response = requests.post(
            url,
            data=payload,
            headers=headers,
            timeout=TIMEOUT_SECONDS,
        )
        return response.status_code, response.text[:1000]  # Truncate response
    except RequestException as exc:
        logger.warning("Webhook delivery failed: %s", exc)
        return 0, str(exc)[:500]


def _process_delivery(delivery_id: int, retry_count: int = 0) -> None:
    """Process a single webhook delivery with retry logic."""
    with db.session.session_scope() as session:
        delivery = session.get(WebhookDelivery, delivery_id)
        if delivery is None:
            return

        subscription = session.get(WebhookSubscription, delivery.subscription_id)
        if subscription is None or not subscription.active:
            delivery.status = "failed"
            session.commit()
            return

        # Try delivery
        delivery.attempts += 1
        delivery.last_attempt_at = datetime.now(timezone.utc)
        
        status_code, response_body = _deliver_webhook_sync(
            subscription.url,
            delivery.payload,
            _build_headers(
                delivery.payload,
                subscription.secret,
                delivery.event_type,
                delivery.id,
            ),
        )

        delivery.response_status = status_code
        delivery.response_body = response_body

        if 200 <= status_code < 300:
            delivery.status = "success"
            session.commit()
            logger.info(
                "Webhook delivered successfully delivery_id=%s event=%s",
                delivery_id,
                delivery.event_type,
            )
            return

        # Retry if needed
        if delivery.attempts < MAX_RETRIES:
            delay = RETRY_DELAYS[min(delivery.attempts - 1, len(RETRY_DELAYS) - 1)]
            delivery.status = "pending"
            session.commit()
            logger.info(
                "Webhook delivery failed (attempt %s/%s), retrying in %ss delivery_id=%s",
                delivery.attempts,
                MAX_RETRIES,
                delay,
                delivery_id,
            )
            _schedule_retry(delivery_id, delay)
        else:
            delivery.status = "failed"
            session.commit()
            logger.warning(
                "Webhook delivery failed permanently delivery_id=%s event=%s attempts=%s",
                delivery_id,
                delivery.event_type,
                delivery.attempts,
            )


def _schedule_retry(delivery_id: int, delay_seconds: int) -> None:
    """Schedule a retry for a failed webhook delivery."""
    timer = Thread(target=_delayed_retry, args=(delivery_id, delay_seconds), daemon=True)
    timer.start()


def _delayed_retry(delivery_id: int, delay_seconds: int) -> None:
    """Wait and then retry delivery."""
    time.sleep(delay_seconds)
    _process_delivery(delivery_id, retry_count=1)


def emit_webhook(
    user_id: int,
    event_type: WebhookEvent,
    data: dict[str, Any],
) -> None:
    """
    Emit a webhook event to all matching active subscriptions for a user.
    
    This method queues the webhook for delivery and returns immediately.
    Delivery is handled asynchronously with retry support.
    
    Args:
        user_id: The user whose subscriptions to notify
        event_type: The type of event (e.g., WebhookEvent.EXPENSE_CREATED)
        data: The event payload data
    """
    with db.session.session_scope() as session:
        subscriptions = (
            session.query(WebhookSubscription)
            .filter_by(user_id=user_id, active=True)
            .all()
        )

        matching = [
            sub for sub in subscriptions
            if event_type.value in json.loads(sub.events or "[]")
        ]

        if not matching:
            return

        payload = json.dumps(
            {
                "event": event_type.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            },
            default=str,
        )

        for sub in matching:
            delivery = WebhookDelivery(
                subscription_id=sub.id,
                event_type=event_type.value,
                payload=payload,
                status="pending",
            )
            session.add(delivery)
            session.flush()  # Get the delivery ID

            # Start async delivery
            delivery_id = delivery.id
            thread = Thread(
                target=_process_delivery,
                args=(delivery_id,),
                daemon=True,
            )
            thread.start()

        session.commit()


def verify_webhook_signature(
    payload: str,
    timestamp: str,
    signature: str,
    secret: str,
) -> bool:
    """
    Verify that a webhook signature is valid.
    
    Args:
        payload: The raw request body
        timestamp: The X-Webhook-Timestamp header value
        signature: The X-Webhook-Signature header value (with sha256= prefix)
        secret: The webhook subscription secret
    
    Returns:
        True if signature is valid and timestamp is recent
    """
    # Check timestamp freshness
    try:
        ts = int(timestamp)
        now = int(time.time())
        if abs(now - ts) > SIGNATURE_TOLERANCE_SECONDS:
            logger.warning("Webhook signature rejected: timestamp too old")
            return False
    except ValueError:
        logger.warning("Webhook signature rejected: invalid timestamp")
        return False

    # Verify signature
    expected = _sign_payload(timestamp, payload, secret)
    expected_full = f"sha256={expected}"
    if not hmac.compare_digest(expected_full, signature):
        logger.warning("Webhook signature rejected: mismatch")
        return False

    return True
