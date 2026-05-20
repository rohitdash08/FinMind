import secrets
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import WebhookDelivery, WebhookEndpoint
from ..services.webhooks import WEBHOOK_EVENT_TYPES

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
    url = str(data.get("url") or "").strip()
    if not _valid_url(url):
        return jsonify(error="valid http(s) url required"), 400
    endpoint = WebhookEndpoint(
        user_id=uid,
        url=url,
        secret=secrets.token_urlsafe(32),
        active=bool(data.get("active", True)),
    )
    db.session.add(endpoint)
    db.session.commit()
    response = _endpoint_to_dict(endpoint)
    response["secret"] = endpoint.secret
    return jsonify(response), 201


@bp.patch("/<int:endpoint_id>")
@jwt_required()
def update_webhook(endpoint_id: int):
    uid = int(get_jwt_identity())
    endpoint = db.session.get(WebhookEndpoint, endpoint_id)
    if not endpoint or endpoint.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "url" in data:
        url = str(data.get("url") or "").strip()
        if not _valid_url(url):
            return jsonify(error="valid http(s) url required"), 400
        endpoint.url = url
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
    db.session.delete(endpoint)
    db.session.commit()
    return "", 204


@bp.get("/<int:endpoint_id>/deliveries")
@jwt_required()
def list_webhook_deliveries(endpoint_id: int):
    uid = int(get_jwt_identity())
    endpoint = db.session.get(WebhookEndpoint, endpoint_id)
    if not endpoint or endpoint.user_id != uid:
        return jsonify(error="not found"), 404
    deliveries = (
        db.session.query(WebhookDelivery)
        .filter_by(endpoint_id=endpoint.id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify([_delivery_to_dict(delivery) for delivery in deliveries])


@bp.get("/event-types")
def list_event_types():
    return jsonify(list(WEBHOOK_EVENT_TYPES))


def _valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _endpoint_to_dict(endpoint: WebhookEndpoint) -> dict:
    return {
        "id": endpoint.id,
        "url": endpoint.url,
        "active": endpoint.active,
        "created_at": endpoint.created_at.isoformat() if endpoint.created_at else None,
    }


def _delivery_to_dict(delivery: WebhookDelivery) -> dict:
    return {
        "id": delivery.id,
        "event_type": delivery.event_type,
        "delivery_id": delivery.delivery_id,
        "attempts": delivery.attempts,
        "success": delivery.success,
        "status_code": delivery.status_code,
        "error": delivery.error,
        "created_at": delivery.created_at.isoformat() if delivery.created_at else None,
    }
