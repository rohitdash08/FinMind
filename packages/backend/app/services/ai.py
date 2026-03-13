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
# Weekly Digest
# ---------------------------------------------------------------------------


def _parse_iso_week(week_str: str) -> tuple[date, date]:
    """Parse 'YYYY-WNN' into (monday, sunday) date pair."""
    parts = week_str.split("-W")
    if len(parts) != 2:
        raise ValueError(f"Invalid week format '{week_str}'. Expected YYYY-WNN.")
    year, week_num = int(parts[0]), int(parts[1])
    if not (1 <= week_num <= 53):
        raise ValueError(f"Week number {week_num} out of range.")
    # ISO week: Monday = day 1
    monday = date.fromisocalendar(year, week_num, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _current_iso_week() -> str:
    """Return current week as 'YYYY-WNN'."""
    today = date.today()
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _week_totals(uid: int, start: date, end: date) -> tuple[float, float]:
    """Return (income, expenses) for the given date range."""
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


def _week_category_breakdown(
    uid: int, start: date, end: date
) -> list[dict]:
    """Return per-category spend for a date range, including category names."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
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

    # Build category name lookup
    cat_ids = [r.category_id for r in rows if r.category_id is not None]
    cat_map: dict[int, str] = {}
    if cat_ids:
        cats = (
            db.session.query(Category.id, Category.name)
            .filter(Category.id.in_(cat_ids))
            .all()
        )
        cat_map = {c.id: c.name for c in cats}

    return [
        {
            "category_id": r.category_id,
            "category_name": cat_map.get(r.category_id, "Uncategorized"),
            "amount": round(float(r.total), 2),
        }
        for r in sorted(rows, key=lambda x: float(x.total), reverse=True)
    ]


def _week_daily_breakdown(uid: int, start: date, end: date) -> list[dict]:
    """Return daily expense totals for each day in the week."""
    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .all()
    )
    day_map = {r.spent_at: round(float(r.total), 2) for r in rows}
    result = []
    current = start
    while current <= end:
        result.append(
            {"date": current.isoformat(), "amount": day_map.get(current, 0.0)}
        )
        current += timedelta(days=1)
    return result


def _week_top_expenses(uid: int, start: date, end: date, limit: int = 5) -> list[dict]:
    """Return the top individual expenses by amount."""
    rows = (
        db.session.query(
            Expense.id,
            Expense.amount,
            Expense.notes,
            Expense.spent_at,
            Expense.category_id,
        )
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
            "id": r.id,
            "amount": round(float(r.amount), 2),
            "notes": r.notes or "",
            "date": r.spent_at.isoformat(),
            "category_id": r.category_id,
        }
        for r in rows
    ]


def _generate_weekly_insights(
    total_spent: float,
    total_income: float,
    net_flow: float,
    category_breakdown: list[dict],
    wow_change_pct: float,
    daily_breakdown: list[dict],
) -> list[str]:
    """Generate heuristic plain-English insights from weekly data."""
    insights: list[str] = []

    # Spending trend
    if wow_change_pct > 20:
        insights.append(
            f"Your spending increased by {wow_change_pct:.1f}% compared to last week. "
            "Consider reviewing discretionary expenses."
        )
    elif wow_change_pct < -20:
        insights.append(
            f"Great job! Your spending decreased by {abs(wow_change_pct):.1f}% vs last week."
        )
    elif wow_change_pct == 0.0 and total_spent == 0:
        insights.append("No expenses recorded this week yet.")
    else:
        insights.append(
            f"Spending this week changed by {wow_change_pct:+.1f}% from the previous week."
        )

    # Top category
    if category_breakdown:
        top_cat = category_breakdown[0]
        pct_of_total = (
            round(top_cat["amount"] / total_spent * 100, 1) if total_spent > 0 else 0
        )
        insights.append(
            f"Your highest spend category is '{top_cat['category_name']}' "
            f"({pct_of_total}% of total weekly spend)."
        )

    # Net flow
    if total_income > 0:
        if net_flow >= 0:
            insights.append(
                f"Positive week: you saved {net_flow:.2f} "
                f"({round(net_flow / total_income * 100, 1)}% of income)."
            )
        else:
            insights.append(
                f"You spent {abs(net_flow):.2f} more than you earned this week."
            )

    # Biggest single-day spend
    if daily_breakdown:
        max_day = max(daily_breakdown, key=lambda d: d["amount"])
        if max_day["amount"] > 0:
            insights.append(
                f"Highest spending day: {max_day['date']} ({max_day['amount']:.2f})."
            )

    return insights


def weekly_digest(uid: int, week_str: str | None = None) -> dict:
    """
    Generate a weekly financial summary digest for a user.

    Parameters
    ----------
    uid : int
        User ID.
    week_str : str, optional
        ISO week string in ``YYYY-WNN`` format (e.g. ``2026-W11``).
        Defaults to the current calendar week.

    Returns
    -------
    dict
        Digest payload including totals, category breakdown, daily spend,
        week-over-week comparison, top expenses, and plain-English insights.
    """
    week_str = (week_str or _current_iso_week()).strip()
    monday, sunday = _parse_iso_week(week_str)

    # Previous week window
    prev_monday = monday - timedelta(days=7)
    prev_sunday = sunday - timedelta(days=7)

    total_income, total_spent = _week_totals(uid, monday, sunday)
    _, prev_spent = _week_totals(uid, prev_monday, prev_sunday)

    if prev_spent > 0:
        wow_pct = round(((total_spent - prev_spent) / prev_spent) * 100, 2)
    else:
        wow_pct = 0.0

    net_flow = round(total_income - total_spent, 2)
    category_breakdown = _week_category_breakdown(uid, monday, sunday)
    prev_category_breakdown = _week_category_breakdown(uid, prev_monday, prev_sunday)

    # Annotate category breakdown with week-over-week delta
    prev_cat_map = {c["category_name"]: c["amount"] for c in prev_category_breakdown}
    for cat in category_breakdown:
        prev_amt = prev_cat_map.get(cat["category_name"], 0.0)
        if prev_amt > 0:
            cat["wow_change_pct"] = round(
                ((cat["amount"] - prev_amt) / prev_amt) * 100, 2
            )
        else:
            cat["wow_change_pct"] = None  # new category this week

    daily_breakdown = _week_daily_breakdown(uid, monday, sunday)
    top_expenses = _week_top_expenses(uid, monday, sunday)

    insights = _generate_weekly_insights(
        total_spent=total_spent,
        total_income=total_income,
        net_flow=net_flow,
        category_breakdown=category_breakdown,
        wow_change_pct=wow_pct,
        daily_breakdown=daily_breakdown,
    )

    return {
        "week": week_str,
        "period": {
            "start": monday.isoformat(),
            "end": sunday.isoformat(),
        },
        "total_spent": round(total_spent, 2),
        "total_income": round(total_income, 2),
        "net_flow": net_flow,
        "week_over_week_change_pct": wow_pct,
        "previous_week_spent": round(prev_spent, 2),
        "category_breakdown": category_breakdown,
        "daily_breakdown": daily_breakdown,
        "top_expenses": top_expenses,
        "insights": insights,
        "transaction_count": sum(1 for d in daily_breakdown if d["amount"] > 0),
    }
