"""Weekly smart digest service for FinMind.

Generates weekly financial summaries with trend analysis,
spending insights, and actionable recommendations.
"""

import json
import logging
from datetime import date, timedelta
from urllib import request as urllib_request

from sqlalchemy import extract, func

from ..config import Settings
from ..extensions import db
from ..models import Bill, Category, Expense

logger = logging.getLogger("finmind.digest")
_settings = Settings()

DIGEST_PERSONA = (
    "You are FinMind's financial analyst. Generate a concise weekly digest "
    "with spending trends, category highlights, and 3 actionable tips. "
    "Return strict JSON only."
)


def _week_range(reference_date: date | None = None) -> tuple[date, date]:
    """Return (Monday, Sunday) for the week containing reference_date."""
    ref = reference_date or date.today()
    monday = ref - timedelta(days=ref.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _weekly_spending(uid: int, start: date, end: date) -> dict:
    """Aggregate spending for the given date range."""
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
    return {
        "income": round(float(income or 0), 2),
        "expenses": round(float(expenses or 0), 2),
        "net_flow": round(float(income or 0) - float(expenses or 0), 2),
    }


def _previous_week_range(start: date) -> tuple[date, date]:
    """Get the previous week range given current week start."""
    prev_monday = start - timedelta(days=7)
    prev_sunday = prev_monday + timedelta(days=6)
    return prev_monday, prev_sunday


def _category_breakdown(uid: int, start: date, end: date) -> list[dict]:
    """Get spending breakdown by category for date range."""
    rows = (
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
    total = sum(float(r.total or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": round(float(r.total or 0), 2),
            "share_pct": round((float(r.total or 0) / total) * 100, 2) if total > 0 else 0,
        }
        for r in rows
    ]


def _daily_spending(uid: int, start: date, end: date) -> list[dict]:
    """Get daily spending totals for chart data."""
    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0).label("daily_total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at)
        .all()
    )
    spending_map = {r.spent_at: float(r.daily_total or 0) for r in rows}
    result = []
    current = start
    while current <= end:
        result.append({
            "date": current.isoformat(),
            "amount": round(spending_map.get(current, 0), 2),
        })
        current += timedelta(days=1)
    return result


def _upcoming_bills(uid: int, days_ahead: int = 14) -> list[dict]:
    """Get upcoming bills for the next N days."""
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= today,
            Bill.next_due_date <= cutoff,
        )
        .order_by(Bill.next_due_date)
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "due_date": b.next_due_date.isoformat(),
            "days_until_due": (b.next_due_date - today).days,
        }
        for b in bills
    ]


def _top_transactions(uid: int, start: date, end: date, limit: int = 5) -> list[dict]:
    """Get the largest transactions in the period."""
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
            "description": e.notes or "Transaction",
            "amount": float(e.amount),
            "date": e.spent_at.isoformat(),
            "category_id": e.category_id,
        }
        for e in rows
    ]


def _detect_trends(
    current: dict, previous: dict, categories: list[dict]
) -> dict:
    """Analyze spending trends between current and previous week."""
    curr_exp = current.get("expenses", 0)
    prev_exp = previous.get("expenses", 0)
    if prev_exp > 0:
        change_pct = round(((curr_exp - prev_exp) / prev_exp) * 100, 2)
    else:
        change_pct = 0.0

    # Find biggest category increase
    top_cat = categories[0] if categories else None

    alerts = []
    if change_pct > 20:
        alerts.append(f"Spending increased {change_pct}% compared to last week")
    if top_cat and top_cat.get("share_pct", 0) > 50:
        alerts.append(
            f"{top_cat['category_name']} dominates at {top_cat['share_pct']}% of spending"
        )

    return {
        "week_over_week_change_pct": change_pct,
        "spending_direction": "up" if change_pct > 5 else "down" if change_pct < -5 else "stable",
        "top_category": top_cat,
        "alerts": alerts,
    }


def _gemini_digest(
    uid: int,
    week_start: date,
    week_end: date,
    analytics: dict,
    api_key: str,
    model: str,
) -> dict:
    """Generate AI-powered digest using Gemini."""
    prompt = (
        f"{DIGEST_PERSONA}\n"
        "Return JSON with keys: summary(str<=200), highlights(list<=3 str), "
        "tips(list<=3 str), mood(one of: great/good/okay/needs_attention).\n"
        f"Week: {week_start.isoformat()} to {week_end.isoformat()}\n"
        f"Analytics: {json.dumps(analytics)}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3},
    }).encode("utf-8")
    req = urllib_request.Request(
        url=url, data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib_request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON in Gemini response")
    return json.loads(text[start : end + 1])


def generate_weekly_digest(
    uid: int,
    reference_date: date | None = None,
    gemini_api_key: str | None = None,
) -> dict:
    """Generate a comprehensive weekly financial digest.

    Returns a dict with financial summary, trends, category breakdown,
    daily spending chart data, upcoming bills, and AI insights.
    """
    week_start, week_end = _week_range(reference_date)
    prev_start, prev_end = _previous_week_range(week_start)

    # Core metrics
    current_week = _weekly_spending(uid, week_start, week_end)
    previous_week = _weekly_spending(uid, prev_start, prev_end)
    categories = _category_breakdown(uid, week_start, week_end)
    daily = _daily_spending(uid, week_start, week_end)
    bills = _upcoming_bills(uid)
    top_txns = _top_transactions(uid, week_start, week_end)
    trends = _detect_trends(current_week, previous_week, categories)

    digest = {
        "period": {
            "start": week_start.isoformat(),
            "end": week_end.isoformat(),
            "label": f"Week of {week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}",
        },
        "summary": current_week,
        "comparison": {
            "previous_week": previous_week,
            "trends": trends,
        },
        "categories": categories,
        "daily_spending": daily,
        "upcoming_bills": bills,
        "top_transactions": top_txns,
        "ai_insights": None,
        "method": "heuristic",
    }

    # Try AI enhancement
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    if key:
        try:
            ai_result = _gemini_digest(
                uid, week_start, week_end, digest, key,
                _settings.gemini_model,
            )
            digest["ai_insights"] = ai_result
            digest["method"] = "gemini"
        except Exception as exc:
            logger.warning("Gemini digest failed for user=%s: %s", uid, exc)
            digest["ai_insights"] = {
                "summary": "AI insights unavailable this week.",
                "highlights": [],
                "tips": [
                    "Review your top spending categories.",
                    "Set aside savings before discretionary spending.",
                    "Track subscriptions for unused services.",
                ],
                "mood": "okay",
            }
    else:
        digest["ai_insights"] = {
            "summary": (
                f"You spent {current_week['expenses']} this week, "
                f"{'up' if trends['spending_direction'] == 'up' else 'down'} "
                f"from {previous_week['expenses']} last week."
            ),
            "highlights": [c["category_name"] for c in categories[:3]],
            "tips": [
                "Review your top spending categories weekly.",
                "Set up automatic savings transfers.",
                "Cancel unused subscriptions.",
            ],
            "mood": "great" if trends["spending_direction"] == "down" else "needs_attention",
        }

    logger.info(
        "Weekly digest generated user=%s week=%s method=%s",
        uid, week_start.isoformat(), digest["method"],
    )
    return digest
