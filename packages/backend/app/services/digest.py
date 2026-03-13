"""Weekly financial digest service.

Aggregates a 7-day spending window, generates AI insight via Gemini,
persists digests for idempotency, and delivers via email.
"""

import json
import logging
from datetime import date, datetime, timedelta
from urllib import request as url_request

from sqlalchemy import func

from ..config import Settings
from ..extensions import db
from ..models import Bill, Category, Expense, User, WeeklyDigest
from .reminders import send_email

logger = logging.getLogger("finmind.digest")
_settings = Settings()

DIGEST_PERSONA = (
    "You are FinMind's weekly financial coach. Summarise the user's spending "
    "week in 2-3 concise, encouraging sentences. Highlight the most notable "
    "trend. Include one specific, actionable tip to improve next week. "
    "Be data-driven, non-judgmental, and concise."
)

# Helpers


def week_boundaries(reference: date | None = None) -> tuple[date, date]:
    """Return (Monday, Sunday) of the last fully completed week."""
    today = reference or date.today()
    # Monday of the current week
    current_monday = today - timedelta(days=today.weekday())
    # Last completed week
    week_end = current_monday - timedelta(days=1)  # previous Sunday
    week_start = week_end - timedelta(days=6)  # previous Monday
    return week_start, week_end


# Data aggregation


def _weekly_totals(uid: int, start: date, end: date) -> tuple[float, float, int]:
    """Return (income, expenses, transaction_count) for the date range."""
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
    tx_count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0), int(tx_count or 0)


def _category_breakdown(uid: int, start: date, end: date) -> list[dict]:
    """Per-category spend with percentages."""
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
    grand = sum(float(r.total or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "name": r.category_name,
            "amount": round(float(r.total or 0), 2),
            "share_pct": (
                round((float(r.total or 0) / grand) * 100, 2) if grand > 0 else 0
            ),
        }
        for r in rows
    ]


def _biggest_expense(uid: int, start: date, end: date) -> dict | None:
    """Single largest expense in the period."""
    row = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .first()
    )
    if not row:
        return None
    return {
        "amount": float(row.amount),
        "notes": row.notes or "Transaction",
        "date": row.spent_at.isoformat(),
    }


def _upcoming_bills(uid: int, from_date: date) -> list[dict]:
    """Bills due within the next 7 days."""
    to_date = from_date + timedelta(days=7)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= from_date,
            Bill.next_due_date <= to_date,
        )
        .order_by(Bill.next_due_date.asc())
        .limit(10)
        .all()
    )
    return [
        {
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "due_date": b.next_due_date.isoformat(),
        }
        for b in bills
    ]


# Core digest computation


def compute_weekly_digest(uid: int, w_start: date, w_end: date) -> dict:
    """Aggregate financial data for the given week."""
    income, expenses, tx_count = _weekly_totals(uid, w_start, w_end)

    # Previous week for comparison
    prev_start = w_start - timedelta(days=7)
    prev_end = w_end - timedelta(days=7)
    _, prev_expenses, _ = _weekly_totals(uid, prev_start, prev_end)

    wow_change = 0.0
    if prev_expenses > 0:
        wow_change = round(((expenses - prev_expenses) / prev_expenses) * 100, 2)

    cats = _category_breakdown(uid, w_start, w_end)
    biggest = _biggest_expense(uid, w_start, w_end)
    days = (w_end - w_start).days + 1
    daily_avg = round(expenses / days, 2) if days > 0 else 0.0

    user = db.session.get(User, uid)
    currency = user.preferred_currency if user else "INR"

    return {
        "user_id": uid,
        "week_start": w_start.isoformat(),
        "week_end": w_end.isoformat(),
        "currency": currency,
        "summary": {
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net_flow": round(income - expenses, 2),
            "week_over_week_change_pct": wow_change,
            "transaction_count": tx_count,
        },
        "category_breakdown": cats,
        "highlights": {
            "top_category": cats[0]["name"] if cats else None,
            "biggest_expense": biggest,
            "daily_average": daily_avg,
        },
        "upcoming_bills": _upcoming_bills(uid, w_end + timedelta(days=1)),
    }


# AI insight


