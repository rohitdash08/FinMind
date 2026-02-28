from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from ..extensions import db
from ..models import User, Expense, Bill

bp = Blueprint("digest", __name__, url_prefix="/api/digest")


@bp.route("/weekly", methods=["GET"])
@jwt_required()
def get_weekly_digest():
    uid = get_jwt_identity()
    
    # Get date range for current week
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    # Get expenses this week
    expenses = Expense.query.filter(
        Expense.user_id == int(uid),
        Expense.date >= week_start,
        Expense.date <= week_end
    ).all()
    
    # Get bills due this week
    bills = Bill.query.filter(
        Bill.user_id == int(uid),
        Bill.due_date >= week_start,
        Bill.due_date <= week_end
    ).all()
    
    # Calculate totals
    total_expenses = sum(e.amount for e in expenses)
    total_bills = sum(b.amount for b in bills)
    
    # Get category breakdown
    category_totals = {}
    for e in expenses:
        cat = e.category or "Uncategorized"
        category_totals[cat] = category_totals.get(cat, 0) + e.amount
    
    return jsonify(
        period={
            "start": week_start.isoformat(),
            "end": week_end.isoformat()
        },
        summary={
            "total_expenses": float(total_expenses),
            "total_bills_due": float(total_bills),
            "transaction_count": len(expenses),
            "bills_due_count": len(bills)
        },
        category_breakdown={
            cat: float(amount) for cat, amount in category_totals.items()
        },
        recent_transactions=[
            {
                "id": e.id,
                "description": e.description,
                "amount": float(e.amount),
                "date": e.date.isoformat(),
                "category": e.category
            }
            for e in expenses[:5]
        ]
    )


@bp.route("/monthly", methods=["GET"])
@jwt_required()
def get_monthly_digest():
    uid = get_jwt_identity()
    
    today = datetime.now().date()
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    
    expenses = Expense.query.filter(
        Expense.user_id == int(uid),
        Expense.date >= month_start,
        Expense.date <= month_end
    ).all()
    
    bills = Bill.query.filter(
        Bill.user_id == int(uid),
        Bill.due_date >= month_start,
        Bill.due_date <= month_end
    ).all()
    
    total_expenses = sum(e.amount for e in expenses)
    total_bills = sum(b.amount for b in bills)
    
    return jsonify(
        period={
            "start": month_start.isoformat(),
            "end": month_end.isoformat()
        },
        summary={
            "total_expenses": float(total_expenses),
            "total_bills_due": float(total_bills),
            "daily_average": float(total_expenses / today.day) if today.day > 0 else 0
        }
    )
