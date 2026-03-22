"""
Webhook endpoint management routes.

Users register, list, and delete webhook endpoints.
All mutations require a valid JWT (current_user).
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..services.webhook import WebhookEndpoint, WebhookDelivery

bp = Blueprint("webhooks", __name__)

# ── supported event types ───────────────────────────────────────────────────
VALID_EVENTS = {
    "expense.created",
    "expense.updated",
    "expense.deleted",
    "bill.created",
    "bill.paid",
    "budget.exceeded",
    "reminder.fired",
}


def _validate_events(events: list) -> tuple[bool, str]:
    if not isinstance(events, list) or not events:
        return False, "events must be a non-empty list"
    invalid = set(events) - VALID_EVENTS
    if invalid:
        return False, f"unknown events: {sorted(invalid)}"
    return True, ""


# ── CRUD ───────────────────────────────────────────────────────────────────────
@bp.post("/")
@jwt_required()
def register_endpoint():
    """Register a new webhook endpoint.

    Body: {"url": "https://...", "secret": "...", "events": ["expense.created"]}
    """
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    url = data.get("url", "").strip()
    secret = data.get("secret", "").strip()
    events = data.get("events", [])

    if not url or not url.startswith(("http://", "https://")):
        return jsonify(error="url must be a valid http/https URL"), 400
    if not secret or len(secret) < 16:
        return jsonify(error="secret must be at least 16 characters"), 400

    ok, msg = _validate_events(events)
    if not ok:
        return jsonify(error=msg, valid_events=sorted(VALID_EVENTS)), 400

    ep = WebhookEndpoint(user_id=user_id, url=url, secret=secret, events=events)
    db.session.add(ep)
    db.session.commit()

    return jsonify(id=ep.id, url=ep.url, events=ep.events, active=ep.active), 201


@bp.get("/")
@jwt_required()
def list_endpoints():
    user_id = get_jwt_identity()
    endpoints = WebhookEndpoint.query.filter_by(user_id=user_id).all()
    return jsonify([
        {"id": ep.id, "url": ep.url, "events": ep.events, "active": ep.active}
        for ep in endpoints
    ])


@bp.delete("/<int:ep_id>")
@jwt_required()
def delete_endpoint(ep_id: int):
    user_id = get_jwt_identity()
    ep = WebhookEndpoint.query.filter_by(id=ep_id, user_id=user_id).first_or_404()
    db.session.delete(ep)
    db.session.commit()
    return "", 204


@bp.patch("/<int:ep_id>")
@jwt_required()
def update_endpoint(ep_id: int):
    """Enable/disable an endpoint or update its event subscriptions."""
    user_id = get_jwt_identity()
    ep = WebhookEndpoint.query.filter_by(id=ep_id, user_id=user_id).first_or_404()
    data = request.get_json(silent=True) or {}

    if "active" in data:
        ep.active = bool(data["active"])
    if "events" in data:
        ok, msg = _validate_events(data["events"])
        if not ok:
            return jsonify(error=msg, valid_events=sorted(VALID_EVENTS)), 400
        ep.events = data["events"]

    db.session.commit()
    return jsonify(id=ep.id, url=ep.url, events=ep.events, active=ep.active)


# ── Delivery history ───────────────────────────────────────────────────────────
@bp.get("/<int:ep_id>/deliveries")
@jwt_required()
def list_deliveries(ep_id: int):
    user_id = get_jwt_identity()
    ep = WebhookEndpoint.query.filter_by(id=ep_id, user_id=user_id).first_or_404()
    deliveries = ep.deliveries.order_by(WebhookDelivery.created_at.desc()).limit(50).all()
    return jsonify([
        {
            "id": d.id,
            "event": d.event,
            "status_code": d.status_code,
            "attempts": d.attempts,
            "success": d.success,
            "error": d.error,
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
            "created_at": d.created_at.isoformat(),
        }
        for d in deliveries
    ])
