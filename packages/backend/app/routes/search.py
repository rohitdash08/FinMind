"""Unified search across transactions, bills, and reminders.

Provides a single endpoint to search all financial data with
filters for amount range, date range, type, and full-text.
"""

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from ..extensions import db
from ..models import Expense, Bill, Reminder

bp = Blueprint("search", __name__)
logger = logging.getLogger("finmind.search")


@bp.get("")
@jwt_required()
def unified_search():
    """Search across expenses, bills, and reminders.

    Query params:
        q (str): Search term (matches notes/name/message).
        type (str): Filter by type — expense, bill, reminder, or all (default).
        min_amount (float): Minimum amount filter.
        max_amount (float): Maximum amount filter.
        from_date (str): Start date (YYYY-MM-DD).
        to_date (str): End date (YYYY-MM-DD).
        sort (str): Sort by — date, amount, relevance (default: date).
        limit (int): Max results per type (default 50, max 200).
    """
    uid = int(get_jwt_identity())
    q = (request.args.get("q") or "").strip()
    search_type = (request.args.get("type") or "all").lower()
    sort_by = (request.args.get("sort") or "date").lower()

    try:
        limit = min(200, max(1, int(request.args.get("limit", "50"))))
    except (ValueError, TypeError):
        limit = 50

    min_amount = _parse_float(request.args.get("min_amount"))
    max_amount = _parse_float(request.args.get("max_amount"))
    from_date = _parse_date(request.args.get("from_date"))
    to_date = _parse_date(request.args.get("to_date"))

    results = []

    if search_type in ("all", "expense"):
        results.extend(_search_expenses(uid, q, min_amount, max_amount, from_date, to_date, sort_by, limit))

    if search_type in ("all", "bill"):
        results.extend(_search_bills(uid, q, min_amount, max_amount, sort_by, limit))

    if search_type in ("all", "reminder"):
        results.extend(_search_reminders(uid, q, limit))

    # Sort combined results
    if sort_by == "amount":
        results.sort(key=lambda r: r.get("amount", 0), reverse=True)
    else:
        results.sort(key=lambda r: r.get("date", ""), reverse=True)

    logger.info("Search user=%s q='%s' results=%s", uid, q[:20], len(results))
    return jsonify({"query": q, "total": len(results), "results": results})


def _search_expenses(uid, q, min_amt, max_amt, from_d, to_d, sort_by, limit):
    query = db.session.query(Expense).filter(Expense.user_id == uid)
    if q:
        query = query.filter(Expense.notes.ilike(f"%{q}%"))
    if min_amt is not None:
        query = query.filter(Expense.amount >= min_amt)
    if max_amt is not None:
        query = query.filter(Expense.amount <= max_amt)
    if from_d:
        query = query.filter(Expense.spent_at >= from_d)
    if to_d:
        query = query.filter(Expense.spent_at <= to_d)

    if sort_by == "amount":
        query = query.order_by(Expense.amount.desc())
    else:
        query = query.order_by(Expense.spent_at.desc())

    items = query.limit(limit).all()
    return [
        {
            "type": "expense",
            "id": e.id,
            "description": e.notes or "",
            "amount": float(e.amount),
            "currency": e.currency,
            "date": e.spent_at.isoformat(),
            "category_id": e.category_id,
        }
        for e in items
    ]


def _search_bills(uid, q, min_amt, max_amt, sort_by, limit):
    query = db.session.query(Bill).filter(Bill.user_id == uid, Bill.active == True)
    if q:
        query = query.filter(Bill.name.ilike(f"%{q}%"))
    if min_amt is not None:
        query = query.filter(Bill.amount >= min_amt)
    if max_amt is not None:
        query = query.filter(Bill.amount <= max_amt)

    if sort_by == "amount":
        query = query.order_by(Bill.amount.desc())
    else:
        query = query.order_by(Bill.next_due_date.desc())

    items = query.limit(limit).all()
    return [
        {
            "type": "bill",
            "id": b.id,
            "description": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value if b.cadence else None,
        }
        for b in items
    ]


def _search_reminders(uid, q, limit):
    query = db.session.query(Reminder).filter(Reminder.user_id == uid)
    if q:
        query = query.filter(Reminder.message.ilike(f"%{q}%"))
    items = query.order_by(Reminder.send_at.desc()).limit(limit).all()
    return [
        {
            "type": "reminder",
            "id": r.id,
            "description": r.message,
            "amount": None,
            "currency": None,
            "date": r.send_at.isoformat() if r.send_at else "",
            "sent": r.sent,
        }
        for r in items
    ]


def _parse_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_date(val):
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except ValueError:
        return None
