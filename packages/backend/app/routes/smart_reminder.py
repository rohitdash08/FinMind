"""Smart reminder timing optimization routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.smart_reminder import (
    log_activity,
    get_activity_pattern,
    get_preferences,
    update_preferences,
    get_optimal_time,
    get_optimal_days,
    should_send_reminder,
)

bp = Blueprint("smart_reminder", __name__)


@bp.post("/activity")
@jwt_required()
def log_activity_route():
    """Log a user activity event for timing analysis."""
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data or not data.get("action"):
        return jsonify({"error": "Action is required"}), 400

    result = log_activity(user_id, data["action"])
    return jsonify(result), 201


@bp.get("/activity/pattern")
@jwt_required()
def get_pattern_route():
    """Get user activity pattern analysis."""
    user_id = int(get_jwt_identity())
    result = get_activity_pattern(user_id)
    return jsonify(result), 200


@bp.get("/preferences")
@jwt_required()
def get_preferences_route():
    """Get reminder preferences."""
    user_id = int(get_jwt_identity())
    result = get_preferences(user_id)
    return jsonify(result), 200


@bp.put("/preferences")
@jwt_required()
def update_preferences_route():
    """Update reminder preferences."""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    result = update_preferences(user_id, **data)
    return jsonify(result), 200


@bp.get("/optimal-time")
@jwt_required()
def get_optimal_time_route():
    """Get optimal reminder delivery time."""
    user_id = int(get_jwt_identity())
    result = get_optimal_time(user_id)
    return jsonify(result), 200


@bp.get("/optimal-days")
@jwt_required()
def get_optimal_days_route():
    """Get optimal reminder delivery days."""
    user_id = int(get_jwt_identity())
    result = get_optimal_days(user_id)
    return jsonify(result), 200


@bp.get("/should-send")
@jwt_required()
def should_send_route():
    """Check if a reminder should be sent now."""
    user_id = int(get_jwt_identity())
    hour = request.args.get("hour", type=int)
    result = should_send_reminder(user_id, current_hour=hour)
    return jsonify(result), 200
