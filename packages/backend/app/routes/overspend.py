"""Category overspend early warning routes."""

import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.overspend_warning import check_overspend

bp = Blueprint("overspend", __name__)
logger = logging.getLogger("finmind.overspend")


@bp.get("")
@jwt_required()
def overspend_warnings():
    """Return overspend warnings for all categories this month.

    Query params:
        reference_months (int): Past months for baseline (default 3, max 12).
        level (str): Filter by warning level (optional).
    """
    uid = int(get_jwt_identity())

    try:
        ref_months = min(12, max(1, int(request.args.get("reference_months", "3"))))
    except (ValueError, TypeError):
        ref_months = 3

    level_filter = request.args.get("level", "").lower().strip() or None

    warnings = check_overspend(uid, reference_months=ref_months)

    if level_filter:
        warnings = [w for w in warnings if w["level"] == level_filter]

    return jsonify(warnings)
