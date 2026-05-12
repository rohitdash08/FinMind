"""Webhook subscription management routes."""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..services.webhooks import WebhookSubscription, EVENT_TYPES
import secrets

bp = Blueprint("webhooks", __name__)


@bp.get("/events")
@jwt_required()
def list_event_types():
    """List supported webhook event types."""
    return jsonify(event_types=EVENT_TYPES)


@bp.get("/")
@jwt_required()
def list_subscriptions():
    uid = int(get_jwt_identity())
    subs = db.session.query(WebhookSubscription).filter_by(user_id=uid).all()
    return jsonify(subscriptions=[_serialize(s) for s in subs])


@bp.post("/")
@jwt_required()
def create_subscription():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    url = data.get("url")
    events = data.get("events", [])

    if not url:
        return jsonify(error="url required"), 400
    if not events:
        return jsonify(error="events array required"), 400

    invalid = [e for e in events if e not in EVENT_TYPES]
    if invalid:
        return jsonify(error=f"invalid events: {invalid}"), 400

    secret = secrets.token_hex(32)
    sub = WebhookSubscription(
        user_id=uid,
        url=url,
        secret=secret,
        events=",".join(events),
    )
    db.session.add(sub)
    db.session.commit()

    return jsonify(subscription=_serialize(sub), secret=secret), 201


@bp.delete("/<int:sub_id>")
@jwt_required()
def delete_subscription(sub_id):
    uid = int(get_jwt_identity())
    sub = db.session.query(WebhookSubscription).filter_by(id=sub_id, user_id=uid).first()
    if not sub:
        return jsonify(error="not found"), 404
    db.session.delete(sub)
    db.session.commit()
    return jsonify(message="deleted"), 200


def _serialize(s: WebhookSubscription) -> dict:
    return {
        "id": s.id,
        "url": s.url,
        "events": s.events.split(","),
        "active": s.active,
        "created_at": s.created_at.isoformat(),
    }
