from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.subscription_detector import (
    detect_subscriptions,
    list_subscriptions,
    update_subscription,
    get_price_history,
    check_price_increases,
)
import logging

bp = Blueprint("subscriptions", __name__)
logger = logging.getLogger("finmind.subscriptions")


@bp.get("")
@jwt_required()
def list_subs():
    uid = int(get_jwt_identity())
    status = request.args.get("status")
    subs = list_subscriptions(uid, status)
    return jsonify(subs)


@bp.post("/detect")
@jwt_required()
def detect():
    uid = int(get_jwt_identity())
    subs = detect_subscriptions(uid)
    logger.info("Subscription detection user=%s count=%s", uid, len(subs))
    return jsonify(subs), 201


@bp.patch("/<int:sub_id>")
@jwt_required()
def update(sub_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    result = update_subscription(sub_id, uid, data)
    if not result:
        return jsonify(error="not found"), 404
    return jsonify(result)


@bp.get("/<int:sub_id>/price-history")
@jwt_required()
def price_history(sub_id: int):
    uid = int(get_jwt_identity())
    history = get_price_history(sub_id, uid)
    if history is None:
        return jsonify(error="not found"), 404
    return jsonify(history)


@bp.post("/check-increases")
@jwt_required()
def check_increases():
    uid = int(get_jwt_identity())
    alerts = check_price_increases(uid)
    return jsonify(alerts)
