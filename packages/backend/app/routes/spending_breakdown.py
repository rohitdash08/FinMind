"""Route: GET /insights/spending-breakdown — Essential vs Discretionary (#120)."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.spending_breakdown import get_spending_breakdown

bp = Blueprint("spending_breakdown", __name__)


@bp.get("/spending-breakdown")
@jwt_required()
def get_breakdown():
    """Return essential vs discretionary spending breakdown for the authenticated user.

    Query params:
      month (str, optional): YYYY-MM format. Defaults to the current month.

    Returns 200 with:
      {
        "month": "YYYY-MM",
        "total_spent": float,
        "essential_total": float,
        "discretionary_total": float,
        "uncategorized_total": float,
        "essential_percentage": float,
        "discretionary_percentage": float,
        "uncategorized_percentage": float,
        "categories": [ CategoryBreakdown, ... ],
        "insight": str
      }
    """
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()

    result = get_spending_breakdown(uid, ym)
    return jsonify(result), 200