import json
from datetime import date, timedelta
from urllib import request as urllib_request

from sqlalchemy import func

from ..config import Settings
from ..extensions import db
from ..models import Expense, Category

_settings = Settings()
DIGEST_PERSONA = (
    "You are FinMind's weekly digest narrator. Summarize the user's financial "
    "week in 2-3 sentences. Be concise, data-driven, and encouraging. "
    "Highlight the most important trend and one actionable suggestion."
)


def _week_totals(user_id: int, start: date, end: date) -> tuple[float, float]:
    """Return (total_expenses, total_income) for the date range."""
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    return float(expenses or 0), float(income or 0)


def _top_categories(user_id: int, start: date, end: date) -> list[dict]:
    """Return top spending categories for the date range."""
    rows = (
        db.session.query(
            Expense.category_id, func.coalesce(func.sum(Expense.amount), 0)
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .order_by(func.sum(Expense.amount).desc())
        .limit(5)
        .all()
    )
    result = []
    for cat_id, amount in rows:
        name = "Uncategorized"
        if cat_id:
            cat = db.session.get(Category, cat_id)
            if cat:
                name = cat.name
        result.append({"category_id": cat_id, "name": name, "amount": round(float(amount), 2)})
    return result


def _transaction_count(user_id: int, start: date, end: date) -> int:
    return (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    ) or 0


def _gemini_narrative(
    total_expenses: float,
    total_income: float,
    net: float,
    wow_change: float,
    top_categories: list[dict],
    api_key: str,
    model: str,
) -> str:
    prompt = (
        f"{DIGEST_PERSONA}\n"
        f"This week: spent={total_expenses:.2f}, earned={total_income:.2f}, "
        f"net={net:.2f}, week-over-week change={wow_change:.1f}%.\n"
        f"Top categories: {top_categories}\n"
        "Return a plain text narrative summary (2-3 sentences, no JSON)."
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4},
        }
    ).encode("utf-8")
    req = urllib_request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=10) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))
    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    return text.strip()


def _heuristic_narrative(
    total_expenses: float,
    total_income: float,
    net: float,
    wow_change: float,
    top_categories: list[dict],
) -> str:
    if not top_categories:
        return "No transactions recorded this week. Start tracking to get insights!"
    top_name = top_categories[0]["name"]
    top_amount = top_categories[0]["amount"]
    trend = "up" if wow_change > 0 else "down" if wow_change < 0 else "flat"
    if trend == "up":
        direction = f"Spending is up {abs(wow_change):.1f}% compared to last week."
    elif trend == "down":
        direction = f"Spending is down {abs(wow_change):.1f}% compared to last week."
    else:
        direction = "Spending is on par with last week."
    return (
        f"You spent a total of {total_expenses:.2f} this week, "
        f"with {top_name} being your top category at {top_amount:.2f}. "
        f"{direction}"
    )


def generate_weekly_digest(user_id: int) -> dict:
    """Generate a weekly financial digest for the given user."""
    today = date.today()
    week_end = today
    week_start = today - timedelta(days=6)
    prev_week_end = week_start - timedelta(days=1)
    prev_week_start = prev_week_end - timedelta(days=6)

    total_expenses, total_income = _week_totals(user_id, week_start, week_end)
    prev_expenses, _ = _week_totals(user_id, prev_week_start, prev_week_end)

    net = round(total_income - total_expenses, 2)
    daily_average = round(total_expenses / 7, 2)

    if prev_expenses > 0:
        wow_change = round(((total_expenses - prev_expenses) / prev_expenses) * 100, 2)
    else:
        wow_change = 0.0

    top_cats = _top_categories(user_id, week_start, week_end)
    tx_count = _transaction_count(user_id, week_start, week_end)

    # Generate narrative
    key = (_settings.gemini_api_key or "").strip()
    model = _settings.gemini_model
    method = "heuristic"
    narrative = ""

    if key:
        try:
            narrative = _gemini_narrative(
                total_expenses, total_income, net, wow_change, top_cats, key, model
            )
            method = "gemini"
        except Exception:
            narrative = _heuristic_narrative(
                total_expenses, total_income, net, wow_change, top_cats
            )
    else:
        narrative = _heuristic_narrative(
            total_expenses, total_income, net, wow_change, top_cats
        )

    return {
        "period": {
            "start": week_start.isoformat(),
            "end": week_end.isoformat(),
        },
        "total_expenses": round(total_expenses, 2),
        "total_income": round(total_income, 2),
        "net": net,
        "top_categories": top_cats,
        "daily_average": daily_average,
        "wow_change": wow_change,
        "narrative": narrative,
        "transactions_count": tx_count,
        "method": method,
    }
