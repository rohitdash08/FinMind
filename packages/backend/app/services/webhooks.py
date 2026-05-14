import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from flask import current_app

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
    "reminder.scheduled",
    "reminder.sent",
}

MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 5


def generate_secret() -> str:
    return secrets.token_urlsafe(32)


def validate_target_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an http or https URL")
    if len(parsed.geturl()) > 500:
        raise ValueError("url is too long")
    return parsed.geturl()


def normalize_event_types(raw) -> list[str]:
    if raw is None:
        return ["*"]
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = raw
    else:
        raise ValueError("event_types must be a list")

    normalized = sorted({str(value).strip() for value in values if str(value).strip()})
    if not normalized or "*" in normalized:
        return ["*"]

    unsupported = [value for value in normalized if value not in EVENT_TYPES]
    if unsupported:
        raise ValueError(f"unsupported event type: {unsupported[0]}")
    return normalized


def endpoint_event_types(endpoint: WebhookEndpoint) -> list[str]:
    try:
        parsed = json.loads(endpoint.event_types)
    except json.JSONDecodeError:
        return ["*"]
    if not isinstance(parsed, list):
        return ["*"]
    return [str(value) for value in parsed]


def endpoint_accepts_event(endpoint: WebhookEndpoint, event_type: str) -> bool:
    configured = endpoint_event_types(endpoint)
    return "*" in configured or event_type in configured


def build_event_payload(event_type: str, data: dict) -> dict:
    return {
        "event": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def queue_webhook_event(user_id: int, event_type: str, data: dict) -> int:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported event type: {event_type}")

    endpoints = (
        db.session.query(WebhookEndpoint)
        .filter_by(user_id=user_id, active=True)
        .order_by(WebhookEndpoint.id)
        .all()
    )
    queued = 0
    for endpoint in endpoints:
        if not endpoint_accepts_event(endpoint, event_type):
            continue
        payload = build_event_payload(event_type, data)
        db.session.add(
            WebhookDelivery(
                endpoint_id=endpoint.id,
                user_id=user_id,
                event_type=event_type,
                payload_json=json.dumps(payload, separators=(",", ":"), default=str),
                status="pending",
                next_attempt_at=datetime.utcnow(),
            )
        )
        queued += 1
    if queued:
        db.session.commit()
    return queued


def publish_webhook_event(user_id: int, event_type: str, data: dict) -> None:
    try:
        queue_webhook_event(user_id=user_id, event_type=event_type, data=data)
    except Exception:
        current_app.logger.exception("Failed to queue webhook event %s", event_type)
        db.session.rollback()


def sign_payload(secret: str, timestamp: str, payload_json: str) -> str:
    signed = f"{timestamp}.{payload_json}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def deliver_webhook(
    endpoint: WebhookEndpoint, delivery: WebhookDelivery
) -> tuple[bool, str | None]:
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = sign_payload(endpoint.secret, timestamp, delivery.payload_json)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "FinMind-Webhooks/1.0",
        "X-FinMind-Event": delivery.event_type,
        "X-FinMind-Delivery": str(delivery.id),
        "X-FinMind-Timestamp": timestamp,
        "X-FinMind-Signature": signature,
    }
    try:
        response = requests.post(
            endpoint.url,
            data=delivery.payload_json.encode("utf-8"),
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return False, str(exc)[:500]

    if 200 <= response.status_code < 300:
        return True, None
    return False, f"HTTP {response.status_code}"[:500]


def process_due_deliveries(
    *, user_id: int | None = None, now: datetime | None = None, limit: int = 100
) -> dict:
    now = now or datetime.utcnow()
    query = (
        db.session.query(WebhookDelivery)
        .join(WebhookEndpoint, WebhookEndpoint.id == WebhookDelivery.endpoint_id)
        .filter(
            WebhookDelivery.status == "pending",
            WebhookDelivery.next_attempt_at <= now,
            WebhookEndpoint.active.is_(True),
        )
    )
    if user_id is not None:
        query = query.filter(WebhookDelivery.user_id == user_id)
    query = query.order_by(WebhookDelivery.created_at, WebhookDelivery.id).limit(limit)

    processed = delivered = failed = retrying = 0
    for delivery in query.all():
        processed += 1
        delivery.attempts += 1
        ok, error = deliver_webhook(delivery.endpoint, delivery)
        delivery.updated_at = now
        if ok:
            delivery.status = "delivered"
            delivery.delivered_at = now
            delivery.last_error = None
            delivered += 1
            continue

        delivery.last_error = error or "delivery failed"
        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "failed"
            failed += 1
        else:
            backoff_minutes = 2 ** (delivery.attempts - 1)
            delivery.next_attempt_at = now + timedelta(minutes=backoff_minutes)
            retrying += 1

    if processed:
        db.session.commit()
    return {
        "processed": processed,
        "delivered": delivered,
        "retrying": retrying,
        "failed": failed,
    }
