"""Webhook event system: signed delivery, retry, failure handling.

Events emitted by the backend (see docs/webhooks.md):
    expense.created, expense.updated, expense.deleted,
    bill.created, bill.paid,
    reminder.created.

Subscribers register a target URL plus a secret. Each delivery is signed
with HMAC-SHA256 over the raw JSON body and sent in the
``X-FinMind-Signature`` header (``sha256=<hex>``). Failed attempts are
retried with exponential backoff up to ``MAX_ATTEMPTS`` and then marked
``FAILED``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Iterable

import requests

from ..extensions import db
from ..models import Webhook, WebhookDelivery, WebhookDeliveryStatus

logger = logging.getLogger("finmind.webhooks")

EVENT_TYPES: tuple[str, ...] = (
    "expense.created",
    "expense.updated",
    "expense.deleted",
    "bill.created",
    "bill.paid",
    "reminder.created",
)

MAX_ATTEMPTS = 5
REQUEST_TIMEOUT_SECONDS = 5
SIGNATURE_HEADER = "X-FinMind-Signature"
EVENT_HEADER = "X-FinMind-Event"
DELIVERY_HEADER = "X-FinMind-Delivery"
TIMESTAMP_HEADER = "X-FinMind-Timestamp"


def generate_secret() -> str:
    return secrets.token_hex(32)


def sign_payload(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(secret, body), signature or "")


def _matches(subscription: str, event_type: str) -> bool:
    subs = [s.strip() for s in (subscription or "").split(",") if s.strip()]
    if not subs or "*" in subs:
        return True
    if event_type in subs:
        return True
    namespace = event_type.split(".", 1)[0] + ".*"
    return namespace in subs


def _backoff(attempts: int) -> timedelta:
    # 30s, 1m, 5m, 15m, 30m
    schedule = [30, 60, 300, 900, 1800]
    idx = min(max(attempts - 1, 0), len(schedule) - 1)
    return timedelta(seconds=schedule[idx])


def emit_event(user_id: int, event_type: str, data: dict[str, Any]) -> int:
    """Queue webhook deliveries for matching subscribers and try once.

    Returns the number of deliveries created. Failures are silently retried
    later via :func:`process_pending`; emission never raises.
    """
    try:
        hooks: Iterable[Webhook] = (
            db.session.query(Webhook)
            .filter_by(user_id=user_id, active=True)
            .all()
        )
    except Exception:
        logger.exception("webhook lookup failed user=%s event=%s", user_id, event_type)
        return 0

    created = 0
    for hook in hooks:
        if not _matches(hook.events, event_type):
            continue
        envelope = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "data": data,
        }
        delivery = WebhookDelivery(
            webhook_id=hook.id,
            event_type=event_type,
            payload=json.dumps(envelope, separators=(",", ":"), default=str),
            status=WebhookDeliveryStatus.PENDING.value,
            next_attempt_at=datetime.utcnow(),
        )
        db.session.add(delivery)
        db.session.flush()
        _attempt_delivery(hook, delivery)
        created += 1
    if created:
        db.session.commit()
    return created


def _attempt_delivery(hook: Webhook, delivery: WebhookDelivery) -> bool:
    body = delivery.payload.encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        EVENT_HEADER: delivery.event_type,
        DELIVERY_HEADER: str(delivery.id),
        TIMESTAMP_HEADER: str(int(datetime.utcnow().timestamp())),
        SIGNATURE_HEADER: sign_payload(hook.secret, body),
    }
    delivery.attempts = (delivery.attempts or 0) + 1
    try:
        response = requests.post(
            hook.url, data=body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
        delivery.last_status_code = response.status_code
        if 200 <= response.status_code < 300:
            delivery.status = WebhookDeliveryStatus.SUCCESS.value
            delivery.delivered_at = datetime.utcnow()
            delivery.last_error = None
            logger.info(
                "webhook delivered id=%s url=%s event=%s status=%s",
                delivery.id, hook.url, delivery.event_type, response.status_code,
            )
            return True
        delivery.last_error = f"HTTP {response.status_code}"
    except requests.RequestException as exc:
        delivery.last_status_code = None
        delivery.last_error = str(exc)[:500]
    except Exception as exc:  # pragma: no cover
        delivery.last_status_code = None
        delivery.last_error = f"unexpected: {exc}"[:500]

    if delivery.attempts >= MAX_ATTEMPTS:
        delivery.status = WebhookDeliveryStatus.FAILED.value
        logger.warning(
            "webhook permanently failed id=%s url=%s event=%s error=%s",
            delivery.id, hook.url, delivery.event_type, delivery.last_error,
        )
    else:
        delivery.status = WebhookDeliveryStatus.PENDING.value
        delivery.next_attempt_at = datetime.utcnow() + _backoff(delivery.attempts)
        logger.info(
            "webhook retry scheduled id=%s next=%s attempts=%s",
            delivery.id, delivery.next_attempt_at, delivery.attempts,
        )
    return False


def process_pending(limit: int = 50) -> dict[str, int]:
    """Retry deliveries whose ``next_attempt_at`` has elapsed."""
    now = datetime.utcnow()
    pending = (
        db.session.query(WebhookDelivery)
        .filter(
            WebhookDelivery.status == WebhookDeliveryStatus.PENDING.value,
            WebhookDelivery.next_attempt_at <= now,
        )
        .order_by(WebhookDelivery.next_attempt_at)
        .limit(limit)
        .all()
    )
    delivered = 0
    failed = 0
    for delivery in pending:
        hook = db.session.get(Webhook, delivery.webhook_id)
        if not hook or not hook.active:
            delivery.status = WebhookDeliveryStatus.FAILED.value
            delivery.last_error = "webhook removed or inactive"
            failed += 1
            continue
        if _attempt_delivery(hook, delivery):
            delivered += 1
        elif delivery.status == WebhookDeliveryStatus.FAILED.value:
            failed += 1
    db.session.commit()
    return {"processed": len(pending), "delivered": delivered, "failed": failed}
