"""Savings Goals API routes for goal-based tracking."""
from flask import Blueprint, request, jsonify, g
from ..extensions import db
from ..models_savings import SavingsGoal, SavingsMilestone
from datetime import datetime
from decimal import Decimal

bp = Blueprint("savings", __name__, url_prefix="/savings")


@bp.route("/goals", methods=["POST"])
def create_goal():
    """Create a new savings goal."""
    data = request.get_json()
    name = data.get("name", "").strip()
    target_amount = data.get("target_amount")
    currency = data.get("currency", "INR")
    deadline = data.get("deadline")
    icon = data.get("icon")
    color = data.get("color")
    
    if not name:
        return jsonify({"error": "Goal name is required"}), 400
    
    if not target_amount or float(target_amount) <= 0:
        return jsonify({"error": "Target amount must be positive"}), 400
    
    goal = SavingsGoal(
        user_id=g.user.id,
        name=name,
        target_amount=Decimal(str(target_amount)),
        currency=currency,
        icon=icon,
        color=color
    )
    
    if deadline:
        try:
            goal.deadline = datetime.strptime(deadline, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid deadline format. Use YYYY-MM-DD"}), 400
    
    db.session.add(goal)
    db.session.commit()
    
    return jsonify({
        "message": "Savings goal created successfully",
        "goal": {
            "id": goal.id,
            "name": goal.name,
            "target_amount": float(goal.target_amount),
            "current_amount": float(goal.current_amount),
            "currency": goal.currency,
            "progress_percentage": goal.progress_percentage,
            "deadline": goal.deadline.isoformat() if goal.deadline else None,
            "icon": goal.icon,
            "color": goal.color,
            "is_completed": goal.is_completed,
            "created_at": goal.created_at.isoformat()
        }
    }), 201


@bp.route("/goals", methods=["GET"])
def list_goals():
    """List all savings goals for the current user."""
    goals = SavingsGoal.query.filter_by(user_id=g.user.id).order_by(SavingsGoal.created_at.desc()).all()
    
    return jsonify({
        "goals": [{
            "id": g.id,
            "name": g.name,
            "target_amount": float(g.target_amount),
            "current_amount": float(g.current_amount),
            "currency": g.currency,
            "progress_percentage": g.progress_percentage,
            "remaining_amount": g.remaining_amount,
            "deadline": g.deadline.isoformat() if g.deadline else None,
            "icon": g.icon,
            "color": g.color,
            "is_completed": g.is_completed,
            "completed_at": g.completed_at.isoformat() if g.completed_at else None,
            "created_at": g.created_at.isoformat(),
            "milestones_count": len(g.milestones)
        } for g in goals]
    }), 200


@bp.route("/goals/<int:goal_id>", methods=["GET"])
def get_goal(goal_id):
    """Get a specific savings goal with milestones."""
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=g.user.id).first()
    
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    
    return jsonify({
        "goal": {
            "id": goal.id,
            "name": goal.name,
            "target_amount": float(goal.target_amount),
            "current_amount": float(goal.current_amount),
            "currency": goal.currency,
            "progress_percentage": goal.progress_percentage,
            "remaining_amount": goal.remaining_amount,
            "deadline": goal.deadline.isoformat() if goal.deadline else None,
            "icon": goal.icon,
            "color": goal.color,
            "is_completed": goal.is_completed,
            "completed_at": goal.completed_at.isoformat() if goal.completed_at else None,
            "created_at": goal.created_at.isoformat(),
            "milestones": [{
                "id": m.id,
                "name": m.name,
                "target_amount": float(m.target_amount),
                "is_reached": m.is_reached,
                "reached_at": m.reached_at.isoformat() if m.reached_at else None,
                "progress_percentage": m.progress_percentage
            } for m in goal.milestones]
        }
    }), 200