def _extract_text(raw: str) -> str:
    """Strip markdown fences from model output."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def generate_ai_insight(
    digest_payload: dict,
    gemini_api_key: str | None = None,
    persona: str | None = None,
) -> tuple[str, str]:
    """Return (insight_text, method).

    Tries Gemini first, falls back to heuristic tips.
    """
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = _settings.gemini_model
    persona_text = (persona or DIGEST_PERSONA).strip()

    if key:
        try:
            return _gemini_insight(digest_payload, key, model, persona_text)
        except Exception:
            logger.warning("Gemini unavailable for digest, using heuristic")

    return _heuristic_insight(digest_payload), "heuristic"


def _gemini_insight(
    payload: dict, api_key: str, model: str, persona: str
) -> tuple[str, str]:
    prompt = (
        f"{persona}\n"
        "Analyse this weekly spending data and reply with a brief plain-text "
        "summary (no JSON, no markdown). 2-3 sentences max.\n"
        f"data={json.dumps(payload, default=str)}"
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
        result = json.loads(resp.read().decode("utf-8"))
    text = (
        result.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    return _extract_text(text), "gemini"


def _heuristic_insight(payload: dict) -> str:
    """Generate a simple rule-based insight."""
    summary = payload.get("summary", {})
    wow = summary.get("week_over_week_change_pct", 0)
    expenses = summary.get("total_expenses", 0)
    top = payload.get("highlights", {}).get("top_category")

    parts = []
    if wow > 0:
        parts.append(f"Your spending increased by {abs(wow)}% compared to last week.")
    elif wow < 0:
        parts.append(
            f"Great job! Spending decreased by {abs(wow)}% compared to " "last week."
        )
    else:
        parts.append("Your spending was steady compared to last week.")

    if top:
        parts.append(f"Top category: {top}.")

    if expenses > 0:
        parts.append("Tip: Review your top spending category for potential savings.")

    return " ".join(parts)


# Persist & retrieve


def get_or_create_digest(
    uid: int,
    w_start: date | None = None,
    gemini_api_key: str | None = None,
) -> dict:
    """Idempotent: return existing or create new digest for the week."""
    if w_start is None:
        w_start, _ = week_boundaries()

    # Normalise to Monday
    w_start = w_start - timedelta(days=w_start.weekday())
    w_end = w_start + timedelta(days=6)

    existing = (
        db.session.query(WeeklyDigest)
        .filter_by(user_id=uid, week_start=w_start)
        .first()
    )
    if existing:
        return _digest_to_dict(existing)

    payload = compute_weekly_digest(uid, w_start, w_end)
    insight_text, method = generate_ai_insight(payload, gemini_api_key=gemini_api_key)

    digest = WeeklyDigest(
        user_id=uid,
        week_start=w_start,
        week_end=w_end,
        payload=payload,
        ai_insight=insight_text,
        method=method,
    )
    db.session.add(digest)
    db.session.commit()
    logger.info(
        "Created weekly digest id=%s user=%s week=%s method=%s",
        digest.id,
        uid,
        w_start,
        method,
    )
    return _digest_to_dict(digest)


def _digest_to_dict(d: WeeklyDigest) -> dict:
    return {
        "id": d.id,
        "user_id": d.user_id,
        "week_start": d.week_start.isoformat(),
        "week_end": d.week_end.isoformat(),
        "payload": d.payload,
        "ai_insight": d.ai_insight,
        "method": d.method,
        "delivered_at": (d.delivered_at.isoformat() if d.delivered_at else None),
        "channel": d.channel,
        "created_at": d.created_at.isoformat(),
    }


# Delivery


def _format_digest_email(user: User, digest_data: dict) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for the weekly digest email."""
    payload = digest_data.get("payload", {})
    summary = payload.get("summary", {})
    cats = payload.get("category_breakdown", [])
    highlights = payload.get("highlights", {})
    bills = payload.get("upcoming_bills", [])
    insight = digest_data.get("ai_insight", "")
    currency = payload.get("currency", "INR")

    w_start = digest_data["week_start"]
    w_end = digest_data["week_end"]

    subject = f"FinMind Weekly Digest — {w_start} to {w_end}"
    user_name = user.email.split("@")[0] if user and user.email else "there"

    lines = [
        f"Hi {user_name},\n",
        "Here's your FinMind weekly spending summary for " f"{w_start} to {w_end}.\n",
        "─── SUMMARY ───",
        f"  Income:       {currency} {summary.get('total_income', 0):,.2f}",
        f"  Expenses:     {currency} {summary.get('total_expenses', 0):,.2f}",
        f"  Net Flow:     {currency} {summary.get('net_flow', 0):,.2f}",
        f"  Transactions: {summary.get('transaction_count', 0)}",
        f"  vs Last Week: {summary.get('week_over_week_change_pct', 0):+.1f}%",
        "",
    ]

    if cats:
        lines.append("─── CATEGORY BREAKDOWN ───")
        for c in cats[:5]:
            lines.append(
                f"  {c['name']}: {currency} {c['amount']:,.2f} " f"({c['share_pct']}%)"
            )
        lines.append("")

    biggest = highlights.get("biggest_expense")
    if biggest:
        lines.append("─── HIGHLIGHTS ───")
        lines.append(
            f"  Biggest Expense: {currency} {biggest['amount']:,.2f} "
            f"— {biggest['notes']} ({biggest['date']})"
        )
        lines.append(
            f"  Daily Average:   {currency} "
            f"{highlights.get('daily_average', 0):,.2f}"
        )
        lines.append("")

    if bills:
        lines.append("─── UPCOMING BILLS ───")
        for b in bills:
            lines.append(
                f"  {b['name']}: {b.get('currency', currency)} "
                f"{b['amount']:,.2f} — due {b['due_date']}"
            )
        lines.append("")

    if insight:
        lines.append("─── AI INSIGHT ───")
        lines.append(f"  {insight}")
        lines.append("")

    lines.append("Stay on track! — FinMind")

    # --- HTML Formatting ---
    def format_money(amount: float) -> str:
        return f"{currency} {amount:,.2f}"

    inc_str = format_money(summary.get("total_income", 0))
    exp_str = format_money(summary.get("total_expenses", 0))
    net_flow = summary.get("net_flow", 0)
    net_str = format_money(net_flow)
    wow_pct = summary.get("week_over_week_change_pct", 0)
    wow_str = f"{wow_pct:+.1f}%"

    html_lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head><style>",
        "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 20px; }",  # noqa: E501
        ".container { max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); }",  # noqa: E501
        ".header { background-color: #0f172a; color: #ffffff; padding: 24px; text-align: center; }",  # noqa: E501
        ".header h1 { margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.025em; }",  # noqa: E501
        ".content { padding: 32px; }",
        ".greeting { font-size: 18px; font-weight: 600; margin-bottom: 24px; }",
        ".section { margin-bottom: 32px; }",
        ".section-title { font-size: 16px; font-weight: 600; color: #0f172a; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #e2e8f0; }",  # noqa: E501
        ".insight-box { background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 16px; border-radius: 8px; color: #166534; font-size: 14px; line-height: 1.5; }",  # noqa: E501
        ".footer { text-align: center; padding: 24px; color: #64748b; font-size: 12px; background-color: #f8fafc; }",  # noqa: E501
        "</style></head>",
        "<body>",
        "<div class='container'>",
        "<div class='header'>",
        "<h1>FinMind Weekly Digest</h1>",
        "</div>",
        "<div class='content'>",
        f"<div class='greeting'>Hi {user_name},</div>",
        f"<p style='color: #475569; font-size: 15px; line-height: 1.5;'>Here is your financial summary for <strong>{w_start}</strong> to <strong>{w_end}</strong>.</p>",  # noqa: E501
        # Summary Cards (Income, Expenses, Net Flow)
        "<div class='section'>",
        "<table width='100%' cellpadding='0' cellspacing='0' style='margin-bottom: 16px;'><tr>",  # noqa: E501
        f"<td width='32%' style='background-color: #f8fafc; padding: 16px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;'><div style='font-size: 12px; color: #64748b; text-transform: uppercase; font-weight: 600; margin-bottom: 8px;'>Income</div><div style='font-size: 20px; font-weight: 700; color: #16a34a;'>{inc_str}</div></td>",  # noqa: E501
        "<td width='2%'></td>",
        f"<td width='32%' style='background-color: #f8fafc; padding: 16px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;'><div style='font-size: 12px; color: #64748b; text-transform: uppercase; font-weight: 600; margin-bottom: 8px;'>Expenses</div><div style='font-size: 20px; font-weight: 700; color: #dc2626;'>{exp_str}</div></td>",  # noqa: E501
        "<td width='2%'></td>",
        f"<td width='32%' style='background-color: #f8fafc; padding: 16px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;'><div style='font-size: 12px; color: #64748b; text-transform: uppercase; font-weight: 600; margin-bottom: 8px;'>Net Flow</div><div style='font-size: 20px; font-weight: 700; color: {'#16a34a' if net_flow >= 0 else '#dc2626'};'>{net_str}</div></td>",  # noqa: E501
        "</tr></table>",
        "</div>",
    ]

    if insight:
        html_lines.extend(
            [
                "<div class='section'>",
                "<div class='section-title'>AI Insight</div>",
                f"<div class='insight-box'>✨ {insight}</div>",
                "</div>",
            ]
        )

    if cats:
        html_lines.extend(
            [
                "<div class='section'>",
                "<div class='section-title'>Category Breakdown</div>",
                "<table width='100%' cellpadding='0' cellspacing='0'>",
            ]
        )
        for c in cats[:5]:
            html_lines.append(
                f"<tr><td style='padding: 12px 0; border-bottom: 1px solid #f1f5f9; color: #334155; font-size: 15px;'>{c['name']}</td><td style='padding: 12px 0; border-bottom: 1px solid #f1f5f9; text-align: right; color: #0f172a; font-weight: 600; font-size: 15px;'>{format_money(c['amount'])} <span style='color: #64748b; font-size: 13px; font-weight: 400;'>({c['share_pct']}%)</span></td></tr>"  # noqa: E501
            )
        html_lines.append("</table></div>")

    if highlights.get("biggest_expense"):
        biggest = highlights.get("biggest_expense")
        html_lines.extend(
            [
                "<div class='section'>",
                "<div class='section-title'>Highlights</div>",
                "<table width='100%' cellpadding='0' cellspacing='0'>",
                f"<tr><td style='padding: 12px 0; border-bottom: 1px solid #f1f5f9; color: #334155; font-size: 15px;'>Biggest Expense ({biggest['date']})<br><span style='color: #64748b; font-size: 13px;'>{biggest['notes']}</span></td><td style='padding: 12px 0; border-bottom: 1px solid #f1f5f9; text-align: right; color: #dc2626; font-weight: 600; font-size: 15px;'>{format_money(biggest['amount'])}</td></tr>",  # noqa: E501
                f"<tr><td style='padding: 12px 0; border-bottom: 1px solid #f1f5f9; color: #334155; font-size: 15px;'>Daily Average</td><td style='padding: 12px 0; border-bottom: 1px solid #f1f5f9; text-align: right; color: #0f172a; font-weight: 600; font-size: 15px;'>{format_money(highlights.get('daily_average', 0))}</td></tr>",  # noqa: E501
                f"<tr><td style='padding: 12px 0; border-bottom: 1px solid #f1f5f9; color: #334155; font-size: 15px;'>vs Last Week</td><td style='padding: 12px 0; border-bottom: 1px solid #f1f5f9; text-align: right; color: {'#16a34a' if wow_pct <= 0 else '#dc2626'}; font-weight: 600; font-size: 15px;'>{wow_str}</td></tr>",  # noqa: E501
                "</table></div>",
            ]
        )

    if bills:
        html_lines.extend(
            [
                "<div class='section'>",
                "<div class='section-title'>Upcoming Bills (Next 7 Days)</div>",
                "<table width='100%' cellpadding='0' cellspacing='0'>",
            ]
        )
        for b in bills:
            html_lines.append(
                f"<tr><td style='padding: 12px 0; border-bottom: 1px solid #f1f5f9; color: #334155; font-size: 15px;'>{b['name']}<br><span style='color: #64748b; font-size: 13px;'>Due: {b['due_date']}</span></td><td style='padding: 12px 0; border-bottom: 1px solid #f1f5f9; text-align: right; color: #0f172a; font-weight: 600; font-size: 15px;'>{currency} {b['amount']:,.2f}</td></tr>"  # noqa: E501
            )
        html_lines.append("</table></div>")

    html_lines.extend(
        [
            "</div>",
            "<div class='footer'>",
            "You are receiving this because you opted into Weekly Digests.<br>",
            "FinMind Money OS",
            "</div>",
            "</div>",
            "</body>",
            "</html>",
        ]
    )

    html_body = "".join(html_lines)

    return subject, "\n".join(lines), html_body


