import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import WebhookEndpoint, WebhookEvent

bp = Blueprint("webhooks", __name__)
logger = logging.getLogger("finmind.webhooks")

MAX_RETRIES = 5
RETRY_DELAYS = [1, 2, 4, 8, 16]  # seconds


def _gen_secret() -> str:
    import secrets

    return secrets.token_hex(32)


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


def _endpoint_to_dict(ep: WebhookEndpoint) -> dict:
    return {
        "id": ep.id,
        "url": ep.url,
        "active": ep.active,
        "events": ep.events,
        "created_at": ep.created_at.isoformat(),
    }


def _event_to_dict(ev: WebhookEvent) -> dict:
    return {
        "id": ev.id,
        "endpoint_id": ev.endpoint_id,
        "event_type": ev.event_type,
        "status": ev.status,
        "attempts": ev.attempts,
        "created_at": ev.created_at.isoformat(),
    }


@bp.get("")
@jwt_required()
def list_endpoints():
    uid = int(get_jwt_identity())
    eps = (
        WebhookEndpoint.query.filter_by(user_id=uid)
        .order_by(WebhookEndpoint.created_at.desc())
        .all()
    )
    return jsonify([_endpoint_to_dict(e) for e in eps])


@bp.post("")
@jwt_required()
def create_endpoint():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="url required"), 400
    if not url.startswith("https://"):
        # allow http only in dev
        return jsonify(error="url must be https"), 400

    events = data.get("events") or "*"
    if isinstance(events, list):
        events = ",".join(events)

    secret = _gen_secret()
    ep = WebhookEndpoint(user_id=uid, url=url, secret=secret, events=events)
    db.session.add(ep)
    db.session.commit()
    logger.info("webhook created id=%s user=%s", ep.id, uid)

    resp = _endpoint_to_dict(ep)
    # show secret once on creation
    resp["secret"] = secret
    return jsonify(resp), 201


@bp.patch("/<int:ep_id>")
@jwt_required()
def update_endpoint(ep_id: int):
    uid = int(get_jwt_identity())
    ep = db.session.get(WebhookEndpoint, ep_id)
    if not ep or ep.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    if "url" in data:
        url = data["url"].strip()
        if not url.startswith("https://"):
            return jsonify(error="url must be https"), 400
        ep.url = url
    if "active" in data:
        ep.active = bool(data["active"])
    if "events" in data:
        evts = data["events"]
        ep.events = ",".join(evts) if isinstance(evts, list) else str(evts)

    db.session.commit()
    return jsonify(_endpoint_to_dict(ep))


@bp.delete("/<int:ep_id>")
@jwt_required()
def delete_endpoint(ep_id: int):
    uid = int(get_jwt_identity())
    ep = db.session.get(WebhookEndpoint, ep_id)
    if not ep or ep.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(ep)
    db.session.commit()
    return jsonify(message="deleted")


@bp.post("/<int:ep_id>/test")
@jwt_required()
def test_endpoint(ep_id: int):
    """fire a test event to verify the endpoint works."""
    uid = int(get_jwt_identity())
    ep = db.session.get(WebhookEndpoint, ep_id)
    if not ep or ep.user_id != uid:
        return jsonify(error="not found"), 404

    test_payload = {
        "event": "webhook.test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"message": "test ping from finmind"},
    }
    payload_bytes = json.dumps(test_payload, separators=(",", ":")).encode()
    sig = _sign_payload(payload_bytes, ep.secret)

    try:
        resp = requests.post(
            ep.url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-FinMind-Signature": f"sha256={sig}",
                "X-FinMind-Event": "webhook.test",
            },
            timeout=10,
        )
        return jsonify(
            status=resp.status_code,
            delivered=resp.status_code < 400,
        )
    except requests.RequestException as exc:
        return jsonify(status=0, delivered=False, error=str(exc)), 200


def dispatch_event(event_type: str, data: dict, user_id: int | None = None):
    """queue webhook deliveries for all matching endpoints. runs in background."""
    # pull matching endpoints
    q = WebhookEndpoint.query.filter_by(active=True)
    if user_id is not None:
        q = q.filter_by(user_id=user_id)
    endpoints = q.all()

    for ep in endpoints:
        # check if this endpoint subscribes to this event
        if ep.events != "*" and event_type not in ep.events.split(","):
            continue

        ev = WebhookEvent(
            endpoint_id=ep.id,
            event_type=event_type,
            payload=json.dumps(data, default=str),
            status="pending",
            next_attempt_at=datetime.utcnow(),
        )
        db.session.add(ev)
    db.session.commit()

    # fire deliveries in background so we don't block the request
    thread = threading.Thread(target=_process_pending, daemon=True)
    thread.start()


def _process_pending():
    """drain pending webhook events."""
    # small sleep to let the commit settle
    time.sleep(0.1)
    pending = (
        WebhookEvent.query.filter_by(status="pending")
        .filter(WebhookEvent.next_attempt_at <= datetime.utcnow())
        .limit(50)
        .all()
    )
    for ev in pending:
        _deliver(ev)


def _deliver(ev: WebhookEvent):
    ep = db.session.get(WebhookEndpoint, ev.endpoint_id)
    if not ep or not ep.active:
        ev.status = "failed"
        ev.last_error = "endpoint inactive"
        db.session.commit()
        return

    payload_bytes = ev.payload.encode()
    sig = _sign_payload(payload_bytes, ep.secret)

    ev.attempts += 1
    try:
        resp = requests.post(
            ep.url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-FinMind-Signature": f"sha256={sig}",
                "X-FinMind-Event": ev.event_type,
            },
            timeout=10,
        )
        if resp.status_code < 400:
            ev.status = "delivered"
            ev.last_error = None
        else:
            _handle_delivery_failure(ev, f"HTTP {resp.status_code}")
    except requests.RequestException as exc:
        _handle_delivery_failure(ev, str(exc))

    db.session.commit()


def _handle_delivery_failure(ev: WebhookEvent, error: str):
    ev.last_error = error[:500]
    if ev.attempts >= MAX_RETRIES:
        ev.status = "failed"
        logger.warning(
            "webhook delivery failed after %d attempts: %s", ev.attempts, error
        )
    else:
        # exponential backoff
        delay_idx = min(ev.attempts - 1, len(RETRY_DELAYS) - 1)
        ev.next_attempt_at = datetime.utcnow() + timedelta(
            seconds=RETRY_DELAYS[delay_idx]
        )
        logger.info(
            "webhook retry scheduled attempt=%d next=%s",
            ev.attempts,
            ev.next_attempt_at,
        )


@bp.get("/events")
@jwt_required()
def list_events():
    """recent webhook events for debugging."""
    uid = int(get_jwt_identity())
    # join to filter by user's endpoints
    events = (
        WebhookEvent.query.join(WebhookEndpoint)
        .filter(WebhookEndpoint.user_id == uid)
        .order_by(WebhookEvent.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify([_event_to_dict(e) for e in events])
