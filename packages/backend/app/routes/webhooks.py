from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Webhook
import secrets

bp = Blueprint("webhooks", __name__)

@bp.post("")
@jwt_required()
def create_webhook():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    url = data.get("url")
    if not url:
        return jsonify(error="url required"), 400
    
    # MZ Style Secret Generation: 폼 미친 랜덤 문자열
    secret = secrets.token_hex(16)
    
    wh = Webhook(
        user_id=uid,
        url=url,
        secret=secret,
        active=True
    )
    db.session.add(wh)
    db.session.commit()
    
    return jsonify({
        "id": wh.id,
        "url": wh.url,
        "secret": wh.secret,
        "active": wh.active,
        "created_at": wh.created_at.isoformat()
    }), 201

@bp.get("")
@jwt_required()
def list_webhooks():
    uid = int(get_jwt_identity())
    webhooks = Webhook.query.filter_by(user_id=uid).all()
    return jsonify([{
        "id": w.id,
        "url": w.url,
        "active": w.active,
        "created_at": w.created_at.isoformat()
    } for w in webhooks])

@bp.delete("/<int:webhook_id>")
@jwt_required()
def delete_webhook(webhook_id):
    uid = int(get_jwt_identity())
    wh = db.session.get(Webhook, webhook_id)
    if not wh or wh.user_id != uid:
        return jsonify(error="not found"), 404
    
    db.session.delete(wh)
    db.session.commit()
    return jsonify(message="deleted")
