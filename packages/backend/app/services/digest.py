"""Weekly financial digest — generates smart summaries with trends and insights."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Bill, Category, Expense, User
from .reminders import send_email

import logging

logger = logging.getLogger("finmind.digest")


def generate_weekly_digest(user_id: int, end_date: Optional[date] = None) -> dict:
    """Generate a weekly financial summary for a user.

    Args:
        user_id: The user's ID.
        end_date: End of the reporting week (defaults to today).

    Returns:
        Dictionary containing the full digest payload.
    """
    if end_date is None:
        end_date = date.today()
    start_date = end_date - timedelta(days=6)
    prev_start = start_date - timedelta(days=7)
    prev_end = start_date - timedelta(days=1)

    digest = {
        "user_id": user_id,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "summary": {},
        "vs_previous_week": {},
        "top_categories": [],
        "daily_breakdown": [],
        "upcoming_bills": [],
        "insights": [],
    }

    # --- Current week totals ---
    current_income = _sum_expenses(user_id, start_date, end_date, expense_type="INCOME")
    current_spending = _sum_expenses(user_id, start_date, end_date, exclude_type="INCOME")
    current_net = current_income - current_spending
    transaction_count = _count_expenses(user_id, start_date, end_date)

    digest["summary"] = {
        "total_income": round(current_income, 2),
        "total_spending": round(current_spending, 2),
        "net_flow": round(current_net, 2),
        "transaction_count": transaction_count,
        "avg_daily_spending": round(current_spending / 7, 2) if current_spending else 0,
    }

    # --- Previous week comparison ---
    prev_income = _sum_expenses(user_id, prev_start, prev_end, expense_type="INCOME")
    prev_spending = _sum_expenses(user_id, prev_start, prev_end, exclude_type="INCOME")

    income_change = _pct_change(prev_income, current_income)
    spending_change = _pct_change(prev_spending, current_spending)

    digest["vs_previous_week"] = {
        "income_change_pct": income_change,
        "spending_change_pct": spending_change,
        "income_trend": "up" if income_change > 0 else ("down" if income_change < 0 else "flat"),
        "spending_trend": "up" if spending_change > 0 else ("down" if spending_change < 0 else "flat"),
        "previous_income": round(prev_income, 2),
        "previous_spending": round(prev_spending, 2),
    }

    # --- Top spending categories ---
    category_rows = (
        db.session.query(
            Category.name,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
            func.count(Expense.id).label("count"),
        )
        .outerjoin(Category, (Category.id == Expense.category_id) & (Category.user_id == user_id))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
            Expense.expense_type != "INCOME",
        )
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .limit(5)
        .all()
    )
    total_cat = sum(float(r.total or 0) for r in category_rows)
    digest["top_categories"] = [
        {
            "name": r.name or "Uncategorized",
            "amount": round(float(r.total or 0), 2),
            "transaction_count": r.count,
            "share_pct": round((float(r.total or 0) / total_cat) * 100, 1) if total_cat > 0 else 0,
        }
        for r in category_rows
    ]

    # --- Daily breakdown ---
    for i in range(7):
        day = start_date + timedelta(days=i)
        day_spending = _sum_expenses(user_id, day, day, exclude_type="INCOME")
        day_income = _sum_expenses(user_id, day, day, expense_type="INCOME")
        digest["daily_breakdown"].append({
            "date": day.isoformat(),
            "day_name": day.strftime("%A"),
            "spending": round(day_spending, 2),
            "income": round(day_income, 2),
        })

    # --- Upcoming bills (next 7 days) ---
    next_week = end_date + timedelta(days=7)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active.is_(True),
            Bill.next_due_date >= end_date,
            Bill.next_due_date <= next_week,
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    digest["upcoming_bills"] = [
        {
            "name": b.name,
            "amount": float(b.amount),
            "due_date": b.next_due_date.isoformat(),
            "autopay": b.autopay_enabled,
        }
        for b in bills
    ]

    # --- Smart insights ---
    insights = []

    # Insight: Spending trend
    if spending_change > 15:
        insights.append({
            "type": "warning",
            "title": "Spending increased",
            "message": f"Your spending went up {spending_change:.0f}% compared to last week.",
        })
    elif spending_change < -15:
        insights.append({
            "type": "positive",
            "title": "Great savings week",
            "message": f"You spent {abs(spending_change):.0f}% less than last week. Keep it up!",
        })

    # Insight: Biggest spending day
    if digest["daily_breakdown"]:
        max_day = max(digest["daily_breakdown"], key=lambda d: d["spending"])
        if max_day["spending"] > 0:
            insights.append({
                "type": "info",
                "title": "Biggest spending day",
                "message": f"{max_day['day_name']} was your highest spending day at ${max_day['spending']:.2f}.",
            })

    # Insight: Net positive/negative
    if current_net > 0:
        insights.append({
            "type": "positive",
            "title": "Net positive week",
            "message": f"You earned ${current_net:.2f} more than you spent this week.",
        })
    elif current_net < 0:
        insights.append({
            "type": "warning",
            "title": "Net negative week",
            "message": f"You spent ${abs(current_net):.2f} more than you earned this week.",
        })

    # Insight: Upcoming bills warning
    if digest["upcoming_bills"]:
        total_due = sum(b["amount"] for b in digest["upcoming_bills"])
        non_autopay = [b for b in digest["upcoming_bills"] if not b["autopay"]]
        if non_autopay:
            insights.append({
                "type": "reminder",
                "title": f"{len(non_autopay)} bill(s) due soon",
                "message": f"You have ${total_due:.2f} in bills due in the next 7 days. {len(non_autopay)} require manual payment.",
            })

    # Insight: Top category dominance
    if digest["top_categories"] and digest["top_categories"][0]["share_pct"] > 50:
        top = digest["top_categories"][0]
        insights.append({
            "type": "info",
            "title": f"{top['name']} dominates spending",
            "message": f"{top['name']} accounts for {top['share_pct']}% of your weekly spending.",
        })

    digest["insights"] = insights
    return digest


def send_weekly_digest_email(user_id: int) -> bool:
    """Generate and email the weekly digest to a user."""
    user = db.session.query(User).get(user_id)
    if not user:
        return False

    digest = generate_weekly_digest(user_id)
    summary = digest["summary"]
    period = digest["period"]

    subject = f"FinMind Weekly Digest: {period['start']} to {period['end']}"
    lines = [
        f"Hi! Here's your weekly financial summary ({period['start']} to {period['end']}):",
        "",
        f"💰 Income: ${summary['total_income']:.2f}",
        f"💸 Spending: ${summary['total_spending']:.2f}",
        f"📊 Net flow: ${summary['net_flow']:.2f}",
        f"📝 Transactions: {summary['transaction_count']}",
        "",
    ]

    vs = digest["vs_previous_week"]
    if vs["spending_trend"] != "flat":
        direction = "⬆️" if vs["spending_trend"] == "up" else "⬇️"
        lines.append(f"Spending trend: {direction} {abs(vs['spending_change_pct']):.0f}% vs last week")

    if digest["top_categories"]:
        lines.append("")
        lines.append("Top categories:")
        for cat in digest["top_categories"][:3]:
            lines.append(f"  • {cat['name']}: ${cat['amount']:.2f} ({cat['share_pct']}%)")

    if digest["insights"]:
        lines.append("")
        lines.append("Insights:")
        for ins in digest["insights"]:
            emoji = {"positive": "✅", "warning": "⚠️", "info": "ℹ️", "reminder": "🔔"}.get(ins["type"], "•")
            lines.append(f"  {emoji} {ins['message']}")

    body = "\n".join(lines)
    return send_email(user.email, subject, body)


def _sum_expenses(user_id: int, start: date, end: date,
                  expense_type: str = None, exclude_type: str = None) -> float:
    q = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == user_id,
        Expense.spent_at >= start,
        Expense.spent_at <= end,
    )
    if expense_type:
        q = q.filter(Expense.expense_type == expense_type)
    if exclude_type:
        q = q.filter(Expense.expense_type != exclude_type)
    return float(q.scalar() or 0)


def _count_expenses(user_id: int, start: date, end: date) -> int:
    return (
        db.session.query(func.count(Expense.id))
        .filter(Expense.user_id == user_id, Expense.spent_at >= start, Expense.spent_at <= end)
        .scalar()
    ) or 0


def _pct_change(old: float, new: float) -> float:
    if old == 0:
        return 100.0 if new > 0 else 0.0
    return round(((new - old) / old) * 100, 1)
