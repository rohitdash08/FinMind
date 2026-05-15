from secrets import token_urlsafe
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import WebhookDelivery, WebhookEndpoint
from ..services.webhooks import (
    EVENT_TYPES,
    normalize_event_types,
    retry_pending_deliveries,
)

bp = Blueprint("webhooks", __name__)


@bp.get("/event-types")
@jwt_required()
def event_types():
    return jsonify(sorted(EVENT_TYPES))


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
    data = request.get_json(silent=True) or {}
    url = _normalize_url(data.get("url"))
    if not url:
        return jsonify(error="valid http(s) url required"), 400
    event_types = normalize_event_types(data.get("event_types"))
    if event_types is None:
        return jsonify(error="invalid event_types"), 400
    secret = str(data.get("secret") or "").strip() or token_urlsafe(32)
    endpoint = WebhookEndpoint(
        user_id=uid,
        url=url,
        secret=secret,
        event_types=event_types,
        active=bool(data.get("active", True)),
    )
    db.session.add(endpoint)
    db.session.commit()
    response = _endpoint_to_dict(endpoint)
    response["secret"] = secret
    return jsonify(response), 201


@bp.patch("/<int:endpoint_id>")
@jwt_required()
def update_webhook(endpoint_id: int):
    uid = int(get_jwt_identity())
    endpoint = db.session.get(WebhookEndpoint, endpoint_id)
    if not endpoint or endpoint.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json(silent=True) or {}
    if "url" in data:
        url = _normalize_url(data.get("url"))
        if not url:
            return jsonify(error="valid http(s) url required"), 400
        endpoint.url = url
    if "secret" in data:
        secret = str(data.get("secret") or "").strip()
        if not secret:
            return jsonify(error="secret cannot be empty"), 400
        endpoint.secret = secret
    if "event_types" in data:
        event_types = normalize_event_types(data.get("event_types"))
        if event_types is None:
            return jsonify(error="invalid event_types"), 400
        endpoint.event_types = event_types
    if "active" in data:
        endpoint.active = bool(data.get("active"))
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


@bp.get("/deliveries")
@jwt_required()
def list_deliveries():
    uid = int(get_jwt_identity())
    deliveries = (
        db.session.query(WebhookDelivery)
        .filter_by(user_id=uid)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify([_delivery_to_dict(delivery) for delivery in deliveries])


@bp.post("/deliveries/retry")
@jwt_required()
def retry_deliveries():
    uid = int(get_jwt_identity())
    return jsonify(retried=retry_pending_deliveries(uid))


def _endpoint_to_dict(endpoint: WebhookEndpoint) -> dict:
    return {
        "id": endpoint.id,
        "url": endpoint.url,
        "event_types": _event_types_to_list(endpoint.event_types),
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
        "last_error": delivery.last_error,
        "next_retry_at": (
            delivery.next_retry_at.isoformat() if delivery.next_retry_at else None
        ),
        "delivered_at": (
            delivery.delivered_at.isoformat() if delivery.delivered_at else None
        ),
        "created_at": delivery.created_at.isoformat(),
    }


def _event_types_to_list(value: str) -> list[str]:
    if value == "*":
        return ["*"]
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_url(raw_url) -> str | None:
    url = str(raw_url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url
