"""
Webhook Event System service (Issue #77).

Handles:
- Signed delivery (HMAC-SHA256, X-FinMind-Signature header)
- Retry logic (up to MAX_RETRIES attempts with exponential back-off)
- Delivery logging (WebhookDelivery rows)
- Event type validation

Supported event types
---------------------
expense.created      expense.updated      expense.deleted
bill.created         bill.updated         bill.due
reminder.sent        reminder.failed
goal.achieved        goal.created
budget.exceeded
user.registered

Public API
----------
dispatch_event(uid, event_type, payload)  → dispatch to all matching active webhooks
deliver_webhook(delivery_id)              → (re)attempt a single delivery
retry_failed_deliveries()                 → process all past-due retries
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from ..extensions import db
from .webhook_models_import import Webhook, WebhookDelivery

logger = logging.getLogger("finmind.webhooks")

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_RETRIES        = 3
RETRY_DELAYS       = [60, 300, 900]   # seconds: 1 min, 5 min, 15 min
DELIVERY_TIMEOUT_S = 10

VALID_EVENT_TYPES = frozenset([
    "expense.created", "expense.updated", "expense.deleted",
    "bill.created",    "bill.updated",    "bill.due",
    "reminder.sent",   "reminder.failed",
    "goal.achieved",   "goal.created",
    "budget.exceeded",
    "user.registered",
])

# ── Signing ───────────────────────────────────────────────────────────────────

def generate_secret() -> str:
    """Generate a cryptographically random webhook signing secret."""
    return secrets.token_hex(32)


def sign_payload(secret: str, body: bytes) -> str:
    """Return 'sha256=<hex>' HMAC signature for the given payload."""
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Verify the X-FinMind-Signature header value."""
    expected = sign_payload(secret, body)
    return hmac.compare_digest(expected, signature)


# ── Delivery ──────────────────────────────────────────────────────────────────

def _do_http_post(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
    """
    Attempt HTTP POST delivery.  Returns (status_code, response_body_truncated).
    Raises on network error.
    """
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=DELIVERY_TIMEOUT_S) as resp:
            return resp.status, resp.read(512).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(512).decode("utf-8", errors="replace")


def deliver_webhook(delivery_id: int) -> bool:
    """
    Attempt (or re-attempt) a webhook delivery.

    Updates the WebhookDelivery row with the outcome.
    Returns True on success, False on failure.
    """
    delivery = db.session.get(WebhookDelivery, delivery_id)
    if not delivery:
        logger.warning("Delivery %d not found", delivery_id)
        return False

    webhook = db.session.get(Webhook, delivery.webhook_id)
    if not webhook or not webhook.active:
        delivery.status = "failed"
        delivery.error_message = "webhook deactivated"
        db.session.commit()
        return False

    payload_bytes = delivery.payload.encode("utf-8") if isinstance(delivery.payload, str) else delivery.payload
    signature     = sign_payload(webhook.secret, payload_bytes)

    headers = {
        "Content-Type":          "application/json",
        "X-FinMind-Signature":   signature,
        "X-FinMind-Event":       delivery.event_type,
        "X-FinMind-Delivery-Id": str(delivery.id),
        "User-Agent":            "FinMind-Webhooks/1.0",
    }

    try:
        code, body = _do_http_post(webhook.url, payload_bytes, headers)
        success = 200 <= code < 300
    except Exception as exc:
        code, body = 0, ""
        success = False
        delivery.error_message = str(exc)[:500]

    delivery.response_code = code
    delivery.response_body = body[:500]
    delivery.attempt      += 1

    if success:
        delivery.status       = "success"
        delivery.delivered_at = datetime.now(timezone.utc)
        logger.info("Webhook delivered: delivery=%d event=%s code=%d",
                    delivery.id, delivery.event_type, code)
    else:
        attempt = delivery.attempt
        if attempt <= MAX_RETRIES:
            delay = RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]
            delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            delivery.status = "failed"
            logger.warning("Webhook delivery %d failed (attempt %d), retry in %ds",
                           delivery.id, attempt, delay)
        else:
            delivery.status        = "failed"
            delivery.next_retry_at = None
            logger.error("Webhook delivery %d permanently failed after %d attempts",
                         delivery.id, attempt)

    db.session.commit()
    return success


# ── Dispatch ──────────────────────────────────────────────────────────────────

def dispatch_event(uid: int, event_type: str, payload: dict[str, Any]) -> int:
    """
    Dispatch *event_type* to all active webhooks subscribed by *uid*.

    Creates a WebhookDelivery row for each matching webhook and attempts
    immediate delivery.  Returns the count of deliveries created.

    payload is augmented with metadata before delivery.
    """
    if event_type not in VALID_EVENT_TYPES:
        logger.warning("Unknown event type: %s", event_type)
        return 0

    full_payload = {
        "event":      event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data":       payload,
    }
    payload_json = json.dumps(full_payload)

    webhooks = (
        db.session.query(Webhook)
        .filter_by(user_id=uid, active=True)
        .all()
    )

    count = 0
    for wh in webhooks:
        try:
            subscribed = json.loads(wh.events) if isinstance(wh.events, str) else wh.events
        except (json.JSONDecodeError, TypeError):
            subscribed = []

        # Empty list means subscribe to all events
        if subscribed and event_type not in subscribed:
            continue

        delivery = WebhookDelivery(
            webhook_id=wh.id,
            event_type=event_type,
            payload=payload_json,
            status="pending",
        )
        db.session.add(delivery)
        db.session.flush()

        # Attempt immediate delivery
        deliver_webhook(delivery.id)
        count += 1

    if count == 0:
        db.session.rollback()
    else:
        db.session.commit()

    return count


def retry_failed_deliveries() -> int:
    """Process all WebhookDelivery rows that are past their next_retry_at time."""
    now = datetime.now(timezone.utc)
    due = (
        db.session.query(WebhookDelivery)
        .filter(
            WebhookDelivery.status == "failed",
            WebhookDelivery.next_retry_at.isnot(None),
            WebhookDelivery.next_retry_at <= now,
        )
        .all()
    )
    retried = 0
    for d in due:
        deliver_webhook(d.id)
        retried += 1
    logger.info("Retried %d failed webhook deliveries", retried)
    return retried
