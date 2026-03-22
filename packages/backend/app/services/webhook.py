"""
Webhook delivery service with HMAC-SHA256 signing and exponential-backoff retry.

Design rationale
----------------
- HMAC-SHA256 via X-Hub-Signature-256 follows the GitHub Webhooks convention,
  which is the de-facto OSS standard for signed HTTP callbacks.
- Exponential backoff (base 2s, max 5 attempts) keeps total worst-case delay
  under 62 s while respecting upstream rate limits.
- Fire-and-forget via a background thread keeps the API response time
  unaffected by webhook delivery latency.
- SQLAlchemy model records every attempt so operators can replay or audit
  deliveries without external tooling.
"""

from __future__ import annotations

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
from ..config import Settings

_settings = Settings()
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_RETRIES = 5
BASE_BACKOFF = 2.0          # seconds — doubles each attempt (2, 4, 8, 16, 32)
REQUEST_TIMEOUT = 10        # seconds per attempt
DELIVERY_CONTENT_TYPE = "application/json"


# ── Database model ─────────────────────────────────────────────────────────────
class WebhookEndpoint(db.Model):
    """A registered webhook target for a user."""

    __tablename__ = "webhook_endpoints"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    secret = db.Column(db.String(255), nullable=False)
    events = db.Column(db.JSON, nullable=False, default=list)   # e.g. ["expense.created"]
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    deliveries = db.relationship("WebhookDelivery", backref="endpoint", lazy="dynamic")


class WebhookDelivery(db.Model):
    """Audit log of every webhook delivery attempt."""

    __tablename__ = "webhook_deliveries"

    id = db.Column(db.Integer, primary_key=True)
    endpoint_id = db.Column(db.Integer, db.ForeignKey("webhook_endpoints.id"), nullable=False)
    event = db.Column(db.String(100), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    status_code = db.Column(db.Integer, nullable=True)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    success = db.Column(db.Boolean, default=False, nullable=False)
    error = db.Column(db.Text, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ── Signing ────────────────────────────────────────────────────────────────────
def _sign_payload(secret: str, body: bytes) -> str:
    """Return 'sha256=<hex>' HMAC signature for *body* using *secret*.

    Receiver verification example::

        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = _sign_payload(endpoint.secret, request.data)
        if not hmac.compare_digest(sig, expected):
            abort(401)
    """
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


# ── Delivery ───────────────────────────────────────────────────────────────────
def _deliver_once(url: str, headers: dict, body: bytes) -> tuple[bool, int | None, str | None]:
    """Attempt a single HTTP POST.  Returns (success, status_code, error_message)."""
    try:
        resp = requests.post(url, data=body, headers=headers, timeout=REQUEST_TIMEOUT)
        success = 200 <= resp.status_code < 300
        return success, resp.status_code, None if success else f"HTTP {resp.status_code}"
    except requests.RequestException as exc:
        return False, None, str(exc)


def _deliver_with_retry(delivery_id: int, url: str, secret: str, body: bytes) -> None:
    """Background worker: deliver *body* to *url* with exponential-backoff retry.

    Updates WebhookDelivery record after each attempt.
    Uses a fresh application context so SQLAlchemy sessions work in threads.
    """
    # Import here to avoid circular dependency at module load time.
    from .. import create_app  # noqa: PLC0415

    app = create_app()
    with app.app_context():
        delivery = WebhookDelivery.query.get(delivery_id)
        if delivery is None:
            logger.error("WebhookDelivery %d not found", delivery_id)
            return

        endpoint = delivery.endpoint
        headers = {
            "Content-Type": DELIVERY_CONTENT_TYPE,
            "X-Hub-Signature-256": _sign_payload(secret, body),
            "X-FinMind-Event": delivery.event,
            "X-FinMind-Delivery": str(delivery_id),
        }

        for attempt in range(1, MAX_RETRIES + 1):
            delivery.attempts = attempt
            success, status_code, error = _deliver_once(url, headers, body)
            delivery.status_code = status_code
            delivery.error = error

            if success:
                delivery.success = True
                delivery.delivered_at = datetime.now(timezone.utc)
                db.session.commit()
                logger.info("Webhook %d delivered on attempt %d", delivery_id, attempt)
                return

            logger.warning(
                "Webhook %d attempt %d/%d failed: %s",
                delivery_id, attempt, MAX_RETRIES, error,
            )
            db.session.commit()

            if attempt < MAX_RETRIES:
                sleep_secs = BASE_BACKOFF ** attempt
                logger.debug("Retrying in %.1fs…", sleep_secs)
                time.sleep(sleep_secs)

        # All retries exhausted
        delivery.success = False
        db.session.commit()
        logger.error("Webhook %d failed after %d attempts", delivery_id, MAX_RETRIES)


# ── Public API ─────────────────────────────────────────────────────────────────
def emit_event(event: str, payload: dict[str, Any], user_id: int | None = None) -> None:
    """Fire a webhook event to all matching active endpoints.

    This is the single call-site used by route handlers::

        from .services.webhook import emit_event
        emit_event("expense.created", {"id": expense.id, ...}, user_id=current_user.id)

    Delivery is asynchronous (background thread) so callers are never blocked.

    Args:
        event:    Dot-separated event name, e.g. ``"expense.created"``.
        payload:  JSON-serialisable dict that becomes the request body.
        user_id:  If provided, only endpoints belonging to this user are notified.
    """
    query = WebhookEndpoint.query.filter_by(active=True)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)

    endpoints = [ep for ep in query.all() if event in (ep.events or [])]
    if not endpoints:
        return

    body = json.dumps({"event": event, "data": payload}, default=str).encode()

    for ep in endpoints:
        delivery = WebhookDelivery(
            endpoint_id=ep.id,
            event=event,
            payload=payload,
        )
        db.session.add(delivery)
        db.session.flush()   # populate delivery.id before the thread starts
        db.session.commit()

        thread = threading.Thread(
            target=_deliver_with_retry,
            args=(delivery.id, ep.url, ep.secret, body),
            daemon=True,
        )
        thread.start()
        logger.debug("Fired webhook thread for endpoint %d event=%s", ep.id, event)
