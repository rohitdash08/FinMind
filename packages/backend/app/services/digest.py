"""Weekly financial digest service."""
from datetime import date, timedelta
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Category
import logging

logger = logging.getLogger("finmind.digest")


def get_week_range(d=None):
    d = d or date.today()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _spend_in_range(uid, start, end):
    result = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == uid, Expense.spent_at >= start,
        Expense.spent_at <= end, Expense.expense_type != "INCOME").scalar()
    return float(result)


def _income_in_range(uid, start, end):
    result = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == uid, Expense.spent_at >= start,
        Expense.spent_at <= end, Expense.expense_type == "INCOME").scalar()
    return float(result)


def _category_breakdown(uid, start, end):
    rows = db.session.query(Expense.category_id, func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == uid, Expense.spent_at >= start,
        Expense.spent_at <= end, Expense.expense_type != "INCOME").group_by(Expense.category_id).all()
    cats = {c.id: c.name for c in Category.query.filter_by(user_id=uid).all()}
    return {cats.get(cid, "Uncategorized"): round(float(v), 2) for cid, v in rows}


def generate_weekly_digest(uid, target_date=None):
    monday, sunday = get_week_range(target_date)
    prev_monday = monday - timedelta(days=7)
    prev_sunday = prev_monday + timedelta(days=6)

    spend = _spend_in_range(uid, monday, sunday)
    income = _income_in_range(uid, monday, sunday)
    prev_spend = _spend_in_range(uid, prev_monday, prev_sunday)
    breakdown = _category_breakdown(uid, monday, sunday)
    tx_count = Expense.query.filter(
        Expense.user_id == uid, Expense.spent_at >= monday,
        Expense.spent_at <= sunday).count()

    change = None
    change_pct = None
    if prev_spend > 0:
        change = round(spend - prev_spend, 2)
        change_pct = round(((spend - prev_spend) / prev_spend) * 100, 1)

    insights = []
    if spend > income:
        insights.append("Spending exceeded income this week.")
    elif income > 0 and spend / income < 0.5:
        insights.append("Good savings rate! Under 50% of income spent.")
    if change_pct and abs(change_pct) > 20:
        insights.append(f"Spending {'increased' if change_pct > 0 else 'decreased'} {abs(change_pct)}% vs last week.")

    return {
        "week_range": {"start": monday.isoformat(), "end": sunday.isoformat()},
        "summary": {"total_spent": round(spend, 2), "total_income": round(income, 2),
                     "transaction_count": tx_count, "category_breakdown": breakdown},
        "comparison": {"previous_week_spent": round(prev_spend, 2), "change": change, "change_pct": change_pct},
        "insights": insights,
    }