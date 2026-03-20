"""Route: GET /insights/budget-suggestions — Dynamic Budget Suggestions (#73)."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.budget_suggestions import get_budget_suggestions

bp = Blueprint("budget_suggestions", __name__)


@bp.get("/budget-suggestions")
@jwt_required()
def get_suggestions():
    """Return dynamic budget suggestions for the authenticated user.

    Query params:
      month (str, optional): YYYY-MM anchor month. Defaults to current month.
        The service analyses the MAX_MONTHS (6) months prior to this anchor.

    Returns 200 with:
      {
        "reference_months": ["YYYY-MM", ...],
        "suggestions_count": int,
        "suggestions": [ BudgetSuggestion, ... ]
      }
    """
    uid = int(get_jwt_identity())
    anchor = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()

    result = get_budget_suggestions(uid, anchor)
    return jsonify(result), 200