"""Weekly summary routes for financial digest API."""
from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.weekly_summary import generate_weekly_summary
import logging

bp = Blueprint("weekly_summary", __name__)
logger = logging.getLogger("finmind.weekly_summary")


@bp.get("")
@jwt_required()
def get_weekly_summary():
    """Get weekly financial summary for the authenticated user.
    
    Query Parameters:
        week_of: ISO date string (YYYY-MM-DD) - any date within the target week
                 Defaults to current week
    
    Returns:
        WeeklySummary JSON object with trends, insights, and breakdowns
    """
    uid = int(get_jwt_identity())
    
    # Parse optional week parameter
    week_param = request.args.get("week_of")
    target_date = None
    if week_param:
        try:
            target_date = date.fromisoformat(week_param)
        except ValueError:
            return jsonify(error="Invalid week_of format. Use YYYY-MM-DD"), 400
    
    try:
        summary = generate_weekly_summary(uid, target_date)
        logger.info("Weekly summary served user=%s week=%s", uid, summary["week_start"])
        return jsonify(summary)
    except Exception as e:
        logger.exception("Failed to generate weekly summary user=%s", uid)
        return jsonify(error="Failed to generate summary"), 500
