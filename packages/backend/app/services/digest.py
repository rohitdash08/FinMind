"""Weekly financial digest generation service.

Aggregates expenses by category, compares with prior week, checks bill
payment status, and optionally enriches the summary with AI-powered
insights via the existing Gemini / heuristic pipeline.
"""

import json
import logging
from datetime import date, timedelta
from urllib import request as url_request

from sqlalchemy import func

from ..config import Settings
from ..extensions import db
from ..models import Bill, Category, Expense

logger = logging.getLogger("finmind.digest")
_settings = Settings()

# ---------------------------------------------------------------------------
# Data aggregation helpers
# ---------------------------------------------------------------------------


def _week_range(ref: date | None = None) -> tuple[date, date]:
    """Return (Monday, Sunday) of the week containing *ref* (default: last full week)."""
    today = ref or date.today()
    # Last full week: Monday–Sunday before today's week
    last_sunday = today - timedelta(days=today.isoweekday())
    last_monday = last_sunday - timedelta(days=6)
    return last_monday, last_sunday


def _expenses_by_category(
    uid: int, start: date, end: date
) -> list[dict]:
    """Return [{category_id, category_name, total}] for the date range."""
    rows = (
        db.session.query(
            Expense.category_id,
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
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    return [
        {
            "category_id": r.category_id,
            "category_name": r.cat_name,
            "total": float(r.total),
        }
        for r in rows
    ]


def _total_income(uid: int, start: date, end: date) -> float:
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
    return float(val or 0)


def _total_expenses(uid: int, start: date, end: date) -> float:
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
    return float(val or 0)


def _upcoming_bills(uid: int, start: date, end: date) -> list[dict]:
    """Bills with next_due_date in [start, end]."""
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
        }
        for b in bills
    ]


def _compute_trends(
    current_spend: float, prev_spend: float
) -> dict:
    if prev_spend > 0:
        change_pct = round(((current_spend - prev_spend) / prev_spend) * 100, 2)
    else:
        change_pct = 0.0
    direction = "up" if change_pct > 0 else ("down" if change_pct < 0 else "flat")
    return {
        "spending_change_pct": change_pct,
        "direction": direction,
        "current_week_total": round(current_spend, 2),
        "previous_week_total": round(prev_spend, 2),
    }


# ---------------------------------------------------------------------------
# AI-powered insights
# ---------------------------------------------------------------------------

_DIGEST_PERSONA = (
    "You are FinMind's weekly digest analyst. Summarize the user's financial "
    "week in 3-5 bullet points. Be concise, data-driven, actionable. "
    "Highlight wins, risks, and one concrete tip. Return strict JSON: "
    '{"highlights": ["..."], "tip": "..."}.'
)


def _ai_insights(summary: dict, api_key: str, model: str) -> dict | None:
    """Call Gemini for AI-powered digest insights. Returns None on failure."""
    prompt = (
        f"{_DIGEST_PERSONA}\n\n"
        f"Weekly data:\n{json.dumps(summary, default=str)}"
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
    ).encode()
    req = url_request.Request(
        url=url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with url_request.urlopen(req, timeout=15) as resp:  # nosec B310
            payload = json.loads(resp.read().decode())
        text = (
            payload.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        # Extract JSON
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
    except Exception:
        logger.warning("AI digest insights unavailable", exc_info=True)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_weekly_digest(
    uid: int,
    ref_date: date | None = None,
) -> dict:
    """Build the full weekly digest payload for a user.

    *ref_date* controls which week to summarize (defaults to last full week).
    """
    week_start, week_end = _week_range(ref_date)
    prev_start = week_start - timedelta(days=7)
    prev_end = week_end - timedelta(days=7)

    # Current week data
    category_breakdown = _expenses_by_category(uid, week_start, week_end)
    income = _total_income(uid, week_start, week_end)
    expenses = _total_expenses(uid, week_start, week_end)

    # Previous week for trends
    prev_expenses = _total_expenses(uid, prev_start, prev_end)

    # Bills due this coming week
    next_monday = week_end + timedelta(days=1)
    next_sunday = next_monday + timedelta(days=6)
    bills = _upcoming_bills(uid, next_monday, next_sunday)

    trends = _compute_trends(expenses, prev_expenses)

    digest = {
        "period": {
            "start": week_start.isoformat(),
            "end": week_end.isoformat(),
        },
        "summary": {
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net_flow": round(income - expenses, 2),
        },
        "category_breakdown": category_breakdown,
        "trends": trends,
        "upcoming_bills": bills,
        "upcoming_bills_total": round(sum(b["amount"] for b in bills), 2),
        "generated_at": date.today().isoformat(),
    }

    # AI insights (best-effort)
    api_key = (_settings.gemini_api_key or "").strip()
    if api_key:
        ai = _ai_insights(digest, api_key, _settings.gemini_model)
        if ai:
            digest["ai_insights"] = ai

    return digest


def format_digest_text(digest: dict) -> str:
    """Render digest as a plain-text message suitable for email/WhatsApp."""
    s = digest["summary"]
    t = digest["trends"]
    lines = [
        f"📊 FinMind Weekly Digest ({digest['period']['start']} – {digest['period']['end']})",
        "",
        f"💰 Income: {s['total_income']:.2f}",
        f"💸 Expenses: {s['total_expenses']:.2f}",
        f"📈 Net flow: {s['net_flow']:.2f}",
        "",
        f"📉 Spending vs last week: {t['direction']} ({t['spending_change_pct']:+.1f}%)",
        "",
    ]

    if digest.get("category_breakdown"):
        lines.append("Top categories:")
        for c in digest["category_breakdown"][:5]:
            lines.append(f"  • {c['category_name']}: {c['total']:.2f}")
        lines.append("")

    if digest.get("upcoming_bills"):
        lines.append("Upcoming bills:")
        for b in digest["upcoming_bills"]:
            lines.append(f"  • {b['name']}: {b['amount']:.2f} (due {b['next_due_date']})")
        lines.append("")

    ai = digest.get("ai_insights")
    if ai:
        lines.append("🤖 AI Insights:")
        for h in ai.get("highlights", []):
            lines.append(f"  • {h}")
        if ai.get("tip"):
            lines.append(f"  💡 Tip: {ai['tip']}")

    return "\n".join(lines)
