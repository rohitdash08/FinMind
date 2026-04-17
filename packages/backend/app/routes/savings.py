from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import Expense
import logging

bp = Blueprint("savings", __name__)
logger = logging.getLogger("finmind.savings")


# ---- In-memory storage (would be DB models in production) ----
# Using module-level dicts for simplicity; in production these would be
# SQLAlchemy models with their own tables.

_goals_store = {}
_milestones_store = {}
_goal_counter = [0]
_milestone_counter = [0]


def _next_goal_id():
    _goal_counter[0] += 1
    return _goal_counter[0]


def _next_milestone_id():
    _milestone_counter[0] += 1
    return _milestone_counter[0]


def _calculate_saved_amount(uid, goal):
    """Calculate actual saved amount from income-expense delta since goal start."""
    start = goal.get("created_at", date.today().isoformat())
    if isinstance(start, str):
        start = date.fromisoformat(start)

    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return max(0, float(income) - float(expenses))


@bp.route("/goals", methods=["GET"])
@jwt_required()
def list_goals():
    uid = str(get_jwt_identity())
    goals = _goals_store.get(uid, [])
    result = []
    for g in goals:
        saved = _calculate_saved_amount(int(uid), g)
        pct = round((saved / g["target_amount"]) * 100, 1) if g["target_amount"] > 0 else 0
        result.append({**g, "saved_amount": round(saved, 2), "progress_pct": pct})
    return jsonify({"goals": result})


@bp.route("/goals", methods=["POST"])
@jwt_required()
def create_goal():
    uid = str(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    target = data.get("target_amount")
    if not name or not target:
        return jsonify(error="name and target_amount required"), 400
    try:
        target = float(target)
    except (ValueError, TypeError):
        return jsonify(error="target_amount must be a number"), 400
    if target <= 0:
        return jsonify(error="target_amount must be positive"), 400

    goal = {
        "id": _next_goal_id(),
        "name": name,
        "target_amount": target,
        "currency": data.get("currency", "USD"),
        "deadline": data.get("deadline"),
        "category": data.get("category", "general"),
        "created_at": date.today().isoformat(),
        "active": True,
    }
    _goals_store.setdefault(uid, []).append(goal)
    logger.info("Goal created user=%s goal_id=%s name=%s", uid, goal["id"], name)
    return jsonify(goal), 201


@bp.route("/goals/<int:goal_id>", methods=["DELETE"])
@jwt_required()
def delete_goal(goal_id):
    uid = str(get_jwt_identity())
    goals = _goals_store.get(uid, [])
    _goals_store[uid] = [g for g in goals if g["id"] != goal_id]
    return jsonify(status="deleted")


@bp.route("/goals/<int:goal_id>/milestones", methods=["GET"])
@jwt_required()
def list_milestones(goal_id):
    uid = str(get_jwt_identity())
    milestones = _milestones_store.get(f"{uid}:{goal_id}", [])
    return jsonify({"milestones": milestones})


@bp.route("/goals/<int:goal_id>/milestones", methods=["POST"])
@jwt_required()
def add_milestone(goal_id):
    uid = str(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    amount = data.get("amount")
    if not name or amount is None:
        return jsonify(error="name and amount required"), 400

    milestone = {
        "id": _next_milestone_id(),
        "goal_id": goal_id,
        "name": name,
        "amount": float(amount),
        "achieved": data.get("achieved", False),
        "achieved_at": data.get("achieved_at"),
        "created_at": date.today().isoformat(),
    }
    key = f"{uid}:{goal_id}"
    _milestones_store.setdefault(key, []).append(milestone)
    return jsonify(milestone), 201


@bp.route("/goals/<int:goal_id>/milestones/<int:ms_id>/achieve", methods=["POST"])
@jwt_required()
def achieve_milestone(goal_id, ms_id):
    uid = str(get_jwt_identity())
    key = f"{uid}:{goal_id}"
    for ms in _milestones_store.get(key, []):
        if ms["id"] == ms_id:
            ms["achieved"] = True
            ms["achieved_at"] = date.today().isoformat()
            return jsonify(ms)
    return jsonify(error="Milestone not found"), 404


@bp.route("/overview")
@jwt_required()
def savings_overview():
    uid = int(get_jwt_identity())
    uid_str = str(uid)
    goals = _goals_store.get(uid_str, [])

    total_target = sum(g["target_amount"] for g in goals if g.get("active", True))
    total_saved = 0
    goal_details = []
    for g in goals:
        saved = _calculate_saved_amount(uid, g)
        total_saved += saved
        pct = round((saved / g["target_amount"]) * 100, 1) if g["target_amount"] > 0 else 0
        milestones = _milestones_store.get(f"{uid_str}:{g['id']}", [])
        achieved_ms = sum(1 for m in milestones if m.get("achieved"))
        goal_details.append({
            **g,
            "saved_amount": round(saved, 2),
            "progress_pct": pct,
            "milestones_total": len(milestones),
            "milestones_achieved": achieved_ms,
        })

    return jsonify({
        "total_target": round(total_target, 2),
        "total_saved": round(total_saved, 2),
        "overall_progress_pct": (
            round((total_saved / total_target) * 100, 1) if total_target > 0 else 0
        ),
        "goals_count": len(goals),
        "goals": goal_details,
    })
