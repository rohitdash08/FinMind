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


# --- Weekly Summary ---
from datetime import date, timedelta


def _week_identifier(week_str: str | None) -> tuple[str, date, date]:
    """Return (week_id, start, end) for a week. week_str is YYYY-Www or None for current."""
    today = date.today()
    if week_str and "-" in week_str:
        parts = week_str.split("-")
        year = int(parts[0])
        week_num = int(parts[1].lstrip("Ww"))
        jan4 = date(year, 1, 4)
        start = jan4 + timedelta(weeks=week_num - 1, days=-jan4.weekday())
        end = start + timedelta(days=6)
        return week_str, start, end
    # Current week: Monday to Sunday
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    year, week_num, _ = today.isocalendar()
    return f"{year}-W{week_num:02d}", start, end


def _weekly_totals(uid: int, start: date, end: date) -> tuple[float, float]:
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
        .all()
    )
    return {str(k or "uncat"): float(v) for k, v in rows}


def _prior_week_spend(uid: int, start: date, end: date) -> dict[str, float]:
    """Get expenses by category for the prior week."""
    week_len = (end - start).days + 1
    prev_start = start - timedelta(days=week_len)
    prev_end = prev_start + timedelta(days=week_len - 1)
    return _weekly_category_spend(uid, prev_start, prev_end)


def _build_weekly_analytics(uid: int, start: date, end: date) -> dict:
    _, current_expenses = _weekly_totals(uid, start, end)
    prev_cats = _prior_week_spend(uid, start, end)
    _, prev_expenses = 0, sum(prev_cats.values())

    wow = (
        round(((current_expenses - prev_expenses) / prev_expenses) * 100, 2)
        if prev_expenses > 0
        else 0.0
    )

    cats = _weekly_category_spend(uid, start, end)
    top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]

    # Detect unusual spend: any category up 50%+ vs prior week
    unusual = []
    for cat_id, amount in cats.items():
        prev_amount = prev_cats.get(cat_id, 0)
        if prev_amount > 0 and amount > prev_amount * 1.5:
            unusual.append({
                "category_id": cat_id,
                "current_amount": round(amount, 2),
                "previous_amount": round(prev_amount, 2),
                "increase_pct": round(((amount - prev_amount) / prev_amount) * 100, 2),
            })
    unusual.sort(key=lambda x: x["increase_pct"], reverse=True)

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "current_week_expenses": round(current_expenses, 2),
        "previous_week_expenses": round(prev_expenses, 2),
        "week_over_week_change_pct": wow,
        "top_categories": [{"category_id": k, "amount": round(v, 2)} for k, v in top],
        "unusual_spend": unusual,
    }


def _build_heuristic_response(
    uid: int, week_id: str, start: date, end: date,
    persona: str, warnings: list[str] | None = None,
) -> dict:
    income, expenses = _weekly_totals(uid, start, end)
    net = round(income - expenses, 2)
    analytics = _build_weekly_analytics(uid, start, end)

    insights = []
    tips = []

    if net < 0:
        insights.append(f"You spent ₹{abs(net)} more than you earned this week.")
        tips.append("Review non-essential purchases to get back on track.")
    elif net > 0:
        insights.append(f"You saved ₹{net} this week — great discipline!")
        tips.append("Consider moving your savings to a dedicated account.")

    wow = analytics["week_over_week_change_pct"]
    if wow > 10:
        insights.append(f"Spending is up {wow}% vs last week.")
        tips.append("Identify the top category driving the increase and set a cap.")
    elif wow < -10:
        insights.append(f"Spending is down {abs(wow)}% vs last week. Keep it up!")
        tips.append("You are building good financial habits.")

    if income > 0:
        savings_rate = round((net / income) * 100, 1)
        insights.append(f"Savings rate: {savings_rate}% of income.")

    unusual = analytics["unusual_spend"]
    if unusual:
        top_unusual = unusual[0]
        insights.append(
            f"Unusual spend detected in '{top_unusual['category_id']}': "
            f"₹{top_unusual['current_amount']} vs ₹{top_unusual['previous_amount']} last week "
            f"(+{top_unusual['increase_pct']}%)."
        )

    result = {
        "week": week_id,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "net_flow": net,
        "insights": insights,
        "tips": tips[:3],
        "analytics": analytics,
        "method": "heuristic",
    }
    if warnings:
        result["warnings"] = warnings
    return result


def _gemini_weekly_summary(
    uid: int, week_id: str, start: date, end: date,
    api_key: str, model: str, persona: str,
) -> dict:
    categories = _weekly_category_spend(uid, start, end)
    analytics = _build_weekly_analytics(uid, start, end)
    income, expenses = _weekly_totals(uid, start, end)
    net = round(income - expenses, 2)
    prompt = (
        f"{persona}\n"
        "Use this week data and return strict JSON with keys: "
        "insights (list of strings), tips (list of up to 3 strings).\n"
        f"week={week_id} ({start.isoformat()} to {end.isoformat()})\n"
        f"total_income={round(income,2)} total_expenses={round(expenses,2)} net_flow={net}\n"
        f"category_spend={categories}\n"
        f"week_over_week_change_pct={analytics['week_over_week_change_pct']}\n"
        f"unusual_spend={analytics['unusual_spend']}"
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
    result = {
        "week": week_id,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "net_flow": net,
        "insights": parsed.get("insights", []),
        "tips": parsed.get("tips", [])[:3],
        "analytics": analytics,
        "method": "gemini",
    }
    return result


def weekly_summary_service(
    uid: int,
    week_str: str | None = None,
    gemini_api_key: str | None = None,
    persona: str | None = None,
):
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()
    week_id, start, end = _week_identifier(week_str)

    if key:
        try:
            return _gemini_weekly_summary(uid, week_id, start, end, key, model, persona_text)
        except Exception:
            return _build_heuristic_response(
                uid, week_id, start, end, persona_text, warnings=["gemini_unavailable"]
            )
    return _build_heuristic_response(uid, week_id, start, end, persona_text)
