from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import extract, func

from ..extensions import db
from ..models import BudgetLimit, Category, Expense

bp = Blueprint("budgets", __name__)


def _parse_amount(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _is_valid_month(ym: str) -> bool:
    if len(ym) != 7 or ym[4] != "-":
        return False
    parts = ym.split("-")
    if not (parts[0].isdigit() and parts[1].isdigit()):
        return False
    return 1 <= int(parts[1]) <= 12


def _spent_for_category(uid: int, category_id: int | None, year: int, month: int) -> float:
    q = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == uid,
        extract("year", Expense.spent_at) == year,
        extract("month", Expense.spent_at) == month,
        Expense.expense_type != "INCOME",
    )
    if category_id is not None:
        q = q.filter(Expense.category_id == category_id)
    return float(q.scalar())


def _status(pct: float) -> str:
    if pct > 100:
        return "over"
    if pct >= 90:
        return "critical"
    if pct >= 75:
        return "warning"
    return "ok"


@bp.get("")
@jwt_required()
def list_budgets():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or "").strip()
    if not ym or not _is_valid_month(ym):
        return jsonify(error="month param required (YYYY-MM)"), 400
    year, month = map(int, ym.split("-"))
    limits = db.session.query(BudgetLimit).filter_by(user_id=uid, month=ym).all()
    result = []
    for bl in limits:
        cat_name = "Total"
        if bl.category_id:
            cat = db.session.get(Category, bl.category_id)
            cat_name = cat.name if cat else "Unknown"
        spent = _spent_for_category(uid, bl.category_id, year, month)
        result.append({
            "id": bl.id,
            "category_id": bl.category_id,
            "category_name": cat_name,
            "monthly_limit": float(bl.monthly_limit),
            "month": bl.month,
            "spent": spent,
        })
    return jsonify(result)


@bp.post("")
@jwt_required()
def create_budget():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    amount = _parse_amount(data.get("monthly_limit"))
    if amount is None or amount <= 0:
        return jsonify(error="invalid monthly_limit"), 400
    ym = (data.get("month") or "").strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month"), 400
    category_id = data.get("category_id")
    existing = db.session.query(BudgetLimit).filter_by(
        user_id=uid, category_id=category_id, month=ym
    ).first()
    if existing:
        existing.monthly_limit = amount
        db.session.commit()
        return jsonify({"id": existing.id, "category_id": existing.category_id,
                        "monthly_limit": float(existing.monthly_limit), "month": existing.month}), 200
    bl = BudgetLimit(user_id=uid, category_id=category_id, monthly_limit=amount, month=ym)
    db.session.add(bl)
    db.session.commit()
    return jsonify({"id": bl.id, "category_id": bl.category_id,
                    "monthly_limit": float(bl.monthly_limit), "month": bl.month}), 201


@bp.delete("/<int:budget_id>")
@jwt_required()
def delete_budget(budget_id: int):
    uid = int(get_jwt_identity())
    bl = db.session.get(BudgetLimit, budget_id)
    if not bl or bl.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(bl)
    db.session.commit()
    return jsonify(message="deleted")


@bp.get("/warnings")
@jwt_required()
def budget_warnings():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or "").strip()
    if not ym or not _is_valid_month(ym):
        return jsonify(error="month param required (YYYY-MM)"), 400
    year, month = map(int, ym.split("-"))
    limits = db.session.query(BudgetLimit).filter_by(user_id=uid, month=ym).all()
    result = []
    for bl in limits:
        cat_name = "Total"
        if bl.category_id:
            cat = db.session.get(Category, bl.category_id)
            cat_name = cat.name if cat else "Unknown"
        spent = _spent_for_category(uid, bl.category_id, year, month)
        limit_f = float(bl.monthly_limit)
        remaining = round(limit_f - spent, 2)
        pct = round((spent / limit_f) * 100, 1) if limit_f > 0 else 0
        result.append({
            "category_id": bl.category_id,
            "category_name": cat_name,
            "monthly_limit": limit_f,
            "spent": spent,
            "remaining": remaining,
            "pct_used": pct,
            "status": _status(pct),
        })
    return jsonify(result)
