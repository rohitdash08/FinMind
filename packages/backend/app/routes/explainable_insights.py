from flask import Blueprint, request, jsonify, g
from datetime import datetime
from ..services.explainable_insights import ExplainableInsightsService
from ..middleware.auth import require_auth

insights_bp = Blueprint("insights", __name__)
svc = ExplainableInsightsService()

@insights_bp.route("/api/analytics/insights", methods=["GET"])
@require_auth
def get_insights():
    """Get explainable spending insights for a month."""
    user_id = g.user_id
    now = datetime.utcnow()
    year = int(request.args.get("year", now.year))
    month = int(request.args.get("month", now.month))
    result = svc.get_insights(user_id, year=year, month=month)
    return jsonify(result)