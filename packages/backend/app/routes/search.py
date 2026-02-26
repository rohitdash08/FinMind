from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Expense, Bill, Category
import logging

bp = Blueprint("search", __name__)
logger = logging.getLogger("finmind.search")


@bp.get("")
@jwt_required()
def search():
    uid = int(get_jwt_identity())

    q = (request.args.get("q") or "").strip()
    result_type = (request.args.get("type") or "all").lower()
    category = request.args.get("category")
    min_amount = request.args.get("min_amount")
    max_amount = request.args.get("max_amount")
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    try:
        page = max(1, int(request.args.get("page", "1")))
        per_page = min(100, max(1, int(request.args.get("per_page", "20"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    # Resolve category id from name if needed
    category_id = None
    if category:
        try:
            category_id = int(category)
        except ValueError:
            cat = db.session.query(Category).filter_by(user_id=uid, name=category).first()
            category_id = cat.id if cat else -1  # -1 means no match

    results = []

    if result_type in ("all", "expense"):
        results.extend(_search_expenses(uid, q, category_id, min_amount, max_amount, from_date, to_date))

    if result_type in ("all", "bill"):
        results.extend(_search_bills(uid, q, category_id, min_amount, max_amount, from_date, to_date))

    # Sort by date descending
    results.sort(key=lambda r: r["date"], reverse=True)

    total = len(results)
    start = (page - 1) * per_page
    page_results = results[start : start + per_page]

    return jsonify(
        results=page_results,
        total=total,
        page=page,
        per_page=per_page,
    )


def _search_expenses(uid, q, category_id, min_amount, max_amount, from_date, to_date):
    query = db.session.query(Expense).filter_by(user_id=uid)

    if q:
        query = query.filter(Expense.notes.ilike(f"%{q}%"))
    if category_id is not None:
        query = query.filter(Expense.category_id == category_id)
    if min_amount:
        query = query.filter(Expense.amount >= float(min_amount))
    if max_amount:
        query = query.filter(Expense.amount <= float(max_amount))
    if from_date:
        query = query.filter(Expense.spent_at >= date.fromisoformat(from_date))
    if to_date:
        query = query.filter(Expense.spent_at <= date.fromisoformat(to_date))

    return [
        {
            "id": e.id,
            "type": "expense",
            "description": e.notes or "",
            "amount": float(e.amount),
            "currency": e.currency,
            "category_id": e.category_id,
            "date": e.spent_at.isoformat(),
        }
        for e in query.all()
    ]


def _search_bills(uid, q, category_id, min_amount, max_amount, from_date, to_date):
    query = db.session.query(Bill).filter_by(user_id=uid, active=True)

    if q:
        query = query.filter(Bill.name.ilike(f"%{q}%"))
    if min_amount:
        query = query.filter(Bill.amount >= float(min_amount))
    if max_amount:
        query = query.filter(Bill.amount <= float(max_amount))
    if from_date:
        query = query.filter(Bill.next_due_date >= date.fromisoformat(from_date))
    if to_date:
        query = query.filter(Bill.next_due_date <= date.fromisoformat(to_date))

    # Bills don't have category_id in the model, skip category filter for bills

    return [
        {
            "id": b.id,
            "type": "bill",
            "description": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "category_id": None,
            "date": b.next_due_date.isoformat(),
        }
        for b in query.all()
    ]
