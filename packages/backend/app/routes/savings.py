"""Savings opportunity detection routes."""

import logging

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.savings import detect_savings_opportunities

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


@bp.get("/opportunities")
@jwt_required()
def savings_opportunities():
    """Return detected savings opportunities for the authenticated user."""
    uid = int(get_jwt_identity())
    result = detect_savings_opportunities(uid)
    return jsonify(result)
