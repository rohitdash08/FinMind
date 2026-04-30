import json
import logging
from datetime import date, timedelta

from sqlalchemy import func

from ..config import Settings
from ..extensions import db
from ..models import Category, Expense, WeeklyDigest
from .cache import cache_get, cache_set

logger = logging.getLogger("finmind.digest")
_settings = Settings()


def _week_bounds(ref: date | None = None) -> tuple[date, date]:
    """Return (Monday, Sunday) of the ISO week containing *ref*."""
    d = ref or date.today()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _weekly_digest_key(user_id: int, week_start: date) -> str:
    return f"user:{user_id}:weekly_digest:{week_start.isoformat()}"


def _aggregate_week(uid: int, start: date, end: date) -> dict:
    """Compute income, expenses, and category breakdown for a date range."""
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

    category_rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
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
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    total_exp = float(expenses or 0)
    top_categories = [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": round(float(r.total or 0), 2),
            "share_pct": (
                round((float(r.total or 0) / total_exp) * 100, 2)
                if total_exp > 0
                else 0.0
            ),
        }
        for r in category_rows[:5]
    ]

    return {
        "total_income": round(float(income or 0), 2),
        "total_expenses": round(total_exp, 2),
        "top_categories": top_categories,
    }


def _compute_trends(current: dict, previous: dict) -> dict:
    """Compare current vs previous week and produce trend data."""
    curr_exp = current["total_expenses"]
    prev_exp = previous["total_expenses"]
    curr_inc = current["total_income"]
    prev_inc = previous["total_income"]

    if prev_exp > 0:
        expense_change_pct = round(((curr_exp - prev_exp) / prev_exp) * 100, 2)
    else:
        expense_change_pct = 0.0 if curr_exp == 0 else 100.0

    if prev_inc > 0:
        income_change_pct = round(((curr_inc - prev_inc) / prev_inc) * 100, 2)
    else:
        income_change_pct = 0.0 if curr_inc == 0 else 100.0

    return {
        "expense_change_pct": expense_change_pct,
        "income_change_pct": income_change_pct,
        "previous_week_expenses": prev_exp,
        "previous_week_income": prev_inc,
        "expense_trend": "up" if curr_exp > prev_exp else ("down" if curr_exp < prev_exp else "flat"),
        "income_trend": "up" if curr_inc > prev_inc else ("down" if curr_inc < prev_inc else "flat"),
    }


