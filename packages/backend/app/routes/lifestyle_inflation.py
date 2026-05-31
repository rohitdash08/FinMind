from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.lifestyle_inflation import detect_lifestyle_creep
import logging

bp = Blueprint("lifestyle_inflation", __name__)
logger = logging.getLogger("finmind.lifestyle_inflation")


@bp.get("/detect")
@jwt_required()
def detect():
    uid = int(get_jwt_identity())
    months = int(request.args.get("months", 12))
    result = detect_lifestyle_creep(uid, max(1, min(60, months)))
    logger.info("Lifestyle inflation check user=%s trend=%s", uid, result["trend"])
    return jsonify(result)
