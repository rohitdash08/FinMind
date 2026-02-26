import hashlib
import hmac
import json
import time
from datetime import datetime
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

from flask import current_app

from ..extensions import db
from ..models import WebhookDelivery

SUPPORTED_EVENT_TYPES = {
    "expense.created",
    "bill.created",
    "reminder.created",
}


def emit_webhook_event(*, user_id: int, event_type: str, payload: dict) -> None:
    if event_type not in SUPPORTED_EVENT_TYPES:
        return

    target_url = current_app.config.get("WEBHOOK_TARGET_URL")
    secret = current_app.config.get("WEBHOOK_SIGNING_SECRET")
    retries = int(current_app.config.get("WEBHOOK_MAX_RETRIES") or 3)

    if not target_url or not secret:
        return

    body = json.dumps(
        {
            "event_type": event_type,
            "sent_at": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
        },
        separators=(",", ":"),
        sort_keys=True,
    )

    delivery = WebhookDelivery(
        user_id=user_id,
        event_type=event_type,
        payload_json=body,
        status="pending",
    )
    db.session.add(delivery)
    db.session.flush()

    signature = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256)
    signature_hex = signature.hexdigest()

    last_error = None
    for attempt in range(1, retries + 1):
        delivery.attempts = attempt
        try:
            req = urlrequest.Request(
                target_url,
                data=body.encode("utf-8"),
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-FinMind-Event": event_type,
                    "X-FinMind-Signature": f"sha256={signature_hex}",
                },
            )
            with urlrequest.urlopen(req, timeout=5) as resp:
                if 200 <= getattr(resp, "status", 0) < 300:
                    delivery.status = "sent"
                    delivery.sent_at = datetime.utcnow()
                    delivery.last_error = None
                    db.session.commit()
                    return
                last_error = f"unexpected_status:{getattr(resp, 'status', 'unknown')}"
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)[:500]

        if attempt < retries:
            time.sleep(0.2 * attempt)

    delivery.status = "failed"
    delivery.last_error = (last_error or "delivery_failed")[:500]
    db.session.commit()
