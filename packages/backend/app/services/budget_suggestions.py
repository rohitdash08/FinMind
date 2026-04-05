"""Dynamic budget suggestions (issue #73)."""
import logging
from datetime import date
from sqlalchemy import extract, func
from dateutil.relativedelta import relativedelta
from ..extensions import db
from ..models import Expense, Category

logger = logging.getLogger("finmind.budget_suggestions")


def suggest_budgets(user_id: int, months_history: int = 3) -> dict:
    """
    Analyze N months of spending history and suggest monthly budget limits per category.
    """
    today = date.today()
    all_months = []
    for i in range(months_history):
        d = today - relativedelta(months=i+1)
        all_months.append((d.year, d.month))

    cat_totals: dict = {}
    for y, m in all_months:
        rows = (db.session.query(
                    func.coalesce(Category.name, "Uncategorized").label("name"),
                    func.sum(Expense.amount).label("total"))
                .outerjoin(Category, (Category.id == Expense.category_id) & (Category.user_id == user_id))
                .filter(Expense.user_id == user_id,
                        extract("year", Expense.spent_at) == y,
                        extract("month", Expense.spent_at) == m,
                        Expense.expense_type != "INCOME")
                .group_by(Expense.category_id, Category.name).all())
        for r in rows:
            cat_totals.setdefault(r.name, []).append(float(r.total or 0))

    suggestions = []
    for cat, amounts in cat_totals.items():
        avg = sum(amounts) / len(amounts)
        # Suggest 10% under average for discretionary, at average for essentials
        essential_kw = {"rent","mortgage","utilities","groceries","food","medical","insurance","transport"}
        factor = 1.0 if any(k in cat.lower() for k in essential_kw) else 0.90
        suggestions.append({
            "category": cat,
            "avg_monthly": round(avg, 2),
            "suggested_budget": round(avg * factor, 2),
            "reduction_pct": round((1 - factor) * 100, 0),
            "months_analyzed": len(amounts),
        })

    total_suggested = sum(s["suggested_budget"] for s in suggestions)
    return {
        "months_analyzed": months_history,
        "suggestions": sorted(suggestions, key=lambda x: -x["avg_monthly"]),
        "total_suggested_budget": round(total_suggested, 2),
    }
