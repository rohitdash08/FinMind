"""Routes for auto-detected subscription management.

Provides endpoints for:
  - Triggering subscription detection scan
  - Listing detected subscriptions
  - Getting subscription details
  - Updating subscription status (confirm/dismiss)
  - Getting monthly cost summary
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import subscription_detection as svc

bp = Blueprint("subscriptions", __name__)


@bp.post("/scan")
@jwt_required()
def scan_subscriptions():
    """Scan user's expenses to auto-detect subscription patterns.

    Analyzes all transaction history for recurring patterns and
    creates/updates detected subscription records.

    Returns:
        200: List of detected subscriptions with confidence scores
    """
    uid = int(get_jwt_identity())
    results = svc.detect_subscriptions_for_user(uid)
    return jsonify({
        "detected_count": len(results),
        "subscriptions": results,
    }), 200


@bp.get("")
@jwt_required()
def list_subscriptions():
    """List all detected subscriptions for the current user.

    Query params:
        active_only: bool (default true) - filter to active subscriptions only

    Returns:
        200: List of detected subscriptions
    """
    uid = int(get_jwt_identity())
    active_only = request.args.get("active_only", "true").lower() != "false"
    subs = svc.get_subscriptions(uid, active_only=active_only)
    return jsonify(subs), 200


@bp.get("/summary")
@jwt_required()
def subscription_summary():
    """Get monthly/yearly subscription cost summary.

    Returns:
        200: Cost summary including per-subscription monthly equivalents
    """
    uid = int(get_jwt_identity())
    summary = svc.get_monthly_subscription_cost(uid)
    return jsonify(summary), 200


@bp.get("/<int:sub_id>")
@jwt_required()
def get_subscription(sub_id: int):
    """Get details of a specific detected subscription.

    Returns:
        200: Subscription details
        404: Subscription not found
    """
    uid = int(get_jwt_identity())
    sub = svc.get_subscription_by_id(uid, sub_id)
    if not sub:
        return jsonify(error="Subscription not found"), 404
    return jsonify(svc._sub_to_dict(sub)), 200


@bp.patch("/<int:sub_id>/status")
@jwt_required()
def update_status(sub_id: int):
    """Update subscription status (confirmed, dismissed, detected).

    Body:
        status: str - one of 'confirmed', 'dismissed', 'detected'

    Returns:
        200: Updated subscription
        400: Invalid status
        404: Subscription not found
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    status = data.get("status", "").strip().lower()

    if status not in ("confirmed", "dismissed", "detected"):
        return jsonify(error="Invalid status. Must be: confirmed, dismissed, or detected"), 400

    result = svc.update_subscription_status(uid, sub_id, status)
    if not result:
        return jsonify(error="Subscription not found"), 404

    return jsonify(result), 200