@bp.route("/goals/<int:goal_id>", methods=["PUT"])
def update_goal(goal_id):
    """Update a savings goal."""
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=g.user.id).first()
    
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    
    data = request.get_json()
    
    if "name" in data:
        goal.name = data["name"].strip()
    if "target_amount" in data:
        goal.target_amount = Decimal(str(data["target_amount"]))
    if "current_amount" in data:
        new_amount = Decimal(str(data["current_amount"]))
        goal.current_amount = new_amount
        
        # Check if goal is completed
        if new_amount >= goal.target_amount and not goal.is_completed:
            goal.is_completed = True
            goal.completed_at = datetime.utcnow()
            
            # Mark unreached milestones as reached
            for milestone in goal.milestones:
                if not milestone.is_reached and new_amount >= milestone.target_amount:
                    milestone.is_reached = True
                    milestone.reached_at = datetime.utcnow()
    
    if "deadline" in data:
        if data["deadline"]:
            try:
                goal.deadline = datetime.strptime(data["deadline"], "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"error": "Invalid deadline format"}), 400
        else:
            goal.deadline = None
    
    if "icon" in data:
        goal.icon = data["icon"]
    if "color" in data:
        goal.color = data["color"]
    
    db.session.commit()
    
    return jsonify({
        "message": "Goal updated successfully",
        "goal": {
            "id": goal.id,
            "name": goal.name,
            "progress_percentage": goal.progress_percentage,
            "is_completed": goal.is_completed
        }
    }), 200


@bp.route("/goals/<int:goal_id>", methods=["DELETE"])
def delete_goal(goal_id):
    """Delete a savings goal."""
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=g.user.id).first()
    
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    
    db.session.delete(goal)
    db.session.commit()
    
    return jsonify({"message": "Goal deleted successfully"}), 200


@bp.route("/goals/<int:goal_id>/milestones", methods=["POST"])
def add_milestone(goal_id):
    """Add a milestone to a savings goal."""
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=g.user.id).first()
    
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    
    data = request.get_json()
    name = data.get("name", "").strip()
    target_amount = data.get("target_amount")
    
    if not name:
        return jsonify({"error": "Milestone name is required"}), 400
    
    if not target_amount or float(target_amount) <= 0:
        return jsonify({"error": "Target amount must be positive"}), 400
    
    milestone = SavingsMilestone(
        goal_id=goal.id,
        name=name,
        target_amount=Decimal(str(target_amount))
    )
    
    # Check if already reached
    if goal.current_amount >= milestone.target_amount:
        milestone.is_reached = True
        milestone.reached_at = datetime.utcnow()
    
    db.session.add(milestone)
    db.session.commit()
    
    return jsonify({
        "message": "Milestone added successfully",
        "milestone": {
            "id": milestone.id,
            "name": milestone.name,
            "target_amount": float(milestone.target_amount),
            "is_reached": milestone.is_reached
        }
    }), 201


@bp.route("/goals/<int:goal_id>/milestones/<int:milestone_id>", methods=["DELETE"])
def delete_milestone(goal_id, milestone_id):
    """Delete a milestone from a savings goal."""
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=g.user.id).first()
    
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    
    milestone = SavingsMilestone.query.filter_by(id=milestone_id, goal_id=goal.id).first()
    
    if not milestone:
        return jsonify({"error": "Milestone not found"}), 404
    
    db.session.delete(milestone)
    db.session.commit()
    
    return jsonify({"message": "Milestone deleted successfully"}), 200


@bp.route("/goals/<int:goal_id>/contribute", methods=["POST"])
def contribute_to_goal(goal_id):
    """Add money to a savings goal."""
    goal = SavingsGoal.query.filter_by(id=goal_id, user_id=g.user.id).first()
    
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    
    data = request.get_json()
    amount = data.get("amount", 0)
    
    if float(amount) <= 0:
        return jsonify({"error": "Amount must be positive"}), 400
    
    goal.current_amount += Decimal(str(amount))
    
    # Check milestones
    for milestone in goal.milestones:
        if not milestone.is_reached and goal.current_amount >= milestone.target_amount:
            milestone.is_reached = True
            milestone.reached_at = datetime.utcnow()
    
    # Check if goal completed
    was_completed = goal.is_completed
    if goal.current_amount >= goal.target_amount and not goal.is_completed:
        goal.is_completed = True
        goal.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    response = {
        "message": f"Added {amount} to goal",
        "current_amount": float(goal.current_amount),
        "progress_percentage": goal.progress_percentage
    }
    
    if not was_completed and goal.is_completed:
        response["goal_completed"] = True
        response["message"] = f"Congratulations! You've reached your goal!"
    
    return jsonify(response), 200
