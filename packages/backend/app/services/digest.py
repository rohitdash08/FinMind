"""Weekly financial digest service.

Generates a weekly summary of income, expenses, top spending categories,
day-over-day trends, and actionable insights.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from urllib import request

from sqlalchemy import func

from ..config import Settings
from ..extensions import db
from ..models import Category, Expense

_settings = Settings()

_DEFAULT_PERSONA = (
    "You are FinMind's pragmatic financial coach. Be concise, non-judgmental, "
    "data-driven, and action-oriented."
)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _week_bounds(week_start: date) -> tuple[date, date]:
    """Return (start, end) for the ISO week containing *week_start*.

    The caller may pass any date; we normalise to Monday of that week.
    """
    monday = week_start - timedelta(days=week_start.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _expenses_in_range(uid: int, start: date, end: date) -> list[Expense]:
    return (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .all()
    )


def _income_in_range(uid: int, start: date, end: date) -> float:
    val = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    return float(val)


def _category_name(cat_id: int | None) -> str:
    if cat_id is None:
        return "Uncategorised"
    cat = db.session.get(Category, cat_id)
    return cat.name if cat else "Unknown"


def _daily_breakdown(expenses: list[Expense]) -> list[dict]:
    by_day: dict[str, float] = {}
    for e in expenses:
        key = str(e.spent_at)
        by_day[key] = by_day.get(key, 0.0) + float(e.amount)
    return [{"date": d, "amount": round(v, 2)} for d, v in sorted(by_day.items())]


def _top_categories(expenses: list[Expense], n: int = 5) -> list[dict]:
    totals: dict[str | None, float] = {}
    for e in expenses:
        totals[e.category_id] = totals.get(e.category_id, 0.0) + float(e.amount)
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:n]
    return [
        {"category": _category_name(cid), "amount": round(amt, 2)}
        for cid, amt in ranked
    ]


# ---------------------------------------------------------------------------
# Heuristic digest (no AI required)
# ---------------------------------------------------------------------------


def _heuristic_digest(
    uid: int, start: date, end: date, prev_start: date, prev_end: date
) -> dict:
    expenses = _expenses_in_range(uid, start, end)
    prev_expenses = _expenses_in_range(uid, prev_start, prev_end)
    total = round(sum(float(e.amount) for e in expenses), 2)
    prev_total = round(sum(float(e.amount) for e in prev_expenses), 2)
    income = round(_income_in_range(uid, start, end), 2)

    wow_pct = (
        round(((total - prev_total) / prev_total) * 100, 1)
        if prev_total > 0
        else 0.0
    )

    # Simple insight rules
    tips: list[str] = []
    if total > prev_total * 1.1:
        tips.append(
            f"Spending rose {wow_pct}% vs the previous week — look for one-off items to cut."
        )
    elif total < prev_total * 0.9:
        tips.append(
            f"Great job! You spent {abs(wow_pct)}% less than last week. Keep it up."
        )
    else:
        tips.append("Your spending is stable week-over-week — a great baseline.")

    top = _top_categories(expenses)
    if top:
        tips.append(
            f"Your top spend category this week: {top[0]['category']} "
            f"({top[0]['amount']})."
        )

    if income > 0 and total > income:
        tips.append(
            "Heads up: you spent more than you earned this week. Consider reviewing discretionary items."
        )

    return {
        "week_start": str(start),
        "week_end": str(end),
        "total_expenses": total,
        "total_income": income,
        "net_flow": round(income - total, 2),
        "week_over_week_change_pct": wow_pct,
        "previous_week_expenses": prev_total,
        "top_categories": top,
        "daily_breakdown": _daily_breakdown(expenses),
        "insights": tips,
        "method": "heuristic",
    }


# ---------------------------------------------------------------------------
# Gemini-enhanced digest
# ---------------------------------------------------------------------------


def _gemini_digest(
    uid: int,
    start: date,
    end: date,
    prev_start: date,
    prev_end: date,
    api_key: str,
    model: str,
    persona: str,
) -> dict:
    base = _heuristic_digest(uid, start, end, prev_start, prev_end)

    prompt = (
        f"{persona}\n"
        "Given this weekly financial data, return a JSON object with a single key "
        '"insights" whose value is a list of 3-5 concise, actionable strings. '
        "Do not return anything else.\n"
        f"week_start={start}\n"
        f"total_expenses={base['total_expenses']}\n"
        f"total_income={base['total_income']}\n"
        f"week_over_week_change_pct={base['week_over_week_change_pct']}\n"
        f"top_categories={base['top_categories']}\n"
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
    ).encode()
    req = request.Request(url=url, data=body, headers={"Content-Type": "application/json"}, method="POST")

    with request.urlopen(req, timeout=10) as resp:  # nosec B310
        raw = json.loads(resp.read().decode())

    text = (
        raw.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
        .strip()
    )
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()

    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx > start_idx:
        parsed = json.loads(text[start_idx : end_idx + 1])
        if isinstance(parsed.get("insights"), list):
            base["insights"] = parsed["insights"]

    base["method"] = "gemini"
    return base


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def weekly_digest(
    uid: int,
    week_start: date | None = None,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
) -> dict:
    """Return a weekly financial digest for user *uid*.

    Args:
        uid: User ID.
        week_start: Any date within the desired week (defaults to current week).
        gemini_api_key: Optional Gemini API key for AI-enhanced insights.
        gemini_model: Override Gemini model name.
        persona: System persona for the AI.

    Returns:
        Dictionary with weekly summary data.
    """
    ref = week_start or date.today()
    start, end = _week_bounds(ref)
    prev_start, prev_end = _week_bounds(start - timedelta(days=7))

    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or _DEFAULT_PERSONA).strip()

    if key:
        try:
            return _gemini_digest(uid, start, end, prev_start, prev_end, key, model, persona_text)
        except Exception:
            result = _heuristic_digest(uid, start, end, prev_start, prev_end)
            result["warnings"] = ["gemini_unavailable"]
            return result

    return _heuristic_digest(uid, start, end, prev_start, prev_end)
