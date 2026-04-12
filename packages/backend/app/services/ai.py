import json
from urllib import request

from sqlalchemy import extract, func

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


# ---------------------------------------------------------------------------
# Weekly digest helpers
# ---------------------------------------------------------------------------


def _weekly_totals(uid: int, year: int, week: int) -> tuple[float, float]:
    """Get income and expense totals for an ISO week."""
    from datetime import date as _date

    monday = _date.fromisocalendar(year, week, 1)
    sunday = _date.fromisocalendar(year, week, 7)
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _weekly_category_spend(uid: int, year: int, week: int) -> dict[str, float]:
    """Category breakdown for a week."""
    from datetime import date as _date

    monday = _date.fromisocalendar(year, week, 1)
    sunday = _date.fromisocalendar(year, week, 7)
    rows = (
        db.session.query(
            Expense.category_id, func.coalesce(func.sum(Expense.amount), 0)
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= monday,
            Expense.spent_at <= sunday,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {str(k or "uncat"): float(v) for k, v in rows}


def _build_weekly_analytics(uid: int, year: int, week: int) -> dict:
    """Weekly analytics with week-over-week comparison."""
    _, current_expenses = _weekly_totals(uid, year, week)

    # Previous week
    from datetime import date as _date, timedelta

    prev_monday = _date.fromisocalendar(year, week, 1) - timedelta(weeks=1)
    prev_year, prev_week, _ = prev_monday.isocalendar()
    _, prev_expenses = _weekly_totals(uid, prev_year, prev_week)

    if prev_expenses > 0:
        wow = round(((current_expenses - prev_expenses) / prev_expenses) * 100, 2)
    else:
        wow = 0.0

    cats = _weekly_category_spend(uid, year, week)
    top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
    return {
        "week_over_week_change_pct": wow,
        "current_week_expenses": round(current_expenses, 2),
        "previous_week_expenses": round(prev_expenses, 2),
        "top_categories": [
            {"category_id": k, "amount": round(v, 2)} for k, v in top
        ],
    }


def _heuristic_weekly_digest(
    uid: int,
    year: int,
    week: int,
    persona: str,
    warnings: list[str] | None = None,
) -> dict:
    """Heuristic weekly digest without AI."""
    income, expenses = _weekly_totals(uid, year, week)
    net = round(income - expenses, 2)
    analytics = _build_weekly_analytics(uid, year, week)
    payload = {
        "week": f"{year}-W{week:02d}",
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "net_flow": net,
        "tips": [
            "Review your top spending category and look for savings.",
            "Set a mid-week spending checkpoint to stay on track.",
        ],
        "analytics": analytics,
        "persona": persona,
        "method": "heuristic",
    }
    if warnings:
        payload["warnings"] = warnings
    return payload


def _gemini_weekly_digest(
    uid: int,
    year: int,
    week: int,
    api_key: str,
    model: str,
    persona: str,
) -> dict:
    """AI-powered weekly digest via Gemini."""
    categories = _weekly_category_spend(uid, year, week)
    analytics = _build_weekly_analytics(uid, year, week)
    income, expenses = _weekly_totals(uid, year, week)
    prompt = (
        f"{persona}\n"
        "Use this week data and return strict JSON only with keys: "
        "tips(list <=3), summary(string).\n"
        f"week={year}-W{week:02d}\n"
        f"income={income}\n"
        f"expenses={expenses}\n"
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
    parsed["week"] = f"{year}-W{week:02d}"
    parsed["total_income"] = round(income, 2)
    parsed["total_expenses"] = round(expenses, 2)
    parsed["net_flow"] = round(income - expenses, 2)
    parsed["analytics"] = analytics
    parsed["persona"] = persona
    parsed["method"] = "gemini"
    return parsed


def weekly_digest(
    uid: int,
    year: int,
    week: int,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
) -> dict:
    """Main entry point - try Gemini, fallback to heuristic."""
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()

    if key:
        try:
            return _gemini_weekly_digest(uid, year, week, key, model, persona_text)
        except Exception:
            return _heuristic_weekly_digest(
                uid, year, week, persona_text, warnings=["gemini_unavailable"]
            )
    return _heuristic_weekly_digest(uid, year, week, persona_text)
