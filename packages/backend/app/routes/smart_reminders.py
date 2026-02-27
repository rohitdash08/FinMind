"""Smart reminder timing optimization API."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.smart_reminder import (
    get_preference, update_preference, analyze_payment_patterns,
    optimize_reminders, suggest_reminder_time,
)
import logging

bp = Blueprint("smart_reminders", __name__)
logger = logging.getLogger("finmind.smart_reminders")


@bp.get("/preference")
@jwt_required()
def get_pref():
    uid = int(get_jwt_identity())
    return jsonify(get_preference(uid))


@bp.put("/preference")
@jwt_required()
def update_pref():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    result = update_preference(
        uid,
        hour=data.get("preferred_hour"),
        day_offset=data.get("preferred_day_offset"),
        auto_optimize=data.get("auto_optimize"),
    )
    return jsonify(result)


@bp.get("/patterns")
@jwt_required()
def patterns():
    uid = int(get_jwt_identity())
    return jsonify(analyze_payment_patterns(uid))


@bp.post("/optimize")
@jwt_required()
def optimize():
    uid = int(get_jwt_identity())
    result = optimize_reminders(uid)
    logger.info("Reminder optimization user=%s optimized=%s", uid, result["optimized"])
    return jsonify(result)


@bp.get("/suggest")
@jwt_required()
def suggest():
    uid = int(get_jwt_identity())
    due = request.args.get("due_date")
    if not due:
        return jsonify({"error": "due_date query param required (YYYY-MM-DD)"}), 400
    try:
        due_date = date.fromisoformat(due)
    except ValueError:
        return jsonify({"error": "Invalid date format, use YYYY-MM-DD"}), 400
    return jsonify(suggest_reminder_time(uid, due_date))
