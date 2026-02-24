import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.subscription_detect import detect_subscriptions

bp = Blueprint("subscriptions", __name__)
logger = logging.getLogger("finmind.subscriptions")


@bp.get("/detect")
@jwt_required()
def detect():
    """Return auto-detected subscriptions from the user's expense history."""
    uid = int(get_jwt_identity())

    try:
        min_occ = int(request.args.get("min_occurrences", "3"))
        tolerance = int(request.args.get("tolerance_days", "5"))
    except ValueError:
        return jsonify(error="invalid query parameters"), 400

    results = detect_subscriptions(uid, min_occurrences=min_occ, tolerance_days=tolerance)
    logger.info("Subscription detect user=%s found=%s", uid, len(results))
    return jsonify(results)
