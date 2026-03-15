"""Routes for category overspend early warning system.

Provides endpoints for:
  - Budget management (CRUD)
  - Budget status checking
  - Alert generation and management
  - Spending forecast
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import overspend as svc

bp = Blueprint("budgets", __name__)


# ─── Budget CRUD ────────────────────────────────────────────────────────


@bp.post("")
@jwt_required()
def create_budget():
    """Create a monthly budget for a category.

    Body:
        category_id: int (required)
        monthly_limit: float (required)
        currency: str (default 'INR')
        warning_threshold: float (default 80.0)
        critical_threshold: float (default 95.0)

    Returns:
        201: Created budget
        400: Missing required fields or invalid category
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    category_id = data.get("category_id")
    monthly_limit = data.get("monthly_limit")

    if not category_id or monthly_limit is None:
        return jsonify(error="category_id and monthly_limit are required"), 400

    try:
        monthly_limit = float(monthly_limit)
        if monthly_limit <= 0:
            raise ValueError("must be positive")
    except (TypeError, ValueError):
        return jsonify(error="monthly_limit must be a positive number"), 400

    result = svc.create_budget(
        user_id=uid,
        category_id=int(category_id),
        monthly_limit=monthly_limit,
        currency=data.get("currency", "INR"),
        warning_threshold=float(data.get("warning_threshold", 80.0)),
        critical_threshold=float(data.get("critical_threshold", 95.0)),
    )

    if result is None:
        return jsonify(error="Category not found or does not belong to user"), 400

    return jsonify(result), 201


@bp.get("")
@jwt_required()
def list_budgets():
    """List all category budgets for the current user.

    Query params:
        active_only: bool (default true)

    Returns:
        200: List of budgets
    """
    uid = int(get_jwt_identity())
    active_only = request.args.get("active_only", "true").lower() != "false"
    budgets = svc.get_budgets(uid, active_only=active_only)
    return jsonify(budgets), 200


@bp.get("/<int:budget_id>")
@jwt_required()
def get_budget(budget_id: int):
    """Get a specific budget by ID.

    Returns:
        200: Budget details
        404: Budget not found
    """
    uid = int(get_jwt_identity())
    budget = svc.get_budget_by_id(uid, budget_id)
    if not budget:
        return jsonify(error="Budget not found"), 404
    return jsonify(svc._budget_to_dict(budget)), 200


@bp.patch("/<int:budget_id>")
@jwt_required()
def update_budget(budget_id: int):
    """Update a budget's settings.

    Body (all optional):
        monthly_limit: float
        warning_threshold: float
        critical_threshold: float
        is_active: bool
        currency: str

    Returns:
        200: Updated budget
        404: Budget not found
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    result = svc.update_budget(uid, budget_id, data)
    if result is None:
        return jsonify(error="Budget not found"), 404
    return jsonify(result), 200


@bp.delete("/<int:budget_id>")
@jwt_required()
def delete_budget(budget_id: int):
    """Deactivate a budget.

    Returns:
        200: Success message
        404: Budget not found
    """
    uid = int(get_jwt_identity())
    if svc.delete_budget(uid, budget_id):
        return jsonify(message="Budget deactivated"), 200
    return jsonify(error="Budget not found"), 404


# ─── Budget status & alerts ─────────────────────────────────────────────


@bp.get("/status")
@jwt_required()
def budget_status():
    """Check spending status against all active budgets.

    Returns current spending, remaining budget, alert level,
    and daily safe-to-spend amount.

    Returns:
        200: List of budget statuses
    """
    uid = int(get_jwt_identity())
    statuses = svc.check_budget_status(uid)
    return jsonify(statuses), 200


@bp.get("/forecast")
@jwt_required()
def spending_forecast():
    """Forecast end-of-month spending based on current rate.

    Projects whether each budget will be exceeded by extrapolating
    the current daily spending rate.

    Returns:
        200: List of spending forecasts
    """
    uid = int(get_jwt_identity())
    forecasts = svc.get_spending_forecast(uid)
    return jsonify(forecasts), 200


@bp.post("/alerts/generate")
@jwt_required()
def generate_alerts():
    """Evaluate all budgets and generate alerts for threshold breaches.

    Returns:
        200: List of newly generated alerts
    """
    uid = int(get_jwt_identity())
    alerts = svc.generate_alerts(uid)
    return jsonify({"new_alerts": len(alerts), "alerts": alerts}), 200


@bp.get("/alerts")
@jwt_required()
def list_alerts():
    """List overspend alerts.

    Query params:
        unread_only: bool (default false)
        limit: int (default 50)

    Returns:
        200: List of alerts
    """
    uid = int(get_jwt_identity())
    unread_only = request.args.get("unread_only", "false").lower() == "true"
    try:
        limit = min(200, max(1, int(request.args.get("limit", "50"))))
    except ValueError:
        limit = 50
    alerts = svc.get_alerts(uid, unread_only=unread_only, limit=limit)
    return jsonify(alerts), 200


@bp.patch("/alerts/<int:alert_id>/read")
@jwt_required()
def mark_read(alert_id: int):
    """Mark a specific alert as read.

    Returns:
        200: Success
        404: Alert not found
    """
    uid = int(get_jwt_identity())
    if svc.mark_alert_read(uid, alert_id):
        return jsonify(message="Alert marked as read"), 200
    return jsonify(error="Alert not found"), 404


@bp.post("/alerts/read-all")
@jwt_required()
def mark_all_read():
    """Mark all unread alerts as read.

    Returns:
        200: Count of alerts marked as read
    """
    uid = int(get_jwt_identity())
    count = svc.mark_all_alerts_read(uid)
    return jsonify({"marked_read": count}), 200
