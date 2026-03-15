from datetime import date, timedelta
import json
from urllib import request

from sqlalchemy import extract, func, and_

from ..config import Settings
from ..extensions import db
from ..models import Expense

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


def _get_week_range(base_date: date, offset: int = 0) -> tuple[date, date]:
    """Returns (start_date, end_date) for a week given a base date and offset."""
    # Standardizing on Monday as the start of the week
    start = base_date - timedelta(days=base_date.weekday()) + timedelta(weeks=offset)
    end = start + timedelta(days=6)
    return start, end


def _get_weekly_stats(uid: int, start: date, end: date):
    """Aggregates spending and income for a given date range."""
    rows = (
        db.session.query(
            Expense.expense_type, func.coalesce(func.sum(Expense.amount), 0)
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .group_by(Expense.expense_type)
        .all()
    )
    stats = {"EXPENSE": 0.0, "INCOME": 0.0}
    for row in rows:
        stats[row[0]] = float(row[1])
    return stats


def _get_weekly_category_breakdown(uid: int, start: date, end: date):
    rows = (
        db.session.query(
            Expense.category_id, func.coalesce(func.sum(Expense.amount), 0)
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    return {str(k or "uncat"): float(v) for k, v in rows}


def _get_daily_breakdown(uid: int, start: date, end: date):
    rows = (
        db.session.query(
            Expense.spent_at, func.coalesce(func.sum(Expense.amount), 0)
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
    # Fill in zeros for days with no expenses
    daily = {}
    curr = start
    while curr <= end:
        daily[curr.strftime("%Y-%m-%d")] = 0.0
        curr += timedelta(days=1)

    for row in rows:
        daily[row[0].strftime("%Y-%m-%d")] = float(row[1])

    return daily


def _heuristic_weekly_insights(uid: int, current_stats: dict, prev_stats: dict, categories: dict):
    insights = []
    curr_exp = current_stats["EXPENSE"]
    prev_exp = prev_stats["EXPENSE"]

    if prev_exp > 0:
        change = ((curr_exp - prev_exp) / prev_exp) * 100
        if change > 10:
            insights.append(f"Spending increased by {round(change, 1)}% compared to last week. Watch out for lifestyle creep!")
        elif change < -10:
            insights.append(f"Great job! You spent {round(abs(change), 1)}% less than last week.")

    top_cat = next(iter(categories.items()), None)
    if top_cat and top_cat[1] > 0:
        insights.append(f"Your top spending category this week was Category {top_cat[0]}, accounting for {round(top_cat[1], 2)}.")

    if current_stats["INCOME"] > curr_exp:
        insights.append("You maintained a positive net flow this week. Consider moving the surplus to savings.")
    elif curr_exp > current_stats["INCOME"] and current_stats["INCOME"] > 0:
        insights.append("Your expenses exceeded your income this week. Review your discretionary spending.")

    if not insights:
        insights = ["Maintain your current momentum.", "Keep tracking every expense.", "Review your upcoming bills."]

    return insights[:3]


def _gemini_weekly_digest(uid: int, start: date, end: date, api_key: str, model: str, persona: str):
    current_stats = _get_weekly_stats(uid, start, end)
    prev_start, prev_end = _get_week_range(start, offset=-1)
    prev_stats = _get_weekly_stats(uid, prev_start, prev_end)
    categories = _get_weekly_category_breakdown(uid, start, end)
    daily = _get_daily_breakdown(uid, start, end)

    wow_change = 0.0
    if prev_stats["EXPENSE"] > 0:
        wow_change = round(((current_stats["EXPENSE"] - prev_stats["EXPENSE"]) / prev_stats["EXPENSE"]) * 100, 2)

    prompt = (
        f"{persona}\n"
        "Generate 3 concise, actionable financial insights based on this week's data. "
        "Return strict JSON with key 'insights' (list of strings).\n"
        f"week_range={start} to {end}\n"
        f"current_week_stats={current_stats}\n"
        f"previous_week_stats={prev_stats}\n"
        f"wow_change={wow_change}%\n"
        f"category_breakdown={categories}\n"
        f"daily_breakdown={daily}"
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

    with request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    parsed = _extract_json_object(text)

    return {
        "week_start": start.strftime("%Y-%m-%d"),
        "week_end": end.strftime("%Y-%m-%d"),
        "total_spent": round(current_stats["EXPENSE"], 2),
        "total_income": round(current_stats["INCOME"], 2),
        "net_flow": round(current_stats["INCOME"] - current_stats["EXPENSE"], 2),
        "wow_change_pct": wow_change,
        "category_breakdown": categories,
        "daily_breakdown": daily,
        "insights": parsed.get("insights", []),
        "method": "gemini"
    }


def weekly_financial_digest(
    uid: int,
    week_offset: int = 0,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
):
    start, end = _get_week_range(date.today(), offset=week_offset)
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()

    if key:
        try:
            return _gemini_weekly_digest(uid, start, end, key, model, persona_text)
        except Exception:
            pass

    # Heuristic Fallback
    current_stats = _get_weekly_stats(uid, start, end)
    prev_start, prev_end = _get_week_range(start, offset=-1)
    prev_stats = _get_weekly_stats(uid, prev_start, prev_end)
    categories = _get_weekly_category_breakdown(uid, start, end)
    daily = _get_daily_breakdown(uid, start, end)

    wow_change = 0.0
    if prev_stats["EXPENSE"] > 0:
        wow_change = round(((current_stats["EXPENSE"] - prev_stats["EXPENSE"]) / prev_stats["EXPENSE"]) * 100, 2)

    return {
        "week_start": start.strftime("%Y-%m-%d"),
        "week_end": end.strftime("%Y-%m-%d"),
        "total_spent": round(current_stats["EXPENSE"], 2),
        "total_income": round(current_stats["INCOME"], 2),
        "net_flow": round(current_stats["INCOME"] - current_stats["EXPENSE"], 2),
        "wow_change_pct": wow_change,
        "category_breakdown": categories,
        "daily_breakdown": daily,
        "insights": _heuristic_weekly_insights(uid, current_stats, prev_stats, categories),
        "method": "heuristic"
    }
