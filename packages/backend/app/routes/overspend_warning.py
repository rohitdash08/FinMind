"""Route: GET /insights/overspend-warnings — Category Overspend Early Warning (#117)."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.overspend_warning import get_overspend_warnings

bp = Blueprint("overspend_warning", __name__)


@bp.get("/overspend-warnings")
@jwt_required()
def overspend_warnings():
    """Return early overspend warnings for categories in the current month.

    Query params:
      month (str, optional): YYYY-MM format. Defaults to current month.

    Returns 200 with:
      {
        "month": "YYYY-MM",
        "days_elapsed": int,
        "days_in_month": int,
        "warnings": [ OverspendWarning, ... ],
        "warning_count": int,
        "critical_count": int,
        "over_budget_count": int,
        "total_at_risk": float
      }
    """
    uid = int(get_jwt_identity())
    month = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()

    result = get_overspend_warnings(uid, month)
    return jsonify(result), 200