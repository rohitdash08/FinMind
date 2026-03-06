from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services import savings as svc
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


def _goal_json(goal, include_milestones=False):
    pct = (goal.current_amount or 0) / goal.target_amount * 100 if goal.target_amount else 0
    data = {
        "id": goal.id,
        "name": goal.name,
        "target_amount": goal.target_amount,
        "current_amount": goal.current_amount or 0,
        "progress_pct": round(pct, 2),
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "completed": goal.completed,
        "completed_at": goal.completed_at.isoformat() if goal.completed_at else None,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
    }
    if include_milestones:
        data["milestones"] = svc.get_milestones(goal)
    return data


@bp.post("/goals")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("name") or not data.get("target_amount"):
        return jsonify(error="name and target_amount required"), 400
    deadline = None
    if data.get("deadline"):
        deadline = date.fromisoformat(data["deadline"])
    goal = svc.create_goal(uid, data["name"], float(data["target_amount"]), deadline)
    logger.info("Created savings goal id=%s user=%s", goal.id, uid)
    return jsonify(_goal_json(goal)), 201


@bp.get("/goals")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = svc.get_goals(uid)
    return jsonify([_goal_json(g) for g in goals])


@bp.get("/goals/<int:goal_id>")
@jwt_required()
def get_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = svc.get_goal(goal_id, uid)
    if not goal:
        return jsonify(error="not found"), 404
    data = _goal_json(goal, include_milestones=True)
    deposits = svc.get_deposits(goal_id)
    data["deposits"] = [
        {
            "id": d.id,
            "amount": d.amount,
            "note": d.note,
            "deposited_at": d.deposited_at.isoformat() if d.deposited_at else None,
        }
        for d in deposits
    ]
    return jsonify(data)


@bp.put("/goals/<int:goal_id>")
@jwt_required()
def update_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = svc.get_goal(goal_id, uid)
    if not goal:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    deadline = None
    if "deadline" in data and data["deadline"]:
        deadline = date.fromisoformat(data["deadline"])
    svc.update_goal(
        goal,
        name=data.get("name"),
        target_amount=float(data["target_amount"]) if "target_amount" in data else None,
        deadline=deadline,
    )
    return jsonify(_goal_json(goal))


@bp.delete("/goals/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = svc.get_goal(goal_id, uid)
    if not goal:
        return jsonify(error="not found"), 404
    svc.delete_goal(goal)
    return jsonify(message="deleted")


@bp.post("/goals/<int:goal_id>/deposit")
@jwt_required()
def deposit(goal_id):
    uid = int(get_jwt_identity())
    goal = svc.get_goal(goal_id, uid)
    if not goal:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if not data.get("amount") or float(data["amount"]) <= 0:
        return jsonify(error="positive amount required"), 400
    svc.deposit(goal, float(data["amount"]), data.get("note"))
    logger.info("Deposit to goal id=%s amount=%s", goal_id, data["amount"])
    return jsonify(_goal_json(goal, include_milestones=True))


@bp.post("/goals/<int:goal_id>/withdraw")
@jwt_required()
def withdraw(goal_id):
    uid = int(get_jwt_identity())
    goal = svc.get_goal(goal_id, uid)
    if not goal:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if not data.get("amount") or float(data["amount"]) <= 0:
        return jsonify(error="positive amount required"), 400
    if float(data["amount"]) > (goal.current_amount or 0):
        return jsonify(error="insufficient balance"), 400
    svc.withdraw(goal, float(data["amount"]))
    logger.info("Withdraw from goal id=%s amount=%s", goal_id, data["amount"])
    return jsonify(_goal_json(goal, include_milestones=True))
