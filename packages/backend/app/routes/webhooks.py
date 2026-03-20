from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import secrets
from ..extensions import db
from ..models import WebhookSubscription, WebhookDeliveryLog
from ..services.webhook_service import WebhookService

bp = Blueprint("webhooks", __name__)

@bp.get("")
@jwt_required()
def list_webhooks():
    uid = int(get_jwt_identity())
    subs = WebhookSubscription.query.filter_by(user_id=uid).all()
    return jsonify([_sub_to_dict(s) for s in subs])

@bp.post("")
@jwt_required()
def create_webhook():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    target_url = data.get("target_url")
    event_types = data.get("event_types")
    
    if not target_url or not event_types or not isinstance(event_types, list):
        return jsonify(error="target_url and event_types (list) are required"), 400
        
    sub = WebhookSubscription(
        user_id=uid,
        target_url=target_url,
        event_types=event_types,
        secret_key=secrets.token_hex(16),
        active=True
    )
    db.session.add(sub)
    db.session.commit()
    
    return jsonify(_sub_to_dict(sub)), 201

@bp.patch("/<int:sub_id>")
@jwt_required()
def update_webhook(sub_id: int):
    uid = int(get_jwt_identity())
    sub = WebhookSubscription.query.filter_by(id=sub_id, user_id=uid).first()
    if not sub:
        return jsonify(error="not found"), 404
        
    data = request.get_json() or {}
    if "target_url" in data:
        sub.target_url = data["target_url"]
    if "event_types" in data:
        sub.event_types = data["event_types"]
    if "active" in data:
        sub.active = bool(data["active"])
        
    db.session.commit()
    return jsonify(_sub_to_dict(sub))

@bp.delete("/<int:sub_id>")
@jwt_required()
def delete_webhook(sub_id: int):
    uid = int(get_jwt_identity())
    sub = WebhookSubscription.query.filter_by(id=sub_id, user_id=uid).first()
    if not sub:
        return jsonify(error="not found"), 404
        
    db.session.delete(sub)
    db.session.commit()
    return jsonify(message="deleted")

@bp.get("/<int:sub_id>/deliveries")
@jwt_required()
def list_deliveries(sub_id: int):
    uid = int(get_jwt_identity())
    sub = WebhookSubscription.query.filter_by(id=sub_id, user_id=uid).first()
    if not sub:
        return jsonify(error="not found"), 404
        
    logs = WebhookDeliveryLog.query.filter_by(subscription_id=sub.id).order_by(WebhookDeliveryLog.created_at.desc()).limit(50).all()
    return jsonify([_log_to_dict(l) for l in logs])

@bp.post("/<int:sub_id>/test")
@jwt_required()
def test_webhook(sub_id: int):
    uid = int(get_jwt_identity())
    sub = WebhookSubscription.query.filter_by(id=sub_id, user_id=uid).first()
    if not sub:
        return jsonify(error="not found"), 404
        
    test_data = {"test": True, "message": "This is a test webhook from FinMind"}
    WebhookService.emit_event(uid, sub.event_types[0] if sub.event_types else "test.event", test_data)
    return jsonify(message="Test webhook dispatched")

def _sub_to_dict(s):
    return {
        "id": s.id,
        "target_url": s.target_url,
        "event_types": s.event_types,
        "secret_key": s.secret_key,
        "active": s.active,
        "created_at": s.created_at.isoformat()
    }

def _log_to_dict(l):
    return {
        "id": l.id,
        "event_type": l.event_type,
        "response_status": l.response_status,
        "success": l.success,
        "created_at": l.created_at.isoformat()
    }
