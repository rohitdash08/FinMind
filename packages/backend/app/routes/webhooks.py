"""
Webhook Routes for FinMind

Provides endpoints for:
- Registering webhook subscriptions
- Triggering webhook delivery
- Managing webhooks
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_babel import gettext
import logging

from ..extensions import db
from ..models import Webhook, User, WebhookDelivery, WebhookDeliveryStatus, WebhookAuditLog
from ..services.webhooks import webhook_service, WebhookEventType

bp = Blueprint("webhooks", __name__)
logger = logging.getLogger("finmind.webhooks")

# Configure rate limiter
limiter = Limiter(
    get_remote_address,
    app=bp,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=current_app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
)


@bp.get("")
@jwt_required()
def list_webhooks():
    """List all webhooks for the current user"""
    uid = int(get_jwt_identity())
    webhooks = db.session.query(Webhook).filter_by(user_id=uid).order_by(
        Webhook.created_at.desc()
    ).all()
    return jsonify([_webhook_to_dict(w) for w in webhooks])


@bp.post("")
@limiter.limit("10 per minute")
@jwt_required()
def create_webhook():
    """
    Register a new webhook subscription.

    Args:
        url (str, required): The webhook URL to receive events. Must start with http:// or https://
        secret (str, optional): Custom signing secret for webhook verification
        events (list[str], optional): List of event types to subscribe to. If None, all events are delivered.

    Returns:
        dict: Webhook details including masked secret

    Example:
        POST /webhooks
        {
            "url": "https://example.com/webhook",
            "secret": "my-secret-key",
            "events": ["expense.created", "bill.created"]
        }

    Response:
        {
            "id": 1,
            "url": "https://example.com/webhook",
            "secret": "my-se***",
            "events": ["expense.created", "bill.created"],
            "active": true,
            "created_at": "2026-03-09T13:38:00",
            "last_delivered_at": null
        }

    Errors:
        400: Invalid request (missing url, invalid url format, invalid events)
        401: Unauthorized
        409: Webhook URL already exists for user
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    url = data.get("url")
    if not url:
        return jsonify(error=gettext("url is required")), 400

    # Validate URL
    is_valid, error_msg = webhook_service._validate_url(url)
    if not is_valid:
        return jsonify(error=error_msg), 400

    # Validate events if provided
    events = data.get("events")
    if events is not None:
        valid_events = [e.value for e in WebhookEventType]
        invalid_events = [e for e in events if e not in valid_events]
        if invalid_events:
            return jsonify(
                error=gettext(f"Invalid events: {', '.join(invalid_events)}. "
                           f"Valid events: {', '.join(valid_events)}")
            ), 400

    webhook = Webhook(
        user_id=uid,
        url=url,
        secret=data.get("secret"),
        events=events,
        active=True,
    )
    db.session.add(webhook)
    db.session.commit()

    # Log audit
    _log_webhook_audit(
        webhook,
        "created",
        new_data=_webhook_to_dict(webhook),
        request_obj=request
    )

    logger.info("Created webhook id=%s for user=%s url=%s events=%s", webhook.id, uid, url, events)
    return jsonify(_webhook_to_dict(webhook)), 201


@bp.get("/events")
def list_available_events():
    """List all available webhook event types"""
    events = [
        {"type": e.value, "description": e.value.replace(".", " ").title()}
        for e in WebhookEventType
    ]
    return jsonify(events)


@bp.get("/deliveries/<int:webhook_id>")
@jwt_required()
def list_webhook_deliveries(webhook_id: int):
    """List delivery records for a specific webhook"""
    uid = int(get_jwt_identity())

    # Verify webhook belongs to user
    webhook = db.session.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != uid:
        return jsonify(error=gettext("not found")), 404

    # Get query parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')
    
    # Build query
    query = db.session.query(WebhookDelivery).filter_by(
        webhook_id=webhook_id
    )
    
    if status:
        query = query.filter_by(status=status)
    
    # Apply pagination
    pagination = query.order_by(WebhookDelivery.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    deliveries = pagination.items
    
    return jsonify({
        "deliveries": [_delivery_to_dict(d) for d in deliveries],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        }
    })


