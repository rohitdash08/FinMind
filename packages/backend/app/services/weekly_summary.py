"""Service for generating weekly financial digest / summary."""

from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import extract, func, and_

from ..extensions import db
from ..models import Expense, Bill, Category
from ..services.cache import cache_get, cache_set


def weekly_summary_key(user_id: int, week_start: str) -> str:
    return f"user:{user_id}:weekly_summary:{week_start}"


def get_week_bounds(reference_date: date | None = None) -> tuple[date, date]:
    """Return (monday, sunday) of the week containing *reference_date*."""
    ref = reference_date or date.today()
    monday = ref - timedelta(days=ref.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def generate_weekly_summary(user_id: int, week_of: date | None = None) -> dict:
    """Build a comprehensive weekly financial digest for *user_id*.

    The digest includes:
    - total income / expenses / net for the week
    - daily spending breakdown
    - category breakdown
    - top expenses
    - upcoming bills (next 7 days from week end)
    - week-over-week trend comparison
    """
    monday, sunday = get_week_bounds(week_of)
    cache_key = weekly_summary_key(user_id, monday.isoformat())
    # Only serve cache if the week is in the past (complete)
    if sunday < date.today():
        cached = cache_get(cache_key)
        if cached:
            return cached

    payload: dict = {
        "week": {
            "start": monday.isoformat(),
            "end": sunday.isoformat(),
        },
        "totals": {
            "income": 0.0,
            "expenses": 0.0,
            "net": 0.0,
            "transaction_count": 0,
        },
        "daily_breakdown": [],
        "category_breakdown": [],
        "top_expenses": [],
        "upcoming_bills": [],
        "trends": {
            "expense_change_pct": None,
            "income_change_pct": None,
            "previous_week_expenses": 0.0,
            "previous_week_income": 0.0,
        },
    }

    # --- Totals -----------------------------------------------------------
    income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
            Expense.expense_type == "INCOME",
        )
        .scalar()
        or 0
    )
    expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
            Expense.expense_type != "INCOME",
        )
        .scalar()
        or 0
    )
    tx_count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
        )
        .scalar()
        or 0
    )
    payload["totals"] = {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net": round(income - expenses, 2),
        "transaction_count": tx_count,
    }

    # --- Daily breakdown ---------------------------------------------------
    daily_rows = (
        db.session.query(
            Expense.spent_at,
            Expense.expense_type,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
        )
        .group_by(Expense.spent_at, Expense.expense_type)
        .order_by(Expense.spent_at)
        .all()
    )
    daily_map: dict[str, dict] = {}
    for row in daily_rows:
        day_str = row.spent_at.isoformat()
        if day_str not in daily_map:
            daily_map[day_str] = {"date": day_str, "income": 0.0, "expenses": 0.0}
        if row.expense_type == "INCOME":
            daily_map[day_str]["income"] = round(float(row.total), 2)
        else:
            daily_map[day_str]["expenses"] = round(float(row.total), 2)
    # Fill missing days
    for i in range(7):
        d = (monday + timedelta(days=i)).isoformat()
        if d not in daily_map:
            daily_map[d] = {"date": d, "income": 0.0, "expenses": 0.0}
    payload["daily_breakdown"] = sorted(daily_map.values(), key=lambda x: x["date"])

    # --- Category breakdown ------------------------------------------------
    cat_rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
            func.count(Expense.id).label("count"),
        )
        .outerjoin(
            Category,
            and_(Category.id == Expense.category_id, Category.user_id == user_id),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    total_cat = sum(float(r.total_amount or 0) for r in cat_rows)
    payload["category_breakdown"] = [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": round(float(r.total_amount or 0), 2),
            "count": r.count,
            "share_pct": (
                round((float(r.total_amount or 0) / total_cat) * 100, 2)
                if total_cat > 0
                else 0
            ),
        }
        for r in cat_rows
    ]

    # --- Top expenses ------------------------------------------------------
    top = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .limit(5)
        .all()
    )
    payload["top_expenses"] = [
        {
            "id": e.id,
            "description": e.notes or "",
            "amount": float(e.amount),
            "date": e.spent_at.isoformat(),
            "category_id": e.category_id,
            "currency": e.currency,
        }
        for e in top
    ]

    # --- Upcoming bills (next 7 days from sunday) --------------------------
    bills_end = sunday + timedelta(days=7)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active.is_(True),
            Bill.next_due_date >= monday,
            Bill.next_due_date <= bills_end,
        )
        .order_by(Bill.next_due_date)
        .limit(10)
        .all()
    )
    payload["upcoming_bills"] = [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
        }
        for b in bills
    ]

    # --- Week-over-week trends ---------------------------------------------
    prev_monday = monday - timedelta(days=7)
    prev_sunday = monday - timedelta(days=1)
    prev_expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= prev_monday,
            Expense.spent_at <= prev_sunday,
            Expense.expense_type != "INCOME",
        )
        .scalar()
        or 0
    )
    prev_income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= prev_monday,
            Expense.spent_at <= prev_sunday,
            Expense.expense_type == "INCOME",
        )
        .scalar()
        or 0
    )
    payload["trends"] = {
        "previous_week_expenses": round(prev_expenses, 2),
        "previous_week_income": round(prev_income, 2),
        "expense_change_pct": (
            round(((expenses - prev_expenses) / prev_expenses) * 100, 1)
            if prev_expenses > 0
            else None
        ),
        "income_change_pct": (
            round(((income - prev_income) / prev_income) * 100, 1)
            if prev_income > 0
            else None
        ),
    }

    # Cache completed weeks for 1 hour
    if sunday < date.today():
        cache_set(cache_key, payload, ttl_seconds=3600)

    return payload
