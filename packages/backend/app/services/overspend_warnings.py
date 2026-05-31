import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, CategoryBudget, Expense

logger = logging.getLogger("finmind.overspend")


def set_budget(
    user_id: int,
    category_id: int,
    monthly_limit: Decimal,
    warning_threshold_pct: Decimal = Decimal("80.00"),
) -> dict[str, Any]:
    existing = (
        db.session.query(CategoryBudget)
        .filter_by(user_id=user_id, category_id=category_id)
        .first()
    )
    if existing:
        existing.monthly_limit = monthly_limit
        existing.warning_threshold_pct = warning_threshold_pct
        cb_ref = existing
    else:
        cb_ref = CategoryBudget(
            user_id=user_id,
            category_id=category_id,
            monthly_limit=monthly_limit,
            warning_threshold_pct=warning_threshold_pct,
        )
        db.session.add(cb_ref)
    db.session.commit()
    logger.info("Budget set user=%s category=%s limit=%s", user_id, category_id, monthly_limit)
    return {"id": cb_ref.id, "category_id": category_id, "monthly_limit": float(monthly_limit), "warning_threshold_pct": float(warning_threshold_pct)}


def get_budgets(user_id: int) -> list[dict[str, Any]]:
    rows = (
        db.session.query(CategoryBudget)
        .filter_by(user_id=user_id)
        .all()
    )
    return [
        {
            "id": r.id,
            "category_id": r.category_id,
            "monthly_limit": float(r.monthly_limit),
            "warning_threshold_pct": float(r.warning_threshold_pct),
        }
        for r in rows
    ]


def delete_budget(user_id: int, budget_id: int) -> bool:
    cb = db.session.get(CategoryBudget, budget_id)
    if not cb or cb.user_id != user_id:
        return False
    db.session.delete(cb)
    db.session.commit()
    return True


def check_warnings(user_id: int, ym: str | None = None) -> list[dict[str, Any]]:
    if ym is None:
        today = date.today()
        ym = today.strftime("%Y-%m")
    year, month = map(int, ym.split("-"))

    budgets = (
        db.session.query(CategoryBudget)
        .filter_by(user_id=user_id)
        .all()
    )
    warnings: list[dict[str, Any]] = []
    for cb in budgets:
        spent = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                Expense.category_id == cb.category_id,
                Expense.expense_type != "INCOME",
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
            )
            .scalar()
        )
        spent_float = float(spent or 0)
        limit_float = float(cb.monthly_limit)
        pct = (spent_float / limit_float * 100) if limit_float > 0 else 0
        warning_threshold = float(cb.warning_threshold_pct)

        cat = db.session.get(Category, cb.category_id)
        cat_name = cat.name if cat else "Unknown"

        entry = {
            "category_id": cb.category_id,
            "category_name": cat_name,
            "monthly_limit": limit_float,
            "spent": spent_float,
            "usage_pct": round(pct, 1),
            "remaining": round(max(limit_float - spent_float, 0), 2),
        }
        if pct >= 100:
            entry["level"] = "exceeded"
            entry["message"] = f"Overspent {cat_name}: {spent_float:.2f} vs limit {limit_float:.2f}"
        elif pct >= warning_threshold:
            entry["level"] = "warning"
            entry["message"] = f"Approaching limit for {cat_name}: {spent_float:.2f} / {limit_float:.2f} ({pct:.0f}%)"
        else:
            entry["level"] = "ok"
            entry["message"] = ""
        warnings.append(entry)

    return warnings
