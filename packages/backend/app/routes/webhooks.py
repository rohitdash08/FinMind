import secrets
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import WebhookDelivery, WebhookEndpoint

bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


@bp.route("", methods=["POST"])
@jwt_required()
def register():
    """Register a new webhook endpoint."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return jsonify({"error": "Valid URL required"}), 400
    secret = secrets.token_hex(32)
    endpoint = WebhookEndpoint(user_id=user_id, url=url, secret=secret)
    db.session.add(endpoint)
    db.session.commit()
    return jsonify({
        "id": endpoint.id,
        "url": endpoint.url,
        "secret": secret,
        "active": endpoint.active,
        "created_at": endpoint.created_at.isoformat(),
        "note": "Store the secret securely. It will not be shown again.",
    }), 201


@bp.route("", methods=["GET"])
@jwt_required()
def list_endpoints():
    user_id = int(get_jwt_identity())
    endpoints = WebhookEndpoint.query.filter_by(user_id=user_id).all()
    return jsonify([{
        "id": e.id,
        "url": e.url,
        "active": e.active,
        "created_at": e.created_at.isoformat(),
    } for e in endpoints])


@bp.route("/<int:endpoint_id>", methods=["DELETE"])
@jwt_required()
def delete_endpoint(endpoint_id):
    user_id = int(get_jwt_identity())
    endpoint = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=user_id).first_or_404()
    endpoint.active = False
    db.session.commit()
    return jsonify({"message": "Webhook endpoint deactivated"}), 200


@bp.route("/deliveries", methods=["GET"])
@jwt_required()
def list_deliveries():
    user_id = int(get_jwt_identity())
    endpoints = WebhookEndpoint.query.filter_by(user_id=user_id).all()
    endpoint_ids = [e.id for e in endpoints]
    deliveries = (
        WebhookDelivery.query
        .filter(WebhookDelivery.endpoint_id.in_(endpoint_ids))
        .order_by(WebhookDelivery.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify([{
        "id": d.id,
        "endpoint_id": d.endpoint_id,
        "event_type": d.event_type,
        "attempt": d.attempt,
        "status_code": d.status_code,
        "success": d.success,
        "error": d.error,
        "created_at": d.created_at.isoformat(),
    } for d in deliveries])
