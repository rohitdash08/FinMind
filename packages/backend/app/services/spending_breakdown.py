import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense, SpendingCategory

logger = logging.getLogger("finmind.spending_breakdown")


def _get_default_essential_categories() -> set[str]:
    return {
        "groceries", "rent", "mortgage", "utilities", "electricity",
        "water", "gas", "health", "medical", "insurance",
        "transport", "education", "loan", "emi",
    }


def get_or_create_spending_category(user_id: int, category_id: int, category_name: str) -> SpendingCategory:
    existing = (
        db.session.query(SpendingCategory)
        .filter(
            SpendingCategory.user_id == user_id,
            SpendingCategory.category_id == category_id,
        )
        .first()
    )
    if existing:
        return existing

    is_essential = category_name.lower() in _get_default_essential_categories()
    sc = SpendingCategory(
        user_id=user_id,
        category_id=category_id,
        is_essential=is_essential,
    )
    db.session.add(sc)
    db.session.commit()
    return sc


def get_spending_breakdown(user_id: int, ym: str | None = None) -> dict:
    if not ym:
        ym = date.today().strftime("%Y-%m")
    year, month = map(int, ym.split("-"))

    category_rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == user_id),
        )
        .filter(
            Expense.user_id == user_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    essential_total = Decimal("0.00")
    discretionary_total = Decimal("0.00")
    categories_breakdown = []

    for row in category_rows:
        cat_id = row.category_id
        cat_name = row.category_name
        amount = Decimal(str(row.total_amount or 0))

        sc = None
        if cat_id:
            sc = get_or_create_spending_category(user_id, cat_id, cat_name)

        is_essential = sc.is_essential if sc else cat_name.lower() in _get_default_essential_categories()

        if is_essential:
            essential_total += amount
        else:
            discretionary_total += amount

        categories_breakdown.append({
            "category_id": cat_id,
            "category_name": cat_name,
            "amount": float(amount),
            "is_essential": is_essential,
        })

    grand_total = essential_total + discretionary_total
    return {
        "period": ym,
        "essential": {
            "total": float(essential_total),
            "share_pct": round(float(essential_total / grand_total * 100), 2) if grand_total > 0 else 0,
            "categories": [c for c in categories_breakdown if c["is_essential"]],
        },
        "discretionary": {
            "total": float(discretionary_total),
            "share_pct": round(float(discretionary_total / grand_total * 100), 2) if grand_total > 0 else 0,
            "categories": [c for c in categories_breakdown if not c["is_essential"]],
        },
        "total_spending": float(grand_total),
    }


def update_spending_category(user_id: int, category_id: int, is_essential: bool) -> bool:
    sc = (
        db.session.query(SpendingCategory)
        .filter(
            SpendingCategory.user_id == user_id,
            SpendingCategory.category_id == category_id,
        )
        .first()
    )
    if not sc:
        cat = db.session.get(Category, category_id)
        if not cat or cat.user_id != user_id:
            return False
        sc = SpendingCategory(
            user_id=user_id,
            category_id=category_id,
            is_essential=is_essential,
        )
        db.session.add(sc)
    else:
        sc.is_essential = is_essential
    db.session.commit()
    return True


def get_spending_trends(user_id: int, months: int = 6) -> dict:
    today = date.today()
    trends = []
    for i in range(months - 1, -1, -1):
        ym = date(today.year, today.month, 1)
        if today.month - i <= 0:
            ym = date(today.year - 1, 12 + (today.month - i), 1)
        else:
            ym = date(today.year, today.month - i, 1)

        ym_str = ym.strftime("%Y-%m")
        breakdown = get_spending_breakdown(user_id, ym_str)
        trends.append({
            "period": ym_str,
            "essential": breakdown["essential"]["total"],
            "discretionary": breakdown["discretionary"]["total"],
            "total": breakdown["total_spending"],
        })

    return {"trends": trends, "periods": months}
