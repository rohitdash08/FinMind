"""Weekly financial digest generator.

Produces a structured summary of a user's financial activity for any
given week, highlighting spending trends, category breakdowns, anomalies,
and actionable insights.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from urllib import request as urllib_request

from sqlalchemy import and_, func

from ..config import Settings
from ..extensions import db
from ..models import Bill, Category, Expense, User

logger = logging.getLogger("finmind.digest")
_settings = Settings()

DEFAULT_PERSONA = (
    "You are FinMind's weekly financial digest writer. Be concise, "
    "encouraging, data-driven. Highlight wins and flag concerns."
)


# ---------------------------------------------------------------------------
# Data collection helpers
# ---------------------------------------------------------------------------

def _week_bounds(ref_date: date | None = None) -> tuple[date, date]:
    """Return (monday, sunday) of the week containing *ref_date*.

    If *ref_date* is None, returns the previous complete week.
    """
    today = ref_date or date.today()
    if ref_date is None:
        # Previous complete week
        today = today - timedelta(days=7)
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _weekly_expenses(uid: int, start: date, end: date) -> list[dict]:
    """All non-income expenses in the date range."""
    rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .order_by(Expense.spent_at)
        .all()
    )
    return [
        {
            "id": e.id,
            "amount": float(e.amount),
            "currency": e.currency,
            "category_id": e.category_id,
            "notes": e.notes,
            "spent_at": e.spent_at.isoformat(),
        }
        for e in rows
    ]


def _weekly_income(uid: int, start: date, end: date) -> float:
    """Total income in the date range."""
    total = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "INCOME",
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    )
    return float(total or 0)


def _category_map(uid: int) -> dict[int, str]:
    """Map category ID → name for a user."""
    rows = db.session.query(Category).filter_by(user_id=uid).all()
    return {c.id: c.name for c in rows}


def _previous_week_total(uid: int, start: date) -> float:
    """Total expenses for the week before *start*."""
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)
    total = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            Expense.spent_at >= prev_start,
            Expense.spent_at <= prev_end,
        )
        .scalar()
    )
    return float(total or 0)


def _upcoming_bills(uid: int, start: date, end: date) -> list[dict]:
    """Bills due in the date range."""
    rows = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
        )
        .order_by(Bill.next_due_date)
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "due_date": b.next_due_date.isoformat(),
            "autopay": b.autopay_enabled,
        }
        for b in rows
    ]


# ---------------------------------------------------------------------------
# Digest computation
# ---------------------------------------------------------------------------

def _compute_category_breakdown(
    expenses: list[dict], cat_map: dict[int, str]
) -> list[dict]:
    """Group expenses by category, sorted by total descending."""
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for e in expenses:
        name = cat_map.get(e["category_id"], "Uncategorized")
        totals[name] = totals.get(name, 0) + e["amount"]
        counts[name] = counts.get(name, 0) + 1
    breakdown = [
        {
            "category": name,
            "total": round(amount, 2),
            "count": counts[name],
            "pct": 0.0,  # filled below
        }
        for name, amount in totals.items()
    ]
    grand_total = sum(b["total"] for b in breakdown)
    for b in breakdown:
        b["pct"] = round((b["total"] / grand_total * 100) if grand_total else 0, 1)
    breakdown.sort(key=lambda x: x["total"], reverse=True)
    return breakdown


def _compute_daily_spending(
    expenses: list[dict], start: date, end: date
) -> list[dict]:
    """Per-day spending totals for sparkline / chart data."""
    daily: dict[str, float] = {}
    for d in range(7):
        day = start + timedelta(days=d)
        daily[day.isoformat()] = 0.0
    for e in expenses:
        day = e["spent_at"]
        daily[day] = daily.get(day, 0) + e["amount"]
    return [{"date": k, "total": round(v, 2)} for k, v in sorted(daily.items())]


def _detect_anomalies(
    expenses: list[dict],
    cat_map: dict[int, str],
    weekly_total: float,
    prev_week_total: float,
) -> list[str]:
    """Flag noteworthy patterns."""
    flags = []

    # Week-over-week change
    if prev_week_total > 0:
        change_pct = ((weekly_total - prev_week_total) / prev_week_total) * 100
        if change_pct > 30:
            flags.append(
                f"Spending jumped {change_pct:.0f}% vs last week "
                f"(₹{prev_week_total:,.0f} → ₹{weekly_total:,.0f})"
            )
        elif change_pct < -20:
            flags.append(
                f"Great job! Spending dropped {abs(change_pct):.0f}% vs last week"
            )

    # Single large transaction (> 40% of weekly total)
    if weekly_total > 0:
        for e in expenses:
            if e["amount"] / weekly_total > 0.4:
                cat = cat_map.get(e["category_id"], "Uncategorized")
                flags.append(
                    f"Large transaction: ₹{e['amount']:,.0f} in {cat} "
                    f"on {e['spent_at']} ({e['amount']/weekly_total*100:.0f}% of weekly spend)"
                )

    # No spending (possibly missing data)
    if not expenses:
        flags.append("No expenses recorded this week — is everything tracked?")

    return flags


def _heuristic_tips(
    breakdown: list[dict],
    weekly_total: float,
    prev_week_total: float,
    income: float,
) -> list[str]:
    """Generate actionable tips without AI."""
    tips = []
    if breakdown:
        top = breakdown[0]
        tips.append(
            f"Your biggest category was {top['category']} "
            f"(₹{top['total']:,.0f}, {top['pct']}% of spend). "
            "Review if any items were avoidable."
        )
    if income > 0 and weekly_total > income:
        tips.append(
            f"You spent ₹{weekly_total - income:,.0f} more than you earned this week. "
            "Check if this is sustainable."
        )
    elif income > 0:
        saved = income - weekly_total
        tips.append(f"You saved ₹{saved:,.0f} this week — keep it up!")
    if prev_week_total > 0 and weekly_total > prev_week_total * 1.1:
        tips.append("Spending trended up — set a mini-budget challenge for next week.")
    if not tips:
        tips.append("Consistent week. Stay the course!")
    return tips[:3]


# ---------------------------------------------------------------------------
# AI-enhanced digest (optional)
# ---------------------------------------------------------------------------

def _gemini_insights(
    digest_data: dict, api_key: str, model: str, persona: str
) -> dict | None:
    """Ask Gemini for a narrative summary + tips. Returns None on failure."""
    prompt = (
        f"{persona}\n"
        "Given this weekly financial digest data, return strict JSON with keys: "
        "narrative (2-3 sentence summary), tips (list of 3 actionable tips), "
        "mood (one of: great, good, okay, concerning, critical).\n"
        f"data={json.dumps(digest_data, default=str)}"
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
    req = urllib_request.Request(
        url=url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=10) as resp:  # nosec B310
            payload = json.loads(resp.read().decode("utf-8"))
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
        if start == -1 or end == -1:
            return None
        return json.loads(text[start:end + 1])
    except Exception:
        logger.debug("Gemini digest enhancement failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_weekly_digest(
    uid: int,
    week_of: date | None = None,
    gemini_api_key: str | None = None,
    persona: str | None = None,
) -> dict:
    """Generate a complete weekly financial digest for user *uid*.

    Parameters
    ----------
    uid : int
        User ID.
    week_of : date | None
        Any date within the target week. If None, uses the previous
        complete week.
    gemini_api_key : str | None
        Optional Gemini key for AI-enhanced narrative. Falls back to
        heuristic tips if unavailable.
    persona : str | None
        Optional AI persona override.

    Returns
    -------
    dict
        Complete digest payload ready for API response or email template.
    """
    start, end = _week_bounds(week_of)
    cat_map = _category_map(uid)

    expenses = _weekly_expenses(uid, start, end)
    income = _weekly_income(uid, start, end)
    weekly_total = round(sum(e["amount"] for e in expenses), 2)
    prev_total = _previous_week_total(uid, start)

    breakdown = _compute_category_breakdown(expenses, cat_map)
    daily = _compute_daily_spending(expenses, start, end)
    anomalies = _detect_anomalies(expenses, cat_map, weekly_total, prev_total)
    bills = _upcoming_bills(uid, end + timedelta(days=1), end + timedelta(days=7))

    # Week-over-week change
    if prev_total > 0:
        wow_change_pct = round(
            ((weekly_total - prev_total) / prev_total) * 100, 1
        )
    else:
        wow_change_pct = 0.0

    digest = {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "total_expenses": weekly_total,
        "total_income": round(income, 2),
        "net_flow": round(income - weekly_total, 2),
        "previous_week_expenses": round(prev_total, 2),
        "week_over_week_change_pct": wow_change_pct,
        "transaction_count": len(expenses),
        "daily_spending": daily,
        "category_breakdown": breakdown,
        "anomalies": anomalies,
        "upcoming_bills": bills,
    }

    # AI enhancement
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()

    if key:
        ai = _gemini_insights(digest, key, model, persona_text)
        if ai:
            digest["narrative"] = ai.get("narrative", "")
            digest["ai_tips"] = ai.get("tips", [])
            digest["mood"] = ai.get("mood", "okay")
            digest["method"] = "gemini"
        else:
            digest["tips"] = _heuristic_tips(breakdown, weekly_total, prev_total, income)
            digest["method"] = "heuristic"
            digest["warnings"] = ["gemini_unavailable"]
    else:
        digest["tips"] = _heuristic_tips(breakdown, weekly_total, prev_total, income)
        digest["method"] = "heuristic"

    logger.info(
        "Generated weekly digest user=%s week=%s..%s total=%.2f txns=%d",
        uid, start, end, weekly_total, len(expenses),
    )
    return digest


def generate_digest_email_body(digest: dict) -> str:
    """Render a digest dict into a plain-text email body."""
    lines = [
        f"📊 FinMind Weekly Digest ({digest['week_start']} → {digest['week_end']})",
        "",
        f"Total Spent: ₹{digest['total_expenses']:,.2f}",
        f"Total Income: ₹{digest['total_income']:,.2f}",
        f"Net Flow: ₹{digest['net_flow']:,.2f}",
        f"vs Last Week: {digest['week_over_week_change_pct']:+.1f}%",
        f"Transactions: {digest['transaction_count']}",
        "",
    ]

    if digest.get("narrative"):
        lines.append(digest["narrative"])
        lines.append("")

    if digest["category_breakdown"]:
        lines.append("📂 By Category:")
        for cat in digest["category_breakdown"][:5]:
            lines.append(
                f"  • {cat['category']}: ₹{cat['total']:,.2f} "
                f"({cat['pct']}%, {cat['count']} txns)"
            )
        lines.append("")

    if digest.get("anomalies"):
        lines.append("⚠️ Noteworthy:")
        for a in digest["anomalies"]:
            lines.append(f"  • {a}")
        lines.append("")

    tips = digest.get("ai_tips") or digest.get("tips", [])
    if tips:
        lines.append("💡 Tips:")
        for t in tips:
            lines.append(f"  • {t}")
        lines.append("")

    if digest.get("upcoming_bills"):
        lines.append("📅 Upcoming Bills (next 7 days):")
        for b in digest["upcoming_bills"]:
            auto = " (autopay)" if b["autopay"] else ""
            lines.append(f"  • {b['name']}: ₹{b['amount']:,.2f} due {b['due_date']}{auto}")
        lines.append("")

    lines.append("— FinMind")
    return "\n".join(lines)
