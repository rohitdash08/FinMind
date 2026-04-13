"""Advanced search across transactions & bills."""

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from ..extensions import db
from ..models import Expense, Bill, Category
import logging

bp = Blueprint("search", __name__)
logger = logging.getLogger("finmind.search")


@bp.get("")
@jwt_required()
def search():
    """Search across expenses and bills.

    Query params: q (text), min_amount, max_amount, category_id,
    expense_type, from_date, to_date, source (expenses|bills|all)
    """
    uid = int(get_jwt_identity())
    q = (request.args.get("q") or "").strip()
    source = (request.args.get("source") or "all").strip().lower()
    min_amount = request.args.get("min_amount")
    max_amount = request.args.get("max_amount")
    category_id = request.args.get("category_id")
    expense_type = request.args.get("expense_type")
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    results = {"expenses": [], "bills": [], "total": 0}

    # Search expenses
    if source in ("all", "expenses"):
        query = db.session.query(Expense).filter_by(user_id=uid)
        if q:
            query = query.filter(Expense.notes.ilike(f"%{q}%"))
        if min_amount:
            try:
                query = query.filter(Expense.amount >= Decimal(min_amount))
            except (InvalidOperation, ValueError):
                return jsonify(error="invalid min_amount"), 400
        if max_amount:
            try:
                query = query.filter(Expense.amount <= Decimal(max_amount))
            except (InvalidOperation, ValueError):
                return jsonify(error="invalid max_amount"), 400
        if category_id:
            query = query.filter(Expense.category_id == int(category_id))
        if expense_type:
            query = query.filter(Expense.expense_type == expense_type.upper())
        if from_date:
            try:
                query = query.filter(Expense.spent_at >= date.fromisoformat(from_date))
            except ValueError:
                return jsonify(error="invalid from_date"), 400
        if to_date:
            try:
                query = query.filter(Expense.spent_at <= date.fromisoformat(to_date))
            except ValueError:
                return jsonify(error="invalid to_date"), 400
        expenses = query.order_by(Expense.spent_at.desc()).limit(50).all()
        results["expenses"] = [
            {
                "id": e.id,
                "type": "expense",
                "amount": float(e.amount),
                "currency": e.currency,
                "description": e.notes or "",
                "category_id": e.category_id,
                "expense_type": e.expense_type,
                "date": e.spent_at.isoformat(),
            }
            for e in expenses
        ]

    # Search bills
    if source in ("all", "bills"):
        bq = db.session.query(Bill).filter_by(user_id=uid)
        if q:
            bq = bq.filter(Bill.name.ilike(f"%{q}%"))
        if min_amount:
            try:
                bq = bq.filter(Bill.amount >= Decimal(min_amount))
            except (InvalidOperation, ValueError):
                pass
        if max_amount:
            try:
                bq = bq.filter(Bill.amount <= Decimal(max_amount))
            except (InvalidOperation, ValueError):
                pass
        bills = bq.order_by(Bill.next_due_date.desc()).limit(50).all()
        results["bills"] = [
            {
                "id": b.id,
                "type": "bill",
                "amount": float(b.amount),
                "currency": b.currency,
                "name": b.name,
                "next_due_date": b.next_due_date.isoformat(),
                "cadence": b.cadence.value if b.cadence else None,
            }
            for b in bills
        ]

    results["total"] = len(results["expenses"]) + len(results["bills"])
    logger.info("Search user=%s q=%s results=%d", uid, q, results["total"])
    return jsonify(results)
