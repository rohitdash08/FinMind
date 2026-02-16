"""Webhook Event System: domain event emission, signed delivery,
retry & dead-letter."""

import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta

import requests as http_requests

from ..extensions import db, redis_client
from ..models import WebhookDeliveryLog, WebhookEvent, WebhookSubscription

logger = logging.getLogger("finmind.webhooks")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEBHOOK_QUEUE_KEY = "webhook:event_queue"
MAX_ATTEMPTS = 5
RETRY_BACKOFF_SECONDS = [30, 120, 900, 3600, 14400]  # 30s, 2m, 15m, 1h, 4h
AUTO_DISABLE_THRESHOLD = 10
DELIVERY_TIMEOUT_SECONDS = 10

SUPPORTED_EVENT_TYPES = [
    "expense.created",
    "expense.updated",
    "expense.deleted",
    "bill.created",
    "bill.paid",
    "reminder.triggered",
    "budget.suggestion_generated",
]

# ---------------------------------------------------------------------------
# Signature helpers
# ---------------------------------------------------------------------------


def generate_secret() -> str:
    """Generate a 32-byte hex-encoded HMAC secret."""
    return secrets.token_hex(32)


def compute_signature(secret: str, timestamp: str, payload: str) -> str:
    """HMAC-SHA256 signature over ``timestamp.payload``."""
    message = f"{timestamp}.{payload}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------------
# Domain event emission
# ---------------------------------------------------------------------------


def emit_event(
    user_id: int,
    event_type: str,
    payload: dict,
    event_version: str = "1",
):
    """Create a domain event row and enqueue it for async delivery."""
    correlation_id = str(uuid.uuid4())
    event = WebhookEvent(
        user_id=user_id,
        event_type=event_type,
        event_version=event_version,
        payload=json.dumps(payload),
        correlation_id=correlation_id,
    )
    db.session.add(event)
    db.session.commit()

    try:
        redis_client.lpush(WEBHOOK_QUEUE_KEY, event.id)
    except Exception:
        logger.warning("Failed to enqueue webhook event id=%s", event.id)

    logger.info(
        "Emitted event type=%s corr=%s user=%s",
        event_type,
        correlation_id,
        user_id,
    )
    return event


# ---------------------------------------------------------------------------
# Queue worker — processes new events
# ---------------------------------------------------------------------------


def process_event_queue():
    """Pop events from Redis queue and dispatch to matching subscribers."""
    while True:
        raw = redis_client.rpop(WEBHOOK_QUEUE_KEY)
        if not raw:
            break
        try:
            event_id = int(raw)
            _dispatch_event(event_id)
        except Exception:
            logger.exception("Failed to process webhook event id=%s", raw)


def _dispatch_event(event_id: int):
    """Deliver a single event to all matching, active subscriptions."""
    event = db.session.get(WebhookEvent, event_id)
    if not event:
        return

    subscriptions = (
        db.session.query(WebhookSubscription)
        .filter(
            WebhookSubscription.user_id == event.user_id,
            WebhookSubscription.active.is_(True),
        )
        .all()
    )

    for sub in subscriptions:
        try:
            sub_events = json.loads(sub.event_types)
        except (json.JSONDecodeError, TypeError):
            continue

        if event.event_type not in sub_events and "*" not in sub_events:
            continue

        _attempt_delivery(event, sub)


# ---------------------------------------------------------------------------
# Retry worker — retries pending deliveries whose backoff has elapsed
# ---------------------------------------------------------------------------


def process_retries():
    """Retry deliveries that have reached their next_retry_at."""
    now = datetime.utcnow()
    logs = (
        db.session.query(WebhookDeliveryLog)
        .filter(
            WebhookDeliveryLog.status == "pending",
            WebhookDeliveryLog.next_retry_at.isnot(None),
            WebhookDeliveryLog.next_retry_at <= now,
        )
        .all()
    )

    for log in logs:
        event = db.session.get(WebhookEvent, log.event_id)
        sub = db.session.get(WebhookSubscription, log.subscription_id)

        if not event or not sub or not sub.active:
            log.status = "dead_letter"
            db.session.commit()
            continue

        log.attempt += 1
        log.next_retry_at = None
        _do_deliver(event, sub, log)


# ---------------------------------------------------------------------------
# HTTP delivery
# ---------------------------------------------------------------------------


def _attempt_delivery(event: WebhookEvent, sub: WebhookSubscription):
    """First attempt — create a delivery log row and POST."""
    log = WebhookDeliveryLog(
        event_id=event.id,
        subscription_id=sub.id,
        attempt=1,
        status="pending",
    )
    db.session.add(log)
    db.session.commit()

    _do_deliver(event, sub, log)


def _do_deliver(
    event: WebhookEvent,
    sub: WebhookSubscription,
    log: WebhookDeliveryLog,
):
    """Execute the HTTP POST and update the delivery log accordingly."""
    timestamp = str(int(time.time()))
    payload_str = event.payload
    signature = compute_signature(sub.secret, timestamp, payload_str)

    headers = {
        "Content-Type": "application/json",
        "X-FinMind-Signature": signature,
        "X-FinMind-Timestamp": timestamp,
        "X-FinMind-Event": event.event_type,
        "X-FinMind-Event-Version": event.event_version,
        "X-FinMind-Delivery-Id": event.correlation_id,
        "X-FinMind-Correlation-Id": event.correlation_id,
    }

    start = time.monotonic()
    try:
        resp = http_requests.post(
            sub.url,
            data=payload_str,
            headers=headers,
            timeout=DELIVERY_TIMEOUT_SECONDS,
        )
        latency = int((time.monotonic() - start) * 1000)
        log.status_code = resp.status_code
        log.response_body = resp.text[:2000]
        log.latency_ms = latency

        if 200 <= resp.status_code < 300:
            log.status = "delivered"
            log.delivered_at = datetime.utcnow()
            log.failure_class = None
            sub.consecutive_failures = 0
        else:
            log.failure_class = "http_4xx" if resp.status_code < 500 else "http_5xx"
            _handle_failure(log, sub)

    except http_requests.Timeout:
        log.latency_ms = int((time.monotonic() - start) * 1000)
        log.failure_class = "timeout"
        _handle_failure(log, sub)

    except http_requests.ConnectionError:
        log.latency_ms = int((time.monotonic() - start) * 1000)
        log.failure_class = "connection_error"
        _handle_failure(log, sub)

    except Exception as exc:
        log.latency_ms = int((time.monotonic() - start) * 1000)
        log.failure_class = "ssl_error" if "ssl" in str(exc).lower() else "unknown"
        _handle_failure(log, sub)

    db.session.commit()


