"""Weekly financial digest service.

Generates a smart weekly summary with spending trends, category
breakdowns, week-over-week comparisons, and AI-powered narrative
insights (Gemini or heuristic fallback).
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any
from urllib import request as urllib_request

from sqlalchemy import func

from ..config import Settings
from ..extensions import db, redis_client
from ..models import Category, Expense

logger = logging.getLogger("finmind.weekly_digest")
_settings = Settings()

DIGEST_CACHE_TTL = 600  # 10 minutes

DEFAULT_PERSONA = (
    "You are FinMind's weekly financial analyst. Be concise, data-driven, "
    "and encouraging. Highlight actionable insights the user can apply next week."
)


# ---------------------------------------------------------------------------
# Data aggregation helpers
# ---------------------------------------------------------------------------

def _week_bounds(week_start: date | None = None) -> tuple[date, date]:
    """Return (Monday, Sunday) of the requested week.

    If *week_start* is ``None`` the most-recently completed week is used.
    """
    if week_start is None:
        today = date.today()
        # Last Monday
        monday = today - timedelta(days=today.weekday() + 7)
    else:
        monday = week_start - timedelta(days=week_start.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _total_spending(uid: int, start: date, end: date) -> float:
    val = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    )
    return float(val or 0)


def _total_income(uid: int, start: date, end: date) -> float:
    val = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    )
    return float(val or 0)


def _category_breakdown(
    uid: int, start: date, end: date
) -> list[dict[str, Any]]:
    """Per-category spending with names resolved."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(func.sum(Expense.amount), 0),
            func.count(Expense.id),
        )
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .group_by(Expense.category_id)
        .all()
    )
    # Resolve names
    cat_ids = [r[0] for r in rows if r[0] is not None]
    name_map: dict[int | None, str] = {None: "Uncategorized"}
    if cat_ids:
        cats = (
            db.session.query(Category.id, Category.name)
            .filter(Category.id.in_(cat_ids))
            .all()
        )
        name_map.update({c.id: c.name for c in cats})

    total = sum(float(r[1]) for r in rows) or 1.0
    result = []
    for cat_id, amount, txn_count in rows:
        amt = float(amount)
        result.append(
            {
                "category_id": cat_id,
                "category_name": name_map.get(cat_id, f"cat-{cat_id}"),
                "amount": round(amt, 2),
                "transaction_count": int(txn_count),
                "percentage": round((amt / total) * 100, 1),
            }
        )
    result.sort(key=lambda x: x["amount"], reverse=True)
    return result


def _daily_breakdown(
    uid: int, start: date, end: date
) -> list[dict[str, Any]]:
    """Spending per day within the range."""
    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0),
            func.count(Expense.id),
        )
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at)
        .all()
    )
    return [
        {
            "date": str(d),
            "amount": round(float(a), 2),
            "transaction_count": int(c),
        }
        for d, a, c in rows
    ]


def _transaction_count(uid: int, start: date, end: date) -> int:
    return (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    ) or 0


# ---------------------------------------------------------------------------
# Heuristic insights (no AI required)
# ---------------------------------------------------------------------------

def _heuristic_insights(
    spending: float,
    prev_spending: float,
    categories: list[dict],
    wow_pct: float,
) -> list[str]:
    """Generate rule-based insights when Gemini is unavailable."""
    tips: list[str] = []

    if wow_pct > 20:
        tips.append(
            f"Your spending rose {wow_pct:.1f}% week-over-week. "
            "Review discretionary purchases to stay on track."
        )
    elif wow_pct < -10:
        tips.append(
            f"Great job! You cut spending by {abs(wow_pct):.1f}% compared to last week."
        )
    else:
        tips.append("Your spending is relatively stable week-over-week.")

    if categories:
        top = categories[0]
        tips.append(
            f"Top category: {top['category_name']} "
            f"({top['percentage']:.0f}% of total, "
            f"${top['amount']:.2f})."
        )

    if len(categories) >= 3:
        bottom = categories[-1]
        tips.append(
            f"Lowest spend: {bottom['category_name']} (${bottom['amount']:.2f})."
        )

    if spending == 0:
        tips.append("No expenses recorded this week. Keep logging to get better insights!")

    return tips


