"""Smart Digest service — generates weekly financial summaries.

Aggregates a user's income, expenses, category breakdown, bill obligations,
and spending trends for a given ISO week, then optionally enriches the
summary with AI-generated insights via Gemini.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any
from urllib import request as urllib_request

from sqlalchemy import extract, func

from ..config import Settings
from ..extensions import db
from ..models import Bill, Category, Expense

logger = logging.getLogger("finmind.smart_digest")
_settings = Settings()

DEFAULT_PERSONA = (
    "You are FinMind's weekly financial analyst. Summarise the user's week "
    "in 3-5 bullet points. Be concise, data-driven, and action-oriented. "
    "Highlight wins, risks, and one concrete saving tip. Return strict JSON "
    "with keys: highlights (list of strings), risk_flag (string or null), "
    "saving_tip (string)."
)


# ---------------------------------------------------------------------------
# Data aggregation helpers
# ---------------------------------------------------------------------------


def _week_bounds(iso_year: int, iso_week: int) -> tuple[date, date]:
    """Return (Monday, Sunday) for the given ISO year/week."""
    jan4 = date(iso_year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = start_of_week1 + timedelta(weeks=iso_week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _weekly_totals(
    uid: int, start: date, end: date
) -> tuple[float, float]:
    """Return (total_income, total_expenses) for the date range."""
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


def _category_breakdown(
    uid: int, start: date, end: date
) -> list[dict[str, Any]]:
    """Return per-category expense totals for the date range."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == uid),
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
            "category_name": r.category_name,
            "amount": round(float(r.total or 0), 2),
            "share_pct": (
                round((float(r.total or 0) / total) * 100, 2)
                if total > 0
                else 0.0
            ),
        }
        for r in rows
    ]


def _daily_spending(
    uid: int, start: date, end: date
) -> list[dict[str, Any]]:
    """Return per-day expense totals for the date range."""
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


def _top_transactions(
    uid: int, start: date, end: date, limit: int = 5
) -> list[dict[str, Any]]:
    """Return the largest expense transactions for the date range."""
    rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "amount": round(float(e.amount), 2),
            "description": e.notes or "Transaction",
            "date": e.spent_at.isoformat(),
            "category_id": e.category_id,
            "currency": e.currency,
        }
        for e in rows
    ]


def _upcoming_bills(uid: int, start: date, end: date) -> list[dict[str, Any]]:
    """Return bills due within the date range."""
    rows = (
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
            "amount": round(float(b.amount), 2),
            "currency": b.currency,
            "due_date": b.next_due_date.isoformat(),
        }
        for b in rows
    ]


def _week_over_week_change(
    uid: int, start: date, end: date
) -> float:
    """Calculate percentage change vs the previous week's expenses."""
    prev_start = start - timedelta(days=7)
    prev_end = end - timedelta(days=7)
    _, current = _weekly_totals(uid, start, end)
    _, previous = _weekly_totals(uid, prev_start, prev_end)
    if previous > 0:
        return round(((current - previous) / previous) * 100, 2)
    return 0.0


# ---------------------------------------------------------------------------
# AI enrichment
# ---------------------------------------------------------------------------


