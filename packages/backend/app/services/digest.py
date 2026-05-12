from datetime import date, timedelta
from sqlalchemy import func, desc
from ..extensions import db
from ..models import Expense, Category

def generate_weekly_digest(user_id: int):
    """
    Generates a weekly financial summary for the user covering the last 7 days.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=7)

    # 1. Total expenses in the last 7 days
    total_spent = db.session.query(func.sum(Expense.amount)).filter(
        Expense.user_id == user_id,
        Expense.expense_type == "EXPENSE",
        Expense.spent_at >= start_date,
        Expense.spent_at <= end_date
    ).scalar() or 0.0

    # 2. Expenses grouped by category
    category_breakdown_query = db.session.query(
        Category.name, func.sum(Expense.amount).label("total")
    ).join(Expense, Expense.category_id == Category.id).filter(
        Expense.user_id == user_id,
        Expense.expense_type == "EXPENSE",
        Expense.spent_at >= start_date,
        Expense.spent_at <= end_date
    ).group_by(Category.name).all()

    category_breakdown = [
        {"category": name, "amount": float(total)} 
        for name, total in category_breakdown_query
    ]

    # 3. Biggest single expense
    biggest_expense = db.session.query(Expense).filter(
        Expense.user_id == user_id,
        Expense.expense_type == "EXPENSE",
        Expense.spent_at >= start_date,
        Expense.spent_at <= end_date
    ).order_by(desc(Expense.amount)).first()

    biggest_expense_data = None
    if biggest_expense:
        category_name = None
        if biggest_expense.category_id:
            cat = db.session.get(Category, biggest_expense.category_id)
            if cat:
                category_name = cat.name

        biggest_expense_data = {
            "amount": float(biggest_expense.amount),
            "currency": biggest_expense.currency,
            "category": category_name,
            "notes": biggest_expense.notes,
            "spent_at": biggest_expense.spent_at.isoformat()
        }

    return {
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_spent": float(total_spent),
        "category_breakdown": category_breakdown,
        "biggest_expense": biggest_expense_data
    }
