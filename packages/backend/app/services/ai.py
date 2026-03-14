import json
from datetime import date, timedelta
from urllib import request

from sqlalchemy import extract, func

from ..config import Settings
from ..extensions import db
from ..models import Expense, Bill

_settings = Settings()
DEFAULT_PERSONA = (
    "You are FinMind's pragmatic financial coach. Be concise, non-judgmental, "
    "data-driven, and action-oriented. Return actionable, realistic guidance."
)


def _monthly_totals(uid: int, ym: str) -> tuple[float, float]:
    year, month = map(int, ym.split("-"))
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _category_spend(uid: int, ym: str) -> dict[str, float]:
    year, month = map(int, ym.split("-"))
    rows = (
        db.session.query(
            Expense.category_id, func.coalesce(func.sum(Expense.amount), 0)
        )
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {str(k or "uncat"): float(v) for k, v in rows}


def _previous_month(ym: str) -> str:
    year, month = map(int, ym.split("-"))
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _build_analytics(uid: int, ym: str) -> dict:
    _, current_expenses = _monthly_totals(uid, ym)
    _, prev_expenses = _monthly_totals(uid, _previous_month(ym))
    if prev_expenses > 0:
        mom = round(((current_expenses - prev_expenses) / prev_expenses) * 100, 2)
    else:
        mom = 0.0
    cats = _category_spend(uid, ym)
    top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
    return {
        "month_over_month_change_pct": mom,
        "current_month_expenses": round(current_expenses, 2),
        "previous_month_expenses": round(prev_expenses, 2),
        "top_categories": [{"category_id": k, "amount": round(v, 2)} for k, v in top],
    }


def _heuristic_budget(
    uid: int, ym: str, persona: str, warnings: list[str] | None = None
):
    income, expenses = _monthly_totals(uid, ym)
    target = round((expenses * 0.9) if expenses else 500.0, 2)
    payload = {
        "month": ym,
        "suggested_total": target,
        "breakdown": {
            "needs": round(target * 0.5, 2),
            "wants": round(target * 0.3, 2),
            "savings": round(target * 0.2, 2),
        },
        "tips": [
            "Cap discretionary spending in the highest category by 10%.",
            "Set one automatic transfer to savings on payday.",
        ],
        "analytics": _build_analytics(uid, ym),
        "persona": persona,
        "method": "heuristic",
    }
    if warnings:
        payload["warnings"] = warnings
    payload["net_flow"] = round(income - expenses, 2)
    return payload


def _extract_json_object(raw: str) -> dict:
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


def _gemini_budget_suggestion(
    uid: int, ym: str, api_key: str, model: str, persona: str
) -> dict:
    categories = _category_spend(uid, ym)
    analytics = _build_analytics(uid, ym)
    prompt = (
        f"{persona}\n"
        "Use this month data and return strict JSON only with keys: "
        "suggested_total, breakdown(needs,wants,savings), tips(list <=3).\n"
        f"month={ym}\n"
        f"category_spend={categories}\n"
        f"analytics={analytics}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
    ).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))
    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    parsed = _extract_json_object(text)
    parsed["month"] = ym
    parsed["analytics"] = analytics
    parsed["persona"] = persona
    parsed["method"] = "gemini"
    return parsed


def monthly_budget_suggestion(
    uid: int,
    ym: str,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
):
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()

    if key:
        try:
            return _gemini_budget_suggestion(uid, ym, key, model, persona_text)
        except Exception:
            return _heuristic_budget(
                uid, ym, persona_text, warnings=["gemini_unavailable"]
            )
    return _heuristic_budget(uid, ym, persona_text)


# ============ Weekly Summary Functions ============


def _get_week_range(week_offset: int = 0) -> tuple[date, date]:
    """Get the start and end dates for a week.

    Args:
        week_offset: 0 for current week, -1 for last week, etc.

    Returns:
        Tuple of (start_date, end_date) for the week
    """
    today = date.today()
    # Find Monday of the current week
    monday = today - timedelta(days=today.weekday())
    # Apply offset
    target_monday = monday + timedelta(weeks=week_offset)
    sunday = target_monday + timedelta(days=6)
    return target_monday, sunday


def _weekly_totals(uid: int, start_date: date, end_date: date) -> tuple[float, float]:
    """Get income and expenses for a date range."""
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _weekly_category_spend(uid: int, start_date: date, end_date: date) -> dict[str, float]:
    """Get category spending for a date range."""
    rows = (
        db.session.query(
            Expense.category_id, func.coalesce(func.sum(Expense.amount), 0)
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {str(k or "uncat"): float(v) for k, v in rows}


def _upcoming_bills(uid: int, days_ahead: int = 7) -> list[dict]:
    """Get bills due in the next N days."""
    today = date.today()
    future_date = today + timedelta(days=days_ahead)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active == True,
            Bill.next_due_date >= today,
            Bill.next_due_date <= future_date,
        )
        .order_by(Bill.next_due_date)
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "due_date": b.next_due_date.isoformat(),
            "days_until_due": (b.next_due_date - today).days,
        }
        for b in bills
    ]


