from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import WebhookSubscription
from ..services.webhooks import SUPPORTED_WEBHOOK_EVENTS

bp = Blueprint("webhooks", __name__)


@bp.get("")
@jwt_required()
def list_webhooks():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(WebhookSubscription)
        .filter_by(user_id=uid)
        .order_by(WebhookSubscription.created_at.desc())
        .all()
    )
    return jsonify([_subscription_to_dict(item) for item in items])


@bp.post("")
@jwt_required()
def create_webhook():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    target_url = str(data.get("target_url") or "").strip()
    secret = str(data.get("secret") or "").strip()
    description = str(data.get("description") or "").strip() or None
    subscribed_events = data.get("subscribed_events") or []

    error = _validate_subscription_input(
        target_url=target_url, secret=secret, subscribed_events=subscribed_events
    )
    if error:
        return jsonify(error=error), 400

    item = WebhookSubscription(
        user_id=uid,
        target_url=target_url,
        secret=secret,
        description=description,
        subscribed_events=sorted(set(subscribed_events)),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(_subscription_to_dict(item)), 201


@bp.patch("/<int:webhook_id>")
@jwt_required()
def update_webhook(webhook_id: int):
    uid = int(get_jwt_identity())
    item = db.session.get(WebhookSubscription, webhook_id)
    if not item or item.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}
    target_url = str(data.get("target_url") or item.target_url).strip()
    secret = str(data.get("secret") or item.secret).strip()
    subscribed_events = data.get("subscribed_events", item.subscribed_events)
    error = _validate_subscription_input(
        target_url=target_url, secret=secret, subscribed_events=subscribed_events
    )
    if error:
        return jsonify(error=error), 400

    item.target_url = target_url
    item.secret = secret
    item.description = str(data.get("description") or item.description or "").strip() or None
    item.active = bool(data.get("active", item.active))
    item.subscribed_events = sorted(set(subscribed_events))
    item.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_subscription_to_dict(item))


@bp.delete("/<int:webhook_id>")
@jwt_required()
def delete_webhook(webhook_id: int):
    uid = int(get_jwt_identity())
    item = db.session.get(WebhookSubscription, webhook_id)
    if not item or item.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify(message="deleted")


def _validate_subscription_input(
    *, target_url: str, secret: str, subscribed_events: list[str]
) -> str | None:
    if not target_url:
        return "target_url required"
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "invalid target_url"
    if not secret:
        return "secret required"
    if not isinstance(subscribed_events, list) or not subscribed_events:
        return "subscribed_events must be a non-empty list"
    invalid = sorted({event for event in subscribed_events if event not in SUPPORTED_WEBHOOK_EVENTS})
    if invalid:
        return f"unsupported subscribed_events: {', '.join(invalid)}"
    return None


def _subscription_to_dict(item: WebhookSubscription) -> dict:
    return {
        "id": item.id,
        "target_url": item.target_url,
        "description": item.description,
        "active": item.active,
        "subscribed_events": item.subscribed_events or [],
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "last_success_at": item.last_success_at.isoformat() if item.last_success_at else None,
        "last_failure_at": item.last_failure_at.isoformat() if item.last_failure_at else None,
        "failure_count": item.failure_count,
    }
