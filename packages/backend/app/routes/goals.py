"""
Goal-based savings tracking & milestones — #133

Allows users to create savings goals, track progress, set milestones,
and get notified when milestones are reached.

Models:
- SavingsGoal: id, user_id, name, target_amount, current_amount, currency, deadline, status
- SavingsMilestone: id, goal_id, name, target_amount, reached_at

API:
- CRUD for savings goals
- Track contributions (add/withdraw)
- Milestone auto-detection
- Progress summary
"""
from datetime import datetime, date
from decimal import Decimal
from enum import Enum as PyEnum

from flask import Blueprint, jsonify, request
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Boolean, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship

from ..extensions import db


# ─── Models ───────────────────────────────────────────────────────

class GoalStatus(str, PyEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class SavingsGoal(db.Model):
    __tablename__ = "savings_goals"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    target_amount = Column(Numeric(12, 2), nullable=False)
    current_amount = Column(Numeric(12, 2), default=0.00, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    deadline = Column(Date, nullable=True)
    status = Column(String(20), default=GoalStatus.ACTIVE.value, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    milestones = relationship("SavingsMilestone", back_populates="goal", cascade="all, delete-orphan")

    @property
    def progress_pct(self) -> float:
        if self.target_amount and float(self.target_amount) > 0:
            return round((float(self.current_amount) / float(self.target_amount)) * 100, 1)
        return 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, float(self.target_amount) - float(self.current_amount))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "target_amount": float(self.target_amount),
            "current_amount": float(self.current_amount),
            "currency": self.currency,
            "progress_pct": self.progress_pct,
            "remaining": self.remaining,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "status": self.status,
            "notes": self.notes,
            "milestones": [m.to_dict() for m in self.milestones],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SavingsMilestone(db.Model):
    __tablename__ = "savings_milestones"

    id = Column(Integer, primary_key=True)
    goal_id = Column(Integer, ForeignKey("savings_goals.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    target_amount = Column(Numeric(12, 2), nullable=False)
    reached_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    goal = relationship("SavingsGoal", back_populates="milestones")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "target_amount": float(self.target_amount),
            "reached": self.reached_at is not None,
            "reached_at": self.reached_at.isoformat() if self.reached_at else None,
        }


# ─── Blueprint ────────────────────────────────────────────────────

goals_bp = Blueprint("goals", __name__, url_prefix="/api/savings-goals")


@goals_bp.route("", methods=["GET"])
def list_goals():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    goals = SavingsGoal.query.filter_by(user_id=user_id).order_by(SavingsGoal.created_at.desc()).all()
    return jsonify({"goals": [g.to_dict() for g in goals]}), 200


@goals_bp.route("", methods=["POST"])
def create_goal():
    data = request.get_json()
    if not data or not data.get("name") or not data.get("target_amount"):
        return jsonify({"error": "name and target_amount required"}), 400

    goal = SavingsGoal(
        user_id=data["user_id"],
        name=data["name"],
        target_amount=data["target_amount"],
        currency=data.get("currency", "USD"),
        deadline=datetime.strptime(data["deadline"], "%Y-%m-%d").date() if data.get("deadline") else None,
        notes=data.get("notes"),
    )
    db.session.add(goal)
    db.session.commit()

    # Auto-create milestones at 25%, 50%, 75%, 100%
    target = float(goal.target_amount)
    for pct, label in [(25, "25% Complete"), (50, "Halfway There!"), (75, "75% Complete"), (100, "Goal Reached! 🎉")]:
        milestone = SavingsMilestone(
            goal_id=goal.id,
            name=label,
            target_amount=round(target * pct / 100, 2),
        )
        db.session.add(milestone)
    db.session.commit()

    return jsonify(goal.to_dict()), 201


@goals_bp.route("/<int:goal_id>", methods=["GET"])
def get_goal(goal_id: int):
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    return jsonify(goal.to_dict()), 200


@goals_bp.route("/<int:goal_id>/contribute", methods=["POST"])
def contribute(goal_id: int):
    """Add (positive) or withdraw (negative) from a savings goal."""
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    if goal.status != GoalStatus.ACTIVE.value:
        return jsonify({"error": "Goal is not active"}), 400

    data = request.get_json()
    amount = data.get("amount")
    if not amount or float(amount) == 0:
        return jsonify({"error": "Non-zero amount required"}), 400

    new_amount = float(goal.current_amount) + float(amount)
    if new_amount < 0:
        return jsonify({"error": "Cannot withdraw more than current amount"}), 400

    goal.current_amount = new_amount

    # Check milestone completions
    newly_reached = []
    for milestone in goal.milestones:
        if milestone.reached_at is None and float(goal.current_amount) >= float(milestone.target_amount):
            milestone.reached_at = datetime.utcnow()
            newly_reached.append(milestone.name)

    if float(goal.current_amount) >= float(goal.target_amount):
        goal.status = GoalStatus.COMPLETED.value

    db.session.commit()

    return jsonify({
        "goal": goal.to_dict(),
        "new_milestones": newly_reached,
        "message": f"{'Deposited' if float(amount) > 0 else 'Withdrawn'} ${abs(float(amount)):.2f}. {'🎉 ' + ', '.join(newly_reached) if newly_reached else ''}",
    }), 200


@goals_bp.route("/<int:goal_id>", methods=["DELETE"])
def delete_goal(goal_id: int):
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal:
        return jsonify({"error": "Goal not found"}), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify({"message": "Goal deleted"}), 200


@goals_bp.route("/summary", methods=["GET"])
def summary():
    """Overall savings summary for a user."""
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    goals = SavingsGoal.query.filter_by(user_id=user_id).all()
    total_target = sum(float(g.target_amount) for g in goals)
    total_saved = sum(float(g.current_amount) for g in goals)
    active = [g for g in goals if g.status == GoalStatus.ACTIVE.value]
    completed = [g for g in goals if g.status == GoalStatus.COMPLETED.value]

    return jsonify({
        "total_goals": len(goals),
        "active_goals": len(active),
        "completed_goals": len(completed),
        "total_target": total_target,
        "total_saved": total_saved,
        "overall_progress_pct": round((total_saved / total_target) * 100, 1) if total_target else 0,
        "goals": [g.to_dict() for g in goals],
    }), 200
