import json
from datetime import date, timedelta
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


def _range_totals(uid: int, start_date: date, end_date: date) -> tuple[float, float]:
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


def _range_category_spend(uid: int, start_date: date, end_date: date) -> list[dict]:
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(func.sum(Expense.amount), 0),
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
    return sorted(
        [
            {
                "category_id": str(category_id or "uncat"),
                "amount": round(float(amount), 2),
            }
            for category_id, amount in rows
        ],
        key=lambda item: item["amount"],
        reverse=True,
    )


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return round(((current - previous) / previous) * 100, 2)


def _daily_net(uid: int, start_date: date, end_date: date) -> list[dict]:
    daily = []
    cursor = start_date
    while cursor <= end_date:
        income, expenses = _range_totals(uid, cursor, cursor)
        net = round(income - expenses, 2)
        daily.append(
            {
                "date": cursor.isoformat(),
                "income": round(income, 2),
                "expenses": round(expenses, 2),
                "net_flow": net,
            }
        )
        cursor += timedelta(days=1)
    return daily


def _build_weekly_insights(
    current_income: float,
    current_expenses: float,
    previous_expenses: float,
    top_categories: list[dict],
) -> list[str]:
    insights = []
    if current_expenses > previous_expenses:
        insights.append(
            "Spending increased week over week — review variable categories."
        )
    elif current_expenses < previous_expenses:
        insights.append(
            "Great progress — spending dropped compared with last week."
        )
    else:
        insights.append(
            "Spending is flat versus last week; keep monitoring consistency."
        )

    if current_income > 0:
        savings_rate = max(
            0.0,
            ((current_income - current_expenses) / current_income) * 100,
        )
        insights.append(f"Estimated savings rate this week is {savings_rate:.1f}%.")
    else:
        insights.append(
            "No income recorded this week; focus on reducing discretionary spend."
        )

    if top_categories:
        top = top_categories[0]
        top_category_note = (
            f"Top spending category this week: "
            f"{top['category_id']} ({top['amount']:.2f})."
        )
        insights.append(top_category_note)
    return insights[:3]


def weekly_financial_summary(uid: int, end_date: date | None = None) -> dict:
    week_end = end_date or date.today()
    week_start = week_end - timedelta(days=6)
    previous_end = week_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)

    current_income, current_expenses = _range_totals(uid, week_start, week_end)
    previous_income, previous_expenses = _range_totals(
        uid,
        previous_start,
        previous_end,
    )
    current_net = round(current_income - current_expenses, 2)
    previous_net = round(previous_income - previous_expenses, 2)

    top_categories = _range_category_spend(uid, week_start, week_end)[:3]
    expense_share_denominator = current_expenses if current_expenses > 0 else 1.0
    for item in top_categories:
        item["share_pct"] = round((item["amount"] / expense_share_denominator) * 100, 2)

    savings_rate = round(
        (
            ((current_income - current_expenses) / current_income) * 100
            if current_income > 0
            else 0.0
        ),
        2,
    )

    return {
        "period": {
            "start_date": week_start.isoformat(),
            "end_date": week_end.isoformat(),
            "days": 7,
        },
        "totals": {
            "income": round(current_income, 2),
            "expenses": round(current_expenses, 2),
            "net_flow": current_net,
            "savings_rate_pct": savings_rate,
        },
        "trends": {
            "income_change_pct": _pct_change(current_income, previous_income),
            "expenses_change_pct": _pct_change(current_expenses, previous_expenses),
            "net_flow_change_pct": _pct_change(current_net, previous_net),
        },
        "top_categories": top_categories,
        "daily": _daily_net(uid, week_start, week_end),
        "insights": _build_weekly_insights(
            current_income=current_income,
            current_expenses=current_expenses,
            previous_expenses=previous_expenses,
            top_categories=top_categories,
        ),
        "method": "heuristic",
    }


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
