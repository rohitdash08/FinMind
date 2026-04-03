"""Smart reminder timing routes."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.smart_reminder import analyze_timing, suggest_reminder_time

bp = Blueprint("smart_reminders", __name__)


@bp.get("/timing")
@jwt_required()
def timing_analysis():
    """Analyze optimal reminder timing based on user behavior."""
    uid = int(get_jwt_identity())
    return jsonify(analyze_timing(uid))


@bp.get("/suggest")
@jwt_required()
def suggest_time():
    """Suggest reminder date for a given due date.

    Query: due_date (YYYY-MM-DD)
    """
    uid = int(get_jwt_identity())
    raw = request.args.get("due_date")
    if not raw:
        return jsonify(error="due_date required"), 400
    try:
        due = date.fromisoformat(raw)
    except ValueError:
        return jsonify(error="invalid due_date"), 400

    suggested = suggest_reminder_time(uid, due)
    return jsonify({"due_date": due.isoformat(), "suggested_reminder": suggested.isoformat()})
