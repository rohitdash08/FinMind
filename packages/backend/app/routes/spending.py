"""API route for essential vs discretionary spending breakdown (Issue #120)."""

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.spending_breakdown import get_spending_breakdown, classify_category

bp = Blueprint("spending_breakdown", __name__)
logger = logging.getLogger("finmind.spending_breakdown")


@bp.get("")
@jwt_required()
def breakdown():
    """Return essential vs discretionary spending breakdown for a month.

    Query params:
        month (str): YYYY-MM format, defaults to current month
    """
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()

    if len(ym) != 7 or ym[4] != "-":
        return jsonify(error="invalid month, expected YYYY-MM"), 400
    parts = ym.split("-")
    if not (parts[0].isdigit() and parts[1].isdigit()):
        return jsonify(error="invalid month, expected YYYY-MM"), 400
    year, month = int(parts[0]), int(parts[1])
    if not (1 <= month <= 12):
        return jsonify(error="invalid month, expected YYYY-MM"), 400

    result = get_spending_breakdown(uid, year, month)
    logger.info(
        "Spending breakdown user=%s period=%s essential=%.2f discretionary=%.2f",
        uid, ym, result.essential_total, result.discretionary_total,
    )
    return jsonify(result.to_dict())
