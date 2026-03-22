from flask import Blueprint, jsonify
from ..extensions import db
from ..models import Expense, Bill
from datetime import datetime, timedelta

bp = Blueprint('insights', __name__, url_prefix='/insights')

@bp.route('/weekly', methods=['GET'])
def weekly_summary():
    current_date = datetime.utcnow()
    start_of_week = current_date - timedelta(days=current_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    weekly_expenses = Expense.query.filter(
        Expense.date >= start_of_week,
        Expense.date <= end_of_week
    ).all()

    weekly_bills = Bill.query.filter(
        Bill.due_date >= start_of_week,
        Bill.due_date <= end_of_week
    ).all()

    total_expenses = sum(expense.amount for expense in weekly_expenses)
    total_bills = sum(bill.amount for bill in weekly_bills)

    summary = {
        "start_of_week": start_of_week.isoformat(),
        "end_of_week": end_of_week.isoformat(),
        "total_expenses": total_expenses,
        "total_bills": total_bills,
        "expenses": [{"id": exp.id, "amount": exp.amount, "category": exp.category, "date": exp.date.isoformat()} for exp in weekly_expenses],
        "bills": [{"id": bill.id, "amount": bill.amount, "name": bill.name, "due_date": bill.due_date.isoformat()} for bill in weekly_bills]
    }

    return jsonify(summary)