import json

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import WebhookDelivery, WebhookEndpoint
from ..services.webhooks import (
    EVENT_TYPES,
    endpoint_event_types,
    generate_secret,
    normalize_event_types,
    process_due_deliveries,
    validate_target_url,
)


bp = Blueprint("webhooks", __name__)


@bp.get("")
@jwt_required()
def list_webhooks():
    uid = int(get_jwt_identity())
    endpoints = (
        db.session.query(WebhookEndpoint)
        .filter_by(user_id=uid)
        .order_by(WebhookEndpoint.created_at.desc())
        .all()
    )
    return jsonify([_endpoint_to_dict(endpoint) for endpoint in endpoints])


@bp.post("")
@jwt_required()
def create_webhook():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        url = validate_target_url(data.get("url"))
        event_types = normalize_event_types(data.get("event_types"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    secret = str(data.get("secret") or "").strip() or generate_secret()
    endpoint = WebhookEndpoint(
        user_id=uid,
        url=url,
        secret=secret,
        event_types=json.dumps(event_types),
        active=bool(data.get("active", True)),
    )
    db.session.add(endpoint)
    db.session.commit()
    payload = _endpoint_to_dict(endpoint)
    payload["secret"] = secret
    return jsonify(payload), 201


@bp.patch("/<int:endpoint_id>")
@jwt_required()
def update_webhook(endpoint_id: int):
    uid = int(get_jwt_identity())
    endpoint = db.session.get(WebhookEndpoint, endpoint_id)
    if not endpoint or endpoint.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}

    if "url" in data:
        try:
            endpoint.url = validate_target_url(data.get("url"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
    if "event_types" in data:
        try:
            endpoint.event_types = json.dumps(
                normalize_event_types(data.get("event_types"))
            )
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
    if "active" in data:
        endpoint.active = bool(data.get("active"))
    if "secret" in data:
        secret = str(data.get("secret") or "").strip()
        if not secret:
            return jsonify(error="secret cannot be empty"), 400
        endpoint.secret = secret

    db.session.commit()
    return jsonify(_endpoint_to_dict(endpoint))


@bp.delete("/<int:endpoint_id>")
@jwt_required()
def delete_webhook(endpoint_id: int):
    uid = int(get_jwt_identity())
    endpoint = db.session.get(WebhookEndpoint, endpoint_id)
    if not endpoint or endpoint.user_id != uid:
        return jsonify(error="not found"), 404
    endpoint.active = False
    db.session.commit()
    return jsonify(message="disabled")


@bp.get("/events")
@jwt_required()
def list_supported_events():
    return jsonify(events=sorted(EVENT_TYPES))


@bp.get("/deliveries")
@jwt_required()
def list_deliveries():
    uid = int(get_jwt_identity())
    status = (request.args.get("status") or "").strip()
    query = (
        db.session.query(WebhookDelivery)
        .filter_by(user_id=uid)
        .order_by(WebhookDelivery.created_at.desc())
    )
    if status:
        query = query.filter(WebhookDelivery.status == status)
    deliveries = query.limit(100).all()
    return jsonify([_delivery_to_dict(delivery) for delivery in deliveries])


@bp.post("/deliveries/run")
@jwt_required()
def run_due_deliveries():
    uid = int(get_jwt_identity())
    result = process_due_deliveries(user_id=uid)
    return jsonify(result), 200


def _endpoint_to_dict(endpoint: WebhookEndpoint) -> dict:
    return {
        "id": endpoint.id,
        "url": endpoint.url,
        "event_types": endpoint_event_types(endpoint),
        "active": endpoint.active,
        "created_at": endpoint.created_at.isoformat(),
    }


def _delivery_to_dict(delivery: WebhookDelivery) -> dict:
    return {
        "id": delivery.id,
        "endpoint_id": delivery.endpoint_id,
        "event_type": delivery.event_type,
        "status": delivery.status,
        "attempts": delivery.attempts,
        "next_attempt_at": (
            delivery.next_attempt_at.isoformat() if delivery.next_attempt_at else None
        ),
        "last_error": delivery.last_error,
        "delivered_at": (
            delivery.delivered_at.isoformat() if delivery.delivered_at else None
        ),
        "created_at": delivery.created_at.isoformat(),
    }
