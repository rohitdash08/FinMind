import json
from datetime import date, timedelta
from urllib import request

from sqlalchemy import extract, func

from ..config import Settings
from ..extensions import db
from ..models import Bill, Category, Expense

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


def _normalize_week_start(raw: str | None) -> date:
    selected = date.fromisoformat(raw) if raw else date.today()
    return selected - timedelta(days=selected.weekday())


def _week_range(week_start: date) -> tuple[date, date]:
    return week_start, week_start + timedelta(days=6)


def _expenses_for_range(uid: int, start: date, end: date, currency: str | None = None):
    q = db.session.query(Expense).filter(
        Expense.user_id == uid,
        Expense.spent_at >= start,
        Expense.spent_at <= end,
    )
    if currency:
        q = q.filter(Expense.currency == currency)
    return q.order_by(Expense.spent_at.asc(), Expense.created_at.asc()).all()


def _amount(expense: Expense) -> float:
    return float(expense.amount or 0)


def _category_names(uid: int) -> dict[int, str]:
    rows = db.session.query(Category).filter(Category.user_id == uid).all()
    return {row.id: row.name for row in rows}


def _summarize_expenses(
    expenses: list[Expense], category_names: dict[int, str]
) -> dict:
    income = 0.0
    expenses_total = 0.0
    category_totals: dict[str, float] = {}
    daily_totals: dict[str, float] = {}

    for item in expenses:
        amount = _amount(item)
        day_key = item.spent_at.isoformat()
        if item.expense_type == "INCOME":
            income += amount
            continue
        expenses_total += amount
        daily_totals[day_key] = daily_totals.get(day_key, 0.0) + amount
        category = category_names.get(item.category_id or 0, "Uncategorized")
        category_totals[category] = category_totals.get(category, 0.0) + amount

    sorted_categories = sorted(
        category_totals.items(), key=lambda item: item[1], reverse=True
    )
    top_expenses = sorted(
        [item for item in expenses if item.expense_type != "INCOME"],
        key=lambda item: (_amount(item), item.spent_at),
        reverse=True,
    )[:5]

    return {
        "income": round(income, 2),
        "expenses": round(expenses_total, 2),
        "net_flow": round(income - expenses_total, 2),
        "transaction_count": len(expenses),
        "category_breakdown": [
            {"category": category, "amount": round(amount, 2)}
            for category, amount in sorted_categories
        ],
        "daily_breakdown": [
            {"date": day, "amount": round(amount, 2)}
            for day, amount in sorted(daily_totals.items())
        ],
        "top_expenses": [
            {
                "id": item.id,
                "date": item.spent_at.isoformat(),
                "description": item.notes,
                "amount": round(_amount(item), 2),
                "category": category_names.get(item.category_id or 0, "Uncategorized"),
            }
            for item in top_expenses
        ],
    }


def _upcoming_bills(
    uid: int, start: date, end: date, currency: str | None = None
) -> list[dict]:
    q = db.session.query(Bill).filter(
        Bill.user_id == uid,
        Bill.active.is_(True),
        Bill.next_due_date >= start,
        Bill.next_due_date <= end,
    )
    if currency:
        q = q.filter(Bill.currency == currency)
    bills = q.order_by(Bill.next_due_date.asc(), Bill.amount.desc()).all()
    return [
        {
            "id": bill.id,
            "name": bill.name,
            "amount": round(float(bill.amount or 0), 2),
            "currency": bill.currency,
            "due_date": bill.next_due_date.isoformat(),
            "autopay_enabled": bill.autopay_enabled,
        }
        for bill in bills
    ]


def _trend_label(current: float, previous: float) -> str:
    if previous == 0 and current == 0:
        return "flat"
    if previous == 0:
        return "new_activity"
    delta_pct = ((current - previous) / previous) * 100
    if delta_pct > 10:
        return "up"
    if delta_pct < -10:
        return "down"
    return "flat"


def _weekly_insights(
    current: dict, previous: dict, upcoming_bills: list[dict]
) -> tuple[list[str], list[str]]:
    insights: list[str] = []
    recommendations: list[str] = []

    trend = _trend_label(current["expenses"], previous["expenses"])
    if trend == "up":
        insights.append("Weekly expenses increased more than 10% versus last week.")
        recommendations.append(
            "Review the top expense and category drivers before the next spend cycle."
        )
    elif trend == "down":
        insights.append("Weekly expenses decreased more than 10% versus last week.")
        recommendations.append(
            "Preserve the lower-spend pattern by setting a weekly category cap."
        )
    elif current["expenses"] == 0:
        insights.append("No weekly expense activity was recorded.")
        recommendations.append(
            "Add transactions for this week to unlock a more useful digest."
        )
    else:
        insights.append("Weekly expenses are broadly stable versus last week.")
        recommendations.append("Keep monitoring category mix for one-off spikes.")

    if current["category_breakdown"]:
        top = current["category_breakdown"][0]
        insights.append(f"{top['category']} is the largest spend category this week.")
        recommendations.append(
            f"Set a specific weekly limit for {top['category']} if it is discretionary."
        )

    if upcoming_bills:
        due_total = round(sum(item["amount"] for item in upcoming_bills), 2)
        insights.append(
            f"{len(upcoming_bills)} bill(s) totaling {due_total} are due this week."
        )
        recommendations.append(
            "Keep bill cash reserved separately from discretionary spend."
        )

    return insights[:5], recommendations[:5]


def weekly_financial_digest(
    uid: int, week: str | None = None, currency: str | None = None
) -> dict:
    week_start = _normalize_week_start(week)
    week_end = week_start + timedelta(days=6)
    previous_start = week_start - timedelta(days=7)
    previous_end = week_start - timedelta(days=1)
    currency_filter = (currency or "").strip() or None
    category_names = _category_names(uid)

    current = _summarize_expenses(
        _expenses_for_range(uid, week_start, week_end, currency_filter),
        category_names,
    )
    previous = _summarize_expenses(
        _expenses_for_range(uid, previous_start, previous_end, currency_filter),
        category_names,
    )
    bills = _upcoming_bills(uid, week_start, week_end, currency_filter)
    insights, recommendations = _weekly_insights(current, previous, bills)

    previous_expenses = previous["expenses"]
    week_over_week_change_pct = (
        round(((current["expenses"] - previous_expenses) / previous_expenses) * 100, 2)
        if previous_expenses
        else 0.0
    )

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "currency": currency_filter,
        "summary": current,
        "previous_week": {
            "week_start": previous_start.isoformat(),
            "week_end": previous_end.isoformat(),
            "expenses": previous["expenses"],
            "income": previous["income"],
            "net_flow": previous["net_flow"],
        },
        "week_over_week_change_pct": week_over_week_change_pct,
        "upcoming_bills": bills,
        "insights": insights,
        "recommendations": recommendations,
        "method": "deterministic",
    }
