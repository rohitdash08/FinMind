import json
from datetime import date, timedelta
from urllib import request

from sqlalchemy import extract, func

from ..config import Settings
from ..extensions import db
from ..models import Category, Expense

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


def _money(value) -> float:
    return round(float(value or 0), 2)


def _week_start(raw: str | None = None) -> date:
    if raw:
        parsed = date.fromisoformat(raw)
        return parsed - timedelta(days=parsed.weekday())
    today = date.today()
    return today - timedelta(days=today.weekday())


def _week_totals(uid: int, start: date) -> tuple[float, float]:
    end = start + timedelta(days=6)
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
    return _money(income), _money(expenses)


def _daily_week_totals(uid: int, start: date) -> list[dict]:
    end = start + timedelta(days=6)
    rows = (
        db.session.query(
            Expense.spent_at,
            Expense.expense_type,
            func.coalesce(func.sum(Expense.amount), 0),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .group_by(Expense.spent_at, Expense.expense_type)
        .all()
    )
    by_day = {
        (start + timedelta(days=offset)): {"income": 0.0, "expenses": 0.0}
        for offset in range(7)
    }
    for spent_at, expense_type, amount in rows:
        bucket = by_day[spent_at]
        if expense_type == "INCOME":
            bucket["income"] += float(amount or 0)
        else:
            bucket["expenses"] += float(amount or 0)
    return [
        {
            "date": day.isoformat(),
            "income": _money(values["income"]),
            "expenses": _money(values["expenses"]),
            "net_flow": _money(values["income"] - values["expenses"]),
        }
        for day, values in by_day.items()
    ]


def _weekly_category_spend(uid: int, start: date) -> list[dict]:
    end = start + timedelta(days=6)
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized"),
            func.coalesce(func.sum(Expense.amount), 0),
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
        .limit(5)
        .all()
    )
    return [
        {
            "category_id": category_id,
            "category_name": category_name,
            "amount": _money(amount),
        }
        for category_id, category_name, amount in rows
    ]


def _percentage_change(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


def _weekly_digest_insights(
    income: float,
    expenses: float,
    previous_expenses: float,
    top_categories: list[dict],
) -> tuple[list[str], list[str]]:
    insights: list[str] = []
    actions: list[str] = []
    if income == 0 and expenses == 0:
        insights.append("No activity was recorded for this week yet.")
        actions.append("Add this week's income and expenses to unlock a useful digest.")
        return insights, actions

    net_flow = income - expenses
    if net_flow >= 0:
        insights.append("This week is cash-flow positive based on recorded activity.")
        actions.append("Move part of the positive weekly balance into savings.")
    else:
        insights.append("This week is cash-flow negative based on recorded activity.")
        actions.append(
            "Review flexible spending before adding new non-essential expenses."
        )

    change = _percentage_change(expenses, previous_expenses)
    if change > 10:
        insights.append(f"Weekly spending is up {change}% from the previous week.")
        actions.append(
            "Audit the highest category and set a short-term cap for next week."
        )
    elif change < -10:
        insights.append(
            f"Weekly spending is down {abs(change)}% from the previous week."
        )
        actions.append("Keep the same controls that reduced spending this week.")
    elif previous_expenses:
        insights.append("Weekly spending is broadly in line with the previous week.")

    if top_categories and expenses > 0:
        top = top_categories[0]
        share = round((top["amount"] / expenses) * 100, 2)
        insights.append(
            f"{top['category_name']} is the largest spend area at {share}% of expenses."
        )
        actions.append(
            f"Check whether {top['category_name']} has avoidable repeat costs."
        )

    return insights[:4], actions[:4]


def weekly_financial_digest(uid: int, week_start: str | None = None) -> dict:
    start = _week_start(week_start)
    end = start + timedelta(days=6)
    previous_start = start - timedelta(days=7)
    income, expenses = _week_totals(uid, start)
    previous_income, previous_expenses = _week_totals(uid, previous_start)
    top_categories = _weekly_category_spend(uid, start)
    insights, actions = _weekly_digest_insights(
        income, expenses, previous_expenses, top_categories
    )
    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "total_income": income,
        "total_expenses": expenses,
        "net_flow": _money(income - expenses),
        "average_daily_expense": _money(expenses / 7),
        "previous_week": {
            "week_start": previous_start.isoformat(),
            "week_end": (previous_start + timedelta(days=6)).isoformat(),
            "total_income": previous_income,
            "total_expenses": previous_expenses,
            "net_flow": _money(previous_income - previous_expenses),
        },
        "trend": {
            "income_change_pct": _percentage_change(income, previous_income),
            "expense_change_pct": _percentage_change(expenses, previous_expenses),
            "net_flow_change": _money(
                (income - expenses) - (previous_income - previous_expenses)
            ),
        },
        "daily_totals": _daily_week_totals(uid, start),
        "top_categories": top_categories,
        "insights": insights,
        "recommended_actions": actions,
        "method": "heuristic",
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
