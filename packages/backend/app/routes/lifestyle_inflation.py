"""Lifestyle inflation detection API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.lifestyle_inflation import detect_inflation
import logging

bp = Blueprint("lifestyle_inflation", __name__)
logger = logging.getLogger("finmind.lifestyle_inflation")


@bp.get("/")
@jwt_required()
def get_inflation():
    uid = int(get_jwt_identity())
    months = int(request.args.get("months", 6))
    result = detect_inflation(uid, months)
    logger.info("Inflation analysis user=%s detected=%s", uid, result["inflation_detected"])
    return jsonify(result)
