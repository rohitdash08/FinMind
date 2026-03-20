from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.reminder_timing import get_optimized_reminder_timing

bp = Blueprint("reminder_timing", __name__)


@bp.route("/reminder-timing", methods=["GET"])
@jwt_required()
def reminder_timing():
    """
    GET /insights/reminder-timing?months=3

    Analyzes payment behavior to suggest optimal reminder timing.
    Returns per-reminder suggestions plus general payment behavior insights.
    """
    user_id = get_jwt_identity()
    try:
        months = int(request.args.get("months", 3))
    except (ValueError, TypeError):
        months = 3

    result = get_optimized_reminder_timing(user_id=int(user_id), months=months)

    return jsonify(
        {
            "avg_days_before_payment": result.avg_days_before_payment,
            "on_time_rate": result.on_time_rate,
            "general_recommendation": result.general_recommendation,
            "summary": result.summary,
            "optimized_reminders": [
                {
                    "reminder_id": r.reminder_id,
                    "current_reminder_days_before": r.current_reminder_days_before,
                    "suggested_days_before": r.suggested_days_before,
                    "reasoning": r.reasoning,
                    "confidence": r.confidence,
                }
                for r in result.optimized_reminders
            ],
        }
    )