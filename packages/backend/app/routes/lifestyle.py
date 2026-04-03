"""Lifestyle inflation detection routes."""

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.lifestyle_inflation import detect_lifestyle_inflation

bp = Blueprint("lifestyle", __name__)
logger = logging.getLogger("finmind.lifestyle")


@bp.get("")
@jwt_required()
def inflation_report():
    """Return a lifestyle inflation analysis report.

    Query params:
        months (int): How many months to analyze (default 6, max 24).
    """
    uid = int(get_jwt_identity())

    try:
        months = min(24, max(2, int(request.args.get("months", "6"))))
    except (ValueError, TypeError):
        months = 6

    report = detect_lifestyle_inflation(uid, months=months)
    logger.info("Lifestyle inflation check user=%s trend=%s", uid, report["overall_trend"])
    return jsonify(report)
