from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import WebhookEndpoint
import secrets

bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")

@bp.post("/")
@jwt_required()
def create_webhook():
    user_id = get_jwt_identity()
    data = request.json or {}
    url = data.get("url")
    event_types = data.get("event_types", "*")

    if not url:
        return jsonify(error="URL is required"), 400

    endpoint = WebhookEndpoint(
        user_id=user_id,
        url=url,
        secret=secrets.token_hex(32),
        event_types=event_types
    )
    db.session.add(endpoint)
    db.session.commit()

    return jsonify({
        "id": endpoint.id,
        "url": endpoint.url,
        "secret": endpoint.secret,
        "event_types": endpoint.event_types,
        "active": endpoint.active
    }), 201

@bp.get("/")
@jwt_required()
def list_webhooks():
    user_id = get_jwt_identity()
    endpoints = WebhookEndpoint.query.filter_by(user_id=user_id).all()
    return jsonify([
        {
            "id": ep.id,
            "url": ep.url,
            "event_types": ep.event_types,
            "active": ep.active
        } for ep in endpoints
    ]), 200

@bp.delete("/<int:endpoint_id>")
@jwt_required()
def delete_webhook(endpoint_id):
    user_id = get_jwt_identity()
    endpoint = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=user_id).first()
    if not endpoint:
        return jsonify(error="Endpoint not found"), 404
        
    db.session.delete(endpoint)
    db.session.commit()
    return jsonify(success=True), 200
