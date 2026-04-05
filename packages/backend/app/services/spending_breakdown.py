"""
Essential vs discretionary spending breakdown (issue #120).
Classifies categories as essential or discretionary and computes split.
"""
import logging
from datetime import date
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Category

logger = logging.getLogger("finmind.spending")

# Default category classification (user can override via essential_categories table)
DEFAULT_ESSENTIAL = {
    "rent", "mortgage", "utilities", "groceries", "food", "gas", "insurance",
    "medical", "healthcare", "transport", "transportation", "electricity",
    "water", "internet", "phone", "education", "childcare",
}


def classify_category(name: str, user_overrides: dict = None) -> str:
    if user_overrides and name.lower() in user_overrides:
        return user_overrides[name.lower()]
    return "essential" if name.lower() in DEFAULT_ESSENTIAL else "discretionary"


def get_spending_breakdown(user_id: int, year: int, month: int,
                           user_overrides: dict = None) -> dict:
    rows = (
        db.session.query(
            func.coalesce(Category.name, "Uncategorized").label("cat_name"),
            func.sum(Expense.amount).label("total"),
        )
        .outerjoin(Category, (Category.id == Expense.category_id) & (Category.user_id == user_id))
        .filter(
            Expense.user_id == user_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .all()
    )

    essential, discretionary = [], []
    essential_total = discretionary_total = 0.0

    for r in rows:
        amt = float(r.total or 0)
        kind = classify_category(r.cat_name, user_overrides)
        entry = {"category": r.cat_name, "amount": round(amt, 2), "type": kind}
        if kind == "essential":
            essential.append(entry); essential_total += amt
        else:
            discretionary.append(entry); discretionary_total += amt

    total = essential_total + discretionary_total
    return {
        "period": f"{year}-{month:02d}",
        "total": round(total, 2),
        "essential": {"total": round(essential_total, 2),
                      "pct": round(essential_total / total * 100, 1) if total else 0,
                      "categories": sorted(essential, key=lambda x: -x["amount"])},
        "discretionary": {"total": round(discretionary_total, 2),
                          "pct": round(discretionary_total / total * 100, 1) if total else 0,
                          "categories": sorted(discretionary, key=lambda x: -x["amount"])},
        "insight": _insight(essential_total, discretionary_total, total),
    }


def _insight(ess, disc, total) -> str:
    if total == 0: return "No spending data for this period."
    disc_pct = disc / total * 100
    if disc_pct > 60: return f"Heads up — {disc_pct:.0f}% of spending is discretionary. Consider reviewing non-essentials."
    if disc_pct < 20: return "Great discipline — most spending is on essentials."
    return f"Balanced spending: {ess/total*100:.0f}% essential, {disc_pct:.0f}% discretionary."