def _extract_json_object(raw: str) -> dict:
    """Extract a JSON object from a possibly markdown-wrapped AI response."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("model did not return JSON object")
    return json.loads(text[start : end + 1])


def _gemini_insights(
    summary_data: dict,
    api_key: str,
    model: str,
    persona: str,
) -> dict:
    """Call Gemini to generate AI-powered weekly insights."""
    prompt = (
        f"{persona}\n"
        "Given the following weekly financial data, return strict JSON only "
        "with keys: highlights (list of strings, 3-5 items), "
        "risk_flag (string or null), saving_tip (string).\n"
        f"Data: {json.dumps(summary_data)}"
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
    with urllib_request.urlopen(req, timeout=15) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))
    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    return _extract_json_object(text)


def _heuristic_insights(summary_data: dict) -> dict:
    """Generate basic insights without AI when Gemini is unavailable."""
    highlights: list[str] = []
    risk_flag = None
    saving_tip = "Review your top spending category for potential savings."

    income = summary_data.get("total_income", 0)
    expenses = summary_data.get("total_expenses", 0)
    wow = summary_data.get("week_over_week_change_pct", 0)

    if income > expenses:
        highlights.append(
            f"Positive cash flow: earned {income:.2f}, spent {expenses:.2f}."
        )
    elif expenses > 0:
        highlights.append(
            f"Spending exceeded income: earned {income:.2f}, spent {expenses:.2f}."
        )
        risk_flag = "Expenses exceeded income this week."

    if wow > 20:
        highlights.append(
            f"Spending increased {wow:.1f}% compared to last week."
        )
        risk_flag = risk_flag or "Significant spending increase detected."
    elif wow < -10:
        highlights.append(
            f"Great job! Spending decreased {abs(wow):.1f}% vs last week."
        )

    categories = summary_data.get("category_breakdown", [])
    if categories:
        top = categories[0]
        highlights.append(
            f"Top category: {top['category_name']} "
            f"({top['share_pct']:.0f}% of spending)."
        )
        saving_tip = (
            f"Consider setting a budget cap on '{top['category_name']}' "
            f"to reduce spending by 10-15%."
        )

    if not highlights:
        highlights.append("No transactions recorded this week.")

    return {
        "highlights": highlights,
        "risk_flag": risk_flag,
        "saving_tip": saving_tip,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_week_param(week_str: str | None) -> tuple[int, int]:
    """Parse an ISO week string 'YYYY-Www' into (iso_year, iso_week).

    If *week_str* is ``None`` or empty the current week is returned.
    Raises ``ValueError`` on invalid format.
    """
    if not week_str:
        today = date.today()
        iso_year, iso_week, _ = today.isocalendar()
        return iso_year, iso_week

    week_str = week_str.strip()
    if len(week_str) < 7 or week_str[4] != "-" or week_str[5] != "W":
        raise ValueError(
            f"Invalid week format '{week_str}', expected YYYY-Www (e.g. 2026-W14)"
        )

    try:
        iso_year = int(week_str[:4])
        iso_week = int(week_str[6:])
    except (ValueError, IndexError) as exc:
        raise ValueError(
            f"Invalid week format '{week_str}', expected YYYY-Www"
        ) from exc

    if not 1 <= iso_week <= 53:
        raise ValueError(f"Week number must be 1-53, got {iso_week}")

    return iso_year, iso_week


def generate_weekly_digest(
    user_id: int,
    iso_year: int,
    iso_week: int,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
) -> dict[str, Any]:
    """Build a complete weekly financial digest for *user_id*.

    Returns a dict ready for JSON serialisation containing:
    - period metadata (week, date range)
    - financial summary (income, expenses, net, wow change)
    - category breakdown
    - daily spending trend
    - top transactions
    - upcoming bills in the week
    - AI or heuristic insights
    """
    start, end = _week_bounds(iso_year, iso_week)
    income, expenses = _weekly_totals(user_id, start, end)
    wow_change = _week_over_week_change(user_id, start, end)
    categories = _category_breakdown(user_id, start, end)
    daily = _daily_spending(user_id, start, end)
    top_txns = _top_transactions(user_id, start, end)
    bills = _upcoming_bills(user_id, start, end)
    bills_total = round(sum(b["amount"] for b in bills), 2)

    summary_data = {
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "net_flow": round(income - expenses, 2),
        "week_over_week_change_pct": wow_change,
        "category_breakdown": categories,
    }

    # AI insights (Gemini) or heuristic fallback
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()
    warnings: list[str] = []

    if key:
        try:
            ai_insights = _gemini_insights(summary_data, key, model, persona_text)
            method = "gemini"
        except Exception:
            logger.warning("Gemini unavailable, falling back to heuristic insights")
            ai_insights = _heuristic_insights(summary_data)
            method = "heuristic"
            warnings.append("gemini_unavailable")
    else:
        ai_insights = _heuristic_insights(summary_data)
        method = "heuristic"

    payload: dict[str, Any] = {
        "period": {
            "iso_year": iso_year,
            "iso_week": iso_week,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        "summary": {
            "total_income": summary_data["total_income"],
            "total_expenses": summary_data["total_expenses"],
            "net_flow": summary_data["net_flow"],
            "week_over_week_change_pct": wow_change,
            "upcoming_bills_total": bills_total,
            "upcoming_bills_count": len(bills),
        },
        "category_breakdown": categories,
        "daily_spending": daily,
        "top_transactions": top_txns,
        "upcoming_bills": bills,
        "insights": ai_insights,
        "persona": persona_text,
        "method": method,
    }
    if warnings:
        payload["warnings"] = warnings

    logger.info(
        "Weekly digest generated user=%s week=%d-W%02d method=%s",
        user_id,
        iso_year,
        iso_week,
        method,
    )
    return payload