# ---------------------------------------------------------------------------
# Failure / retry / dead-letter logic
# ---------------------------------------------------------------------------


def _handle_failure(log: WebhookDeliveryLog, sub: WebhookSubscription):
    """Decide whether to retry, dead-letter, or auto-disable."""
    sub.consecutive_failures += 1

    if sub.consecutive_failures >= AUTO_DISABLE_THRESHOLD:
        sub.active = False
        sub.disabled_at = datetime.utcnow()
        log.status = "dead_letter"
        logger.warning(
            "Auto-disabled subscription id=%s after %d consecutive failures",
            sub.id,
            sub.consecutive_failures,
        )
        return

    if log.attempt >= MAX_ATTEMPTS:
        log.status = "dead_letter"
        logger.info(
            "Dead-letter: delivery exhausted %d attempts event=%s sub=%s",
            MAX_ATTEMPTS,
            log.event_id,
            log.subscription_id,
        )
        return

    idx = min(log.attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)
    delay = RETRY_BACKOFF_SECONDS[idx]
    log.status = "pending"
    log.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
    logger.info(
        "Retry scheduled: delivery id=%s attempt=%d in %ds",
        log.id,
        log.attempt + 1,
        delay,
    )


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


def deliver_test_ping(sub: WebhookSubscription) -> dict:
    """Send a test ``ping`` event to verify connectivity."""
    payload = {"event": "ping", "message": "webhook test delivery"}
    payload_str = json.dumps(payload)
    timestamp = str(int(time.time()))
    signature = compute_signature(sub.secret, timestamp, payload_str)

    headers = {
        "Content-Type": "application/json",
        "X-FinMind-Signature": signature,
        "X-FinMind-Timestamp": timestamp,
        "X-FinMind-Event": "ping",
        "X-FinMind-Event-Version": "1",
        "X-FinMind-Delivery-Id": str(uuid.uuid4()),
        "X-FinMind-Correlation-Id": str(uuid.uuid4()),
    }

    start = time.monotonic()
    try:
        resp = http_requests.post(
            sub.url,
            data=payload_str,
            headers=headers,
            timeout=DELIVERY_TIMEOUT_SECONDS,
        )
        latency = int((time.monotonic() - start) * 1000)
        return {
            "success": 200 <= resp.status_code < 300,
            "status_code": resp.status_code,
            "latency_ms": latency,
        }
    except http_requests.Timeout:
        return {"success": False, "error": "timeout"}
    except http_requests.ConnectionError:
        return {"success": False, "error": "connection_error"}
    except Exception as exc:
        return {"success": False, "error": str(exc)[:200]}


def delivery_metrics(user_id: int) -> dict:
    """Aggregate delivery stats for a user's webhook subscriptions."""
    sub_ids = [
        s.id
        for s in db.session.query(WebhookSubscription.id)
        .filter_by(user_id=user_id)
        .all()
    ]
    if not sub_ids:
        return {
            "total_deliveries": 0,
            "delivered": 0,
            "failed": 0,
            "dead_letter": 0,
            "pending_retries": 0,
            "avg_latency_ms": None,
            "failure_breakdown": {},
        }

    from sqlalchemy import func

    logs = db.session.query(WebhookDeliveryLog).filter(
        WebhookDeliveryLog.subscription_id.in_(sub_ids)
    )
    total = logs.count()
    delivered = logs.filter(WebhookDeliveryLog.status == "delivered").count()
    dead = logs.filter(WebhookDeliveryLog.status == "dead_letter").count()
    pending = logs.filter(
        WebhookDeliveryLog.status == "pending",
        WebhookDeliveryLog.next_retry_at.isnot(None),
    ).count()

    avg_lat = (
        db.session.query(func.avg(WebhookDeliveryLog.latency_ms))
        .filter(
            WebhookDeliveryLog.subscription_id.in_(sub_ids),
            WebhookDeliveryLog.latency_ms.isnot(None),
        )
        .scalar()
    )

    breakdown_rows = (
        db.session.query(
            WebhookDeliveryLog.failure_class,
            func.count(WebhookDeliveryLog.id),
        )
        .filter(
            WebhookDeliveryLog.subscription_id.in_(sub_ids),
            WebhookDeliveryLog.failure_class.isnot(None),
        )
        .group_by(WebhookDeliveryLog.failure_class)
        .all()
    )
    failure_breakdown = {row[0]: row[1] for row in breakdown_rows}

    return {
        "total_deliveries": total,
        "delivered": delivered,
        "failed": total - delivered - pending - dead,
        "dead_letter": dead,
        "pending_retries": pending,
        "avg_latency_ms": round(float(avg_lat), 1) if avg_lat else None,
        "failure_breakdown": failure_breakdown,
    }
