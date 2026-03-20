"""Weekly financial digest service.

Aggregates a user's transactions, bills, and category spend for a given
ISO-week and produces a structured summary with trend analysis and
actionable insights.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any
from urllib import request as urllib_request

from sqlalchemy import extract, func, and_

from ..config import Settings
from ..extensions import db
from ..models import Bill, Category, Expense

_settings = Settings()

DEFAULT_DIGEST_PERSONA = (
    "You are FinMind's weekly digest assistant. Summarise the user's financial "
    "week concisely, highlighting trends, anomalies, and one actionable tip. "
    "Return strict JSON only."
)


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def week_bounds(iso_year: int, iso_week: int) -> tuple[date, date]:
    """Return (monday, sunday) for a given ISO year/week."""
    jan4 = date(iso_year, 1, 4)  # Jan 4 is always in ISO week 1
    start_of_week1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = start_of_week1 + timedelta(weeks=iso_week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def previous_week(iso_year: int, iso_week: int) -> tuple[int, int]:
    """Return (year, week) for the previous ISO week."""
    monday, _ = week_bounds(iso_year, iso_week)
    prev_day = monday - timedelta(days=1)
    return prev_day.isocalendar()[:2]


def parse_week_string(week_str: str) -> tuple[int, int]:
    """Parse '2026-W12' into (2026, 12). Raises ValueError on bad input."""
    parts = week_str.split("-W")
    if len(parts) != 2:
        raise ValueError(f"invalid week format: {week_str!r}, expected YYYY-Www")
    return int(parts[0]), int(parts[1])


def current_week_string() -> str:
    today = date.today()
    y, w, _ = today.isocalendar()
    return f"{y}-W{w:02d}"


# ---------------------------------------------------------------------------
# Data aggregation
# ---------------------------------------------------------------------------

def _week_totals(uid: int, start: date, end: date) -> tuple[float, float]:
    """Return (income, expenses) for a user in a date range."""
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


def _week_category_breakdown(
    uid: int, start: date, end: date
) -> list[dict[str, Any]]:
    """Category-level expense breakdown for a date range."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .outerjoin(
            Category,
            and_(Category.id == Expense.category_id, Category.user_id == uid),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    total = sum(float(r.total or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.name,
            "amount": round(float(r.total or 0), 2),
            "share_pct": (
                round((float(r.total or 0) / total) * 100, 2)
                if total > 0
                else 0
            ),
        }
        for r in rows
    ]


def _week_transactions(
    uid: int, start: date, end: date, limit: int = 20
) -> list[dict[str, Any]]:
    """Return recent transactions within a date range."""
    rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .order_by(Expense.spent_at.desc(), Expense.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "description": e.notes or "Transaction",
            "amount": float(e.amount),
            "date": e.spent_at.isoformat(),
            "type": e.expense_type,
            "category_id": e.category_id,
            "currency": e.currency,
        }
        for e in rows
    ]


