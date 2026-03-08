from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import WebhookTarget, WebhookDelivery, WebhookEvent
from app.services.webhooks import WebhookService
import json
import time
import requests

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")


@webhooks_bp.route("/targets", methods=["POST"])
def create_webhook_target():
    """Create a new webhook target."""
    data = request.get_json()
    
    try:
        target = WebhookService.create_target(
            user_id=data["user_id"],
            url=data["url"],
            secret=data["secret"],
            events=data["events"]
        )
        
        return jsonify({
            "id": target.id,
            "url": target.url,
            "events": target.events,
            "enabled": target.enabled,
            "created_at": target.created_at.isoformat()
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@webhooks_bp.route("/targets", methods=["GET"])
def get_webhook_targets():
    """Get all webhook targets for the authenticated user."""
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id parameter is required"}), 400
        
    try:
        targets = WebhookService.get_targets(user_id=int(user_id))
        return jsonify([
            {
                "id": t.id,
                "url": t.url,
                "events": t.events,
                "enabled": t.enabled,
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat()
            } for t in targets
        ]), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@webhooks_bp.route("/targets/<int:target_id>", methods=["PUT"])
def update_webhook_target(target_id):
    """Update an existing webhook target."""
    data = request.get_json()
    
    try:
        target = WebhookService.update_target(target_id, **data)
        if not target:
            return jsonify({"error": "Webhook target not found"}), 404
            
        return jsonify({
            "id": target.id,
            "url": target.url,
            "events": target.events,
            "enabled": target.enabled,
            "created_at": target.created_at.isoformat(),
            "updated_at": target.updated_at.isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@webhooks_bp.route("/targets/<int:target_id>", methods=["DELETE"])
def delete_webhook_target(target_id):
    """Delete a webhook target."""
    try:
        WebhookService.delete_target(target_id)
        return "", 204
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@webhooks_bp.route("/deliveries", methods=["GET"])
def get_webhook_deliveries():
    """Get webhook delivery history."""
    target_id = request.args.get("target_id")
    user_id = request.args.get("user_id")
    
    query = WebhookDelivery.query
    
    if target_id:
        query = query.filter(WebhookDelivery.target_id == int(target_id))
    if user_id:
        query = query.join(WebhookTarget).filter(WebhookTarget.user_id == int(user_id))
        
    try:
        deliveries = query.order_by(WebhookDelivery.created_at.desc()).all()
        return jsonify([
            {
                "id": d.id,
                "target_id": d.target_id,
                "event_type": d.event_type,
                "status": d.status,
                "attempt_count": d.attempt_count,
                "last_attempt_at": d.last_attempt_at.isoformat() if d.last_attempt_at else None,
                "next_attempt_at": d.next_attempt_at.isoformat() if d.next_attempt_at else None,
                "response_status": d.response_status,
                "response_body": d.response_body,
                "created_at": d.created_at.isoformat()
            } for d in deliveries
        ]), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@webhooks_bp.route("/deliveries/<int:delivery_id>/redeliver", methods=["POST"])
def redeliver_webhook(delivery_id):
    """Redeliver a failed webhook."""
    try:
        WebhookService.redeliver(delivery_id)
        return jsonify({"message": "Webhook delivery scheduled"}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@webhooks_bp.route("/events", methods=["GET"])
def get_webhook_events():
    """Get all available webhook event types."""
    return jsonify([
        {"type": event.value, "description": WebhookService.get_event_description(event)}
        for event in WebhookEvent
    ]), 200


@webhooks_bp.route("/test", methods=["POST"])
def test_webhook():
    """Test webhook delivery to a specific URL."""
    data = request.get_json()
    
    try:
        test_payload = {
            "type": "test.event",
            "timestamp": int(time.time()),
            "data": {"message": "This is a test event"}
        }
        
        signature = WebhookService.generate_signature(
            data["secret"],
            json.dumps(test_payload),
            str(int(time.time()))
        )
        
        headers = {
            "Content-Type": "application/json",
            "X-FinMind-Event": "test.event",
            "X-FinMind-Timestamp": str(int(time.time())),
            "X-FinMind-Signature": f"sha256={signature}"
        }
        
        response = requests.post(data["url"], json=test_payload, headers=headers, timeout=10)
        
        return jsonify({
            "status": "success",
            "status_code": response.status_code,
            "response_body": response.text,
            "headers": dict(response.headers)
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@webhooks_bp.route("/event-types", methods=["GET"])
def get_event_types():
    """Get detailed information about all available event types."""
    return jsonify([
        {
            "type": event.value,
            "description": WebhookService.get_event_description(event),
            "payload_example": WebhookService.get_event_payload_example(event)
        } for event in WebhookEvent
    ]), 200
