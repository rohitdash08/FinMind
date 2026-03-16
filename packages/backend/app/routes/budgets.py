"""Category budget management and overspend early-warning endpoints (#117)."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Category, CategoryBudget, Expense

bp = Blueprint("budgets", __name__)

# Warning levels based on % of budget consumed
WARN_LEVEL_CRITICAL = 100   # Over budget
WARN_LEVEL_HIGH = 90        # ≥ 90 % — almost over
WARN_LEVEL_MEDIUM = 75      # ≥ 75 % — getting close


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


def _spent_this_month(user_id: int, category_id: int, month: str) -> float:
    """Sum of EXPENSE-type transactions for (user, category, month)."""
    year, mo = map(int, month.split("-"))
    result = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.category_id == category_id,
            Expense.expense_type != "INCOME",
            func.strftime("%Y", Expense.spent_at) == str(year),
            func.strftime("%m", Expense.spent_at) == f"{mo:02d}",
        )
        .scalar()
    )
    return float(result or 0)


def _warning_level(pct: float) -> str:
    if pct >= WARN_LEVEL_CRITICAL:
        return "CRITICAL"
    if pct >= WARN_LEVEL_HIGH:
        return "HIGH"
    if pct >= WARN_LEVEL_MEDIUM:
        return "MEDIUM"
    return "OK"


def _budget_json(b: CategoryBudget) -> dict:
    return {
        "id": b.id,
        "category_id": b.category_id,
        "month": b.month,
        "budget_limit": float(b.budget_limit),
        "warning_threshold_pct": b.warning_threshold_pct,
        "created_at": b.created_at.isoformat(),
    }


# ── Budget CRUD ───────────────────────────────────────────────────────────────


@bp.get("")
@jwt_required()
def list_budgets():
    uid = int(get_jwt_identity())
    budgets = CategoryBudget.query.filter_by(user_id=uid).order_by(
        CategoryBudget.month.desc(), CategoryBudget.category_id
    ).all()
    return jsonify([_budget_json(b) for b in budgets])


@bp.post("")
@jwt_required()
def create_budget():
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)

    category_id = data.get("category_id")
    if not category_id:
        return jsonify(error="category_id is required"), 400

    # Verify category belongs to user
    cat = Category.query.filter_by(id=category_id, user_id=uid).first()
    if not cat:
        return jsonify(error="category not found"), 404

    budget_limit = float(data.get("budget_limit", 0))
    if budget_limit <= 0:
        return jsonify(error="budget_limit must be positive"), 400

    month = (data.get("month") or "").strip() or None
    if month:
        try:
            date(int(month[:4]), int(month[5:7]), 1)
        except (ValueError, IndexError):
            return jsonify(error="month must be YYYY-MM"), 400

    threshold = int(data.get("warning_threshold_pct", 80))
    if not (1 <= threshold <= 100):
        return jsonify(error="warning_threshold_pct must be 1-100"), 400

    budget = CategoryBudget(
        user_id=uid,
        category_id=category_id,
        month=month,
        budget_limit=budget_limit,
        warning_threshold_pct=threshold,
    )
    db.session.add(budget)
    db.session.commit()
    return jsonify(_budget_json(budget)), 201


@bp.patch("/<int:budget_id>")
@jwt_required()
def update_budget(budget_id: int):
    uid = int(get_jwt_identity())
    budget = CategoryBudget.query.filter_by(id=budget_id, user_id=uid).first()
    if not budget:
        return jsonify(error="budget not found"), 404

    data = request.get_json(force=True)
    if "budget_limit" in data:
        bl = float(data["budget_limit"])
        if bl <= 0:
            return jsonify(error="budget_limit must be positive"), 400
        budget.budget_limit = bl
    if "warning_threshold_pct" in data:
        t = int(data["warning_threshold_pct"])
        if not (1 <= t <= 100):
            return jsonify(error="warning_threshold_pct must be 1-100"), 400
        budget.warning_threshold_pct = t
    if "month" in data:
        budget.month = data["month"] or None

    db.session.commit()
    return jsonify(_budget_json(budget))


@bp.delete("/<int:budget_id>")
@jwt_required()
def delete_budget(budget_id: int):
    uid = int(get_jwt_identity())
    budget = CategoryBudget.query.filter_by(id=budget_id, user_id=uid).first()
    if not budget:
        return jsonify(error="budget not found"), 404

    db.session.delete(budget)
    db.session.commit()
    return jsonify(message="budget deleted"), 200


# ── Overspend warning ─────────────────────────────────────────────────────────


@bp.get("/overspend")
@jwt_required()
def overspend_warnings():
    """Returns per-category spending status vs budget limits for the given month.

    Query params:
      - month: YYYY-MM (defaults to current month)
      - only_warnings: if "true", only categories at >= warning_threshold_pct
    """
    uid = int(get_jwt_identity())
    month = (request.args.get("month") or _current_month()).strip()
    only_warnings = request.args.get("only_warnings", "false").lower() == "true"

    # Find budget rows applicable to this month:
    # a) exact match for the month, OR b) null month (default / global limit)
    budgets = CategoryBudget.query.filter(
        CategoryBudget.user_id == uid,
        db.or_(
            CategoryBudget.month == month,
            CategoryBudget.month.is_(None),
        ),
    ).all()

    results = []
    for b in budgets:
        cat = Category.query.get(b.category_id)
        spent = _spent_this_month(uid, b.category_id, month)
        limit = float(b.budget_limit)
        pct = round((spent / limit) * 100, 1) if limit > 0 else 0.0
        level = _warning_level(pct)

        if only_warnings and level == "OK":
            continue

        results.append(
            {
                "budget_id": b.id,
                "category_id": b.category_id,
                "category_name": cat.name if cat else None,
                "month": month,
                "budget_limit": limit,
                "spent": round(spent, 2),
                "remaining": round(limit - spent, 2),
                "pct_used": pct,
                "warning_threshold_pct": b.warning_threshold_pct,
                "warning_level": level,
                "is_over_budget": spent > limit,
            }
        )

    # Sort: CRITICAL first, then HIGH, then MEDIUM, then OK; then by pct desc
    level_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "OK": 3}
    results.sort(key=lambda r: (level_order.get(r["warning_level"], 9), -r["pct_used"]))

    return jsonify(
        {
            "month": month,
            "warnings": results,
            "summary": {
                "critical": sum(1 for r in results if r["warning_level"] == "CRITICAL"),
                "high": sum(1 for r in results if r["warning_level"] == "HIGH"),
                "medium": sum(1 for r in results if r["warning_level"] == "MEDIUM"),
                "ok": sum(1 for r in results if r["warning_level"] == "OK"),
                "total": len(results),
            },
        }
    )
