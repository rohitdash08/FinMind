"""Weekly financial digest generation service."""

import json
import logging
from datetime import date, timedelta
from urllib import request as url_request

from sqlalchemy import func

from ..config import Settings
from ..extensions import db
from ..models import Expense, Category, User, WeeklyDigest

logger = logging.getLogger("finmind.digest")
_settings = Settings()

DEFAULT_PERSONA = (
    "You are FinMind's weekly financial digest writer. Be concise, insightful, "
    "and action-oriented. Highlight trends, flag concerns, celebrate wins."
)


def _week_boundaries(reference_date=None):
    """Return (start, end) of the previous completed week (Mon-Sun)."""
    today = reference_date or date.today()
    end = today - timedelta(days=today.weekday() + 1)  # last Sunday
    start = end - timedelta(days=6)  # Monday before
    return start, end


def _weekly_expenses(user_id, start, end):
    """Fetch expenses grouped by category for a given week."""
    rows = (
        db.session.query(
            Category.name,
            func.coalesce(func.sum(Expense.amount), 0),
            func.count(Expense.id),
        )
        .select_from(Expense)
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Category.name)
        .all()
    )
    return [
        {
            "category": name or "Uncategorized",
            "total": float(total),
            "count": int(count),
        }
        for name, total, count in rows
    ]


def _weekly_income(user_id, start, end):
    """Fetch total income for a given week."""
    result = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    return float(result or 0)


def _previous_week_total(user_id, start):
    """Get total expenses from the week before."""
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)
    result = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= prev_start,
            Expense.spent_at <= prev_end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(result or 0)


def _build_digest_data(user_id, start, end):
    """Compile raw data for digest generation."""
    by_category = _weekly_expenses(user_id, start, end)
    total_spent = sum(c["total"] for c in by_category)
    total_income = _weekly_income(user_id, start, end)
    prev_total = _previous_week_total(user_id, start)

    wow_change = 0.0
    if prev_total > 0:
        wow_change = round(((total_spent - prev_total) / prev_total) * 100, 2)

    top_categories = sorted(by_category, key=lambda x: x["total"], reverse=True)[:5]

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "total_spent": round(total_spent, 2),
        "total_income": round(total_income, 2),
        "net_flow": round(total_income - total_spent, 2),
        "week_over_week_change_pct": wow_change,
        "previous_week_spent": round(prev_total, 2),
        "top_categories": top_categories,
        "transaction_count": sum(c["count"] for c in by_category),
    }


def _heuristic_summary(data):
    """Generate a plain summary without AI."""
    lines = [f"Week of {data['week_start']} to {data['week_end']}:"]
    lines.append(f"Total spent: {data['total_spent']:.2f}")
    lines.append(f"Total income: {data['total_income']:.2f}")
    lines.append(f"Net flow: {data['net_flow']:.2f}")

    if data["week_over_week_change_pct"] > 0:
        lines.append(
            f"Spending increased {data['week_over_week_change_pct']}% vs last week."
        )
    elif data["week_over_week_change_pct"] < 0:
        lines.append(
            f"Spending decreased {abs(data['week_over_week_change_pct'])}% vs last week."
        )

    if data["top_categories"]:
        lines.append("Top categories:")
        for cat in data["top_categories"][:3]:
            lines.append(
                f"  - {cat['category']}: {cat['total']:.2f} ({cat['count']} txns)"
            )

    tips = []
    if data["net_flow"] < 0:
        tips.append(
            "Your expenses exceeded income this week. Review discretionary spending."
        )
    if data["week_over_week_change_pct"] > 20:
        tips.append(
            "Spending jumped significantly. Check if any large one-time purchases drove this."
        )
    if not tips:
        tips.append("Good week! Keep maintaining your spending habits.")

    return {"summary": "\n".join(lines), "tips": tips, "method": "heuristic"}


def _ai_summary(data, api_key, model):
    """Generate an AI-powered summary using Gemini."""
    prompt = (
        f"{DEFAULT_PERSONA}\n\n"
        "Generate a brief weekly financial digest from this data. "
        "Return JSON with keys: summary (string, 3-5 sentences), "
        "tips (list of 2-3 actionable tips), highlights (list of 1-2 positive notes).\n\n"
        f"Data: {json.dumps(data)}"
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

    req = url_request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with url_request.urlopen(req, timeout=15) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))

    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )

    # Try to parse JSON from response
    try:
        from .ai import _extract_json_object

        parsed = _extract_json_object(text)
        parsed["method"] = "gemini"
        return parsed
    except (ValueError, json.JSONDecodeError):
        return {"summary": text.strip(), "tips": [], "method": "gemini_raw"}


def generate_digest(user_id, reference_date=None):
    """Generate a weekly digest for a user and store it."""
    start, end = _week_boundaries(reference_date)

    # Check if digest already exists for this week
    existing = WeeklyDigest.query.filter_by(user_id=user_id, week_start=start).first()
    if existing:
        return existing

    data = _build_digest_data(user_id, start, end)

    # Skip if no transactions
    if data["transaction_count"] == 0:
        return None

    # Try AI, fall back to heuristic
    api_key = (_settings.gemini_api_key or "").strip()
    model = _settings.gemini_model
    if api_key:
        try:
            result = _ai_summary(data, api_key, model)
        except Exception:
            logger.warning(
                "Gemini digest failed, falling back to heuristic", exc_info=True
            )
            result = _heuristic_summary(data)
    else:
        result = _heuristic_summary(data)

    digest = WeeklyDigest(
        user_id=user_id,
        week_start=start,
        week_end=end,
        summary=result.get("summary", ""),
        tips=json.dumps(result.get("tips", [])),
        highlights=json.dumps(result.get("highlights", [])),
        raw_data=json.dumps(data),
        method=result.get("method", "unknown"),
    )
    db.session.add(digest)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        # Race condition: another request created it first, return that one
        return WeeklyDigest.query.filter_by(user_id=user_id, week_start=start).first()

    return digest


def generate_all_digests(reference_date=None):
    """Generate digests for all active users. Called by scheduler."""
    users = User.query.all()
    generated = 0
    for user in users:
        try:
            result = generate_digest(user.id, reference_date)
            if result:
                generated += 1
        except Exception:
            logger.exception("Failed to generate digest for user %s", user.id)
    logger.info("Generated %d digests for %d users", generated, len(users))
    return generated
