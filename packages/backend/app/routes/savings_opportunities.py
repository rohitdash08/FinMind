from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.savings_opportunities import detect_savings_opportunities
import logging

bp = Blueprint("savings_opportunities", __name__)
logger = logging.getLogger("finmind.savings_opportunities_route")


@bp.get("/savings-opportunities")
@jwt_required()
def get_savings_opportunities():
    """
    GET /insights/savings-opportunities?month=YYYY-MM

    Returns ranked savings opportunities for the authenticated user
    based on their spending patterns in the given month.

    Query params:
      month  — target month in YYYY-MM format (default: current month)

    Response 200:
      {
        "month": "2026-03",
        "total_spent": 45200.0,
        "total_potential_savings": 6800.5,
        "opportunities_count": 4,
        "opportunities": [
          {
            "id": "overspend-12",
            "title": "High spending in Dining",
            "description": "...",
            "category": "Dining",
            "estimated_savings": 4200.0,
            "priority": "high",
            "rule": "category_overspend"
          },
          ...
        ]
      }
    """
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()

    result = detect_savings_opportunities(uid, ym)
    logger.info(
        "Savings opportunities served user=%s month=%s count=%d",
        uid, ym, result["opportunities_count"],
    )
    return jsonify(result)
