"""Weekly/monthly financial digest API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.financial_digest import generate_digest, get_digest_history
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/")
@jwt_required()
def get_digest():
    uid = int(get_jwt_identity())
    period = request.args.get("period", "weekly")
    if period not in ("weekly", "monthly"):
        return jsonify({"error": "period must be 'weekly' or 'monthly'"}), 400
    result = generate_digest(uid, period)
    logger.info("Digest generated user=%s period=%s", uid, period)
    return jsonify(result)


@bp.get("/history")
@jwt_required()
def history():
    uid = int(get_jwt_identity())
    limit = int(request.args.get("limit", 10))
    return jsonify(get_digest_history(uid, limit))
