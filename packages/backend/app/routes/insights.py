from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion
from ..services.weekly_digest import generate_weekly_digest, _week_range
from ..services.cache import cache_get, cache_set
import logging

bp = Blueprint("insights", __name__)
logger = logging.getLogger("finmind.insights")


@bp.get("/budget-suggestion")
@jwt_required()
def budget_suggestion():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None
    suggestion = monthly_budget_suggestion(
        uid,
        ym,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    logger.info("Budget suggestion served user=%s month=%s", uid, ym)
    return jsonify(suggestion)


@bp.get("/weekly-digest")
@jwt_required()
def weekly_digest():
    """Generate a weekly financial summary with trends and insights.

    Query params:
      - week_start: ISO date (YYYY-MM-DD) for the Monday of the target week.
                    Defaults to the current week.

    Returns:
      - period: week date range
      - summary: income, expenses, net, transaction count
      - trends: week-over-week spending change percentage
      - categories: spending breakdown by category
      - insights: human-readable financial insights
    """
    uid = int(get_jwt_identity())
    ws_param = request.args.get("week_start", "").strip()

    if ws_param:
        try:
            week_start = date.fromisoformat(ws_param)
        except ValueError:
            return jsonify(error="Invalid week_start format, expected YYYY-MM-DD"), 400
    else:
        week_start = None

    # Generate digest (uses DB queries)
    digest = generate_weekly_digest(uid, week_start)

    logger.info("Weekly digest served user=%s week=%s", uid, digest["period"]["label"])
    return jsonify(digest)
