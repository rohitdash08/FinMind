from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..models_savings import SavingsGoal, SavingsMilestone, SavingsContribution
from ..services.savings import savings_service

bp = Blueprint("savings", __name__)


# ── helpers ──────────────────────────────────────────────────


def _goal_dict(g: SavingsGoal) -> dict:
    remaining = float(g.target_amount) - float(g.current_amount)
    progress_pct = (
        round(float(g.current_amount) / float(g.target_amount) * 100, 2)
        if float(g.target_amount) > 0
        else 0.0
    )
    milestones = [
        {
            "id": m.id,
            "percentage": m.percentage,
            "reached": m.reached,
            "reached_at": m.reached_at.isoformat() if m.reached_at else None,
        }
        for m in g.milestones.order_by(SavingsMilestone.percentage).all()
    ]
    return {
        "id": g.id,
        "name": g.name,
        "target_amount": float(g.target_amount),
        "current_amount": float(g.current_amount),
        "remaining": max(remaining, 0),
        "progress_pct": progress_pct,
        "currency": g.currency,
        "deadline": g.deadline.isoformat() if g.deadline else None,
        "status": g.status,
        "milestones": milestones,
        "created_at": g.created_at.isoformat(),
        "updated_at": g.updated_at.isoformat(),
    }


def _contribution_dict(c: SavingsContribution) -> dict:
    return {
        "id": c.id,
        "goal_id": c.goal_id,
        "amount": float(c.amount),
        "notes": c.notes,
        "contributed_at": c.contributed_at.isoformat(),
    }


# ── routes ───────────────────────────────────────────────────


@bp.get("")
@jwt_required()
def list_goals():
    uid = int(get_jwt_identity())
    goals = savings_service.list_goals(uid)
    return jsonify([_goal_dict(g) for g in goals])


@bp.post("")
@jwt_required()
def create_goal():
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)
    goal, error = savings_service.create_goal(uid, data)
    if error:
        return jsonify(error=error), 400
    return jsonify(_goal_dict(goal)), 201


@bp.get("/summary")
@jwt_required()
def get_summary():
    uid = int(get_jwt_identity())
    summary = savings_service.get_summary(uid)
    return jsonify(summary)


@bp.get("/<int:goal_id>")
@jwt_required()
def get_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal = savings_service.get_goal(uid, goal_id)
    if not goal:
        return jsonify(error="not found"), 404
    return jsonify(_goal_dict(goal))


@bp.patch("/<int:goal_id>")
@jwt_required()
def update_goal(goal_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)
    goal, error = savings_service.update_goal(uid, goal_id, data)
    if error:
        status = 404 if error == "not found" else 400
        return jsonify(error=error), status
    return jsonify(_goal_dict(goal))


@bp.delete("/<int:goal_id>")
@jwt_required()
def delete_goal(goal_id: int):
    uid = int(get_jwt_identity())
    ok, error = savings_service.delete_goal(uid, goal_id)
    if not ok:
        return jsonify(error=error), 404
    return jsonify(message="deleted")


@bp.post("/<int:goal_id>/contribute")
@jwt_required()
def contribute(goal_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)
    amount = data.get("amount")
    notes = data.get("notes")
    contribution, meta, error = savings_service.contribute(uid, goal_id, amount, notes)
    if error:
        status = 404 if error == "not found" else 400
        return jsonify(error=error), status
    result = _contribution_dict(contribution)
    result.update(meta)
    return jsonify(result), 201


@bp.post("/<int:goal_id>/abandon")
@jwt_required()
def abandon_goal(goal_id: int):
    uid = int(get_jwt_identity())
    goal, error = savings_service.abandon_goal(uid, goal_id)
    if error:
        status = 404 if error == "not found" else 400
        return jsonify(error=error), status
    return jsonify(_goal_dict(goal))
