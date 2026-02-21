from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import secrets
from ..models import WebhookSubscription, db

bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")

@bp.post("/subscribe")
@jwt_required()
def subscribe():
    user_id = get_jwt_identity()
    data = request.get_json()
    
    url = data.get("url")
    if not url:
        return jsonify(error="url is required"), 400
        
    # Generate a secret for the user to verify signatures
    secret = secrets.token_hex(32)
    
    sub = WebhookSubscription(
        user_id=user_id,
        url=url,
        secret=secret
    )
    db.session.add(sub)
    db.session.commit()
    
    return jsonify({
        "id": sub.id,
        "url": sub.url,
        "secret": sub.secret,
        "msg": "Store this secret securely to verify webhook signatures."
    }), 201

@bp.get("/")
@jwt_required()
def list_subscriptions():
    user_id = get_jwt_identity()
    subs = WebhookSubscription.query.filter_by(user_id=user_id).all()
    return jsonify([{
        "id": s.id,
        "url": s.url,
        "is_active": s.is_active,
        "created_at": s.created_at.isoformat()
    } for s in subs]), 200

@bp.delete("/<int:sub_id>")
@jwt_required()
def unsubscribe(sub_id):
    user_id = get_jwt_identity()
    sub = WebhookSubscription.query.filter_by(id=sub_id, user_id=user_id).first_or_404()
    db.session.delete(sub)
    db.session.commit()
    return jsonify(status="deleted"), 200
