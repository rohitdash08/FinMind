"""Autonomous budget optimization (issue #92)."""
import logging
from datetime import date
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Category

logger = logging.getLogger("finmind.budget")


def optimize_budget(user_id: int, year: int, month: int, 
                    target_savings_pct: float = 20.0) -> dict:
    """
    Analyze spending and suggest budget adjustments to hit a savings target.
    """
    income = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                   .filter(Expense.user_id == user_id,
                           extract("year", Expense.spent_at) == year,
                           extract("month", Expense.spent_at) == month,
                           Expense.expense_type == "INCOME").scalar() or 0)

    cat_rows = (db.session.query(
                    func.coalesce(Category.name, "Uncategorized").label("name"),
                    func.sum(Expense.amount).label("total"))
                .outerjoin(Category, (Category.id == Expense.category_id) & (Category.user_id == user_id))
                .filter(Expense.user_id == user_id,
                        extract("year", Expense.spent_at) == year,
                        extract("month", Expense.spent_at) == month,
                        Expense.expense_type != "INCOME")
                .group_by(Expense.category_id, Category.name)
                .order_by(func.sum(Expense.amount).desc()).all())

    total_expense = sum(float(r.total or 0) for r in cat_rows)
    current_savings = income - total_expense
    current_savings_pct = (current_savings / income * 100) if income > 0 else 0
    target_savings = income * (target_savings_pct / 100)
    gap = target_savings - current_savings

    # Essential categories — don't cut these
    essential = {"rent","mortgage","housing","utilities","groceries","food",
                 "medical","healthcare","insurance","transport","transportation"}

    suggestions = []
    remaining_gap = gap

    for r in cat_rows:
        if remaining_gap <= 0: break
        cat = (r.name or "").lower()
        amt = float(r.total or 0)
        if cat in essential: continue
        # Suggest cutting up to 30% of discretionary categories
        cut = min(amt * 0.30, remaining_gap)
        if cut > 1:
            suggestions.append({
                "category": r.name, "current": round(amt, 2),
                "suggested": round(amt - cut, 2),
                "reduction": round(cut, 2),
                "reduction_pct": round(cut / amt * 100, 1),
            })
            remaining_gap -= cut

    return {
        "period": f"{year}-{month:02d}",
        "income": round(income, 2),
        "current_expenses": round(total_expense, 2),
        "current_savings": round(current_savings, 2),
        "current_savings_pct": round(current_savings_pct, 1),
        "target_savings_pct": target_savings_pct,
        "target_savings": round(target_savings, 2),
        "gap": round(max(gap, 0), 2),
        "achievable": remaining_gap <= 0,
        "suggestions": suggestions,
        "summary": f"{'Target achievable' if remaining_gap <= 0 else f'Gap of ${remaining_gap:.0f} remaining'} by cutting discretionary spending.",
    }
