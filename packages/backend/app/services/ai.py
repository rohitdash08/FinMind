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


def _round_money(value: float) -> float:
    return round(float(value or 0), 2)


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return round(((current - previous) / previous) * 100, 2)


def _parse_week_start(week_start: str | None) -> date:
    if not week_start:
        today = date.today()
        return today - timedelta(days=today.weekday())
    return date.fromisoformat(week_start)


def _weekly_rows(uid: int, start: date, end: date) -> list[Expense]:
    return (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .order_by(Expense.spent_at.asc(), Expense.id.asc())
        .all()
    )


def _category_names(uid: int) -> dict[int, str]:
    rows = db.session.query(Category.id, Category.name).filter_by(user_id=uid).all()
    return {int(category_id): name for category_id, name in rows}


def _sum_rows(rows: list[Expense]) -> tuple[float, float]:
    income = 0.0
    expenses = 0.0
    for row in rows:
        amount = float(row.amount or 0)
        if row.expense_type == "INCOME":
            income += amount
        else:
            expenses += amount
    return income, expenses


def _daily_breakdown(rows: list[Expense], start: date) -> list[dict]:
    daily = {
        start
        + timedelta(days=offset): {
            "date": (start + timedelta(days=offset)).isoformat(),
            "income": 0.0,
            "expenses": 0.0,
            "net_flow": 0.0,
            "transaction_count": 0,
        }
        for offset in range(7)
    }
    for row in rows:
        day = daily[row.spent_at]
        amount = float(row.amount or 0)
        if row.expense_type == "INCOME":
            day["income"] += amount
        else:
            day["expenses"] += amount
        day["transaction_count"] += 1
        day["net_flow"] = day["income"] - day["expenses"]

    return [
        {
            **values,
            "income": _round_money(values["income"]),
            "expenses": _round_money(values["expenses"]),
            "net_flow": _round_money(values["net_flow"]),
        }
        for values in daily.values()
    ]


def _category_breakdown(
    rows: list[Expense], category_names: dict[int, str], total_expenses: float
) -> list[dict]:
    totals: dict[str, dict] = {}
    for row in rows:
        if row.expense_type == "INCOME":
            continue
        key = str(row.category_id or "uncategorized")
        label = category_names.get(row.category_id, "Uncategorized")
        item = totals.setdefault(
            key,
            {
                "category_id": row.category_id,
                "category_name": label,
                "amount": 0.0,
                "transaction_count": 0,
                "share_pct": 0.0,
            },
        )
        item["amount"] += float(row.amount or 0)
        item["transaction_count"] += 1

    breakdown = []
    for item in totals.values():
        amount = _round_money(item["amount"])
        item["amount"] = amount
        item["share_pct"] = (
            round((amount / total_expenses) * 100, 2) if total_expenses > 0 else 0.0
        )
        breakdown.append(item)
    return sorted(breakdown, key=lambda item: item["amount"], reverse=True)


def _largest_expenses(
    rows: list[Expense], category_names: dict[int, str], limit: int = 5
) -> list[dict]:
    expense_rows = [row for row in rows if row.expense_type != "INCOME"]
    top_rows = sorted(
        expense_rows, key=lambda row: float(row.amount or 0), reverse=True
    )
    return [
        {
            "id": row.id,
            "description": row.notes or "Transaction",
            "amount": _round_money(float(row.amount or 0)),
            "currency": row.currency,
            "date": row.spent_at.isoformat(),
            "category_id": row.category_id,
            "category_name": category_names.get(row.category_id, "Uncategorized"),
        }
        for row in top_rows[:limit]
    ]


