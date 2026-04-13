"""Webhook event system endpoints."""
import hashlib, hmac, json
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import WebhookSubscription
import logging, requests as req_lib

bp = Blueprint("webhooks", __name__)
logger = logging.getLogger("finmind.webhooks")

VALID_EVENTS = {"expense.created", "expense.updated", "expense.deleted", "bill.due", "goal.reached", "anomaly.detected"}

def _sub_to_dict(s):
    return {"id": s.id, "url": s.url, "events": s.events.split(","), "active": s.active, "created_at": s.created_at.isoformat()}

@bp.get("")
@jwt_required()
def list_subscriptions():
    uid = int(get_jwt_identity())
    subs = db.session.query(WebhookSubscription).filter_by(user_id=uid).order_by(WebhookSubscription.created_at.desc()).all()
    return jsonify([_sub_to_dict(s) for s in subs])

@bp.post("")
@jwt_required()
def create_subscription():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="url required"), 400
    events = data.get("events", [])
    if not events or not isinstance(events, list):
        return jsonify(error="events list required"), 400
    invalid = set(events) - VALID_EVENTS
    if invalid:
        return jsonify(error=f"invalid events: {', '.join(invalid)}"), 400
    sub = WebhookSubscription(user_id=uid, url=url, events=",".join(events), secret=data.get("secret"), active=True)
    db.session.add(sub)
    db.session.commit()
    return jsonify(_sub_to_dict(sub)), 201

@bp.delete("/<int:sub_id>")
@jwt_required()
def delete_subscription(sub_id):
    uid = int(get_jwt_identity())
    sub = db.session.get(WebhookSubscription, sub_id)
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(sub)
    db.session.commit()
    return jsonify(message="deleted")

@bp.get("/events")
@jwt_required()
def list_events():
    return jsonify(events=sorted(VALID_EVENTS))

@bp.post("/test")
@jwt_required()
def test_webhook():
    """Send a test event to a subscription."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    sub_id = data.get("subscription_id")
    sub = db.session.get(WebhookSubscription, sub_id) if sub_id else None
    if not sub or sub.user_id != uid:
        return jsonify(error="subscription not found"), 404
    payload = {"event": "test", "user_id": uid, "message": "Test webhook delivery"}
    headers = {"Content-Type": "application/json"}
    if sub.secret:
        sig = hmac.new(sub.secret.encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()
        headers["X-Webhook-Signature"] = sig
    try:
        resp = req_lib.post(sub.url, json=payload, headers=headers, timeout=5)
        return jsonify(delivered=True, status_code=resp.status_code)
    except Exception as e:
        return jsonify(delivered=False, error=str(e))
