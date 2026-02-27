"""Savings opportunity detection API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.savings_opportunities import detect_opportunities
import logging

bp = Blueprint("savings_opportunities", __name__)
logger = logging.getLogger("finmind.savings_opportunities")


@bp.get("/")
@jwt_required()
def get_opportunities():
    uid = int(get_jwt_identity())
    months = int(request.args.get("months", 3))
    result = detect_opportunities(uid, months)
    logger.info("Savings opportunities user=%s found=%s", uid, len(result["opportunities"]))
    return jsonify(result)
