from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.subscriptions import (
    detect_subscriptions,
    list_detected,
    confirm_subscription,
    delete_subscription,
    get_price_history,
    check_price_increases,
    record_price,
    sub_to_dict,
)
import logging

bp = Blueprint("subscriptions", __name__)
logger = logging.getLogger("finmind.subscriptions")


@bp.get("/detected")
@jwt_required()
def get_detected():
    uid = int(get_jwt_identity())
    subs = list_detected(uid)
    return jsonify([sub_to_dict(s) for s in subs])


@bp.post("/detect")
@jwt_required()
def detect():
    uid = int(get_jwt_identity())
    detected = detect_subscriptions(uid)
    return jsonify(detected=detected, count=len(detected))


@bp.post("/detected/<int:sub_id>/confirm")
@jwt_required()
def confirm(sub_id: int):
    uid = int(get_jwt_identity())
    if not confirm_subscription(uid, sub_id):
        return jsonify(error="not found"), 404
    return jsonify(message="confirmed")


@bp.delete("/detected/<int:sub_id>")
@jwt_required()
def delete(sub_id: int):
    uid = int(get_jwt_identity())
    if not delete_subscription(uid, sub_id):
        return jsonify(error="not found"), 404
    return jsonify(message="deleted")


@bp.get("/detected/<int:sub_id>/price-history")
@jwt_required()
def price_history(sub_id: int):
    uid = int(get_jwt_identity())
    history = get_price_history(sub_id)
    return jsonify(
        [
            {"id": h.id, "amount": float(h.amount), "detected_at": h.detected_at.isoformat()}
            for h in history
        ]
    )


@bp.post("/detected/<int:sub_id>/check-price")
@jwt_required()
def check_price(sub_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    amount = data.get("amount")
    if not amount:
        return jsonify(error="amount required"), 400
    if not record_price(uid, sub_id, float(amount)):
        return jsonify(error="not found"), 404
    return jsonify(message="price recorded")


@bp.get("/price-increases")
@jwt_required()
def price_increases():
    uid = int(get_jwt_identity())
    increases = check_price_increases(uid)
    return jsonify(increases)
