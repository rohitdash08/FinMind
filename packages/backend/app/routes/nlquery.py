import re
from datetime import date, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, Category
import logging

bp = Blueprint("nlquery", __name__)
logger = logging.getLogger("finmind.nlquery")

# Pattern matchers for natural language queries
PATTERNS = [
    {
        "name": "spent_on_category",
        "regex": r"(?:how much|total|what).*(?:spent?|spend)\s+(?:on|for)\s+(.+?)(?:\?|$)",
        "handler": "_handle_spent_on_category",
    },
    {
        "name": "total_spending",
        "regex": r"(?:how much|total|what).*(?:spent?|spend|spending)(?:\s+this\s+month)?",
        "handler": "_handle_total_spending",
    },
    {
        "name": "income_this_month",
        "regex": r"(?:how much|total|what).*(?:income|earn|earned|salary|made)",
        "handler": "_handle_income",
    },
    {
        "name": "biggest_expense",
        "regex": r"(?:biggest|largest|highest|top|max).*(?:expense|spending|purchase)",
        "handler": "_handle_biggest_expense",
    },
]


@bp.post("")
@jwt_required()
def query():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    question = (data.get("question") or "").strip().lower()

    if not question:
        return jsonify(error="question is required"), 400

    # Try each pattern
    for pattern in PATTERNS:
        match = re.search(pattern["regex"], question, re.IGNORECASE)
        if match:
            handler = globals()[pattern["handler"]]
            result = handler(uid, match)
            logger.info(
                "NL query matched pattern=%s user=%s question=%s",
                pattern["name"], uid, question,
            )
            return jsonify({
                "answer": result["answer"],
                "data": result.get("data", {}),
                "pattern": pattern["name"],
                "question": question,
            })

    # No pattern matched
    logger.info("NL query unmatched user=%s question=%s", uid, question)
    return jsonify({
        "answer": "I couldn't understand that question. Try asking things like: "
                  "'How much did I spend on food?', 'What's my income this month?', "
                  "or 'What's my biggest expense?'",
        "data": {},
        "pattern": None,
        "question": question,
    })


def _get_month_range():
    """Return start and end of current month."""
    today = date.today()
    start = today.replace(day=1)
    if today.month == 12:
        end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return start, end


def _handle_spent_on_category(uid, match):
    category_name = match.group(1).strip().rstrip("?. ")
    start, end = _get_month_range()

    # Find category by name (case-insensitive)
    category = (
        db.session.query(Category)
        .filter(
            Category.user_id == uid,
            func.lower(Category.name) == category_name.lower(),
        )
        .first()
    )

    if category:
        result = (
            db.session.query(func.sum(Expense.amount))
            .filter(
                Expense.user_id == uid,
                Expense.category_id == category.id,
                Expense.expense_type == "EXPENSE",
                Expense.spent_at >= start,
                Expense.spent_at <= end,
            )
            .scalar()
        )
        total = float(result) if result else 0.0
        return {
            "answer": f"You spent {total:.2f} on {category.name} this month.",
            "data": {
                "category": category.name,
                "category_id": category.id,
                "total": total,
                "period": {"start": start.isoformat(), "end": end.isoformat()},
            },
        }
    else:
        # Try searching in expense notes
        result = (
            db.session.query(func.sum(Expense.amount))
            .filter(
                Expense.user_id == uid,
                Expense.expense_type == "EXPENSE",
                Expense.notes.ilike(f"%{category_name}%"),
                Expense.spent_at >= start,
                Expense.spent_at <= end,
            )
            .scalar()
        )
        total = float(result) if result else 0.0
        return {
            "answer": f"You spent {total:.2f} on items matching '{category_name}' this month.",
            "data": {
                "search_term": category_name,
                "total": total,
                "period": {"start": start.isoformat(), "end": end.isoformat()},
            },
        }


def _handle_total_spending(uid, match):
    start, end = _get_month_range()
    result = (
        db.session.query(func.sum(Expense.amount))
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    )
    total = float(result) if result else 0.0
    return {
        "answer": f"You've spent {total:.2f} this month.",
        "data": {
            "total": total,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
        },
    }


def _handle_income(uid, match):
    start, end = _get_month_range()
    result = (
        db.session.query(func.sum(Expense.amount))
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    )
    total = float(result) if result else 0.0
    return {
        "answer": f"Your income this month is {total:.2f}.",
        "data": {
            "total": total,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
        },
    }


def _handle_biggest_expense(uid, match):
    start, end = _get_month_range()
    expense = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .order_by(Expense.amount.desc())
        .first()
    )
    if expense:
        return {
            "answer": (
                f"Your biggest expense this month is "
                f"{float(expense.amount):.2f} for '{expense.notes}'."
            ),
            "data": {
                "amount": float(expense.amount),
                "description": expense.notes,
                "date": expense.spent_at.isoformat(),
                "id": expense.id,
            },
        }
    return {
        "answer": "You have no expenses this month.",
        "data": {},
    }