def deliver_digest_email(uid: int, digest_data: dict) -> bool:
    """Send digest email and mark as delivered."""
    user = db.session.get(User, uid)
    if not user:
        return False

    subject, body, html_body = _format_digest_email(user, digest_data)
    success = send_email(user.email, subject, body, html_body=html_body)

    if success:
        digest = db.session.get(WeeklyDigest, digest_data["id"])
        if digest:
            digest.delivered_at = datetime.utcnow()
            digest.channel = "email"
            db.session.commit()
        logger.info("Delivered digest email user=%s digest=%s", uid, digest_data["id"])
    else:
        logger.warning(
            "Failed to deliver digest email user=%s digest=%s", uid, digest_data["id"]
        )

    return success


# Scheduled job entry point


def run_weekly_digest_job(app) -> dict:  # noqa: C901
    """Generate and deliver digests for all opted-in users.

    Intended to be called by APScheduler or a cron trigger.
    Returns summary counts.
    """
    with app.app_context():
        users = db.session.query(User).filter(User.digest_email_enabled.is_(True)).all()
        generated = 0
        delivered = 0
        errors = 0

        for user in users:
            try:
                digest_data = get_or_create_digest(user.id)
                generated += 1
                if deliver_digest_email(user.id, digest_data):
                    delivered += 1
            except Exception:
                logger.exception("Digest job failed for user=%s", user.id)
                errors += 1

        summary = {
            "total_users": len(users),
            "generated": generated,
            "delivered": delivered,
            "errors": errors,
        }
        logger.info("Weekly digest job complete: %s", summary)
        return summary
