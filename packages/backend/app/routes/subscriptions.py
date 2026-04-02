"""
Subscriptions API routes for auto-detected recurring charges.
"""

from datetime import date
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Subscription, SubscriptionStatus, SubscriptionCadence, User
from ..services.subscription_detector import detect_and_create_subscriptions, SubscriptionDetector
import logging

bp = Blueprint("subscriptions", __name__)
logger = logging.getLogger("finmind.subscriptions")


@bp.get("")
@jwt_required()
def list_subscriptions():
    """
    List subscriptions for the current user.
    Query params:
    - status: filter by status (DETECTED, CONFIRMED, DISMISSED). Default: all.
    """
    uid = int(get_jwt_identity())
    q = db.session.query(Subscription).filter_by(user_id=uid)
    
    status_filter = request.args.get("status", "").upper()
    if status_filter in [s.value for s in SubscriptionStatus]:
        q = q.filter_by(status=SubscriptionStatus(status_filter))
    
    items = q.order_by(Subscription.created_at.desc()).all()
    return jsonify([_subscription_to_dict(s) for s in items])


@bp.post("/detect")
@jwt_required()
def detect_subscriptions():
    """
    Manually trigger subscription detection for the current user.
    Returns list of newly detected subscriptions.
    """
    uid = int(get_jwt_identity())
    
    try:
        new_subs = detect_and_create_subscriptions(uid)
        return jsonify({
            "detected": len(new_subs),
            "subscriptions": [_subscription_to_dict(s) for s in new_subs]
        }), 201
    except Exception as e:
        logger.exception("Subscription detection failed user=%s", uid)
        return jsonify(error="detection failed", details=str(e)), 500


@bp.post("/<int:subscription_id>/confirm")
@jwt_required()
def confirm_subscription(subscription_id: int):
    """
    Confirm a detected subscription (user accepts it as a real subscription).
    """
    uid = int(get_jwt_identity())
    sub = db.session.get(Subscription, subscription_id)
    
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404
    
    if sub.status != SubscriptionStatus.DETECTED:
        return jsonify(error="only DETECTED subscriptions can be confirmed"), 400
    
    sub.status = SubscriptionStatus.CONFIRMED
    db.session.commit()
    
    logger.info("Confirmed subscription id=%s user=%s", subscription_id, uid)
    return jsonify(_subscription_to_dict(sub)), 200


@bp.post("/<int:subscription_id>/dismiss")
@jwt_required()
def dismiss_subscription(subscription_id: int):
    """
    Dismiss a detected subscription (user rejects the detection).
    """
    uid = int(get_jwt_identity())
    sub = db.session.get(Subscription, subscription_id)
    
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404
    
    if sub.status == SubscriptionStatus.DISMISSED:
        return jsonify(error="already dismissed"), 400
    
    sub.status = SubscriptionStatus.DISMISSED
    db.session.commit()
    
    logger.info("Dismissed subscription id=%s user=%s", subscription_id, uid)
    return jsonify(_subscription_to_dict(sub)), 200


@bp.delete("/<int:subscription_id>")
@jwt_required()
def delete_subscription(subscription_id: int):
    """
    Delete a subscription (soft-delete by setting status to DISMISSED).
    """
    uid = int(get_jwt_identity())
    sub = db.session.get(Subscription, subscription_id)
    
    if not sub or sub.user_id != uid:
        return jsonify(error="not found"), 404
    
    # Soft delete: mark as dismissed
    sub.status = SubscriptionStatus.DISMISSED
    db.session.commit()
    
    logger.info("Deleted subscription id=%s user=%s", subscription_id, uid)
    return jsonify(message="deleted"), 200


@bp.get("/predictions/refresh")
@jwt_required()
def refresh_predictions():
    """
    Refresh next_predicted_date for all CONFIRMED subscriptions.
    This can be run periodically via cron.
    """
    uid = int(get_jwt_identity())
    
    try:
        detector = SubscriptionDetector()
        detector.refresh_predictions(uid)
        return jsonify(message="predictions refreshed"), 200
    except Exception as e:
        logger.exception("Prediction refresh failed user=%s", uid)
        return jsonify(error="refresh failed", details=str(e)), 500


def _subscription_to_dict(s: Subscription) -> dict:
    """Convert Subscription model to dict for JSON response."""
    return {
        "id": s.id,
        "merchant_name": s.merchant_name,
        "category_id": s.category_id,
        "amount": float(s.amount),
        "currency": s.currency,
        "detected_cadence": s.detected_cadence.value,
        "confidence_score": float(s.confidence_score),
        "occurrence_count": s.occurrence_count,
        "first_occurrence_date": s.first_occurrence_date.isoformat(),
        "last_occurrence_date": s.last_occurrence_date.isoformat(),
        "next_predicted_date": s.next_predicted_date.isoformat() if s.next_predicted_date else None,
        "average_amount": float(s.average_amount) if s.average_amount else None,
        "amount_variance": float(s.amount_variance) if s.amount_variance else None,
        "status": s.status.value,
        "notes": s.notes,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
    }