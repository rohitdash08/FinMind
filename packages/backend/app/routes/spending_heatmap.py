from flask import Blueprint, request, jsonify, g
from datetime import datetime, timedelta
from ..services.spending_heatmap import SpendingHeatmapService
from ..middleware.auth import require_auth

spending_heatmap_bp = Blueprint("spending_heatmap", __name__)
svc = SpendingHeatmapService()

@spending_heatmap_bp.route("/api/analytics/spending-heatmap", methods=["GET"])
@require_auth
def get_spending_heatmap():
    """
    Returns spending data structured for heatmap visualization.
    Query params:
      - period: "month" (default), "year"
      - category: filter by category (optional)
      - year: YYYY (default: current year)
      - month: MM (default: current month, when period=month)
    """
    user_id = g.user_id
    period = request.args.get("period", "month")
    year = int(request.args.get("year", datetime.utcnow().year))
    month = int(request.args.get("month", datetime.utcnow().month))
    category = request.args.get("category")

    if period == "month":
        heatmap = svc.monthly_heatmap(user_id, year=year, month=month, category=category)
    else:
        heatmap = svc.yearly_heatmap(user_id, year=year, category=category)

    return jsonify(heatmap)

@spending_heatmap_bp.route("/api/analytics/spending-heatmap/summary", methods=["GET"])
@require_auth
def get_heatmap_summary():
    """Returns peak spending days and categories for the given period."""
    user_id = g.user_id
    year = int(request.args.get("year", datetime.utcnow().year))
    month = int(request.args.get("month", datetime.utcnow().month))
    summary = svc.peak_spending_summary(user_id, year=year, month=month)
    return jsonify(summary)
