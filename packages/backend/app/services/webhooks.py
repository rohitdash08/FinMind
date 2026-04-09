from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any

import requests
from flask import current_app

from ..extensions import db
from ..models import (
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEvent,
    WebhookSubscription,
)
from ..observability import track_webhook_delivery, track_webhook_event

logger = logging.getLogger("finmind.webhooks")

SUPPORTED_WEBHOOK_EVENTS = {
    "expense.created",
    "expense.updated",
    "expense.deleted",
    "bill.created",
    "bill.paid",
    "reminder.created",
    "reminder.sent",
}

MAX_ATTEMPTS = 5
RETRY_DELAYS_SECONDS = [60, 300, 900, 3600]
CONNECT_TIMEOUT_SECONDS = 3
READ_TIMEOUT_SECONDS = 7


def build_event_payload(
    *,
    event_id: int,
    event_type: str,
    user_id: int,
    resource_type: str,
    resource_id: int | None,
    occurred_at: datetime,
    data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": f"evt_{event_id}",
        "type": event_type,
        "occurred_at": occurred_at.isoformat() + "Z",
        "user_id": user_id,
        "resource": {"type": resource_type, "id": resource_id},
        "data": data,
    }


def serialize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def sign_payload(secret: str, timestamp: str, raw_body: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.{raw_body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def build_headers(
    *,
    subscription: WebhookSubscription,
    event: WebhookEvent,
    delivery: WebhookDelivery,
    raw_body: str,
    timestamp: str,
) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "User-Agent": "FinMind-Webhooks/1.0",
        "X-FinMind-Event": event.event_type,
        "X-FinMind-Event-Id": str(event.id),
        "X-FinMind-Delivery-Id": str(delivery.id),
        "X-FinMind-Timestamp": timestamp,
        "X-FinMind-Signature": sign_payload(subscription.secret, timestamp, raw_body),
    }


def emit_event(
    *,
    user_id: int,
    event_type: str,
    resource_type: str,
    resource_id: int | None,
    data: dict[str, Any],
) -> WebhookEvent:
    if event_type not in SUPPORTED_WEBHOOK_EVENTS:
        raise ValueError(f"unsupported webhook event: {event_type}")

    occurred_at = datetime.utcnow()
    event = WebhookEvent(
        user_id=user_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        payload_json={},
        occurred_at=occurred_at,
    )
    db.session.add(event)
    db.session.flush()

    payload = build_event_payload(
        event_id=event.id,
        event_type=event_type,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        occurred_at=occurred_at,
        data=data,
    )
    event.payload_json = payload

    subscriptions = (
        db.session.query(WebhookSubscription)
        .filter_by(user_id=user_id, active=True)
        .all()
    )
    for subscription in subscriptions:
        subscribed_events = subscription.subscribed_events or []
        if event_type not in subscribed_events:
            continue
        db.session.add(
            WebhookDelivery(
                event_id=event.id,
                subscription_id=subscription.id,
                status=WebhookDeliveryStatus.PENDING.value,
                next_attempt_at=occurred_at,
            )
        )
    track_webhook_event(event_type)
    return event


def attempt_delivery(delivery: WebhookDelivery) -> bool:
    event = db.session.get(WebhookEvent, delivery.event_id)
    subscription = db.session.get(WebhookSubscription, delivery.subscription_id)
    if not event or not subscription or not subscription.active:
        delivery.status = WebhookDeliveryStatus.FAILED.value
        delivery.last_error = "missing event/subscription or inactive subscription"
        delivery.updated_at = datetime.utcnow()
        return False

    raw_body = serialize_payload(event.payload_json)
    timestamp = str(int(time.time()))
    headers = build_headers(
        subscription=subscription,
        event=event,
        delivery=delivery,
        raw_body=raw_body,
        timestamp=timestamp,
    )

    start = time.perf_counter()
    response_code = None
    error = None
    success = False
    try:
        response = requests.post(
            subscription.target_url,
            data=raw_body,
            headers=headers,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        )
        response_code = response.status_code
        success = 200 <= response.status_code < 300
    except requests.RequestException as exc:
        error = str(exc)
    duration_ms = int((time.perf_counter() - start) * 1000)

    delivery.attempt_count += 1
    delivery.last_attempt_at = datetime.utcnow()
    delivery.last_duration_ms = duration_ms
    delivery.last_response_code = response_code
    delivery.last_error = error

    if success:
        delivery.status = WebhookDeliveryStatus.SUCCEEDED.value
        delivery.updated_at = datetime.utcnow()
        subscription.last_success_at = datetime.utcnow()
        subscription.failure_count = 0
        track_webhook_delivery(event.event_type, response_code, "success", duration_ms)
        return True

    subscription.last_failure_at = datetime.utcnow()
    subscription.failure_count += 1
    next_attempt_at = compute_next_attempt(delivery.attempt_count, datetime.utcnow())
    if next_attempt_at is None:
        delivery.status = WebhookDeliveryStatus.FAILED.value
        result = "failed"
    else:
        delivery.status = WebhookDeliveryStatus.RETRY_SCHEDULED.value
        delivery.next_attempt_at = next_attempt_at
        result = "retry"
    delivery.updated_at = datetime.utcnow()
    track_webhook_delivery(event.event_type, response_code, result, duration_ms)
    return False


def compute_next_attempt(attempt_count: int, now: datetime) -> datetime | None:
    if attempt_count >= MAX_ATTEMPTS:
        return None
    delay = RETRY_DELAYS_SECONDS[min(attempt_count - 1, len(RETRY_DELAYS_SECONDS) - 1)]
    return now + timedelta(seconds=delay)


def run_pending_deliveries(limit: int = 100) -> dict[str, int]:
    now = datetime.utcnow()
    items = (
        db.session.query(WebhookDelivery)
        .filter(
            WebhookDelivery.status.in_(
                [
                    WebhookDeliveryStatus.PENDING.value,
                    WebhookDeliveryStatus.RETRY_SCHEDULED.value,
                ]
            ),
            WebhookDelivery.next_attempt_at <= now,
        )
        .order_by(WebhookDelivery.next_attempt_at.asc(), WebhookDelivery.id.asc())
        .limit(limit)
        .all()
    )
    processed = succeeded = retried = failed = 0
    for delivery in items:
        delivery.status = WebhookDeliveryStatus.IN_PROGRESS.value
        db.session.flush()
        processed += 1
        ok = attempt_delivery(delivery)
        if ok:
            succeeded += 1
        elif delivery.status == WebhookDeliveryStatus.RETRY_SCHEDULED.value:
            retried += 1
        else:
            failed += 1
    db.session.commit()
    logger.info(
        "Webhook runner processed=%s succeeded=%s retried=%s failed=%s",
        processed,
        succeeded,
        retried,
        failed,
    )
    return {
        "processed": processed,
        "succeeded": succeeded,
        "retried": retried,
        "failed": failed,
    }
