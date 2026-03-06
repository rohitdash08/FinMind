import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone

import requests
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [10, 30, 60]  # seconds between retries
TIMEOUT = 10


def _sign_payload(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def emit_webhook(user_id: int, event_type: str, data: dict) -> None:
    """Emit a webhook event to all registered endpoints for a user."""
    endpoints = WebhookEndpoint.query.filter_by(user_id=user_id, active=True).all()
    if not endpoints:
        return
    payload = json.dumps({
        "event": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, default=str).encode()

    for endpoint in endpoints:
        _deliver(endpoint, event_type, payload)


def _deliver(endpoint: WebhookEndpoint, event_type: str, payload: bytes) -> None:
    signature = _sign_payload(endpoint.secret, payload)
    headers = {
        "Content-Type": "application/json",
        "X-FinMind-Event": event_type,
        "X-FinMind-Signature-256": signature,
    }
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                endpoint.url, data=payload, headers=headers, timeout=TIMEOUT
            )
            success = 200 <= resp.status_code < 300
            _log_delivery(endpoint.id, event_type, payload, attempt,
                          resp.status_code, resp.text[:500] if not success else None, success)
            if success:
                return
            last_error = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
            _log_delivery(endpoint.id, event_type, payload, attempt, None, last_error, False)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAYS[attempt - 1])

    logger.warning("Webhook delivery failed after %d attempts for endpoint %d: %s",
                   MAX_RETRIES, endpoint.id, last_error)


def _log_delivery(endpoint_id, event_type, payload, attempt, status_code, error, success):
    try:
        record = WebhookDelivery(
            endpoint_id=endpoint_id,
            event_type=event_type,
            payload=payload.decode(),
            attempt=attempt,
            status_code=status_code,
            error=error,
            success=success,
        )
        db.session.add(record)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Failed to log webhook delivery")
