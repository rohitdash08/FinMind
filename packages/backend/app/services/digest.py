import json
from datetime import date, timedelta
from urllib import request

from sqlalchemy import func

from ..config import Settings
from ..extensions import db
from ..models import Category, Expense

_settings = Settings()
DEFAULT_WEEKLY_PERSONA = (
    "You are FinMind's weekly finance analyst. Return concise, practical insights "
    "based on trends, category concentration, and net cash flow."
)


def _scoped_expense_query(uid: int):
    return db.session.query(Expense).filter(Expense.user_id == uid)


def _week_bounds(iso_year: int, iso_week: int) -> tuple[date, date]:
    start = date.fromisocalendar(iso_year, iso_week, 1)
    end = date.fromisocalendar(iso_year, iso_week, 7)
    return start, end


def _weekly_totals(uid: int, start: date, end: date) -> tuple[float, float]:
    scoped = _scoped_expense_query(uid)
    income = (
        scoped.filter(
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .with_entities(func.coalesce(func.sum(Expense.amount), 0))
        .scalar()
    )
    expenses = (
        scoped.filter(
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .with_entities(func.coalesce(func.sum(Expense.amount), 0))
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _category_breakdown(uid: int, start: date, end: date) -> list[dict]:
    rows = (
        _scoped_expense_query(uid)
        .outerjoin(Category, Category.id == Expense.category_id)
        .filter(
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .with_entities(
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("amount"),
        )
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    return [
        {"category": str(row.category_name), "amount": round(float(row.amount), 2)}
        for row in rows
    ]


def _daily_breakdown(uid: int, start: date, end: date) -> list[dict]:
    rows = (
        _scoped_expense_query(uid)
        .filter(
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .with_entities(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0).label("amount"),
        )
        .group_by(Expense.spent_at)
        .all()
    )
    by_day = {row.spent_at: round(float(row.amount), 2) for row in rows}
    return [
        {
            "date": (start + timedelta(days=i)).isoformat(),
            "expenses": by_day.get(start + timedelta(days=i), 0.0),
        }
        for i in range(7)
    ]


def _transaction_count(uid: int, start: date, end: date) -> int:
    return int(
        _scoped_expense_query(uid)
        .filter(Expense.spent_at >= start, Expense.spent_at <= end)
        .with_entities(func.count(Expense.id))
        .scalar()
        or 0
    )


def _heuristic_weekly_insights(payload: dict) -> list[str]:
    totals = payload["totals"]
    expenses = totals["expenses"]
    previous = payload["previous_week_expenses"]
    wow = payload["week_over_week_change_pct"]
    category_breakdown = payload["category_breakdown"]

    if payload["transaction_count"] == 0:
        return [
            "No transactions recorded this week.",
            "Set one spending cap and track it daily next week.",
        ]

    insights = [
        (
            f"Weekly expenses: {expenses:.2f} with "
            f"{wow:+.2f}% vs previous week ({previous:.2f})."
        ),
        f"Net cash flow this week: {totals['net']:.2f}.",
    ]
    if category_breakdown:
        top = category_breakdown[0]
        insights.append(f"Top spend category: {top['category']} ({top['amount']:.2f}).")
    else:
        insights.append("No expense categories were detected this week.")
    return insights


def _extract_json_object(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("model did not return JSON object")
    return json.loads(text[start : end + 1])


def _gemini_weekly_insights(
    payload: dict, api_key: str, model: str, persona: str
) -> list[str]:
    prompt = (
        f"{persona}\n"
        'Return strict JSON only: {"insights":["...","...","..."]}.\n'
        f"week={payload['week']}\n"
        f"totals={payload['totals']}\n"
        f"week_over_week_change_pct={payload['week_over_week_change_pct']}\n"
        f"category_breakdown={payload['category_breakdown']}\n"
        f"daily_breakdown={payload['daily_breakdown']}"
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
    insights = parsed.get("insights") or []
    if not isinstance(insights, list):
        raise ValueError("insights is not a list")
    return [str(item).strip() for item in insights if str(item).strip()]


def weekly_digest(
    uid: int,
    iso_year: int | None = None,
    iso_week: int | None = None,
    *,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
) -> dict:
    if iso_year is None or iso_week is None:
        today = date.today()
        iso_year, iso_week, _ = today.isocalendar()

    start, end = _week_bounds(iso_year, iso_week)
    previous_start = start - timedelta(days=7)
    previous_end = end - timedelta(days=7)

    income, expenses = _weekly_totals(uid, start, end)
    _, previous_expenses = _weekly_totals(uid, previous_start, previous_end)
    week_over_week = (
        round(((expenses - previous_expenses) / previous_expenses) * 100, 2)
        if previous_expenses > 0
        else 0.0
    )

    payload = {
        "week": f"{iso_year}-W{iso_week:02d}",
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "totals": {
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "net": round(income - expenses, 2),
        },
        "transaction_count": _transaction_count(uid, start, end),
        "previous_week_expenses": round(previous_expenses, 2),
        "week_over_week_change_pct": week_over_week,
        "category_breakdown": _category_breakdown(uid, start, end),
        "daily_breakdown": _daily_breakdown(uid, start, end),
    }

    payload["insights"] = _heuristic_weekly_insights(payload)
    payload["method"] = "heuristic"

    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_WEEKLY_PERSONA).strip()
    if key:
        try:
            ai_insights = _gemini_weekly_insights(payload, key, model, persona_text)
            if ai_insights:
                payload["insights"] = ai_insights
                payload["method"] = "gemini"
        except Exception:
            payload.setdefault("warnings", []).append("gemini_unavailable")

    return payload
