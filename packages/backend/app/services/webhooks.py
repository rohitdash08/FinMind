import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from typing import Any

import requests

from ..extensions import db
from ..models import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger("finmind.webhooks")

EVENT_TYPES = {
    "expense.created",
    "expense.updated",
    "expense.deleted",
    "bill.created",
    "bill.paid",
    "reminder.created",
    "reminder.sent",
}

MAX_DELIVERY_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 5


def emit_webhook_event(user_id: int, event_type: str, data: dict[str, Any]) -> None:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported webhook event type: {event_type}")

    endpoints = (
        db.session.query(WebhookEndpoint).filter_by(user_id=user_id, active=True).all()
    )
    for endpoint in endpoints:
        if not _endpoint_matches(endpoint, event_type):
            continue
        delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            user_id=user_id,
            event_type=event_type,
            payload_json=_build_payload(event_type, data),
        )
        db.session.add(delivery)
        db.session.flush()
        attempt_delivery(delivery, endpoint)
    db.session.commit()


def retry_pending_deliveries(user_id: int | None = None) -> int:
    now = datetime.utcnow()
    query = db.session.query(WebhookDelivery).filter(
        WebhookDelivery.status == "pending",
        WebhookDelivery.attempts < MAX_DELIVERY_ATTEMPTS,
        (WebhookDelivery.next_retry_at.is_(None))
        | (WebhookDelivery.next_retry_at <= now),
    )
    if user_id is not None:
        query = query.filter_by(user_id=user_id)

    retried = 0
    for delivery in query.all():
        endpoint = db.session.get(WebhookEndpoint, delivery.endpoint_id)
        if not endpoint or not endpoint.active:
            continue
        attempt_delivery(delivery, endpoint)
        retried += 1
    db.session.commit()
    return retried


def attempt_delivery(delivery: WebhookDelivery, endpoint: WebhookEndpoint) -> None:
    payload = delivery.payload_json
    signature = _sign_payload(endpoint.secret, payload)
    headers = {
        "Content-Type": "application/json",
        "X-FinMind-Event": delivery.event_type,
        "X-FinMind-Delivery": str(delivery.id),
        "X-FinMind-Signature": f"sha256={signature}",
    }
    delivery.attempts += 1
    try:
        response = requests.post(
            endpoint.url,
            data=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if 200 <= response.status_code < 300:
            delivery.status = "delivered"
            delivery.delivered_at = datetime.utcnow()
            delivery.last_error = None
            delivery.next_retry_at = None
            return
        delivery.last_error = f"HTTP {response.status_code}"
    except requests.RequestException as exc:
        delivery.last_error = str(exc)[:500]

    if delivery.attempts >= MAX_DELIVERY_ATTEMPTS:
        delivery.status = "failed"
        delivery.next_retry_at = None
    else:
        delay_seconds = 2 ** (delivery.attempts - 1) * 60
        delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
    logger.warning(
        "Webhook delivery failed id=%s endpoint=%s attempts=%s error=%s",
        delivery.id,
        endpoint.id,
        delivery.attempts,
        delivery.last_error,
    )


def normalize_event_types(raw: Any) -> str | None:
    if raw in (None, "", "*"):
        return "*"
    if not isinstance(raw, list):
        return None
    values = sorted({str(item).strip() for item in raw if str(item).strip()})
    if not values:
        return "*"
    if any(value not in EVENT_TYPES for value in values):
        return None
    return ",".join(values)


def _endpoint_matches(endpoint: WebhookEndpoint, event_type: str) -> bool:
    configured = endpoint.event_types or "*"
    if configured == "*":
        return True
    return event_type in {item.strip() for item in configured.split(",")}


def _build_payload(event_type: str, data: dict[str, Any]) -> str:
    return json.dumps(
        {
            "event": event_type,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "data": data,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _sign_payload(secret: str, payload: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
