from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import secrets

from ..webhooks import (
    WebhookSubscription,
    WebhookDelivery,
    WebhookEvent,
    db,
)

bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")

VALID_EVENTS = {e.value for e in WebhookEvent}


def _current_user_id() -> int:
    return int(get_jwt_identity())


@bp.route("/", methods=["GET"])
@jwt_required()
def list_subscriptions():
    """List all webhook subscriptions for the current user."""
    subs = WebhookSubscription.query.filter_by(user_id=_current_user_id()).all()
    return jsonify([s.to_dict() for s in subs]), 200


@bp.route("/", methods=["POST"])
@jwt_required()
def create_subscription():
    """Create a new webhook subscription."""
    body = request.get_json(force=True) or {}
    url = body.get("url", "").strip()
    events = body.get("events", [])

    if not url:
        return jsonify({"error": "url is required"}), 400
    if not isinstance(events, list) or not events:
        return jsonify({"error": "events must be a non-empty list"}), 400

    invalid = set(events) - VALID_EVENTS
    if invalid:
        return jsonify({"error": f"invalid events: {sorted(invalid)}", "valid_events": sorted(VALID_EVENTS)}), 400

    secret = secrets.token_hex(32)
    sub = WebhookSubscription(
        user_id=_current_user_id(),
        url=url,
        secret=secret,
        events="",
    )
    sub.set_events(events)
    db.session.add(sub)
    db.session.commit()

    data = sub.to_dict()
    data["secret"] = secret  # Only shown on creation
    return jsonify(data), 201


@bp.route("/<int:sub_id>", methods=["GET"])
@jwt_required()
def get_subscription(sub_id: int):
    sub = WebhookSubscription.query.filter_by(id=sub_id, user_id=_current_user_id()).first_or_404()
    return jsonify(sub.to_dict()), 200


@bp.route("/<int:sub_id>", methods=["PUT"])
@jwt_required()
def update_subscription(sub_id: int):
    """Update URL, events, or active state of a subscription."""
    sub = WebhookSubscription.query.filter_by(id=sub_id, user_id=_current_user_id()).first_or_404()
    body = request.get_json(force=True) or {}

    if "url" in body:
        sub.url = body["url"].strip()
    if "events" in body:
        invalid = set(body["events"]) - VALID_EVENTS
        if invalid:
            return jsonify({"error": f"invalid events: {sorted(invalid)}"}), 400
        sub.set_events(body["events"])
    if "is_active" in body:
        sub.is_active = bool(body["is_active"])
        if sub.is_active:
            sub.consecutive_failures = 0  # reset failures on manual re-enable

    db.session.commit()
    return jsonify(sub.to_dict()), 200


@bp.route("/<int:sub_id>", methods=["DELETE"])
@jwt_required()
def delete_subscription(sub_id: int):
    sub = WebhookSubscription.query.filter_by(id=sub_id, user_id=_current_user_id()).first_or_404()
    db.session.delete(sub)
    db.session.commit()
    return jsonify({"deleted": True}), 200


@bp.route("/<int:sub_id>/deliveries", methods=["GET"])
@jwt_required()
def list_deliveries(sub_id: int):
    """List delivery attempts for a subscription (most recent first)."""
    WebhookSubscription.query.filter_by(id=sub_id, user_id=_current_user_id()).first_or_404()
    limit = min(int(request.args.get("limit", 50)), 200)
    deliveries = (
        WebhookDelivery.query.filter_by(subscription_id=sub_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify([d.to_dict() for d in deliveries]), 200


@bp.route("/events", methods=["GET"])
def list_event_types():
    """List all supported webhook event types."""
    return jsonify({"events": sorted(VALID_EVENTS)}), 200
