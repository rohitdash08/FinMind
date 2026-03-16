"""Weekly financial digest service.

Computes a spending / income summary for a given ISO week and optionally
generates a short AI narrative via the Gemini API.
"""

import json
import logging
from datetime import date, timedelta
from urllib import request as url_request

from sqlalchemy import func

from ..config import Settings
from ..extensions import db
from ..models import Bill, Category, Expense

logger = logging.getLogger("finmind.digest")
_settings = Settings()


def _week_bounds(iso_week: str) -> tuple[date, date]:
    """Return (monday, sunday) for an ISO week string like '2026-W11'."""
    year, week = iso_week.split("-W")
    monday = date.fromisocalendar(int(year), int(week), 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _previous_week(iso_week: str) -> str:
    monday, _ = _week_bounds(iso_week)
    prev_monday = monday - timedelta(days=7)
    y, w, _ = prev_monday.isocalendar()
    return f"{y}-W{w:02d}"


def compute_digest(user_id: int, iso_week: str) -> dict:
    """Build the weekly digest payload for *user_id* and *iso_week*."""
    monday, sunday = _week_bounds(iso_week)

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

    # Category breakdown
    cat_rows = (
        db.session.query(
            Category.name,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
            Expense.expense_type != "INCOME",
        )
        .group_by(Category.name)
        .all()
    )
    category_breakdown = [
        {"category": name or "Uncategorized", "amount": round(float(amt), 2)}
        for name, amt in sorted(cat_rows, key=lambda r: float(r[1]), reverse=True)
    ]

    # Bills due this week
    bills_due = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active.is_(True),
            Bill.next_due_date >= monday,
            Bill.next_due_date <= sunday,
        )
        .all()
    )
    upcoming_bills = [
        {
            "name": b.name,
            "amount": float(b.amount),
            "due_date": b.next_due_date.isoformat(),
        }
        for b in bills_due
    ]

    # Week-over-week comparison
    prev = _previous_week(iso_week)
    prev_mon, prev_sun = _week_bounds(prev)
    prev_expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= prev_mon,
            Expense.spent_at <= prev_sun,
            Expense.expense_type != "INCOME",
        )
        .scalar()
        or 0
    )
    if prev_expenses > 0:
        wow_change = round(((expenses - prev_expenses) / prev_expenses) * 100, 2)
    else:
        wow_change = 0.0

    # Top transaction
    top_tx = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .first()
    )
    top_expense = None
    if top_tx:
        top_expense = {
            "amount": float(top_tx.amount),
            "notes": top_tx.notes or "N/A",
            "date": top_tx.spent_at.isoformat(),
        }

    return {
        "week": iso_week,
        "period": {"start": monday.isoformat(), "end": sunday.isoformat()},
        "summary": {
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net_flow": round(income - expenses, 2),
            "transaction_count": _tx_count(user_id, monday, sunday),
        },
        "week_over_week_change_pct": wow_change,
        "category_breakdown": category_breakdown,
        "top_expense": top_expense,
        "upcoming_bills": upcoming_bills,
    }


def _tx_count(uid: int, start: date, end: date) -> int:
    return (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
        or 0
    )


def generate_narrative(digest: dict) -> str:
    """Call Gemini to produce a short plain-text narrative for the digest."""
    api_key = _settings.gemini_api_key
    model = _settings.gemini_model or "gemini-1.5-flash"
    if not api_key:
        return _fallback_narrative(digest)

    prompt = (
        "You are FinMind's financial coach. Write a concise 3-4 sentence "
        "weekly financial summary from this data. Be encouraging and "
        "action-oriented. Do not use markdown.\n\n"
        f"{json.dumps(digest, indent=2)}"
    )
    body = json.dumps(
        {"contents": [{"parts": [{"text": prompt}]}]}
    ).encode()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    req = url_request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with url_request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", _fallback_narrative(digest))
        )
    except Exception:
        logger.warning("Gemini digest narrative failed, using fallback")
        return _fallback_narrative(digest)


def _fallback_narrative(d: dict) -> str:
    s = d["summary"]
    wow = d.get("week_over_week_change_pct", 0)
    direction = "up" if wow > 0 else "down" if wow < 0 else "unchanged"
    return (
        f"This week you earned {s['total_income']:.2f} and spent "
        f"{s['total_expenses']:.2f}, resulting in a net flow of "
        f"{s['net_flow']:.2f}. Your spending is {direction} "
        f"{abs(wow):.1f}% compared to last week."
    )
