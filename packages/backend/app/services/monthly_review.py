"""Guided monthly financial review flow.

Step-by-step review process: spending summary, category analysis,
budget check, goal progress, action items.
"""

from datetime import date, timedelta
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category


class MonthlyReview(db.Model):
    __tablename__ = "monthly_reviews"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    current_step = db.Column(db.Integer, default=1)
    completed = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, default="")
    action_items = db.Column(db.Text, default="")  # JSON list
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    completed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (db.UniqueConstraint("user_id", "year", "month"),)


REVIEW_STEPS = [
    {"step": 1, "name": "spending_overview", "title": "Spending Overview", "description": "Review your total spending this month"},
    {"step": 2, "name": "category_breakdown", "title": "Category Breakdown", "description": "See where your money went"},
    {"step": 3, "name": "vs_last_month", "title": "Month Comparison", "description": "Compare with last month"},
    {"step": 4, "name": "top_expenses", "title": "Top Expenses", "description": "Review your biggest expenses"},
    {"step": 5, "name": "action_items", "title": "Action Items", "description": "Set goals for next month"},
]


def start_review(user_id: int, year: int, month: int) -> dict:
    existing = MonthlyReview.query.filter_by(user_id=user_id, year=year, month=month).first()
    if existing:
        return _serialize_review(existing, user_id)

    review = MonthlyReview(user_id=user_id, year=year, month=month)
    db.session.add(review)
    db.session.commit()
    return _serialize_review(review, user_id)


def get_review(user_id: int, year: int, month: int) -> dict | None:
    r = MonthlyReview.query.filter_by(user_id=user_id, year=year, month=month).first()
    return _serialize_review(r, user_id) if r else None


def get_step_data(user_id: int, year: int, month: int, step: int) -> dict:
    if step < 1 or step > len(REVIEW_STEPS):
        raise ValueError(f"Invalid step: {step}")

    step_info = REVIEW_STEPS[step - 1]
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    data = {"step": step_info}

    if step == 1:
        data["content"] = _spending_overview(user_id, start, end)
    elif step == 2:
        data["content"] = _category_breakdown(user_id, start, end)
    elif step == 3:
        data["content"] = _vs_last_month(user_id, start, end)
    elif step == 4:
        data["content"] = _top_expenses(user_id, start, end)
    elif step == 5:
        data["content"] = {"message": "Set your action items for next month."}

    return data


def advance_step(user_id: int, year: int, month: int, notes: str = "") -> dict:
    r = MonthlyReview.query.filter_by(user_id=user_id, year=year, month=month).first()
    if not r:
        raise ValueError("Review not found. Start one first.")

    if r.completed:
        return _serialize_review(r, user_id)

    if notes:
        existing = r.notes or ""
        r.notes = f"{existing}\n[Step {r.current_step}] {notes}".strip()

    if r.current_step < len(REVIEW_STEPS):
        r.current_step += 1
    else:
        r.completed = True
        r.completed_at = db.func.now()

    db.session.commit()
    return _serialize_review(r, user_id)


def set_action_items(user_id: int, year: int, month: int, items: str) -> dict:
    r = MonthlyReview.query.filter_by(user_id=user_id, year=year, month=month).first()
    if not r:
        raise ValueError("Review not found")
    r.action_items = items
    db.session.commit()
    return _serialize_review(r, user_id)


def list_reviews(user_id: int) -> list[dict]:
    reviews = (MonthlyReview.query.filter_by(user_id=user_id)
               .order_by(MonthlyReview.year.desc(), MonthlyReview.month.desc()).all())
    return [
        {"id": r.id, "year": r.year, "month": r.month, "completed": r.completed,
         "current_step": r.current_step}
        for r in reviews
    ]


def _spending_overview(user_id: int, start: date, end: date) -> dict:
    total = db.session.query(func.sum(Expense.amount)).filter(
        Expense.user_id == user_id, Expense.date >= start, Expense.date <= end
    ).scalar() or 0
    count = db.session.query(func.count(Expense.id)).filter(
        Expense.user_id == user_id, Expense.date >= start, Expense.date <= end
    ).scalar() or 0
    days = (end - start).days + 1
    return {
        "total_spent": round(float(total), 2),
        "transaction_count": count,
        "daily_average": round(float(total) / days, 2),
        "period": f"{start.isoformat()} to {end.isoformat()}",
    }


def _category_breakdown(user_id: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(Category.name, func.sum(Expense.amount), func.count(Expense.id))
        .join(Category, Expense.category_id == Category.id)
        .filter(Expense.user_id == user_id, Expense.date >= start, Expense.date <= end)
        .group_by(Category.name).all()
    )
    total = sum(float(r[1]) for r in rows) if rows else 0
    result = [
        {"category": name, "total": round(float(amt), 2), "count": cnt,
         "percentage": round(float(amt) / total * 100, 1) if total > 0 else 0}
        for name, amt, cnt in rows
    ]
    result.sort(key=lambda x: x["total"], reverse=True)
    return result


def _vs_last_month(user_id: int, start: date, end: date) -> dict:
    if start.month == 1:
        prev_start = date(start.year - 1, 12, 1)
    else:
        prev_start = date(start.year, start.month - 1, 1)
    prev_end = start - timedelta(days=1)

    current_total = float(db.session.query(func.sum(Expense.amount)).filter(
        Expense.user_id == user_id, Expense.date >= start, Expense.date <= end
    ).scalar() or 0)
    prev_total = float(db.session.query(func.sum(Expense.amount)).filter(
        Expense.user_id == user_id, Expense.date >= prev_start, Expense.date <= prev_end
    ).scalar() or 0)

    if prev_total > 0:
        change = round((current_total - prev_total) / prev_total * 100, 1)
    else:
        change = 100.0 if current_total > 0 else 0.0

    return {
        "current_month": round(current_total, 2),
        "previous_month": round(prev_total, 2),
        "change_pct": change,
        "direction": "up" if change > 0 else "down" if change < 0 else "flat",
    }


def _top_expenses(user_id: int, start: date, end: date, limit: int = 10) -> list[dict]:
    rows = (Expense.query.filter(
        Expense.user_id == user_id, Expense.date >= start, Expense.date <= end
    ).order_by(Expense.amount.desc()).limit(limit).all())
    return [
        {"id": e.id, "amount": float(e.amount), "description": e.description, "date": e.date.isoformat()}
        for e in rows
    ]


def _serialize_review(r: MonthlyReview, user_id: int) -> dict:
    return {
        "id": r.id, "year": r.year, "month": r.month,
        "current_step": r.current_step, "total_steps": len(REVIEW_STEPS),
        "completed": r.completed, "notes": r.notes, "action_items": r.action_items,
        "steps": REVIEW_STEPS,
    }
