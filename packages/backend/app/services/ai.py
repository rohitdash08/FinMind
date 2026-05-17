import json
from urllib import request

from datetime import date, timedelta
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


def _week_start(value: date | None = None) -> date:
    anchor = value or date.today()
    return anchor - timedelta(days=anchor.weekday())


def _weekly_rows(uid: int, start: date, end: date):
    return (
        db.session.query(
            Expense.expense_type,
            Expense.category_id,
            Category.name,
            func.coalesce(func.sum(Expense.amount), 0),
            func.count(Expense.id),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .group_by(Expense.expense_type, Expense.category_id, Category.name)
        .all()
    )


def _weekly_totals(uid: int, start: date, end: date) -> dict:
    income = 0.0
    spending = 0.0
    transaction_count = 0
    categories: dict[str, dict] = {}

    for expense_type, category_id, category_name, amount, count in _weekly_rows(
        uid, start, end
    ):
        value = float(amount or 0)
        transaction_count += int(count or 0)
        if expense_type == "INCOME":
            income += value
            continue
        spending += value
        key = str(category_id or "uncategorized")
        categories[key] = {
            "category_id": category_id,
            "category": category_name or "Uncategorized",
            "amount": round(value, 2),
            "transaction_count": int(count or 0),
        }

    top_categories = sorted(
        categories.values(), key=lambda item: item["amount"], reverse=True
    )[:5]
    return {
        "income": round(income, 2),
        "spending": round(spending, 2),
        "net_flow": round(income - spending, 2),
        "transaction_count": transaction_count,
        "top_categories": top_categories,
    }


def weekly_financial_digest(uid: int, week_start: date | None = None) -> dict:
    """Build a deterministic weekly financial summary with trend insights."""
    start = _week_start(week_start)
    end = start + timedelta(days=6)
    previous_start = start - timedelta(days=7)
    previous_end = start - timedelta(days=1)

    current = _weekly_totals(uid, start, end)
    previous = _weekly_totals(uid, previous_start, previous_end)

    previous_spending = previous["spending"]
    if previous_spending:
        spending_change_pct = round(
            ((current["spending"] - previous_spending) / previous_spending) * 100, 2
        )
    else:
        spending_change_pct = 0.0

    insights: list[str] = []
    if current["spending"] == 0 and current["income"] == 0:
        insights.append("No transactions were recorded for this week yet.")
    elif spending_change_pct > 0:
        insights.append(f"Spending increased {spending_change_pct}% vs last week.")
    elif spending_change_pct < 0:
        insights.append(f"Spending decreased {abs(spending_change_pct)}% vs last week.")
    else:
        insights.append("Spending was unchanged compared with last week.")

    if current["top_categories"]:
        top = current["top_categories"][0]
        share = (
            round((top["amount"] / current["spending"]) * 100, 2)
            if current["spending"]
            else 0.0
        )
        insights.append(
            f"{top['category']} was the largest category at {share}% of weekly spend."
        )

    if current["net_flow"] < 0:
        insights.append("Net flow was negative; review discretionary spend first.")
    elif current["net_flow"] > 0:
        insights.append(
            "Net flow was positive; consider moving part of the surplus to savings."
        )

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "summary": current,
        "comparison": {
            "previous_week_start": previous_start.isoformat(),
            "previous_week_end": previous_end.isoformat(),
            "previous_spending": previous["spending"],
            "spending_change_pct": spending_change_pct,
        },
        "insights": insights,
    }
