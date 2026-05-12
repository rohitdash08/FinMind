"""Advanced search across transactions and bills."""

from datetime import date
from decimal import Decimal

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Expense, Bill, Category

bp = Blueprint("search", __name__)


@bp.get("/")
@jwt_required()
def search():
    """Search across expenses and bills with filters.

    Query params:
    - q: text search in notes/name
    - type: expense|bill|all (default: all)
    - min_amount: minimum amount
    - max_amount: maximum amount
    - category_id: filter by category
    - date_from: start date (YYYY-MM-DD)
    - date_to: end date (YYYY-MM-DD)
    - sort: amount_asc|amount_desc|date_asc|date_desc (default: date_desc)
    - limit: max results (default: 50)
    """
    uid = int(get_jwt_identity())
    q = request.args.get("q", "").strip()
    search_type = request.args.get("type", "all")
    min_amount = request.args.get("min_amount", type=float)
    max_amount = request.args.get("max_amount", type=float)
    category_id = request.args.get("category_id", type=int)
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    sort = request.args.get("sort", "date_desc")
    limit = min(request.args.get("limit", 50, type=int), 200)

    results = []

    # Search expenses
    if search_type in ("all", "expense"):
        query = db.session.query(Expense).filter(Expense.user_id == uid)
        if q:
            query = query.filter(Expense.notes.ilike(f"%{q}%"))
        if min_amount is not None:
            query = query.filter(Expense.amount >= min_amount)
        if max_amount is not None:
            query = query.filter(Expense.amount <= max_amount)
        if category_id:
            query = query.filter(Expense.category_id == category_id)
        if date_from:
            query = query.filter(Expense.spent_at >= date.fromisoformat(date_from))
        if date_to:
            query = query.filter(Expense.spent_at <= date.fromisoformat(date_to))

        if sort == "amount_asc":
            query = query.order_by(Expense.amount.asc())
        elif sort == "amount_desc":
            query = query.order_by(Expense.amount.desc())
        elif sort == "date_asc":
            query = query.order_by(Expense.spent_at.asc())
        else:
            query = query.order_by(Expense.spent_at.desc())

        for e in query.limit(limit).all():
            results.append({
                "type": "expense",
                "id": e.id,
                "amount": float(e.amount),
                "currency": e.currency,
                "notes": e.notes,
                "date": e.spent_at.isoformat() if e.spent_at else None,
                "category_id": e.category_id,
                "expense_type": e.expense_type,
            })

    # Search bills
    if search_type in ("all", "bill"):
        query = db.session.query(Bill).filter(Bill.user_id == uid)
        if q:
            query = query.filter(Bill.name.ilike(f"%{q}%"))
        if min_amount is not None:
            query = query.filter(Bill.amount >= min_amount)
        if max_amount is not None:
            query = query.filter(Bill.amount <= max_amount)

        for b in query.limit(limit).all():
            results.append({
                "type": "bill",
                "id": b.id,
                "amount": float(b.amount),
                "currency": b.currency,
                "name": b.name,
                "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None,
                "active": b.active,
            })

    return jsonify(results=results, total=len(results))
