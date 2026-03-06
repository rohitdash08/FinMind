from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import SharedBudget, BudgetMember
from ..services import shared_budget as svc
import logging

bp = Blueprint("shared_budgets", __name__)
logger = logging.getLogger("finmind.shared_budgets")


@bp.post("")
@jwt_required()
def create_budget():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    monthly_limit = data.get("monthly_limit")
    if monthly_limit is None:
        return jsonify(error="monthly_limit required"), 400
    try:
        monthly_limit = float(monthly_limit)
    except (ValueError, TypeError):
        return jsonify(error="invalid monthly_limit"), 400
    budget = svc.create_budget(
        user_id=uid,
        name=name,
        description=(data.get("description") or "").strip(),
        monthly_limit=monthly_limit,
    )
    logger.info("Created shared budget id=%s user=%s", budget.id, uid)
    return jsonify(id=budget.id, name=budget.name), 201


@bp.get("")
@jwt_required()
def list_budgets():
    uid = int(get_jwt_identity())
    budgets = svc.get_user_budgets(uid)
    return jsonify(budgets)


@bp.get("/<int:budget_id>")
@jwt_required()
def get_budget(budget_id):
    uid = int(get_jwt_identity())
    summary = svc.get_budget_summary(budget_id, uid)
    if summary is None:
        return jsonify(error="not found"), 404
    return jsonify(summary)


@bp.put("/<int:budget_id>")
@jwt_required()
def update_budget(budget_id):
    uid = int(get_jwt_identity())
    budget = db.session.get(SharedBudget, budget_id)
    if not budget:
        return jsonify(error="not found"), 404
    owner_member = budget.members.filter_by(user_id=uid, role="owner").first()
    if not owner_member:
        return jsonify(error="only the owner can update"), 403
    data = request.get_json() or {}
    if "name" in data:
        budget.name = (data["name"] or "").strip() or budget.name
    if "description" in data:
        budget.description = (data["description"] or "").strip()
    if "monthly_limit" in data:
        try:
            budget.monthly_limit = float(data["monthly_limit"])
        except (ValueError, TypeError):
            return jsonify(error="invalid monthly_limit"), 400
    db.session.commit()
    return jsonify(id=budget.id, name=budget.name)


@bp.delete("/<int:budget_id>")
@jwt_required()
def delete_budget(budget_id):
    uid = int(get_jwt_identity())
    budget = db.session.get(SharedBudget, budget_id)
    if not budget:
        return jsonify(error="not found"), 404
    owner_member = budget.members.filter_by(user_id=uid, role="owner").first()
    if not owner_member:
        return jsonify(error="only the owner can delete"), 403
    # Delete related records
    from ..models import SharedExpense
    db.session.query(SharedExpense).filter_by(budget_id=budget_id).delete()
    db.session.query(BudgetMember).filter_by(budget_id=budget_id).delete()
    db.session.delete(budget)
    db.session.commit()
    logger.info("Deleted shared budget id=%s user=%s", budget_id, uid)
    return jsonify(message="deleted")


@bp.post("/<int:budget_id>/members")
@jwt_required()
def add_member(budget_id):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()
    if not email:
        return jsonify(error="email required"), 400
    member, err = svc.add_member(budget_id, uid, email)
    if err:
        if err == "budget not found":
            return jsonify(error=err), 404
        if err == "user not found":
            return jsonify(error=err), 404
        return jsonify(error=err), 400
    return jsonify(id=member.id, user_id=member.user_id, role=member.role), 201


@bp.delete("/<int:budget_id>/members/<int:member_id>")
@jwt_required()
def remove_member(budget_id, member_id):
    uid = int(get_jwt_identity())
    err = svc.remove_member(budget_id, uid, member_id)
    if err:
        if "not found" in err:
            return jsonify(error=err), 404
        return jsonify(error=err), 400
    return jsonify(message="removed")


@bp.post("/<int:budget_id>/expenses")
@jwt_required()
def add_expense(budget_id):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    description = (data.get("description") or "").strip()
    if not description:
        return jsonify(error="description required"), 400
    amount = data.get("amount")
    if amount is None:
        return jsonify(error="amount required"), 400
    expense, err = svc.add_expense(
        budget_id=budget_id,
        user_id=uid,
        amount=amount,
        description=description,
        spent_at=data.get("date"),
    )
    if err:
        if "not found" in err:
            return jsonify(error=err), 404
        return jsonify(error=err), 400
    return jsonify(
        id=expense.id,
        amount=float(expense.amount),
        description=expense.description,
        date=expense.spent_at.isoformat(),
    ), 201


@bp.get("/<int:budget_id>/expenses")
@jwt_required()
def list_expenses(budget_id):
    uid = int(get_jwt_identity())
    expenses = svc.list_expenses(budget_id, uid)
    if expenses is None:
        return jsonify(error="not found"), 404
    return jsonify(expenses)
