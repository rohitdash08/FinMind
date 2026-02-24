import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Budget, BudgetPeriod, Category, Expense

bp = Blueprint("budgets", __name__)
logger = logging.getLogger("finmind.budgets")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WARNING_THRESHOLD = Decimal("0.80")  # 80%
EXCEEDED_THRESHOLD = Decimal("1.00")  # 100%


def _budget_to_dict(b: Budget) -> dict:
    return {
        "id": b.id,
        "category_id": b.category_id,
        "amount": float(b.amount),
        "period": b.period.value,
    }


def _period_range(period: BudgetPeriod, ref: date | None = None):
    """Return (start, end) dates for the current period window."""
    today = ref or date.today()
    if period == BudgetPeriod.MONTHLY:
        start = today.replace(day=1)
        if today.month == 12:
            end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(today.year, today.month + 1, 1) - timedelta(days=1)
    else:  # WEEKLY
        start = today - timedelta(days=today.weekday())  # Monday
        end = start + timedelta(days=6)
    return start, end


def _category_spent(user_id: int, category_id: int, start: date, end: date) -> Decimal:
    result = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.category_id == category_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "EXPENSE",
        )
        .scalar()
    )
    return Decimal(str(result))


def _parse_amount(raw) -> Decimal | None:
    try:
        val = Decimal(str(raw)).quantize(Decimal("0.01"))
        return val if val > 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def check_budget_warnings(user_id: int, ref_date: date | None = None):
    """Return list of warning dicts for all budgets of a user."""
    budgets = db.session.query(Budget).filter_by(user_id=user_id).all()
    warnings = []
    for b in budgets:
        start, end = _period_range(b.period, ref_date)
        spent = _category_spent(user_id, b.category_id, start, end)
        cat = db.session.get(Category, b.category_id)
        cat_name = cat.name if cat else "Unknown"
        pct = (spent / b.amount * 100) if b.amount > 0 else Decimal("0")
        level = None
        if spent >= b.amount:
            level = "exceeded"
        elif spent >= b.amount * WARNING_THRESHOLD:
            level = "warning"
        if level:
            warnings.append({
                "budget_id": b.id,
                "category_id": b.category_id,
                "category_name": cat_name,
                "budget_amount": float(b.amount),
                "spent": float(spent),
                "percentage": float(pct.quantize(Decimal("0.1"))),
                "period": b.period.value,
                "level": level,
            })
    return warnings


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@bp.get("")
@jwt_required()
def list_budgets():
    uid = int(get_jwt_identity())
    items = db.session.query(Budget).filter_by(user_id=uid).all()
    return jsonify([_budget_to_dict(b) for b in items])


@bp.post("")
@jwt_required()
def create_budget():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    amount = _parse_amount(data.get("amount"))
    if amount is None:
        return jsonify(error="invalid or missing amount"), 400
    category_id = data.get("category_id")
    if not category_id:
        return jsonify(error="category_id required"), 400
    cat = db.session.query(Category).filter_by(id=category_id, user_id=uid).first()
    if not cat:
        return jsonify(error="category not found"), 404
    period_raw = str(data.get("period", "MONTHLY")).upper()
    if period_raw not in ("MONTHLY", "WEEKLY"):
        return jsonify(error="period must be MONTHLY or WEEKLY"), 400
    period = BudgetPeriod(period_raw)
    existing = db.session.query(Budget).filter_by(
        user_id=uid, category_id=category_id, period=period
    ).first()
    if existing:
        return jsonify(error="budget already exists for this category and period"), 409
    b = Budget(user_id=uid, category_id=category_id, amount=amount, period=period)
    db.session.add(b)
    db.session.commit()
    logger.info("Created budget id=%s user=%s cat=%s", b.id, uid, category_id)
    return jsonify(_budget_to_dict(b)), 201


@bp.patch("/<int:budget_id>")
@jwt_required()
def update_budget(budget_id: int):
    uid = int(get_jwt_identity())
    b = db.session.get(Budget, budget_id)
    if not b or b.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    if "amount" in data:
        amount = _parse_amount(data["amount"])
        if amount is None:
            return jsonify(error="invalid amount"), 400
        b.amount = amount
    if "period" in data:
        period_raw = str(data["period"]).upper()
        if period_raw not in ("MONTHLY", "WEEKLY"):
            return jsonify(error="period must be MONTHLY or WEEKLY"), 400
        b.period = BudgetPeriod(period_raw)
    db.session.commit()
    return jsonify(_budget_to_dict(b))


@bp.delete("/<int:budget_id>")
@jwt_required()
def delete_budget(budget_id: int):
    uid = int(get_jwt_identity())
    b = db.session.get(Budget, budget_id)
    if not b or b.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(b)
    db.session.commit()
    return jsonify(message="deleted")


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------

@bp.get("/warnings")
@jwt_required()
def get_warnings():
    uid = int(get_jwt_identity())
    warnings = check_budget_warnings(uid)
    return jsonify(warnings)
