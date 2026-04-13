"""Financial data integrity and reconciliation."""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category, Bill
from datetime import date
bp = Blueprint("reconciliation", __name__)

@bp.get("/check")
@jwt_required()
def integrity_check():
    uid = int(get_jwt_identity())
    issues = []
    
    # Check for orphaned category references
    orphaned = db.session.query(Expense).filter(Expense.user_id == uid, Expense.category_id != None).all()
    valid_cats = {c.id for c in db.session.query(Category).filter_by(user_id=uid).all()}
    orphan_count = sum(1 for e in orphaned if e.category_id not in valid_cats)
    if orphan_count:
        issues.append({"type": "orphaned_category", "severity": "medium", "count": orphan_count, "message": f"{orphan_count} expenses reference non-existent categories"})

    # Check for negative amounts (except credit accounts)
    neg = db.session.query(Expense).filter(Expense.user_id == uid, Expense.amount < 0).count()
    if neg:
        issues.append({"type": "negative_amount", "severity": "low", "count": neg, "message": f"{neg} expenses have negative amounts"})

    # Check for future-dated expenses
    future = db.session.query(Expense).filter(Expense.user_id == uid, Expense.spent_at > date.today()).count()
    if future:
        issues.append({"type": "future_dated", "severity": "low", "count": future, "message": f"{future} expenses dated in the future"})

    # Check for duplicate expenses (same amount, date, description)
    dupes = db.session.query(Expense.amount, Expense.spent_at, Expense.notes, func.count(Expense.id).label("cnt")).filter(Expense.user_id == uid).group_by(Expense.amount, Expense.spent_at, Expense.notes).having(func.count(Expense.id) > 1).all()
    if dupes:
        total_dupes = sum(r.cnt - 1 for r in dupes)
        issues.append({"type": "duplicate", "severity": "high", "count": total_dupes, "message": f"{total_dupes} potential duplicate expenses found"})

    total_expenses = db.session.query(Expense).filter_by(user_id=uid).count()
    total_income = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.user_id == uid, Expense.expense_type == "INCOME").scalar() or 0)
    total_spent = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.user_id == uid, Expense.expense_type == "EXPENSE").scalar() or 0)

    return jsonify(
        healthy=len(issues) == 0,
        issues=issues,
        issue_count=len(issues),
        summary={"total_records": total_expenses, "total_income": total_income, "total_expenses": total_spent, "balance": round(total_income - total_spent, 2)}
    )