@bp.put("/<int:webhook_id>")
@jwt_required()
def update_webhook(webhook_id: int):
    """Update a webhook subscription"""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    webhook = db.session.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != uid:
        return jsonify(error=gettext("not found")), 404

    try:
        # Check version for optimistic locking
        client_version = data.get("version")
        if client_version is not None and webhook.version != client_version:
            return jsonify(
                error=gettext("Webhook has been modified by another request"),
                current_version=webhook.version
            ), 409

        # Store old data for audit log
        old_data = _webhook_to_dict(webhook)

        # Update fields
        if "url" in data:
            is_valid, error_msg = webhook_service._validate_url(data["url"])
            if not is_valid:
                return jsonify(error=error_msg), 400
            webhook.url = data["url"]

        if "events" in data:
            events = data["events"]
            if events is not None:
                valid_events = [e.value for e in WebhookEventType]
                invalid_events = [e for e in events if e not in valid_events]
                if invalid_events:
                    return jsonify(
                        error=gettext(f"Invalid events: {', '.join(invalid_events)}")
                    ), 400
            webhook.events = events

        if "active" in data:
            webhook.active = data["active"]

        # Increment version for optimistic locking
        webhook.version += 1

        db.session.commit()

        # Log audit
        _log_webhook_audit(
            webhook,
            "updated",
            old_data=old_data,
            new_data=_webhook_to_dict(webhook),
            request_obj=request
        )

        logger.info("Updated webhook id=%s for user=%s", webhook_id, uid)
        return jsonify(_webhook_to_dict(webhook)), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating webhook: {e}", exc_info=True)
        return jsonify(error=gettext("Failed to update webhook")), 500


@bp.delete("/<int:webhook_id>")
@jwt_required()
def delete_webhook(webhook_id: int):
    """Delete a webhook subscription"""
    uid = int(get_jwt_identity())

    webhook = db.session.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != uid:
        return jsonify(error=gettext("not found")), 404

    # Store data for audit log
    old_data = _webhook_to_dict(webhook)

    db.session.delete(webhook)
    db.session.commit()

    # Log audit (note: webhook_id will be None after delete, so we use a separate call)
    audit_log = WebhookAuditLog(
        webhook_id=webhook_id,
        user_id=uid,
        action="deleted",
        old_data=old_data,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    db.session.add(audit_log)
    db.session.commit()

    logger.info("Deleted webhook id=%s for user=%s", webhook_id, uid)
    return jsonify(message=gettext("webhook deleted"))


@bp.post("/test")
@jwt_required()
def test_webhook():
    """Test webhook delivery with a sample event"""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    webhook_id = data.get("webhook_id")
    if not webhook_id:
        return jsonify(error=gettext("webhook_id is required")), 400

    webhook = db.session.get(Webhook, webhook_id)
    if not webhook or webhook.user_id != uid:
        return jsonify(error=gettext("not found")), 404

    # Emit a test expense created event
    test_expense = {
        "id": 99999,
        "amount": 100.0,
        "currency": "USD",
        "expense_type": "EXPENSE",
        "description": "Test webhook event",
        "date": "2026-03-05",
        "category_id": 1,
    }

    payload = webhook_service._build_payload(
        WebhookEventType.EXPENSE_CREATED,
        test_expense,
        uid
    )

    success = webhook_service._deliver_webhook(payload)
    return jsonify({
        "success": success,
        "message": gettext("Test webhook delivered") if success else gettext("Test webhook failed")
    })


@bp.get("/health")
def webhook_health():
    """Health check endpoint for webhooks"""
    try:
        # Check database connection
        db.session.execute(db.text("SELECT 1"))
        
        # Check webhook service configuration
        config_valid = webhook_service._validate_config()
        
        # Check retry queue (if using Celery)
        queue_status = "unknown"
        try:
            from ..tasks import retry_webhook_delivery
            queue_status = "ready"
        except ImportError:
            queue_status = "not configured"
        
        return jsonify({
            "status": "healthy" if config_valid else "degraded",
            "config_valid": config_valid,
            "queue_status": queue_status,
            "version": "1.0.0"
        }), 200
    except Exception as e:
        logger.error(f"Webhook health check failed: {e}", exc_info=True)
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 503


def _log_webhook_audit(webhook: Webhook, action: str, old_data: dict = None, new_data: dict = None, request_obj=None):
    """Record webhook operation audit log"""
    audit_log = WebhookAuditLog(
        webhook_id=webhook.id,
        user_id=webhook.user_id,
        action=action,
        old_data=old_data,
        new_data=new_data,
        ip_address=request_obj.remote_addr if request_obj else None,
        user_agent=request_obj.headers.get('User-Agent') if request_obj else None
    )
    db.session.add(audit_log)
    db.session.commit()


def _webhook_to_dict(w: Webhook) -> dict:
    """Convert Webhook model to dict"""
    return {
        "id": w.id,
        "url": w.url,
        "secret": w.secret[:8] + "..." if w.secret else None,  # Mask secret
        "events": w.events,
        "active": w.active,
        "created_at": w.created_at.isoformat(),
        "last_delivered_at": w.last_delivered_at.isoformat() if w.last_delivered_at else None,
        "version": w.version,
    }


def _delivery_to_dict(d: WebhookDelivery) -> dict:
    """Convert WebhookDelivery model to dict"""
    return {
        "id": d.id,
        "webhook_id": d.webhook_id,
        "event_type": d.event_type,
        "status": d.status,
        "response_status": d.response_status,
        "error_message": d.error_message,
        "retry_count": d.retry_count,
        "last_attempt_at": d.last_attempt_at.isoformat() if d.last_attempt_at else None,
        "created_at": d.created_at.isoformat(),
    }
