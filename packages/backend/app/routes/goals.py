"""Savings goals endpoints."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import goals as goal_service

bp = Blueprint("goals", __name__)


@bp.get("/")
@jwt_required()
def list_goals():
    user_id = int(get_jwt_identity())
    status = request.args.get("status")
    items = goal_service.get_goals(user_id, status)
    return jsonify([_serialize_goal(g) for g in items]), 200


@bp.post("/")
@jwt_required()
def create_goal():
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data or not data.get("name") or not data.get("target_amount"):
        return jsonify(error="name and target_amount are required"), 400

    target = data["target_amount"]
    if not isinstance(target, (int, float)) or target <= 0:
        return jsonify(error="target_amount must be a positive number"), 400

    deadline = None
    if data.get("deadline"):
        try:
            deadline = date.fromisoformat(data["deadline"])
        except ValueError:
            return jsonify(error="deadline must be YYYY-MM-DD format"), 400

    goal = goal_service.create_goal(
        user_id=user_id,
        name=data["name"],
        target_amount=target,
        currency=data.get("currency", "INR"),
        deadline=deadline,
    )
    return jsonify(_serialize_goal(goal)), 201


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id):
    user_id = int(get_jwt_identity())
    goal = goal_service.get_goal(goal_id, user_id)
    if not goal:
        return jsonify(error="Goal not found"), 404
    return jsonify(_serialize_goal(goal)), 200


@bp.put("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id):
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    goal = goal_service.update_goal(goal_id, user_id, **data)
    if not goal:
        return jsonify(error="Goal not found"), 404
    return jsonify(_serialize_goal(goal)), 200


@bp.delete("/<int:goal_id>")
@jwt_required()
def cancel_goal(goal_id):
    user_id = int(get_jwt_identity())
    goal = goal_service.cancel_goal(goal_id, user_id)
    if not goal:
        return jsonify(error="Goal not found"), 404
    return jsonify(_serialize_goal(goal)), 200


@bp.get("/<int:goal_id>/progress")
@jwt_required()
def get_progress(goal_id):
    user_id = int(get_jwt_identity())
    progress = goal_service.get_progress(goal_id, user_id)
    if not progress:
        return jsonify(error="Goal not found"), 404
    return jsonify(progress), 200


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def add_contribution(goal_id):
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data or not data.get("amount"):
        return jsonify(error="amount is required"), 400

    amount = data["amount"]
    if not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify(error="amount must be a positive number"), 400

    contribution, error = goal_service.add_contribution(
        goal_id=goal_id,
        user_id=user_id,
        amount=amount,
        note=data.get("note"),
    )
    if error:
        status_code = 404 if "not found" in error.lower() else 400
        return jsonify(error=error), status_code

    return (
        jsonify(
            {
                "id": contribution.id,
                "goal_id": contribution.goal_id,
                "amount": float(contribution.amount),
                "note": contribution.note,
                "contributed_at": contribution.contributed_at.isoformat(),
            }
        ),
        201,
    )


@bp.get("/<int:goal_id>/contributions")
@jwt_required()
def list_contributions(goal_id):
    user_id = int(get_jwt_identity())
    items = goal_service.get_contributions(goal_id, user_id)
    if items is None:
        return jsonify(error="Goal not found"), 404
    return (
        jsonify(
            [
                {
                    "id": c.id,
                    "amount": float(c.amount),
                    "note": c.note,
                    "contributed_at": c.contributed_at.isoformat(),
                }
                for c in items
            ]
        ),
        200,
    )


def _serialize_goal(goal):
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": float(goal.target_amount),
        "current_amount": float(goal.current_amount),
        "currency": goal.currency,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "status": goal.status,
        "created_at": goal.created_at.isoformat(),
    }
