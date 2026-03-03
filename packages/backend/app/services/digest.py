"""Weekly financial digest — highlights trends and insights.

Provides a ``weekly_digest`` function consumed by the ``/digest`` route.
The digest aggregates expenses for a given ISO week, compares with
the previous week, ranks categories, and optionally generates an
AI-powered narrative via the Gemini API.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from urllib import request as urllib_request

from sqlalchemy import func

from ..config import Settings
from ..extensions import db
from ..models import Category, Expense

_settings = Settings()

DIGEST_PERSONA = (
    "You are FinMind's weekly digest writer. Summarise the user's spending "
    "week in 3-4 concise bullet points. Highlight wins, flag overspends, and "
    "give one actionable tip. Be friendly, data-driven, and brief."
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _week_bounds(iso_year: int, iso_week: int) -> tuple[date, date]:
    """Return (monday, sunday) for the given ISO year/week."""
    jan4 = date(iso_year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = start_of_week1 + timedelta(weeks=iso_week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _week_totals(uid: int, start: date, end: date) -> tuple[float, float]:
    """Return (income, expenses) for the date range [start, end]."""
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _category_spend_range(uid: int, start: date, end: date) -> dict[str, float]:
    """Per-category spend in [start, end]."""
    rows = (
        db.session.query(
            Category.name,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Category.name)
        .all()
    )
    return {(name or "Uncategorized"): float(amount) for name, amount in rows}


def _daily_spend(uid: int, start: date, end: date) -> list[dict]:
    """Return per-day spend totals for [start, end]."""
    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at)
        .all()
    )
    return [{"date": str(d), "amount": float(a)} for d, a in rows]


def _transaction_count(uid: int, start: date, end: date) -> int:
    return (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    ) or 0


# ---------------------------------------------------------------------------
# AI narrative (optional)
# ---------------------------------------------------------------------------

def _gemini_narrative(
    data: dict, api_key: str, model: str, persona: str
) -> str | None:
    prompt = (
        f"{persona}\n\n"
        f"Week: {data['week']}\n"
        f"Total income: {data['income']}\n"
        f"Total expenses: {data['expenses']}\n"
        f"Net flow: {data['net_flow']}\n"
        f"WoW change: {data['wow_change_pct']}%\n"
        f"Top categories: {data['top_categories']}\n"
        f"Daily breakdown: {data['daily_breakdown']}\n\n"
        "Return a short markdown summary (3-4 bullet points)."
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4},
        }
    ).encode()
    req = urllib_request.Request(
        url=url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=10) as resp:  # nosec B310
        payload = json.loads(resp.read().decode())
    return (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def weekly_digest(
    uid: int,
    iso_year: int | None = None,
    iso_week: int | None = None,
    *,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
) -> dict:
    """Build the weekly financial digest for *uid*.

    If *iso_year*/*iso_week* are ``None`` the current week is used.
    """
    today = date.today()
    if iso_year is None or iso_week is None:
        iso_year, iso_week, _ = today.isocalendar()

    start, end = _week_bounds(iso_year, iso_week)
    prev_start, prev_end = _week_bounds(
        *(start - timedelta(weeks=1)).isocalendar()[:2]
    )

    income, expenses = _week_totals(uid, start, end)
    _, prev_expenses = _week_totals(uid, prev_start, prev_end)

    wow = (
        round(((expenses - prev_expenses) / prev_expenses) * 100, 2)
        if prev_expenses > 0
        else 0.0
    )

    cats = _category_spend_range(uid, start, end)
    top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]
    daily = _daily_spend(uid, start, end)
    tx_count = _transaction_count(uid, start, end)

    result: dict = {
        "week": f"{iso_year}-W{iso_week:02d}",
        "period": {"start": str(start), "end": str(end)},
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net_flow": round(income - expenses, 2),
        "transaction_count": tx_count,
        "wow_change_pct": wow,
        "previous_week_expenses": round(prev_expenses, 2),
        "top_categories": [
            {"category": name, "amount": round(amt, 2)} for name, amt in top
        ],
        "daily_breakdown": daily,
    }

    # AI narrative
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DIGEST_PERSONA).strip()

    if key:
        try:
            result["narrative"] = _gemini_narrative(result, key, model, persona_text)
            result["method"] = "gemini"
        except Exception:
            result["narrative"] = None
            result["method"] = "data_only"
            result.setdefault("warnings", []).append("gemini_unavailable")
    else:
        result["narrative"] = None
        result["method"] = "data_only"

    return result
