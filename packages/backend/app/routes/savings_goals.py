from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SavingsGoal

bp = Blueprint("savings_goals", __name__, url_prefix="/api/savings-goals")


@bp.route("", methods=["GET"])
@jwt_required()
def list_goals():
    uid = get_jwt_identity()
    goals = SavingsGoal.query.filter_by(user_id=int(uid)).all()
    return jsonify([
        {
            "id": g.id,
            "name": g.name,
            "target_amount": float(g.target_amount),
            "current_amount": float(g.current_amount),
            "currency": g.currency,
            "deadline": g.deadline.isoformat() if g.deadline else None,
            "completed": g.completed,
            "created_at": g.created_at.isoformat(),
        }
        for g in goals
    ])


@bp.route("", methods=["POST"])
@jwt_required()
def create_goal():
    uid = get_jwt_identity()
    data = request.get_json() or {}
    name = data.get("name")
    target_amount = data.get("target_amount")
    currency = data.get("currency", "USD")
    deadline = data.get("deadline")
    
    if not name or not target_amount:
        return jsonify(error="name and target_amount required"), 400
    
    goal = SavingsGoal(
        user_id=int(uid),
        name=name,
        target_amount=target_amount,
        currency=currency,
        deadline=deadline,
    )
    db.session.add(goal)
    db.session.commit()
    
    return jsonify(id=goal.id, name=goal.name), 201


@bp.route("/<int:goal_id>", methods=["PATCH"])
@jwt_required()
def update_goal(goal_id):
    uid = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=int(uid)).first()
    if not goal:
        return jsonify(error="not found"), 404
    
    data = request.get_json() or {}
    if "current_amount" in data:
        goal.current_amount = data["current_amount"]
        if goal.current_amount >= goal.target_amount:
            goal.completed = True
    if "name" in data:
        goal.name = data["name"]
    if "target_amount" in data:
        goal.target_amount = data["target_amount"]
    if "deadline" in data:
        goal.deadline = data["deadline"]
    
    db.session.commit()
    return jsonify(id=goal.id, completed=goal.completed)


@bp.route("/<int:goal_id>", methods=["DELETE"])
@jwt_required()
def delete_goal(goal_id):
    uid = get_jwt_identity()
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=int(uid)).first()
    if not goal:
        return jsonify(error="not found"), 404
    
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message="deleted")
