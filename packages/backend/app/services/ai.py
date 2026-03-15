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
# Weekly digest
# ---------------------------------------------------------------------------

def _week_range(week_start: str) -> tuple[date, date]:
    start = date.fromisoformat(week_start)
    start = start - timedelta(days=start.weekday())
    return start, start + timedelta(days=6)


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
    from ..models import Category

    rows = (
        db.session.query(
            func.coalesce(Category.name, "Uncategorized").label("cat_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
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
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    return {r.cat_name: float(r.total) for r in rows}


def _weekly_top_transactions(uid: int, start: date, end: date, limit: int = 5) -> list[dict]:
    rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "amount": float(e.amount),
            "notes": e.notes or "",
            "category_id": e.category_id,
            "date": e.spent_at.isoformat(),
        }
        for e in rows
    ]


def _heuristic_weekly_digest(uid: int, week_start: str, persona: str) -> dict:
    from ..models import Bill

    start, end = _week_range(week_start)
    prev_start = start - timedelta(days=7)
    prev_end = end - timedelta(days=7)

    income, expenses = _weekly_totals(uid, start, end)
    _, prev_expenses = _weekly_totals(uid, prev_start, prev_end)

    wow_change = 0.0
    if prev_expenses > 0:
        wow_change = round(((expenses - prev_expenses) / prev_expenses) * 100, 2)

    category_spend = _weekly_category_spend(uid, start, end)
    top_categories = sorted(category_spend.items(), key=lambda x: x[1], reverse=True)[:3]
    top_transactions = _weekly_top_transactions(uid, start, end)

    upcoming_bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= end,
            Bill.next_due_date <= end + timedelta(days=7),
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    upcoming = [
        {"name": b.name, "amount": float(b.amount), "due": b.next_due_date.isoformat()}
        for b in upcoming_bills
    ]

    if wow_change > 15:
        trend = f"Spending is up {wow_change:.1f}% vs last week — review discretionary items."
    elif wow_change < -15:
        trend = f"Great work! Spending is down {abs(wow_change):.1f}% vs last week."
    else:
        trend = f"Spending is relatively stable ({wow_change:+.1f}% vs last week)."

    insights = [trend]
    if income > 0:
        savings_rate = round(((income - expenses) / income) * 100, 1)
        if savings_rate >= 20:
            insights.append(f"Saved {savings_rate}% of income this week — excellent!")
        elif savings_rate > 0:
            insights.append(f"Saved {savings_rate}% of income this week. Target: 20%.")
        else:
            insights.append("Expenses exceeded income this week. Review spending.")

    if top_categories:
        top_name, top_amt = top_categories[0]
        insights.append(f"Top category: {top_name} at {top_amt:.2f}.")

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "summary": {
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net_flow": round(income - expenses, 2),
            "week_over_week_change_pct": wow_change,
        },
        "category_breakdown": [
            {"category": k, "amount": round(v, 2)} for k, v in category_spend.items()
        ],
        "top_categories": [
            {"category": k, "amount": round(v, 2)} for k, v in top_categories
        ],
        "top_transactions": top_transactions,
        "upcoming_bills": upcoming,
        "insights": insights,
        "persona": persona,
        "method": "heuristic",
    }


def _gemini_weekly_digest(
    uid: int, week_start: str, api_key: str, model: str, persona: str
) -> dict:
    base = _heuristic_weekly_digest(uid, week_start, persona)
    prompt = (
        f"{persona}\n"
        "Analyze this week's financial data and return strict JSON only with keys: "
        "insights (list of exactly 3 concise actionable strings), "
        "trend_headline (1 sentence summary).\n"
        f"week_start={base['week_start']}\n"
        f"summary={base['summary']}\n"
        f"top_categories={base['top_categories']}\n"
        f"upcoming_bills={base['upcoming_bills']}"
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
    base["insights"] = parsed.get("insights", base["insights"])
    base["trend_headline"] = parsed.get("trend_headline", "")
    base["method"] = "gemini"
    return base


def weekly_digest(
    uid: int,
    week_start: str,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
) -> dict:
    """Generate a smart weekly financial digest with trends and insights."""
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()

    if key:
        try:
            return _gemini_weekly_digest(uid, week_start, key, model, persona_text)
        except Exception:
            result = _heuristic_weekly_digest(uid, week_start, persona_text)
            result["warnings"] = ["gemini_unavailable"]
            return result
    return _heuristic_weekly_digest(uid, week_start, persona_text)