def _build_weekly_narrative(
    current_income: float,
    current_expenses: float,
    previous_expenses: float,
    category_breakdown: list[dict],
    daily_breakdown: list[dict],
    transaction_count: int,
) -> tuple[list[str], list[dict], list[str]]:
    net_flow = current_income - current_expenses
    highlights: list[str] = []
    insights: list[dict] = []
    recommendations: list[str] = []

    if transaction_count == 0:
        highlights.append("No transactions were recorded for this week.")
        insights.append(
            {
                "type": "activity",
                "severity": "info",
                "title": "No weekly activity",
                "detail": "Add income and expense transactions to generate trends.",
            }
        )
        recommendations.append("Log this week's transactions to unlock the digest.")
        return highlights, insights, recommendations

    highlights.append(
        "Weekly net flow was "
        f"{_round_money(net_flow)} from {_round_money(current_income)} income and "
        f"{_round_money(current_expenses)} expenses."
    )

    expense_change = _pct_change(current_expenses, previous_expenses)
    if previous_expenses > 0:
        direction = "higher" if expense_change >= 0 else "lower"
        highlights.append(
            f"Expenses were {abs(expense_change):.2f}% {direction} than last week."
        )

    if net_flow < 0:
        insights.append(
            {
                "type": "cash_flow",
                "severity": "warning",
                "title": "Negative weekly cash flow",
                "detail": (
                    "Expenses exceeded income by "
                    f"{_round_money(abs(net_flow))} this week."
                ),
            }
        )
        recommendations.append("Review discretionary purchases before next week.")
    else:
        insights.append(
            {
                "type": "cash_flow",
                "severity": "positive",
                "title": "Positive weekly cash flow",
                "detail": f"Income exceeded expenses by {_round_money(net_flow)}.",
            }
        )
        recommendations.append("Move part of the weekly surplus to savings.")

    if category_breakdown:
        top_category = category_breakdown[0]
        insights.append(
            {
                "type": "category",
                "severity": "info",
                "title": f"{top_category['category_name']} led spending",
                "detail": (
                    f"{top_category['category_name']} represented "
                    f"{top_category['share_pct']:.2f}% of weekly expenses."
                ),
            }
        )
        if top_category["share_pct"] >= 40:
            recommendations.append(
                f"Set a cap for {top_category['category_name']} next week."
            )

    expense_days = [day for day in daily_breakdown if day["expenses"] > 0]
    if expense_days:
        busiest_day = max(expense_days, key=lambda day: day["expenses"])
        share = (
            round((busiest_day["expenses"] / current_expenses) * 100, 2)
            if current_expenses > 0
            else 0.0
        )
        insights.append(
            {
                "type": "daily_trend",
                "severity": "info",
                "title": "Highest spend day",
                "detail": (
                    f"{busiest_day['date']} accounted for {share:.2f}% "
                    "of weekly expenses."
                ),
            }
        )

    if current_income == 0 and current_expenses > 0:
        recommendations.append("Record income deposits to track true cash flow.")

    return highlights, insights, recommendations


def weekly_financial_summary(uid: int, week_start: str | None = None) -> dict:
    start = _parse_week_start(week_start)
    end = start + timedelta(days=6)
    previous_start = start - timedelta(days=7)
    previous_end = start - timedelta(days=1)

    rows = _weekly_rows(uid, start, end)
    previous_rows = _weekly_rows(uid, previous_start, previous_end)
    category_names = _category_names(uid)

    current_income, current_expenses = _sum_rows(rows)
    previous_income, previous_expenses = _sum_rows(previous_rows)
    net_flow = current_income - current_expenses
    previous_net_flow = previous_income - previous_expenses

    daily = _daily_breakdown(rows, start)
    categories = _category_breakdown(rows, category_names, current_expenses)
    highlights, insights, recommendations = _build_weekly_narrative(
        current_income,
        current_expenses,
        previous_expenses,
        categories,
        daily,
        len(rows),
    )

    income_count = len([row for row in rows if row.expense_type == "INCOME"])
    expense_count = len(rows) - income_count
    savings_rate = (
        round((net_flow / current_income) * 100, 2) if current_income > 0 else 0.0
    )

    return {
        "period": {
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "previous_week_start": previous_start.isoformat(),
            "previous_week_end": previous_end.isoformat(),
        },
        "summary": {
            "income": _round_money(current_income),
            "expenses": _round_money(current_expenses),
            "net_flow": _round_money(net_flow),
            "transaction_count": len(rows),
            "income_transaction_count": income_count,
            "expense_transaction_count": expense_count,
            "savings_rate_pct": savings_rate,
        },
        "comparison": {
            "previous_income": _round_money(previous_income),
            "previous_expenses": _round_money(previous_expenses),
            "previous_net_flow": _round_money(previous_net_flow),
            "income_change_pct": _pct_change(current_income, previous_income),
            "expense_change_pct": _pct_change(current_expenses, previous_expenses),
            "net_flow_change": _round_money(net_flow - previous_net_flow),
        },
        "category_breakdown": categories,
        "daily_breakdown": daily,
        "largest_expenses": _largest_expenses(rows, category_names),
        "highlights": highlights,
        "insights": insights,
        "recommendations": recommendations,
        "method": "heuristic",
    }


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
