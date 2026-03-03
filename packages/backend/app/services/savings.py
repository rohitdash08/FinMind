"""Goal-based savings tracking & milestones service.

Provides CRUD for savings goals and milestone tracking.
Each goal has a target amount. Progress is tracked via deposits
(linked to the Expense model with expense_type='SAVINGS').
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func

from ..extensions import db
from ..models import SavingsGoal, Expense


def create_goal(
    uid: int,
    name: str,
    target_amount: float,
    currency: str = "INR",
    target_date: date | None = None,
) -> dict:
    goal = SavingsGoal(
        user_id=uid,
        name=name,
        target_amount=target_amount,
        currency=currency,
        target_date=target_date,
    )
    db.session.add(goal)
    db.session.commit()
    return _serialize(goal, 0.0)


def list_goals(uid: int) -> list[dict]:
    goals = (
        db.session.query(SavingsGoal)
        .filter(SavingsGoal.user_id == uid)
        .order_by(SavingsGoal.created_at)
        .all()
    )
    return [_serialize(g, _saved(uid, g.id)) for g in goals]


def get_goal(uid: int, goal_id: int) -> dict | None:
    goal = db.session.query(SavingsGoal).filter(
        SavingsGoal.id == goal_id, SavingsGoal.user_id == uid
    ).first()
    if not goal:
        return None
    return _serialize(goal, _saved(uid, goal.id))


def delete_goal(uid: int, goal_id: int) -> bool:
    goal = db.session.query(SavingsGoal).filter(
        SavingsGoal.id == goal_id, SavingsGoal.user_id == uid
    ).first()
    if not goal:
        return False
    db.session.delete(goal)
    db.session.commit()
    return True


def deposit(uid: int, goal_id: int, amount: float, notes: str = "") -> dict | None:
    """Record a deposit toward a savings goal."""
    goal = db.session.query(SavingsGoal).filter(
        SavingsGoal.id == goal_id, SavingsGoal.user_id == uid
    ).first()
    if not goal:
        return None

    expense = Expense(
        user_id=uid,
        amount=amount,
        currency=goal.currency,
        expense_type="SAVINGS",
        notes=notes or f"Savings: {goal.name}",
        spent_at=date.today(),
        savings_goal_id=goal.id,
    )
    db.session.add(expense)
    db.session.commit()

    saved = _saved(uid, goal.id)
    return _serialize(goal, saved)


def _saved(uid: int, goal_id: int) -> float:
    return float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.savings_goal_id == goal_id,
            Expense.expense_type == "SAVINGS",
        )
        .scalar() or 0
    )


def _milestones(target: float, saved: float) -> list[dict]:
    """Generate milestone markers at 25%, 50%, 75%, 100%."""
    milestones = []
    for pct in (25, 50, 75, 100):
        threshold = target * pct / 100
        milestones.append({
            "percentage": pct,
            "amount": round(threshold, 2),
            "reached": saved >= threshold,
        })
    return milestones


def _serialize(goal: SavingsGoal, saved: float) -> dict:
    target = float(goal.target_amount)
    pct = round((saved / target) * 100, 2) if target > 0 else 0.0
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": round(target, 2),
        "saved_amount": round(saved, 2),
        "remaining": round(max(target - saved, 0), 2),
        "progress_pct": min(pct, 100.0),
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "milestones": _milestones(target, saved),
        "completed": saved >= target,
        "created_at": goal.created_at.isoformat(),
    }
