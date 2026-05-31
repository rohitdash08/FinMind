from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.subscriptions import (
    detect_subscriptions,
    list_detected,
    confirm_subscription,
    delete_subscription,
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
