"""Weekly financial digest service.

Generates comprehensive weekly spending summaries with trend analysis,
category breakdowns, bill reminders, and AI-powered narrative insights.
"""

import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from urllib import request as urllib_request

from sqlalchemy import extract, func

from ..config import Settings
from ..extensions import db
from ..models import Bill, Category, Expense

logger = logging.getLogger("finmind.digest")

_settings = Settings()

DIGEST_PERSONA = (
    "You are FinMind's weekly financial analyst. Summarize spending data in 3-5 concise, "
    "actionable sentences. Highlight notable trends, potential savings, and congratulate "
    "improvements. Be specific about numbers. Never invent data not in the input."
)


def _week_bounds(week_offset: int = 0) -> tuple[date, date]:
    """Return (monday, sunday) for the week offset from the current week.

    week_offset=0 is the current week, -1 is last week, etc.
    """
    today = date.today()
    # ISO weekday: Monday=1 .. Sunday=7
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _to_float(val: Any) -> float:
    """Safely cast Decimal / None to float."""
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


def _category_spending_for_range(
    uid: int, start: date, end: date
) -> list[dict[str, Any]]:
    """Get spending grouped by category for a date range."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
            func.count(Expense.id).label("tx_count"),
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

    total_spending = sum(_to_float(r.total) for r in rows)

    return [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": round(_to_float(r.total), 2),
            "transaction_count": r.tx_count,
            "share_pct": (
                round((_to_float(r.total) / total_spending) * 100, 1)
                if total_spending > 0
                else 0.0
            ),
        }
        for r in rows
    ]


def _total_spending_for_range(uid: int, start: date, end: date) -> float:
    """Total non-income spending in a date range."""
    val = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return round(_to_float(val), 2)


def _total_income_for_range(uid: int, start: date, end: date) -> float:
    """Total income in a date range."""
    val = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    return round(_to_float(val), 2)


def _transaction_count_for_range(uid: int, start: date, end: date) -> int:
    """Count of non-income transactions in a date range."""
    val = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return int(val or 0)


def _daily_spending(uid: int, start: date, end: date) -> list[dict[str, Any]]:
    """Daily spending totals for a date range."""
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
        .order_by(Expense.spent_at.asc())
        .all()
    )
    return [
        {"date": r.spent_at.isoformat(), "amount": round(_to_float(r.total), 2)}
        for r in rows
    ]


def _upcoming_bills(uid: int, within_days: int = 14) -> list[dict[str, Any]]:
    """Bills due within the next N days."""
    today = date.today()
    cutoff = today + timedelta(days=within_days)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= today,
            Bill.next_due_date <= cutoff,
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": round(_to_float(b.amount), 2),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
            "autopay_enabled": b.autopay_enabled,
            "days_until_due": (b.next_due_date - today).days,
        }
        for b in bills
    ]


def _overdue_bills(uid: int) -> list[dict[str, Any]]:
    """Bills that are past their due date and still active."""
    today = date.today()
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date < today,
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": round(_to_float(b.amount), 2),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
            "days_overdue": (today - b.next_due_date).days,
        }
        for b in bills
    ]


def _detect_spikes(
    current_categories: list[dict], prev_categories: list[dict], threshold: float = 1.5
) -> list[dict[str, Any]]:
    """Detect spending spikes: categories where spending is ≥ threshold × previous week."""
    prev_map = {c["category_name"]: c["amount"] for c in prev_categories}
    spikes = []
    for cat in current_categories:
        prev_amount = prev_map.get(cat["category_name"], 0.0)
        if prev_amount > 0 and cat["amount"] >= prev_amount * threshold:
            spikes.append(
                {
                    "category_name": cat["category_name"],
                    "current_amount": cat["amount"],
                    "previous_amount": round(prev_amount, 2),
                    "increase_pct": round(
                        ((cat["amount"] - prev_amount) / prev_amount) * 100, 1
                    ),
                }
            )
        elif prev_amount == 0 and cat["amount"] > 0:
            spikes.append(
                {
                    "category_name": cat["category_name"],
                    "current_amount": cat["amount"],
                    "previous_amount": 0.0,
                    "increase_pct": None,  # new category this week
                }
            )
    return spikes


def _savings_opportunities(
    current_categories: list[dict], prev_categories: list[dict]
) -> list[str]:
    """Generate savings tips based on spending patterns."""
    tips = []
    prev_map = {c["category_name"]: c["amount"] for c in prev_categories}

    # Sort by amount descending
    sorted_cats = sorted(current_categories, key=lambda c: c["amount"], reverse=True)

    if sorted_cats:
        top = sorted_cats[0]
        tips.append(
            f"Your top spending category is {top['category_name']} "
            f"at {top['share_pct']}% of total. Consider setting a weekly budget for it."
        )

    for cat in sorted_cats[:3]:
        prev_amount = prev_map.get(cat["category_name"], 0.0)
        if prev_amount > 0 and cat["amount"] > prev_amount * 1.2:
            increase = round(
                ((cat["amount"] - prev_amount) / prev_amount) * 100, 1
            )
            tips.append(
                f"{cat['category_name']} spending increased {increase}% vs last week. "
                f"Review recent transactions for potential cutbacks."
            )

    if not tips:
        tips.append(
            "Your spending looks consistent. Keep tracking to identify "
            "long-term savings opportunities."
        )

    return tips[:5]


def _generate_ai_narrative(
    digest_data: dict[str, Any],
    gemini_api_key: str | None = None,
) -> str | None:
    """Use Gemini to generate a natural language summary. Returns None on failure."""
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    if not key:
        return None

    model = _settings.gemini_model
    prompt = (
        f"{DIGEST_PERSONA}\n\n"
        f"Week: {digest_data['period']['start']} to {digest_data['period']['end']}\n"
        f"Total spent: {digest_data['summary']['total_spent']}\n"
        f"vs last week: {digest_data['summary']['wow_change_pct']}%\n"
        f"Top categories: {json.dumps(digest_data['categories'][:5])}\n"
        f"Spikes: {json.dumps(digest_data.get('spikes', []))}\n"
        f"Upcoming bills: {len(digest_data.get('bills', {}).get('upcoming', []))}\n"
        f"Overdue bills: {len(digest_data.get('bills', {}).get('overdue', []))}\n\n"
        "Write a concise weekly financial summary in 3-5 sentences. "
        "Return plain text only, no markdown or JSON."
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 300},
        }
    ).encode("utf-8")
    req = urllib_request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=15) as resp:  # nosec B310
            payload = json.loads(resp.read().decode("utf-8"))
        text = (
            payload.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        return text.strip() if text.strip() else None
    except Exception as exc:
        logger.warning("AI narrative generation failed: %s", exc)
        return None


def _heuristic_narrative(digest_data: dict[str, Any]) -> str:
    """Generate a plain-text summary without AI, based on the data alone."""
    summary = digest_data["summary"]
    period = digest_data["period"]
    categories = digest_data.get("categories", [])

    parts = []
    parts.append(
        f"Week of {period['start']} to {period['end']}: "
        f"You spent {summary['total_spent']:.2f} across "
        f"{summary['transaction_count']} transactions."
    )

    if summary["wow_change_pct"] is not None:
        if summary["wow_change_pct"] > 5:
            parts.append(
                f"Spending increased {summary['wow_change_pct']:.1f}% compared to last week."
            )
        elif summary["wow_change_pct"] < -5:
            parts.append(
                f"Great job! Spending decreased {abs(summary['wow_change_pct']):.1f}% "
                f"compared to last week."
            )
        else:
            parts.append("Spending was roughly on par with last week.")

    if categories:
        top = categories[0]
        parts.append(
            f"Top category: {top['category_name']} "
            f"({top['share_pct']}% of total spending)."
        )

    bills = digest_data.get("bills", {})
    overdue = bills.get("overdue", [])
    upcoming = bills.get("upcoming", [])
    if overdue:
        parts.append(
            f"⚠️ You have {len(overdue)} overdue bill(s) requiring attention."
        )
    if upcoming:
        parts.append(
            f"{len(upcoming)} bill(s) due in the next 2 weeks."
        )

    return " ".join(parts)


def generate_weekly_digest(
    uid: int,
    week_offset: int = 0,
    gemini_api_key: str | None = None,
) -> dict[str, Any]:
    """Generate a comprehensive weekly financial digest.

    Args:
        uid: The user's ID.
        week_offset: 0 for current week, -1 for last week, etc.
        gemini_api_key: Optional user-supplied Gemini API key.

    Returns:
        A dictionary with the complete weekly digest.
    """
    current_start, current_end = _week_bounds(week_offset)
    prev_start, prev_end = _week_bounds(week_offset - 1)

    # Core metrics
    total_spent = _total_spending_for_range(uid, current_start, current_end)
    prev_total_spent = _total_spending_for_range(uid, prev_start, prev_end)
    total_income = _total_income_for_range(uid, current_start, current_end)
    tx_count = _transaction_count_for_range(uid, current_start, current_end)

    # Week-over-week change
    if prev_total_spent > 0:
        wow_change = round(
            ((total_spent - prev_total_spent) / prev_total_spent) * 100, 1
        )
    elif total_spent > 0:
        wow_change = 100.0
    else:
        wow_change = None  # No data either week

    # Category breakdown
    categories = _category_spending_for_range(uid, current_start, current_end)
    prev_categories = _category_spending_for_range(uid, prev_start, prev_end)

    # Spikes & savings
    spikes = _detect_spikes(categories, prev_categories)
    savings = _savings_opportunities(categories, prev_categories)

    # Daily breakdown
    daily = _daily_spending(uid, current_start, current_end)

    # Bills
    upcoming = _upcoming_bills(uid)
    overdue = _overdue_bills(uid)

    # Build the digest payload
    digest: dict[str, Any] = {
        "period": {
            "start": current_start.isoformat(),
            "end": current_end.isoformat(),
            "week_offset": week_offset,
        },
        "summary": {
            "total_spent": total_spent,
            "previous_week_spent": prev_total_spent,
            "wow_change_pct": wow_change,
            "total_income": total_income,
            "net_flow": round(total_income - total_spent, 2),
            "transaction_count": tx_count,
            "daily_average": (
                round(total_spent / 7, 2) if total_spent > 0 else 0.0
            ),
        },
        "categories": categories,
        "previous_categories": prev_categories,
        "daily_spending": daily,
        "spikes": spikes,
        "savings_opportunities": savings,
        "bills": {
            "upcoming": upcoming,
            "overdue": overdue,
            "upcoming_total": round(sum(b["amount"] for b in upcoming), 2),
            "overdue_total": round(sum(b["amount"] for b in overdue), 2),
        },
    }

    # AI narrative (with heuristic fallback)
    ai_narrative = _generate_ai_narrative(digest, gemini_api_key=gemini_api_key)
    if ai_narrative:
        digest["narrative"] = ai_narrative
        digest["narrative_method"] = "ai"
    else:
        digest["narrative"] = _heuristic_narrative(digest)
        digest["narrative_method"] = "heuristic"

    return digest


def generate_trends(
    uid: int,
    weeks: int = 8,
) -> dict[str, Any]:
    """Generate spending trend data over multiple weeks for charts.

    Args:
        uid: The user's ID.
        weeks: Number of weeks to include (default 8).

    Returns:
        Dictionary with weekly totals and per-category trends.
    """
    weeks = min(max(weeks, 4), 12)  # Clamp to 4-12

    weekly_totals = []
    category_map: dict[str, list[dict[str, Any]]] = {}

    for offset in range(0, -weeks, -1):
        start, end = _week_bounds(offset)
        total = _total_spending_for_range(uid, start, end)
        income = _total_income_for_range(uid, start, end)
        weekly_totals.append(
            {
                "week_start": start.isoformat(),
                "week_end": end.isoformat(),
                "total_spent": total,
                "total_income": income,
                "net_flow": round(income - total, 2),
            }
        )

        cats = _category_spending_for_range(uid, start, end)
        for cat in cats:
            name = cat["category_name"]
            if name not in category_map:
                category_map[name] = []
            category_map[name].append(
                {
                    "week_start": start.isoformat(),
                    "amount": cat["amount"],
                }
            )

    # Reverse so oldest is first (chronological order)
    weekly_totals.reverse()

    # Compute trend direction per category
    category_trends = []
    for name, data_points in category_map.items():
        data_points.sort(key=lambda d: d["week_start"])
        amounts = [d["amount"] for d in data_points]
        trend = _trend_direction(amounts)
        category_trends.append(
            {
                "category_name": name,
                "trend": trend,
                "data": data_points,
                "total": round(sum(amounts), 2),
                "average": round(sum(amounts) / len(amounts), 2) if amounts else 0.0,
            }
        )

    category_trends.sort(key=lambda c: c["total"], reverse=True)

    return {
        "weeks_included": weeks,
        "weekly_totals": weekly_totals,
        "category_trends": category_trends,
    }


def _trend_direction(values: list[float]) -> str:
    """Determine if a series is increasing, decreasing, or stable.

    Uses simple linear comparison of first vs second half averages.
    """
    if len(values) < 2:
        return "stable"

    mid = len(values) // 2
    first_half = values[:mid] or [0]
    second_half = values[mid:] or [0]

    avg_first = sum(first_half) / len(first_half)
    avg_second = sum(second_half) / len(second_half)

    if avg_first == 0 and avg_second == 0:
        return "stable"
    if avg_first == 0:
        return "increasing"

    change = ((avg_second - avg_first) / avg_first) * 100
    if change > 10:
        return "increasing"
    elif change < -10:
        return "decreasing"
    return "stable"