def _build_weekly_analytics(uid: int, week_start: date, week_end: date) -> dict:
    """Build analytics comparing current week to previous week."""
    # Current week totals
    curr_income, curr_expenses = _weekly_totals(uid, week_start, week_end)

    # Previous week totals
    prev_start = week_start - timedelta(days=7)
    prev_end = week_start - timedelta(days=1)
    _, prev_expenses = _weekly_totals(uid, prev_start, prev_end)

    # Week-over-week change
    if prev_expenses > 0:
        wow_change = round(((curr_expenses - prev_expenses) / prev_expenses) * 100, 2)
    else:
        wow_change = 0.0

    # Category breakdown
    cats = _weekly_category_spend(uid, week_start, week_end)
    top_categories = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]

    # Daily spending pattern
    daily_spend = {}
    current = week_start
    while current <= week_end:
        day_total = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                Expense.spent_at == current,
                Expense.expense_type != "INCOME",
            )
            .scalar() or 0
        )
        daily_spend[current.isoformat()] = float(day_total)
        current += timedelta(days=1)

    return {
        "week_over_week_change_pct": wow_change,
        "current_week_expenses": round(curr_expenses, 2),
        "previous_week_expenses": round(prev_expenses, 2),
        "current_week_income": round(curr_income, 2),
        "net_flow": round(curr_income - curr_expenses, 2),
        "top_categories": [
            {"category_id": k, "amount": round(v, 2)} for k, v in top_categories
        ],
        "daily_spending": daily_spend,
    }


def _heuristic_weekly_summary(uid: int, week_start: date, week_end: date) -> dict:
    """Generate weekly summary using heuristic methods."""
    analytics = _build_weekly_analytics(uid, week_start, week_end)
    bills = _upcoming_bills(uid)

    # Generate insights based on the data
    insights = []
    if analytics["week_over_week_change_pct"] > 20:
        insights.append(
            f"Spending increased by {analytics['week_over_week_change_pct']}% compared to last week. Consider reviewing recent purchases."
        )
    elif analytics["week_over_week_change_pct"] < -20:
        insights.append(
            f"Great job! Spending decreased by {abs(analytics['week_over_week_change_pct'])}% compared to last week."
        )

    if analytics["top_categories"]:
        top_cat = analytics["top_categories"][0]
        insights.append(
            f"Your top spending category was {top_cat['category_id']} at {top_cat['amount']}."
        )

    if bills:
        total_due = sum(b["amount"] for b in bills)
        insights.append(
            f"You have {len(bills)} bill(s) due this week totaling {total_due}."
        )

    # Generate tips based on patterns
    tips = []
    if analytics["net_flow"] < 0:
        tips.append("Your expenses exceeded income this week. Review discretionary spending.")
    if analytics["week_over_week_change_pct"] > 10:
        tips.append("Try to identify one expense you can reduce next week.")

    # Determine trend
    if analytics["week_over_week_change_pct"] > 5:
        trend = "increasing"
    elif analytics["week_over_week_change_pct"] < -5:
        trend = "decreasing"
    else:
        trend = "stable"

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "analytics": analytics,
        "upcoming_bills": bills,
        "insights": insights,
        "tips": tips,
        "trend": trend,
        "method": "heuristic",
    }


def _gemini_weekly_summary(
    uid: int, week_start: date, week_end: date, api_key: str, model: str, persona: str
) -> dict:
    """Generate weekly summary using Gemini AI."""
    analytics = _build_weekly_analytics(uid, week_start, week_end)
    bills = _upcoming_bills(uid)
    categories = _weekly_category_spend(uid, week_start, week_end)

    prompt = (
        f"{persona}\n"
        "Generate a weekly financial digest. Return strict JSON with keys: "
        "insights(list <=4), tips(list <=3), trend(string: increasing/decreasing/stable). "
        "Analyze the weekly data and provide actionable guidance.\n"
        f"week_start={week_start.isoformat()}\n"
        f"week_end={week_end.isoformat()}\n"
        f"category_spend={categories}\n"
        f"analytics={analytics}\n"
        f"upcoming_bills={bills}"
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
    ).encode("utf-8")

    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with request.urlopen(req, timeout=10) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))

    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )

    parsed = _extract_json_object(text)
    parsed["week_start"] = week_start.isoformat()
    parsed["week_end"] = week_end.isoformat()
    parsed["analytics"] = analytics
    parsed["upcoming_bills"] = bills
    parsed["method"] = "gemini"

    return parsed


def weekly_digest(
    uid: int,
    week_offset: int = 0,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
) -> dict:
    """Generate a weekly financial summary with trends and insights.

    Args:
        uid: User ID
        week_offset: 0 for current week, -1 for last week, etc.
        gemini_api_key: Optional Gemini API key for AI-powered insights
        gemini_model: Gemini model to use
        persona: Optional custom persona for AI

    Returns:
        Dictionary containing weekly summary, analytics, insights, and tips
    """
    week_start, week_end = _get_week_range(week_offset)

    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()

    if key:
        try:
            return _gemini_weekly_summary(
                uid, week_start, week_end, key, model, persona_text
            )
        except Exception:
            return _heuristic_weekly_summary(uid, week_start, week_end)

    return _heuristic_weekly_summary(uid, week_start, week_end)
