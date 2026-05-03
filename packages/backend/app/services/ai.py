import json
from urllib import request
from datetime import date, timedelta

from sqlalchemy import extract, func

from ..config import Settings
from ..extensions import db
from ..models import Expense

_settings = Settings()
DEFAULT_PERSONA = (
    "You are FinMind's pragmatic financial coach. Be concise, non-judgmental, "
    "data-driven, and action-oriented. Return actionable, realistic guidance."
)
DEFAULT_WEEKLY_PERSONA = (
    "You are FinMind's financial analyst. Analyze the weekly spending trends "
    "and provide a smart digest with key highlights and actionable insights."
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


def weekly_digest(
    uid: int,
    start_date_str: str | None = None,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
):
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_WEEKLY_PERSONA).strip()

    # Determine current week range
    if start_date_str:
        try:
            start_date = date.fromisoformat(start_date_str)
        except ValueError:
            start_date = date.today() - timedelta(days=date.today().weekday())
    else:
        start_date = date.today() - timedelta(days=date.today().weekday())

    end_date = start_date + timedelta(days=6)

    # Fetch data
    income, expenses = _weekly_stats(uid, start_date, end_date)
    categories = _weekly_category_spend(uid, start_date, end_date)

    # Previous week comparison
    prev_start = start_date - timedelta(days=7)
    prev_end = prev_start + timedelta(days=6)
    _, prev_expenses = _weekly_stats(uid, prev_start, prev_end)

    change_pct = 0.0
    if prev_expenses > 0:
        change_pct = round(((expenses - prev_expenses) / prev_expenses) * 100, 2)

    analytics = {
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "net_flow": round(income - expenses, 2),
        "change_vs_prev_week_pct": change_pct,
        "top_categories": sorted(
            [{"category_id": k, "amount": round(v, 2)} for k, v in categories.items()],
            key=lambda x: x["amount"],
            reverse=True,
        )[:3],
    }

    if key:
        try:
            return _gemini_weekly_digest(
                uid, start_date, end_date, analytics, key, model, persona_text
            )
        except Exception:
            return _heuristic_weekly_digest(
                analytics, persona_text, start_date, end_date, ["gemini_unavailable"]
            )

    return _heuristic_weekly_digest(analytics, persona_text, start_date, end_date)


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


def _weekly_stats(uid: int, start: date, end: date) -> tuple[float, float]:
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


def _weekly_category_spend(uid: int, start: date, end: date) -> dict[str, float]:
    rows = (
        db.session.query(Expense.category_id, func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {str(k or "uncat"): float(v) for k, v in rows}


def _gemini_weekly_digest(
    uid: int, start: date, end: date, analytics: dict, api_key: str, model: str, persona: str
) -> dict:
    prompt = (
        f"{persona}\n"
        "Generate a weekly financial digest based on the following analytics. "
        "Return strict JSON with keys: summary(string), highlights(list of strings), insights(list of strings).\n"
        f"Week: {start.isoformat()} to {end.isoformat()}\n"
        f"Analytics: {json.dumps(analytics)}"
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
    parsed["analytics"] = analytics
    parsed["period"] = {"start": start.isoformat(), "end": end.isoformat()}
    parsed["method"] = "gemini"
    return parsed


def _heuristic_weekly_digest(
    analytics: dict,
    persona: str,
    start: date,
    end: date,
    warnings: list[str] | None = None,
) -> dict:
    expenses = analytics["total_expenses"]
    change = analytics["change_vs_prev_week_pct"]

    summary = f"You spent total {expenses} this week. "
    if change > 0:
        summary += f"This is {change}% more than last week."
    elif change < 0:
        summary += f"Great! You spent {abs(change)}% less than last week."
    else:
        summary += "Your spending was consistent with last week."

    highlights = [
        f"Total Income: {analytics['total_income']}",
        f"Total Expenses: {analytics['total_expenses']}",
    ]
    for cat in analytics["top_categories"]:
        highlights.append(f"Top category: {cat['category_id']} ({cat['amount']})")

    insights = [
        "Monitor your top categories to find saving opportunities.",
        "Ensure your net flow remains positive for better financial health.",
    ]

    payload = {
        "summary": summary,
        "highlights": highlights[:3],
        "insights": insights,
        "analytics": analytics,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "persona": persona,
        "method": "heuristic",
    }
    if warnings:
        payload["warnings"] = warnings
    return payload
