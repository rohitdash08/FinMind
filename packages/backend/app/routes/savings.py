from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.savings import (
    create_goal, list_goals, get_goal, contribute, update_goal, delete_goal,
)
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


@bp.post("")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    target = data.get("target_amount")
    if not name or not target:
        return jsonify({"error": "name and target_amount are required"}), 400
    result = create_goal(
        uid, name, float(target),
        currency=data.get("currency", "INR"),
        deadline=data.get("deadline"),
    )
    logger.info("Goal created id=%s user=%s", result["id"], uid)
    return jsonify(result), 201


@bp.get("")
@jwt_required()
def list_all():
    uid = int(get_jwt_identity())
    return jsonify(list_goals(uid))


@bp.get("/<int:gid>")
@jwt_required()
def detail(gid):
    uid = int(get_jwt_identity())
    goal = get_goal(uid, gid)
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    return jsonify(goal)


@bp.post("/<int:gid>/contribute")
@jwt_required()
def add_contribution(gid):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    amount = data.get("amount")
    if not amount or float(amount) <= 0:
        return jsonify({"error": "Positive amount required"}), 400
    try:
        result = contribute(uid, gid, float(amount))
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.patch("/<int:gid>")
@jwt_required()
def update(gid):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        result = update_goal(uid, gid, **data)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.delete("/<int:gid>")
@jwt_required()
def delete(gid):
    uid = int(get_jwt_identity())
    if delete_goal(uid, gid):
        return jsonify({"deleted": True})
    return jsonify({"error": "Goal not found"}), 404
