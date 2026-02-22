"""Webhook management routes."""

import json
import secrets
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import WebhookEndpoint, WebhookDelivery, WebhookEventType
import logging

bp = Blueprint("webhooks", __name__)
logger = logging.getLogger("finmind.webhooks")

VALID_EVENTS = [e.value for e in WebhookEventType] + ["*"]


def _serialize_endpoint(ep: WebhookEndpoint) -> dict:
    return {
        "id": ep.id,
        "url": ep.url,
        "events": json.loads(ep.events),
        "is_active": ep.is_active,
        "created_at": ep.created_at.isoformat(),
    }


def _serialize_delivery(d: WebhookDelivery) -> dict:
    return {
        "id": d.id,
        "endpoint_id": d.endpoint_id,
        "event_type": d.event_type,
        "response_status": d.response_status,
        "success": d.success,
        "attempts": d.attempts,
        "last_attempt_at": d.last_attempt_at.isoformat() if d.last_attempt_at else None,
        "created_at": d.created_at.isoformat(),
    }


@bp.post("")
@jwt_required()
def create_endpoint():
    """Register a new webhook endpoint."""
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)

    url = (data.get("url") or "").strip()
    events = data.get("events", ["*"])

    if not url:
        return jsonify({"error": "url is required"}), 400
    if not url.startswith("https://"):
        return jsonify({"error": "url must use HTTPS"}), 400

    for event in events:
        if event not in VALID_EVENTS:
            return jsonify({"error": f"invalid event type: {event}"}), 400

    secret = secrets.token_hex(32)
    endpoint = WebhookEndpoint(
        user_id=uid,
        url=url,
        secret=secret,
        events=json.dumps(events),
    )
    db.session.add(endpoint)
    db.session.commit()

    result = _serialize_endpoint(endpoint)
    result["secret"] = secret  # Only shown once at creation
    return jsonify(result), 201


@bp.get("")
@jwt_required()
def list_endpoints():
    uid = int(get_jwt_identity())
    endpoints = WebhookEndpoint.query.filter_by(user_id=uid).all()
    return jsonify([_serialize_endpoint(ep) for ep in endpoints])


@bp.get("/<int:endpoint_id>")
@jwt_required()
def get_endpoint(endpoint_id: int):
    uid = int(get_jwt_identity())
    ep = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=uid).first_or_404()
    return jsonify(_serialize_endpoint(ep))


@bp.patch("/<int:endpoint_id>")
@jwt_required()
def update_endpoint(endpoint_id: int):
    uid = int(get_jwt_identity())
    ep = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=uid).first_or_404()
    data = request.get_json(force=True)

    if "url" in data:
        url = data["url"].strip()
        if not url.startswith("https://"):
            return jsonify({"error": "url must use HTTPS"}), 400
        ep.url = url
    if "events" in data:
        for event in data["events"]:
            if event not in VALID_EVENTS:
                return jsonify({"error": f"invalid event type: {event}"}), 400
        ep.events = json.dumps(data["events"])
    if "is_active" in data:
        ep.is_active = data["is_active"]

    db.session.commit()
    return jsonify(_serialize_endpoint(ep))


@bp.delete("/<int:endpoint_id>")
@jwt_required()
def delete_endpoint(endpoint_id: int):
    uid = int(get_jwt_identity())
    ep = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=uid).first_or_404()
    WebhookDelivery.query.filter_by(endpoint_id=ep.id).delete()
    db.session.delete(ep)
    db.session.commit()
    return jsonify({"message": "deleted"})


@bp.get("/<int:endpoint_id>/deliveries")
@jwt_required()
def list_deliveries(endpoint_id: int):
    """View delivery history for an endpoint."""
    uid = int(get_jwt_identity())
    ep = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=uid).first_or_404()
    deliveries = WebhookDelivery.query.filter_by(endpoint_id=ep.id).order_by(
        WebhookDelivery.created_at.desc()
    ).limit(50).all()
    return jsonify([_serialize_delivery(d) for d in deliveries])


@bp.get("/events")
@jwt_required()
def list_event_types():
    """List all available webhook event types."""
    return jsonify({
        "events": [
            {"type": e.value, "description": e.value.replace(".", " ").title()}
            for e in WebhookEventType
        ]
    })
