import json
import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import AuditLog, Expense, Category, Bill

bp = Blueprint("onboarding", __name__)
logger = logging.getLogger("finmind.onboarding")

ONBOARDING_STEPS = [
    "has_expense",
    "has_category",
    "has_bill",
    "has_budget_goal",
    "profile_complete",
]


def _get_completed_steps(uid):
    rows = (
        db.session.query(AuditLog)
        .filter(AuditLog.user_id == uid, AuditLog.action.like("onboarding_step:%"))
        .all()
    )
    completed = set()
    for r in rows:
        try:
            step = r.action.split(":", 1)[1]
            completed.add(step)
        except IndexError:
            continue
    return completed


def _check_status(uid):
    manual = _get_completed_steps(uid)
    status = {}
    status["has_expense"] = (
        "has_expense" in manual
        or db.session.query(Expense).filter(Expense.user_id == uid).first() is not None
    )
    status["has_category"] = (
        "has_category" in manual
        or db.session.query(Category).filter(Category.user_id == uid).first() is not None
    )
    status["has_bill"] = (
        "has_bill" in manual
        or db.session.query(Bill).filter(Bill.user_id == uid).first() is not None
    )
    status["has_budget_goal"] = "has_budget_goal" in manual
    status["profile_complete"] = "profile_complete" in manual
    return status


@bp.get("/status")
@jwt_required()
def get_status():
    uid = int(get_jwt_identity())
    status = _check_status(uid)
    logger.info("Onboarding status user=%s", uid)
    return jsonify(status)


@bp.post("/complete-step")
@jwt_required()
def complete_step():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    step = (data.get("step") or "").strip()
    if step not in ONBOARDING_STEPS:
        return jsonify(error=f"invalid step, must be one of {ONBOARDING_STEPS}"), 400

    existing = (
        db.session.query(AuditLog)
        .filter(AuditLog.user_id == uid, AuditLog.action == f"onboarding_step:{step}")
        .first()
    )
    if existing:
        return jsonify({"step": step, "already_completed": True})

    log = AuditLog(user_id=uid, action=f"onboarding_step:{step}")
    db.session.add(log)
    db.session.commit()
    logger.info("Onboarding step completed user=%s step=%s", uid, step)
    return jsonify({"step": step, "completed": True}), 201


@bp.get("/suggestions")
@jwt_required()
def get_suggestions():
    uid = int(get_jwt_identity())
    status = _check_status(uid)
    suggestions = []
    if not status["has_expense"]:
        suggestions.append({"step": "has_expense", "action": "Add your first expense"})
    if not status["has_category"]:
        suggestions.append({"step": "has_category", "action": "Create a spending category"})
    if not status["has_bill"]:
        suggestions.append({"step": "has_bill", "action": "Set up a recurring bill"})
    if not status["has_budget_goal"]:
        suggestions.append({"step": "has_budget_goal", "action": "Set a budget goal"})
    if not status["profile_complete"]:
        suggestions.append({"step": "profile_complete", "action": "Complete your profile"})
    return jsonify(suggestions)
