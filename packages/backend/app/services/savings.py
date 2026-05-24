"""Savings goal service.

Public API
----------
create_goal(uid, data)           -> SavingsGoal
get_goals(uid)                   -> list[SavingsGoal]
get_goal(uid, goal_id)           -> SavingsGoal | None
update_goal(uid, goal_id, data)  -> SavingsGoal | None
delete_goal(uid, goal_id)        -> bool
deposit(uid, goal_id, amount, note) -> SavingsGoal | None
get_milestones(uid, goal_id)     -> list[GoalMilestone]
goal_to_dict(goal)               -> dict
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ..extensions import db
from ..models import GoalDeposit, GoalMilestone, GoalStatus, SavingsGoal

logger = logging.getLogger("finmind.savings")

_MILESTONE_PCTS = (25, 50, 75, 100)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_amount(value: Any) -> Decimal | None:
    try:
        d = Decimal(str(value))
        return d if d > 0 else None
    except (InvalidOperation, TypeError):
        return None


def _progress_pct(goal: SavingsGoal) -> float:
    if goal.target_amount <= 0:
        return 0.0
    return float(goal.current_amount / goal.target_amount * 100)


def _record_new_milestones(goal: SavingsGoal) -> None:
    """Record any newly crossed milestone thresholds (idempotent)."""
    pct = _progress_pct(goal)
    existing = {m.pct for m in goal.milestones}
    for threshold in _MILESTONE_PCTS:
        if pct >= threshold and threshold not in existing:
            db.session.add(GoalMilestone(goal_id=goal.id, pct=threshold))
            logger.info(
                "Goal id=%s crossed %s%% milestone (current=%.2f target=%.2f)",
                goal.id, threshold, goal.current_amount, goal.target_amount,
            )


def goal_to_dict(goal: SavingsGoal) -> dict:
    return {
        "id": goal.id,
        "name": goal.name,
        "description": goal.description,
        "target_amount": float(goal.target_amount),
        "current_amount": float(goal.current_amount),
        "progress_pct": round(_progress_pct(goal), 2),
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "status": goal.status,
        "currency": goal.currency,
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_goal(uid: int, data: dict) -> tuple[SavingsGoal | None, str | None]:
    """Create a new savings goal.  Returns (goal, None) or (None, error_msg)."""
    name = (data.get("name") or "").strip()
    if not name:
        return None, "name required"

    target = _parse_amount(data.get("target_amount"))
    if target is None:
        return None, "target_amount must be a positive number"

    raw_date = data.get("target_date")
    target_date = None
    if raw_date:
        try:
            target_date = date.fromisoformat(str(raw_date))
        except ValueError:
            return None, "target_date must be ISO 8601 (YYYY-MM-DD)"

    from ..models import User
    user = db.session.get(User, uid)
    currency = data.get("currency") or (user.preferred_currency if user else "INR")

    goal = SavingsGoal(
        user_id=uid,
        name=name,
        description=(data.get("description") or "").strip() or None,
        target_amount=target,
        current_amount=Decimal("0"),
        target_date=target_date,
        currency=currency,
    )
    db.session.add(goal)
    db.session.commit()
    logger.info("Created savings goal id=%s user=%s target=%.2f", goal.id, uid, goal.target_amount)
    return goal, None


def get_goals(uid: int) -> list[SavingsGoal]:
    return (
        db.session.query(SavingsGoal)
        .filter_by(user_id=uid)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )


def get_goal(uid: int, goal_id: int) -> SavingsGoal | None:
    return db.session.query(SavingsGoal).filter_by(id=goal_id, user_id=uid).first()


def update_goal(uid: int, goal_id: int, data: dict) -> tuple[SavingsGoal | None, str | None]:
    goal = get_goal(uid, goal_id)
    if not goal:
        return None, "not found"

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return None, "name must not be empty"
        goal.name = name

    if "description" in data:
        goal.description = (data["description"] or "").strip() or None

    if "target_amount" in data:
        target = _parse_amount(data["target_amount"])
        if target is None:
            return None, "target_amount must be a positive number"
        goal.target_amount = target

    if "target_date" in data:
        raw = data["target_date"]
        if raw is None:
            goal.target_date = None
        else:
            try:
                goal.target_date = date.fromisoformat(str(raw))
            except ValueError:
                return None, "target_date must be ISO 8601 (YYYY-MM-DD)"

    if "status" in data:
        s = str(data["status"]).upper()
        valid = {e.value for e in GoalStatus}
        if s not in valid:
            return None, f"status must be one of {sorted(valid)}"
        goal.status = s

    goal.updated_at = datetime.utcnow()
    db.session.commit()
    logger.info("Updated savings goal id=%s user=%s", goal.id, uid)
    return goal, None


def delete_goal(uid: int, goal_id: int) -> bool:
    goal = get_goal(uid, goal_id)
    if not goal:
        return False
    db.session.delete(goal)
    db.session.commit()
    logger.info("Deleted savings goal id=%s user=%s", goal_id, uid)
    return True


def deposit(
    uid: int, goal_id: int, amount: Any, note: str | None = None
) -> tuple[SavingsGoal | None, str | None]:
    """Credit an amount towards the goal; auto-complete when target is reached."""
    goal = get_goal(uid, goal_id)
    if not goal:
        return None, "not found"
    if goal.status != GoalStatus.ACTIVE.value:
        return None, "only ACTIVE goals accept deposits"

    amt = _parse_amount(amount)
    if amt is None:
        return None, "amount must be a positive number"

    db.session.add(GoalDeposit(goal_id=goal.id, amount=amt, note=note or None))
    goal.current_amount = (goal.current_amount or Decimal("0")) + amt
    goal.updated_at = datetime.utcnow()

    # Auto-complete
    if goal.current_amount >= goal.target_amount:
        goal.current_amount = goal.target_amount
        goal.status = GoalStatus.COMPLETED.value
        logger.info("Goal id=%s user=%s COMPLETED", goal.id, uid)

    _record_new_milestones(goal)
    db.session.commit()
    return goal, None


def get_milestones(uid: int, goal_id: int) -> list[GoalMilestone] | None:
    goal = get_goal(uid, goal_id)
    if not goal:
        return None
    return goal.milestones.order_by(GoalMilestone.pct).all()
