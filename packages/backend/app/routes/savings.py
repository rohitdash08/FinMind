"""Savings goals routes.

Endpoints
---------
GET    /savings/goals              list all goals for the current user
POST   /savings/goals              create a new goal
GET    /savings/goals/<id>         get one goal
PATCH  /savings/goals/<id>         update name / target_amount / target_date / status
DELETE /savings/goals/<id>         delete a goal
POST   /savings/goals/<id>/deposit add money to a goal
GET    /savings/goals/<id>/milestones list milestones reached
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.savings import (
    create_goal,
    delete_goal,
    deposit,
    get_goal,
    get_goals,
    get_milestones,
    goal_to_dict,
    update_goal,
)

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings.routes")


@bp.get("/goals")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = get_goals(uid)
    return jsonify([goal_to_dict(g) for g in goals])


@bp.post("/goals")
@jwt_required()
def create_goal_endpoint():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    goal, err = create_goal(uid, data)
    if err:
        return jsonify(error=err), 400
    return jsonify(goal_to_dict(goal)), 201


@bp.get("/goals/<int:goal_id>")
@jwt_required()
def get_goal_endpoint(goal_id: int):
    uid = int(get_jwt_identity())
    goal = get_goal(uid, goal_id)
    if not goal:
        return jsonify(error="not found"), 404
    return jsonify(goal_to_dict(goal))


@bp.patch("/goals/<int:goal_id>")
@jwt_required()
def update_goal_endpoint(goal_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    goal, err = update_goal(uid, goal_id, data)
    if err == "not found":
        return jsonify(error=err), 404
    if err:
        return jsonify(error=err), 400
    return jsonify(goal_to_dict(goal))


@bp.delete("/goals/<int:goal_id>")
@jwt_required()
def delete_goal_endpoint(goal_id: int):
    uid = int(get_jwt_identity())
    if not delete_goal(uid, goal_id):
        return jsonify(error="not found"), 404
    return "", 204


@bp.post("/goals/<int:goal_id>/deposit")
@jwt_required()
def deposit_endpoint(goal_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    goal, err = deposit(uid, goal_id, data.get("amount"), data.get("note"))
    if err == "not found":
        return jsonify(error=err), 404
    if err:
        return jsonify(error=err), 400
    return jsonify(goal_to_dict(goal))


@bp.get("/goals/<int:goal_id>/milestones")
@jwt_required()
def milestones_endpoint(goal_id: int):
    uid = int(get_jwt_identity())
    milestones = get_milestones(uid, goal_id)
    if milestones is None:
        return jsonify(error="not found"), 404
    return jsonify([
        {"pct": m.pct, "reached_at": m.reached_at.isoformat()}
        for m in milestones
    ])
