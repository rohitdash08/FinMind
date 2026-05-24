"""Weekly digest service.

Aggregates the past 7 days of transactions per user and sends a
formatted HTML summary email.  The scheduler job runs every Monday
at 08:00 server time via APScheduler.

Public API
----------
build_weekly_digest(uid, reference_date=None) -> dict
render_digest_html(data) -> str
send_weekly_digest(user) -> bool
send_all_weekly_digests() -> {"sent": int, "failed": int}
init_digest_scheduler(app) -> None
"""
from __future__ import annotations

import logging
import re
import smtplib
from datetime import date, timedelta
from email.message import EmailMessage
from typing import Any

from ..extensions import db
from ..models import Category, Expense, User

logger = logging.getLogger("finmind.digest")

# ---------------------------------------------------------------------------
# HTML template (single-file; no extra template-engine dependency)
# ---------------------------------------------------------------------------
_DIGEST_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{{font-family:Arial,sans-serif;color:#333;max-width:600px;margin:auto;padding:24px;}}
  h1{{color:#2563eb;font-size:22px;margin-bottom:4px;}}
  h2{{color:#374151;font-size:15px;border-bottom:1px solid #e5e7eb;padding-bottom:4px;margin-top:24px;}}
  .meta{{color:#6b7280;font-size:13px;margin-bottom:20px;}}
  .stats{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:4px;}}
  .stat{{background:#f3f4f6;border-radius:8px;padding:12px 20px;text-align:center;min-width:100px;}}
  .stat-value{{font-size:20px;font-weight:700;color:#111827;}}
  .stat-label{{font-size:11px;color:#6b7280;margin-top:2px;}}
  .up{{color:#dc2626;}} .down{{color:#16a34a;}} .flat{{color:#6b7280;}}
  table{{width:100%;border-collapse:collapse;margin-top:8px;}}
  th,td{{text-align:left;padding:8px 6px;border-bottom:1px solid #f3f4f6;font-size:14px;}}
  th{{color:#6b7280;font-weight:600;font-size:12px;text-transform:uppercase;}}
  .amount{{font-weight:600;}}
  .highlight{{color:#dc2626;font-weight:700;}}
  .footer{{margin-top:32px;font-size:12px;color:#9ca3af;border-top:1px solid #f3f4f6;padding-top:12px;}}
  .no-data{{color:#9ca3af;font-style:italic;}}
</style>
</head>
<body>
<h1>&#128202; Your Weekly FinMind Digest</h1>
<p class="meta">{date_range}</p>

<div class="stats">
  <div class="stat">
    <div class="stat-value">{currency}&nbsp;{total_spent:.2f}</div>
    <div class="stat-label">Total Spent</div>
  </div>
  <div class="stat">
    <div class="stat-value {wow_class}">{wow_sign}{wow_abs:.1f}%</div>
    <div class="stat-label">vs Previous Week</div>
  </div>
  <div class="stat">
    <div class="stat-value">{num_transactions}</div>
    <div class="stat-label">Transactions</div>
  </div>
</div>

<h2>Top Categories</h2>
{category_table}

{largest_section}

<div class="footer">
  You are receiving this weekly summary from FinMind.
  Digests are sent every Monday morning.
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Data layer helpers
# ---------------------------------------------------------------------------

def _week_expenses(uid: int, week_start: date) -> list[Expense]:
    """Return EXPENSE rows for *uid* within the 7-day window starting at *week_start*."""
    week_end = week_start + timedelta(days=6)
    return (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.expense_type != "INCOME",
            Expense.spent_at >= week_start,
            Expense.spent_at <= week_end,
        )
        .order_by(Expense.spent_at.desc())
        .all()
    )


def _category_name(cat_id: int | None) -> str:
    if cat_id is None:
        return "Uncategorised"
    cat = db.session.get(Category, cat_id)
    return cat.name if cat else f"Category {cat_id}"


# ---------------------------------------------------------------------------
# Public: build digest data
# ---------------------------------------------------------------------------

def build_weekly_digest(uid: int, reference_date: date | None = None) -> dict[str, Any]:
    """Build a digest dict for the 7 days ending on *reference_date* (default: today).

    Returns a plain dict that can be serialised to JSON or passed to
    :func:`render_digest_html`.
    """
    today = reference_date or date.today()
    week_start = today - timedelta(days=6)
    prev_start = week_start - timedelta(days=7)

    current_expenses = _week_expenses(uid, week_start)
    previous_expenses = _week_expenses(uid, prev_start)

    total_current = sum(float(e.amount) for e in current_expenses)
    total_previous = sum(float(e.amount) for e in previous_expenses)

    if total_previous > 0:
        wow_change = round(
            ((total_current - total_previous) / total_previous) * 100, 1
        )
    else:
        wow_change = 0.0

    # Category breakdown
    cat_totals: dict[int | None, float] = {}
    for e in current_expenses:
        cat_totals[e.category_id] = cat_totals.get(e.category_id, 0.0) + float(e.amount)

    categories = sorted(
        [
            {
                "category_id": k,
                "name": _category_name(k),
                "amount": round(v, 2),
            }
            for k, v in cat_totals.items()
        ],
        key=lambda x: x["amount"],
        reverse=True,
    )

    largest = (
        max(current_expenses, key=lambda e: float(e.amount))
        if current_expenses
        else None
    )

    user = db.session.get(User, uid)
    currency = (user.preferred_currency if user else None) or "INR"

    return {
        "user_id": uid,
        "currency": currency,
        "date_range": f"{week_start.isoformat()} – {today.isoformat()}",
        "week_start": week_start.isoformat(),
        "week_end": today.isoformat(),
        "total_spent": round(total_current, 2),
        "total_previous_week": round(total_previous, 2),
        "wow_change_pct": wow_change,
        "num_transactions": len(current_expenses),
        "top_categories": categories[:3],
        "all_categories": categories,
        "largest_expense": {
            "amount": round(float(largest.amount), 2),
            "notes": largest.notes or "",
            "date": largest.spent_at.isoformat(),
        }
        if largest
        else None,
    }


# ---------------------------------------------------------------------------
# Public: render HTML
# ---------------------------------------------------------------------------

def render_digest_html(data: dict[str, Any]) -> str:
    """Render a digest data dict into an HTML email string."""
    currency = data["currency"]
    total = data["total_spent"] or 1.0
    wow = data["wow_change_pct"]

    if wow > 0:
        wow_class, wow_sign, wow_abs = "up", "+", wow
    elif wow < 0:
        wow_class, wow_sign, wow_abs = "down", "-", abs(wow)
    else:
        wow_class, wow_sign, wow_abs = "flat", "", 0.0

    # Category table rows
    rows = ""
    for cat in data["top_categories"]:
        share = round(cat["amount"] / total * 100, 1)
        rows += (
            f"<tr>"
            f"<td>{cat['name']}</td>"
            f"<td class='amount'>{cat['amount']:.2f}</td>"
            f"<td>{share}%</td>"
            f"</tr>\n"
        )
    category_table = (
        f"<table><tr><th>Category</th><th>{currency}</th><th>Share</th></tr>"
        f"{rows}</table>"
        if rows
        else "<p class='no-data'>No expenses recorded this week.</p>"
    )

    # Largest expense block
    largest = data.get("largest_expense")
    if largest:
        desc = largest["notes"] or "No description"
        largest_section = (
            "<h2>Largest Single Expense</h2>"
            f"<p><span class='highlight'>{currency}&nbsp;{largest['amount']:.2f}</span>"
            f" &mdash; {desc} <span style='color:#9ca3af'>({largest['date']})</span></p>"
        )
    else:
        largest_section = ""

    return _DIGEST_HTML.format(
        date_range=data["date_range"],
        currency=currency,
        total_spent=data["total_spent"],
        wow_class=wow_class,
        wow_sign=wow_sign,
        wow_abs=wow_abs,
        num_transactions=data["num_transactions"],
        category_table=category_table,
        largest_section=largest_section,
    )


# ---------------------------------------------------------------------------
# Public: send helpers
# ---------------------------------------------------------------------------

def _send_html_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an HTML email via SMTP.  Returns False if SMTP is not configured."""
    from ..config import Settings

    cfg = Settings()
    if not cfg.smtp_url or not cfg.email_from:
        logger.warning("SMTP not configured; digest not sent to %s", to_email)
        return False
    try:
        m = re.match(r"smtp\+ssl://(.+?):(.+?)@(.+?):(\d+)", cfg.smtp_url)
        if not m:
            logger.error("Unparseable SMTP_URL: %s", cfg.smtp_url)
            return False
        user, pwd, host, port = m.groups()
        msg = EmailMessage()
        msg["From"] = cfg.email_from
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content("Please view this email in an HTML-capable mail client.")
        msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP_SSL(host, int(port)) as s:
            s.login(user, pwd)
            s.send_message(msg)
        logger.info("Digest sent to %s", to_email)
        return True
    except Exception:
        logger.exception("SMTP error sending digest to %s", to_email)
        return False


def send_weekly_digest(user: User) -> bool:
    """Build and email the weekly digest for *user*.  Returns True on success."""
    try:
        data = build_weekly_digest(user.id)
        html = render_digest_html(data)
        subject = f"\U0001f4ca Your weekly spending digest ({data['date_range']})"
        return _send_html_email(user.email, subject, html)
    except Exception:
        logger.exception("Failed to build/send digest for user %s", user.id)
        return False


def send_all_weekly_digests() -> dict[str, int]:
    """Iterate all users and send each a weekly digest.

    Returns a summary dict ``{"sent": N, "failed": M}``.
    """
    users = db.session.query(User).all()
    sent = failed = 0
    for user in users:
        if send_weekly_digest(user):
            sent += 1
        else:
            failed += 1
    logger.info("Weekly digest run complete: sent=%d failed=%d", sent, failed)
    return {"sent": sent, "failed": failed}


# ---------------------------------------------------------------------------
# Public: scheduler init
# ---------------------------------------------------------------------------

def init_digest_scheduler(app) -> None:
    """Register the weekly digest APScheduler job inside *app*.

    Called once from :func:`app.create_app`.  The job fires every Monday
    at 08:00 local server time.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler(daemon=True)

        def _job() -> None:
            with app.app_context():
                send_all_weekly_digests()

        scheduler.add_job(
            _job,
            trigger="cron",
            day_of_week="mon",
            hour=8,
            minute=0,
            id="weekly_digest",
            replace_existing=True,
        )
        scheduler.start()
        app.extensions["digest_scheduler"] = scheduler
        logger.info("Weekly digest scheduler started (cron: Monday 08:00)")
    except Exception:
        logger.exception("Could not start digest scheduler")
