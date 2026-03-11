import json
from datetime import datetime, date, timedelta
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


# === Weekly Digest Functions ===

def _weekly_totals(uid: int, week_start: str) -> tuple[float, float, dict]:
    """Get income, expenses, and category breakdown for a week."""
    from datetime import datetime
    year, month, day = map(int, week_start.split("-"))
    week_start_date = datetime(year, month, day)
    week_end = week_start_date + timedelta(days=6)
    
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start_date.date(),
            Expense.spent_at <= week_end.date(),
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start_date.date(),
            Expense.spent_at <= week_end.date(),
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    
    # Category breakdown
    rows = (
        db.session.query(
            Expense.category_id, func.coalesce(func.sum(Expense.amount), 0)
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= week_start_date.date(),
            Expense.spent_at <= week_end.date(),
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    categories = {str(k or "uncat"): float(v) for k, v in rows}
    
    return float(income or 0), float(expenses or 0), categories


def _previous_week(week_start: str) -> str:
    """Get the previous week's start date."""
    from datetime import datetime
    year, month, day = map(int, week_start.split("-"))
    prev = datetime(year, month, day) - timedelta(days=7)
    return prev.strftime("%Y-%m-%d")


def _get_week_start(weeks_ago: int = 0) -> str:
    """Get the start date of the week (Monday) for given weeks_ago."""
    from datetime import datetime, timedelta
    today = date.today()
    # Get Monday of current week
    monday = today - timedelta(days=today.weekday())
    # Go back the requested number of weeks
    target_monday = monday - timedelta(weeks=weeks_ago)
    return target_monday.strftime("%Y-%m-%d")


def _build_weekly_analytics(uid: int, week_start: str) -> dict:
    """Build analytics for weekly comparison."""
    _, current_expenses = _weekly_totals(uid, week_start)[:2]
    _, prev_expenses = _weekly_totals(uid, _previous_week(week_start))[:2]
    
    if prev_expenses > 0:
        wow = round(((current_expenses - prev_expenses) / prev_expenses) * 100, 2)
    else:
        wow = 0.0
    
    _, _, categories = _weekly_totals(uid, week_start)
    top = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]
    
    return {
        "week_over_week_change_pct": wow,
        "current_week_expenses": round(current_expenses, 2),
        "previous_week_expenses": round(prev_expenses, 2),
        "top_categories": [{"category_id": k, "amount": round(v, 2)} for k, v in top],
    }


def _heuristic_weekly_digest(uid: int, week_start: str, persona: str):
    """Generate weekly digest using heuristic approach."""
    income, expenses, categories = _weekly_totals(uid, week_start)
    analytics = _build_weekly_analytics(uid, week_start)
    
    # Generate insights based on spending patterns
    tips = []
    if analytics["week_over_week_change_pct"] > 20:
        tips.append("Your spending increased significantly compared to last week. Review your discretionary expenses.")
    elif analytics["week_over_week_change_pct"] < -20:
        tips.append("Great job! You spent significantly less than last week.")
    
    if categories:
        top_cat = max(categories.items(), key=lambda x: x[1])
        tips.append(f"Your highest spending was in {top_cat[0]} this week.")
    
    # Basic savings rate
    net_flow = round(income - expenses, 2)
    savings_rate = round((net_flow / income * 100), 2) if income > 0 else 0
    
    return {
        "week_start": week_start,
        "week_end": (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d"),
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net_flow": net_flow,
        "savings_rate_pct": savings_rate,
        "category_breakdown": categories,
        "tips": tips[:3],
        "analytics": analytics,
        "method": "heuristic",
    }


def _gemini_weekly_digest(
    uid: int, week_start: str, api_key: str, model: str, persona: str
) -> dict:
    """Generate weekly digest using Gemini AI."""
    from datetime import datetime
    week_end = (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
    
    income, expenses, categories = _weekly_totals(uid, week_start)
    analytics = _build_weekly_analytics(uid, week_start)
    
    prompt = (
        f"{persona}\n"
        "Generate a weekly financial digest. Return strict JSON with keys: "
        "summary (2-3 sentences), tips (list <=3), highlights (list <=2).\n"
        f"week={week_start} to {week_end}\n"
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
    with request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    
    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    parsed = _extract_json_object(text)
    
    # Combine with base data
    return {
        "week_start": week_start,
        "week_end": week_end,
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net_flow": round(income - expenses, 2),
        "savings_rate_pct": round((income - expenses) / income * 100, 2) if income > 0 else 0,
        "category_breakdown": categories,
        "summary": parsed.get("summary", ""),
        "tips": parsed.get("tips", []),
        "highlights": parsed.get("highlights", []),
        "analytics": analytics,
        "method": "gemini",
    }


def weekly_digest(
    uid: int,
    weeks_ago: int = 0,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
):
    """Get weekly financial digest."""
    from datetime import datetime, timedelta
    
    week_start = _get_week_start(weeks_ago)
    
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()
    
    if key:
        try:
            return _gemini_weekly_digest(uid, week_start, key, model, persona_text)
        except Exception:
            return _heuristic_weekly_digest(uid, week_start, persona_text)
    return _heuristic_weekly_digest(uid, week_start, persona_text)