# ---------------------------------------------------------------------------
# Gemini-powered narrative
# ---------------------------------------------------------------------------

def _gemini_narrative(
    uid: int,
    week_label: str,
    spending: float,
    income: float,
    wow_pct: float,
    categories: list[dict],
    api_key: str,
    model: str,
    persona: str,
) -> str:
    """Call Gemini to produce a short narrative summary."""
    cat_summary = ", ".join(
        f"{c['category_name']}: ${c['amount']:.2f} ({c['percentage']:.0f}%)"
        for c in categories[:5]
    )
    prompt = (
        f"{persona}\n\n"
        f"Week: {week_label}\n"
        f"Total spending: ${spending:.2f}\n"
        f"Total income: ${income:.2f}\n"
        f"Week-over-week change: {wow_pct:+.1f}%\n"
        f"Category breakdown: {cat_summary}\n\n"
        "Write a 3-4 sentence weekly financial digest for the user. "
        "Mention the most important trend and one actionable tip."
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 256},
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_weekly_digest(
    uid: int,
    week_start: date | None = None,
    *,
    currency: str | None = None,
    gemini_api_key: str | None = None,
    persona: str | None = None,
) -> dict[str, Any]:
    """Build a full weekly financial digest for *uid*.

    Parameters
    ----------
    uid : int
        Authenticated user id.
    week_start : date | None
        Any date in the desired week (snapped to Monday).
        ``None`` means most-recently completed week.
    currency : str | None
        Optional currency filter header (informational; all amounts are in
        the user's stored currency).
    gemini_api_key : str | None
        Per-request Gemini key override.
    persona : str | None
        AI persona override.

    Returns
    -------
    dict
        Complete digest payload ready for JSON serialisation.
    """
    monday, sunday = _week_bounds(week_start)
    prev_monday = monday - timedelta(days=7)
    prev_sunday = sunday - timedelta(days=7)

    week_label = f"{monday.isoformat()} to {sunday.isoformat()}"

    # Try cache
    cache_key = f"digest:{uid}:{monday.isoformat()}"
    if currency:
        cache_key += f":{currency}"
    try:
        cached = redis_client.get(cache_key)
        if cached:
            logger.info("Digest cache hit user=%s week=%s", uid, monday)
            return json.loads(cached)
    except Exception:
        pass  # Redis unavailable is non-fatal

    # Core metrics
    spending = _total_spending(uid, monday, sunday)
    income = _total_income(uid, monday, sunday)
    prev_spending = _total_spending(uid, prev_monday, prev_sunday)
    txn_count = _transaction_count(uid, monday, sunday)

    if prev_spending > 0:
        wow_pct = round(((spending - prev_spending) / prev_spending) * 100, 2)
    else:
        wow_pct = 0.0

    categories = _category_breakdown(uid, monday, sunday)
    daily = _daily_breakdown(uid, monday, sunday)

    # AI narrative or heuristic fallback
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()
    narrative = None
    method = "heuristic"
    warnings: list[str] = []

    if key:
        try:
            narrative = _gemini_narrative(
                uid, week_label, spending, income, wow_pct,
                categories, key, model, persona_text,
            )
            method = "gemini"
        except Exception as exc:
            logger.warning("Gemini digest failed, using heuristic: %s", exc)
            warnings.append("gemini_unavailable")

    insights = _heuristic_insights(spending, prev_spending, categories, wow_pct)

    digest: dict[str, Any] = {
        "week": week_label,
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "total_spending": round(spending, 2),
        "total_income": round(income, 2),
        "net_flow": round(income - spending, 2),
        "transaction_count": txn_count,
        "week_over_week_change_pct": wow_pct,
        "previous_week_spending": round(prev_spending, 2),
        "category_breakdown": categories,
        "daily_breakdown": daily,
        "insights": insights,
        "method": method,
    }
    if narrative:
        digest["narrative"] = narrative
    if currency:
        digest["currency"] = currency
    if warnings:
        digest["warnings"] = warnings

    # Cache result
    try:
        redis_client.setex(cache_key, DIGEST_CACHE_TTL, json.dumps(digest))
    except Exception:
        pass

    logger.info(
        "Weekly digest generated user=%s week=%s method=%s",
        uid, monday, method,
    )
    return digest