def _upcoming_bills(uid: int, start: date, end: date) -> list[dict[str, Any]]:
    """Bills due within the week."""
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    return [
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


def _daily_spending(uid: int, start: date, end: date) -> list[dict[str, Any]]:
    """Per-day expense totals across the week."""
    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at.asc())
        .all()
    )
    return [
        {"date": r.spent_at.isoformat(), "amount": round(float(r.total or 0), 2)}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Trend computation
# ---------------------------------------------------------------------------

def _compute_trends(
    uid: int,
    iso_year: int,
    iso_week: int,
    current_income: float,
    current_expenses: float,
) -> dict[str, Any]:
    """Week-over-week trend metrics."""
    prev_y, prev_w = previous_week(iso_year, iso_week)
    prev_start, prev_end = week_bounds(prev_y, prev_w)
    prev_income, prev_expenses = _week_totals(uid, prev_start, prev_end)

    def pct_change(current: float, previous: float) -> float:
        if previous > 0:
            return round(((current - previous) / previous) * 100, 2)
        return 0.0 if current == 0 else 100.0

    return {
        "previous_week": f"{prev_y}-W{prev_w:02d}",
        "previous_income": round(prev_income, 2),
        "previous_expenses": round(prev_expenses, 2),
        "income_change_pct": pct_change(current_income, prev_income),
        "expense_change_pct": pct_change(current_expenses, prev_expenses),
    }


# ---------------------------------------------------------------------------
# AI-powered insights (optional, falls back to heuristic)
# ---------------------------------------------------------------------------

def _heuristic_insights(
    income: float,
    expenses: float,
    trends: dict,
    categories: list[dict],
) -> list[str]:
    """Generate basic insights without AI."""
    tips: list[str] = []
    net = income - expenses
    if net < 0:
        tips.append(
            f"You spent {abs(net):.2f} more than you earned this week. "
            "Review discretionary categories for quick wins."
        )
    elif net > 0:
        tips.append(
            f"Positive cash flow of {net:.2f} this week — consider directing "
            "the surplus to savings or debt repayment."
        )

    exp_change = trends.get("expense_change_pct", 0)
    if exp_change > 20:
        tips.append(
            f"Spending jumped {exp_change:.0f}% vs last week. "
            "Check if this is due to a one-off or a developing habit."
        )
    elif exp_change < -20:
        tips.append(
            f"Great discipline — spending dropped {abs(exp_change):.0f}% vs last week."
        )

    if categories:
        top = categories[0]
        tips.append(
            f"Top spending category: {top['category_name']} "
            f"({top['share_pct']:.0f}% of total). "
            "Look for patterns you can optimise."
        )

    return tips[:5]


def _gemini_digest_insights(
    income: float,
    expenses: float,
    trends: dict,
    categories: list[dict],
    daily: list[dict],
    api_key: str,
    model: str,
    persona: str,
) -> list[str]:
    """Use Gemini to produce richer weekly insights."""
    prompt = (
        f"{persona}\n"
        "Given the user's weekly financial data, return strict JSON with a "
        "single key 'insights' containing a list of 3-5 short insight strings.\n"
        f"income={income}, expenses={expenses}\n"
        f"trends={trends}\n"
        f"top_categories={categories[:5]}\n"
        f"daily_spending={daily}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3},
        }
    ).encode("utf-8")
    req = urllib_request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=10) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))
    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    # Extract JSON
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Gemini did not return valid JSON")
    parsed = json.loads(text[start : end + 1])
    return parsed.get("insights", [])[:5]


# ---------------------------------------------------------------------------
# Main digest builder
# ---------------------------------------------------------------------------

def build_weekly_digest(
    uid: int,
    week_str: str | None = None,
    gemini_api_key: str | None = None,
    persona: str | None = None,
) -> dict[str, Any]:
    """Build a complete weekly financial digest for a user.

    Parameters
    ----------
    uid : int
        User ID.
    week_str : str | None
        ISO week in format 'YYYY-Www' (e.g. '2026-W12'). Defaults to current week.
    gemini_api_key : str | None
        Optional Gemini API key for AI-powered insights.
    persona : str | None
        Optional persona override for AI insights.

    Returns
    -------
    dict
        Complete weekly digest payload.
    """
    if week_str is None:
        week_str = current_week_string()

    iso_year, iso_week = parse_week_string(week_str)
    start, end = week_bounds(iso_year, iso_week)

    # Core aggregations
    income, expenses = _week_totals(uid, start, end)
    net_flow = round(income - expenses, 2)
    categories = _week_category_breakdown(uid, start, end)
    transactions = _week_transactions(uid, start, end)
    bills = _upcoming_bills(uid, start, end)
    daily = _daily_spending(uid, start, end)
    trends = _compute_trends(uid, iso_year, iso_week, income, expenses)

    # Insights (AI or heuristic)
    persona_text = (persona or DEFAULT_DIGEST_PERSONA).strip()
    method = "heuristic"
    warnings: list[str] = []

    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = _settings.gemini_model

    if key:
        try:
            insights = _gemini_digest_insights(
                income, expenses, trends, categories, daily, key, model, persona_text
            )
            method = "gemini"
        except Exception:
            insights = _heuristic_insights(income, expenses, trends, categories)
            warnings.append("gemini_unavailable")
    else:
        insights = _heuristic_insights(income, expenses, trends, categories)

    transaction_count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    ) or 0

    payload: dict[str, Any] = {
        "week": week_str,
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "summary": {
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net_flow": net_flow,
            "transaction_count": transaction_count,
        },
        "trends": trends,
        "category_breakdown": categories,
        "daily_spending": daily,
        "transactions": transactions,
        "upcoming_bills": bills,
        "insights": insights,
        "method": method,
        "persona": persona_text,
    }
    if warnings:
        payload["warnings"] = warnings

    return payload
