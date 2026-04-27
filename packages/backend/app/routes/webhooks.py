from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Webhook, WebhookDelivery
from ..services import webhooks as webhook_service

bp = Blueprint("webhooks", __name__)


def _hook_to_dict(hook: Webhook, include_secret: bool = False) -> dict:
    out = {
        "id": hook.id,
        "url": hook.url,
        "events": [e.strip() for e in hook.events.split(",") if e.strip()],
        "active": hook.active,
        "created_at": hook.created_at.isoformat(),
    }
    if include_secret:
        out["secret"] = hook.secret
    return out


def _delivery_to_dict(d: WebhookDelivery) -> dict:
    return {
        "id": d.id,
        "webhook_id": d.webhook_id,
        "event_type": d.event_type,
        "status": d.status,
        "attempts": d.attempts,
        "last_status_code": d.last_status_code,
        "last_error": d.last_error,
        "next_attempt_at": d.next_attempt_at.isoformat() if d.next_attempt_at else None,
        "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
        "created_at": d.created_at.isoformat(),
    }


def _normalize_events(raw) -> str | None:
    if raw is None:
        return "*"
    if isinstance(raw, str):
        items = [s.strip() for s in raw.split(",") if s.strip()]
    elif isinstance(raw, list):
        items = [str(s).strip() for s in raw if str(s).strip()]
    else:
        return None
    if not items:
        return "*"
    for item in items:
        if item == "*" or item.endswith(".*"):
            continue
        if item not in webhook_service.EVENT_TYPES:
            return None
    return ",".join(items)


@bp.get("")
@jwt_required()
def list_webhooks():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(Webhook)
        .filter_by(user_id=uid)
        .order_by(Webhook.created_at.desc())
        .all()
    )
    return jsonify([_hook_to_dict(h) for h in items])


@bp.post("")
@jwt_required()
def create_webhook():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return jsonify(error="valid url required"), 400
    events = _normalize_events(data.get("events"))
    if events is None:
        return jsonify(error="invalid events; see /webhooks/events"), 400
    secret = (data.get("secret") or "").strip() or webhook_service.generate_secret()
    if len(secret) > 128:
        return jsonify(error="secret too long"), 400
    hook = Webhook(
        user_id=uid,
        url=url,
        secret=secret,
        events=events,
        active=bool(data.get("active", True)),
    )
    db.session.add(hook)
    db.session.commit()
    return jsonify(_hook_to_dict(hook, include_secret=True)), 201


@bp.patch("/<int:webhook_id>")
@jwt_required()
def update_webhook(webhook_id: int):
    uid = int(get_jwt_identity())
    hook = db.session.get(Webhook, webhook_id)
    if not hook or hook.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "url" in data:
        url = (data.get("url") or "").strip()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            return jsonify(error="valid url required"), 400
        hook.url = url
    if "events" in data:
        events = _normalize_events(data.get("events"))
        if events is None:
            return jsonify(error="invalid events"), 400
        hook.events = events
    if "active" in data:
        hook.active = bool(data.get("active"))
    db.session.commit()
    return jsonify(_hook_to_dict(hook))


@bp.delete("/<int:webhook_id>")
@jwt_required()
def delete_webhook(webhook_id: int):
    uid = int(get_jwt_identity())
    hook = db.session.get(Webhook, webhook_id)
    if not hook or hook.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(hook)
    db.session.commit()
    return jsonify(message="deleted")


@bp.get("/events")
def list_event_types():
    return jsonify(events=list(webhook_service.EVENT_TYPES))


@bp.get("/<int:webhook_id>/deliveries")
@jwt_required()
def list_deliveries(webhook_id: int):
    uid = int(get_jwt_identity())
    hook = db.session.get(Webhook, webhook_id)
    if not hook or hook.user_id != uid:
        return jsonify(error="not found"), 404
    items = (
        db.session.query(WebhookDelivery)
        .filter_by(webhook_id=hook.id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify([_delivery_to_dict(d) for d in items])


@bp.post("/run")
@jwt_required()
def run_pending():
    """Process pending deliveries whose retry window has elapsed."""
    result = webhook_service.process_pending()
    return jsonify(result)
