"""REST routes for subscription auto-detection."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.subscription_detector import detect_subscriptions
import logging

bp = Blueprint("subscriptions_detect", __name__)
logger = logging.getLogger("finmind.subscriptions_detect")


@bp.get("")
@jwt_required()
def list_detected_subscriptions():
    """
    GET /subscriptions/detected

    Scans the user's expense history and returns auto-detected subscriptions.

    Query params:
      months (int, 1-24): look-back window in months (default 6)
    """
    uid = int(get_jwt_identity())
    try:
        months = int(request.args.get("months", 6))
    except (TypeError, ValueError):
        months = 6

    result = detect_subscriptions(uid, months=months)
    logger.info(
        "Subscription detection: user=%s months=%s found=%s",
        uid, months, len(result["subscriptions"])
    )
    return jsonify(result), 200