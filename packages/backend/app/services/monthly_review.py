"""Guided monthly financial review flow (issue #102)."""
import logging
from datetime import date
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Bill, Category

logger = logging.getLogger("finmind.monthly_review")


def generate_monthly_review(user_id: int, year: int, month: int) -> dict:
    """
    Step-by-step guided review: summary → insights → action items → next month plan.
    """
    # 1. Summary
    total_expense = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                          .filter(Expense.user_id == user_id,
                                  extract("year", Expense.spent_at) == year,
                                  extract("month", Expense.spent_at) == month,
                                  Expense.expense_type != "INCOME").scalar() or 0)
    total_income = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                         .filter(Expense.user_id == user_id,
                                 extract("year", Expense.spent_at) == year,
                                 extract("month", Expense.spent_at) == month,
                                 Expense.expense_type == "INCOME").scalar() or 0)
    savings = total_income - total_expense
    savings_rate = round(savings / total_income * 100, 1) if total_income > 0 else 0

    # 2. Top categories
    cat_rows = (db.session.query(
                    func.coalesce(Category.name, "Uncategorized").label("name"),
                    func.sum(Expense.amount).label("total"))
                .outerjoin(Category, (Category.id == Expense.category_id) & (Category.user_id == user_id))
                .filter(Expense.user_id == user_id,
                        extract("year", Expense.spent_at) == year,
                        extract("month", Expense.spent_at) == month,
                        Expense.expense_type != "INCOME")
                .group_by(Expense.category_id, Category.name)
                .order_by(func.sum(Expense.amount).desc()).limit(5).all())

    # 3. Uncategorized count
    uncategorized = (db.session.query(func.count(Expense.id))
                     .filter(Expense.user_id == user_id,
                             extract("year", Expense.spent_at) == year,
                             extract("month", Expense.spent_at) == month,
                             Expense.category_id.is_(None)).scalar() or 0)

    # 4. Action items
    actions = []
    if uncategorized > 0:
        actions.append(f"Categorize {uncategorized} uncategorized transaction(s)")
    if savings_rate < 10 and total_income > 0:
        actions.append("Savings rate below 10% — identify discretionary cuts")
    if savings_rate >= 20:
        actions.append("Strong savings rate! Consider moving surplus to savings goals")

    # 5. Next month plan
    next_month = month % 12 + 1
    next_year = year + (1 if month == 12 else 0)
    upcoming_bills = (db.session.query(Bill)
                      .filter(Bill.user_id == user_id, Bill.active.is_(True),
                              extract("month", Bill.next_due_date) == next_month,
                              extract("year", Bill.next_due_date) == next_year).all())

    return {
        "period": f"{year}-{month:02d}",
        "steps": [
            {"step": 1, "title": "Monthly Summary", "data": {
                "income": round(total_income, 2), "expenses": round(total_expense, 2),
                "savings": round(savings, 2), "savings_rate_pct": savings_rate}},
            {"step": 2, "title": "Top Spending Categories", "data": {
                "categories": [{"name": r.name, "amount": float(r.total or 0)} for r in cat_rows]}},
            {"step": 3, "title": "Action Items", "data": {
                "items": actions, "uncategorized_count": int(uncategorized)}},
            {"step": 4, "title": "Next Month Preview", "data": {
                "month": f"{next_year}-{next_month:02d}",
                "upcoming_bills": [{"name": b.name, "amount": float(b.amount)} for b in upcoming_bills],
                "bills_total": round(sum(float(b.amount) for b in upcoming_bills), 2)}},
        ],
    }
