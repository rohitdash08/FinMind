import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.cost_increase_detect import detect_cost_increases

bp = Blueprint("cost_increases", __name__)
logger = logging.getLogger("finmind.cost_increases")


@bp.get("")
@jwt_required()
def list_cost_increases():
    """Return detected subscription cost increases for the current user."""
    uid = int(get_jwt_identity())

    try:
        min_history = int(request.args.get("min_history", "2"))
    except ValueError:
        return jsonify(error="invalid query parameters"), 400

    results = detect_cost_increases(uid, min_history=min_history)
    logger.info("Cost increase detect user=%s found=%s", uid, len(results))
    return jsonify(results)
