"""Advanced search across transactions & bills (issue #105)."""
import logging
from datetime import date
from decimal import Decimal
from sqlalchemy import or_, and_
from ..extensions import db
from ..models import Expense, Bill, Category

logger = logging.getLogger("finmind.search")


def search(user_id: int, query: str = None, amount_min: float = None,
           amount_max: float = None, date_from: str = None, date_to: str = None,
           expense_type: str = None, category_id: int = None,
           include_bills: bool = False, limit: int = 50) -> dict:
    """
    Full-text + filter search across expenses (and optionally bills).
    """
    results = {"expenses": [], "bills": [], "total": 0}

    # -- Expenses --
    q = db.session.query(Expense).filter(Expense.user_id == user_id)
    if query:
        q = q.filter(Expense.notes.ilike(f"%{query}%"))
    if amount_min is not None:
        q = q.filter(Expense.amount >= Decimal(str(amount_min)))
    if amount_max is not None:
        q = q.filter(Expense.amount <= Decimal(str(amount_max)))
    if date_from:
        q = q.filter(Expense.spent_at >= date.fromisoformat(date_from))
    if date_to:
        q = q.filter(Expense.spent_at <= date.fromisoformat(date_to))
    if expense_type:
        q = q.filter(Expense.expense_type == expense_type.upper())
    if category_id is not None:
        q = q.filter(Expense.category_id == category_id)

    expenses = q.order_by(Expense.spent_at.desc()).limit(limit).all()
    results["expenses"] = [{"id": e.id, "amount": float(e.amount), "notes": e.notes,
                             "date": e.spent_at.isoformat(), "type": e.expense_type,
                             "category_id": e.category_id} for e in expenses]

    # -- Bills --
    if include_bills and query:
        bills = (db.session.query(Bill)
                 .filter(Bill.user_id == user_id, Bill.name.ilike(f"%{query}%"))
                 .limit(20).all())
        results["bills"] = [{"id": b.id, "name": b.name, "amount": float(b.amount),
                              "due": b.next_due_date.isoformat() if b.next_due_date else None}
                            for b in bills]

    results["total"] = len(results["expenses"]) + len(results["bills"])
    return results
