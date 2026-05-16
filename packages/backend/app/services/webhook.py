import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests

from ..extensions import db
from ..models import WebhookDeliveryLog, WebhookSubscription

logger = logging.getLogger("finmind.webhook")

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2
REQUEST_TIMEOUT = 10


def _compute_signature(secret: str, payload_bytes: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()


def _deliver_one(subscription: WebhookSubscription, payload: dict[str, Any], signing_secret: str):
    payload_bytes = json.dumps(payload).encode("utf-8")
    signature = _compute_signature(signing_secret, payload_bytes)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "FinMind-Webhook/1.0",
        "X-FinMind-Signature": f"sha256={signature}",
        "X-FinMind-Event": payload.get("event_type", "unknown"),
        "X-FinMind-Delivery": str(time.time()),
    }

    try:
        resp = requests.post(
            subscription.url, data=payload_bytes, headers=headers, timeout=REQUEST_TIMEOUT
        )
        return resp.status_code, None
    except requests.RequestException as exc:
        return None, str(exc)


def _log_delivery(
    subscription_id: int,
    event_type: str,
    attempt: int,
    status_code: int | None,
    error_message: str | None,
    response_body: str | None,
):
    log_entry = WebhookDeliveryLog(
        subscription_id=subscription_id,
        event_type=event_type,
        attempt=attempt,
        status_code=status_code,
        success=status_code is not None and 200 <= status_code < 300,
        error_message=error_message[:1000] if error_message else None,
        response_body=response_body[:2000] if response_body else None,
        delivered_at=datetime.now(timezone.utc),
    )
    db.session.add(log_entry)
    db.session.commit()


def _dispatch_with_retry(
    subscription: WebhookSubscription,
    payload: dict[str, Any],
    signing_secret: str,
):
    event_type = payload.get("event_type", "unknown")
    for attempt in range(1, MAX_RETRIES + 1):
        status_code, error = _deliver_one(subscription, payload, signing_secret)
        _log_delivery(
            subscription_id=subscription.id,
            event_type=event_type,
            attempt=attempt,
            status_code=status_code,
            error_message=error,
            response_body=None,
        )
        if status_code is not None and 200 <= status_code < 300:
            logger.info(
                "Webhook delivered subscription=%s event=%s attempt=%s status=%s",
                subscription.id,
                event_type,
                attempt,
                status_code,
            )
            return
        if attempt < MAX_RETRIES:
            delay = RETRY_BACKOFF_BASE ** (attempt - 1)
            logger.warning(
                "Webhook failed subscription=%s event=%s attempt=%s error=%s retry_in=%ss",
                subscription.id,
                event_type,
                attempt,
                error,
                delay,
            )
            time.sleep(delay)

    logger.error(
        "Webhook exhausted retries subscription=%s event=%s",
        subscription.id,
        event_type,
    )


def emit_event(event_type: str, payload: dict[str, Any], signing_secret: str):
    subscriptions = (
        db.session.query(WebhookSubscription)
        .filter_by(active=True, event_type=event_type)
        .all()
    )
    if not subscriptions:
        logger.debug("No webhook subscriptions for event=%s", event_type)
        return

    payload = dict(payload, event_type=event_type, timestamp=datetime.now(timezone.utc).isoformat())

    for subscription in subscriptions:
        t = threading.Thread(
            target=_dispatch_with_retry,
            args=(subscription, payload, signing_secret),
            daemon=True,
        )
        t.start()
