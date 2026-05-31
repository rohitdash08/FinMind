from datetime import date
from decimal import Decimal
from sqlalchemy import or_, and_
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Bill, Category, Expense

bp = Blueprint("search", __name__)


@bp.get("/search")
@jwt_required()
def search():
    uid = int(get_jwt_identity())
    query = (request.args.get("q") or "").strip()
    from_date = request.args.get("from")
    to_date = request.args.get("to")
    category_id = request.args.get("category_id")
    amount_min = request.args.get("amount_min")
    amount_max = request.args.get("amount_max")
    search_type = (request.args.get("type") or "all").strip()

    results = {"transactions": [], "bills": [], "total_count": 0}

    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(100, max(1, int(request.args.get("page_size", "20"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    offset = (page - 1) * page_size

    if search_type in ("all", "transactions"):
        tq = db.session.query(Expense).filter(Expense.user_id == uid)

        if query:
            tq = tq.filter(Expense.notes.ilike(f"%{query}%"))
        if from_date:
            try:
                tq = tq.filter(Expense.spent_at >= date.fromisoformat(from_date))
            except ValueError:
                pass
        if to_date:
            try:
                tq = tq.filter(Expense.spent_at <= date.fromisoformat(to_date))
            except ValueError:
                pass
        if category_id:
            try:
                tq = tq.filter(Expense.category_id == int(category_id))
            except ValueError:
                pass
        if amount_min:
            try:
                tq = tq.filter(Expense.amount >= Decimal(str(amount_min)))
            except Exception:
                pass
        if amount_max:
            try:
                tq = tq.filter(Expense.amount <= Decimal(str(amount_max)))
            except Exception:
                pass

        total = tq.count()
        rows = tq.order_by(Expense.spent_at.desc()).offset(offset).limit(page_size).all()

        results["transactions"] = [
            {
                "id": e.id,
                "type": "expense",
                "description": e.notes or "Transaction",
                "amount": float(e.amount),
                "date": e.spent_at.isoformat(),
                "expense_type": e.expense_type,
                "category_id": e.category_id,
                "currency": e.currency,
            }
            for e in rows
        ]
        results["total_count"] += total

    if search_type in ("all", "bills"):
        bq = db.session.query(Bill).filter(Bill.user_id == uid, Bill.active.is_(True))

        if query:
            bq = bq.filter(Bill.name.ilike(f"%{query}%"))
        if from_date:
            try:
                bq = bq.filter(Bill.next_due_date >= date.fromisoformat(from_date))
            except ValueError:
                pass
        if to_date:
            try:
                bq = bq.filter(Bill.next_due_date <= date.fromisoformat(to_date))
            except ValueError:
                pass
        if amount_min:
            try:
                bq = bq.filter(Bill.amount >= Decimal(str(amount_min)))
            except Exception:
                pass
        if amount_max:
            try:
                bq = bq.filter(Bill.amount <= Decimal(str(amount_max)))
            except Exception:
                pass

        bill_total = bq.count()
        bill_rows = (
            bq.order_by(Bill.next_due_date.asc()).offset(offset).limit(page_size).all()
        )

        results["bills"] = [
            {
                "id": b.id,
                "type": "bill",
                "name": b.name,
                "amount": float(b.amount),
                "next_due_date": b.next_due_date.isoformat(),
                "cadence": b.cadence.value if hasattr(b.cadence, "value") else str(b.cadence),
                "currency": b.currency,
            }
            for b in bill_rows
        ]
        results["total_count"] += bill_total

    return jsonify(results)