def _generate_ai_insights(uid: int, current: dict, trends: dict) -> str:
    """Generate AI-powered insights using Gemini (or heuristic fallback)."""
    from urllib import request as url_request

    api_key = (_settings.gemini_api_key or "").strip()
    if not api_key:
        return _heuristic_insights(current, trends)

    prompt = (
        "You are FinMind's financial coach. Analyze this weekly spending data and "
        "provide 3-4 concise, actionable insights. Be specific with numbers. "
        "Return plain text, not JSON.\n\n"
        f"Weekly Income: {current['total_income']}\n"
        f"Weekly Expenses: {current['total_expenses']}\n"
        f"Net Flow: {round(current['total_income'] - current['total_expenses'], 2)}\n"
        f"Top Categories: {json.dumps(current['top_categories'])}\n"
        f"Expense Change vs Last Week: {trends['expense_change_pct']}%\n"
        f"Income Change vs Last Week: {trends['income_change_pct']}%\n"
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{_settings.gemini_model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3},
        }
    ).encode("utf-8")
    req = url_request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with url_request.urlopen(req, timeout=10) as resp:  # nosec B310
            payload = json.loads(resp.read().decode("utf-8"))
        text = (
            payload.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        return text.strip() if text.strip() else _heuristic_insights(current, trends)
    except Exception:
        logger.warning("Gemini unavailable for digest insights, using heuristic")
        return _heuristic_insights(current, trends)


def _heuristic_insights(current: dict, trends: dict) -> str:
    """Generate simple heuristic insights when Gemini is unavailable."""
    lines = []
    net = round(current["total_income"] - current["total_expenses"], 2)

    if net >= 0:
        lines.append(
            f"Positive cash flow this week: you saved {net:.2f}. Keep it up!"
        )
    else:
        lines.append(
            f"Spending exceeded income by {abs(net):.2f} this week. "
            "Review discretionary expenses."
        )

    change = trends["expense_change_pct"]
    if change > 10:
        lines.append(
            f"Expenses increased {change:.1f}% compared to last week. "
            "Check your top spending categories."
        )
    elif change < -10:
        lines.append(
            f"Great job! Expenses decreased {abs(change):.1f}% compared to last week."
        )

    cats = current.get("top_categories", [])
    if cats:
        top = cats[0]
        lines.append(
            f"Biggest spending category: {top['category_name']} "
            f"at {top['amount']:.2f} ({top['share_pct']:.0f}% of total)."
        )

    if not lines:
        lines.append("Not enough data to generate insights this week.")

    return " ".join(lines)


def generate_weekly_digest(
    user_id: int, week_start: date | None = None, force: bool = False
) -> dict:
    """Generate (or retrieve cached) weekly digest for a user.

    Args:
        user_id: The user's id.
        week_start: Monday of the target week. Defaults to current week.
        force: When True, regenerate even if a digest already exists.

    Returns:
        Serialised digest dict.
    """
    start, end = _week_bounds(week_start)

    # Check cache first (unless forcing regeneration)
    cache_key = _weekly_digest_key(user_id, start)
    if not force:
        cached = cache_get(cache_key)
        if cached:
            return cached

    # Check DB for existing digest
    if not force:
        existing = (
            db.session.query(WeeklyDigest)
            .filter(WeeklyDigest.user_id == user_id, WeeklyDigest.week_start == start)
            .first()
        )
        if existing:
            result = _digest_to_dict(existing)
            cache_set(cache_key, result, ttl_seconds=600)
            return result

    # Aggregate current and previous week
    current = _aggregate_week(user_id, start, end)

    prev_start = start - timedelta(days=7)
    prev_end = end - timedelta(days=7)
    previous = _aggregate_week(user_id, prev_start, prev_end)

    trends = _compute_trends(current, previous)
    ai_insights = _generate_ai_insights(user_id, current, trends)
    net_flow = round(current["total_income"] - current["total_expenses"], 2)

    # Upsert digest record
    digest = (
        db.session.query(WeeklyDigest)
        .filter(WeeklyDigest.user_id == user_id, WeeklyDigest.week_start == start)
        .first()
    )
    if digest:
        digest.total_income = current["total_income"]
        digest.total_expenses = current["total_expenses"]
        digest.net_flow = net_flow
        digest.top_categories = json.dumps(current["top_categories"])
        digest.trends = json.dumps(trends)
        digest.ai_insights = ai_insights
    else:
        digest = WeeklyDigest(
            user_id=user_id,
            week_start=start,
            week_end=end,
            total_income=current["total_income"],
            total_expenses=current["total_expenses"],
            net_flow=net_flow,
            top_categories=json.dumps(current["top_categories"]),
            trends=json.dumps(trends),
            ai_insights=ai_insights,
        )
        db.session.add(digest)

    db.session.commit()
    result = _digest_to_dict(digest)
    cache_set(cache_key, result, ttl_seconds=600)
    logger.info(
        "Weekly digest generated user=%s week=%s", user_id, start.isoformat()
    )
    return result


def get_digest_history(user_id: int, limit: int = 10) -> list[dict]:
    """Return past weekly digests for a user, most recent first."""
    rows = (
        db.session.query(WeeklyDigest)
        .filter(WeeklyDigest.user_id == user_id)
        .order_by(WeeklyDigest.week_start.desc())
        .limit(limit)
        .all()
    )
    return [_digest_to_dict(r) for r in rows]


def _digest_to_dict(digest: WeeklyDigest) -> dict:
    """Serialise a WeeklyDigest model instance to a plain dict."""
    top_categories = []
    if digest.top_categories:
        try:
            top_categories = json.loads(digest.top_categories)
        except (json.JSONDecodeError, TypeError):
            top_categories = []

    trends = {}
    if digest.trends:
        try:
            trends = json.loads(digest.trends)
        except (json.JSONDecodeError, TypeError):
            trends = {}

    return {
        "id": digest.id,
        "user_id": digest.user_id,
        "week_start": digest.week_start.isoformat(),
        "week_end": digest.week_end.isoformat(),
        "total_income": float(digest.total_income),
        "total_expenses": float(digest.total_expenses),
        "net_flow": float(digest.net_flow),
        "top_categories": top_categories,
        "trends": trends,
        "ai_insights": digest.ai_insights or "",
        "created_at": digest.created_at.isoformat() if digest.created_at else None,
    }
