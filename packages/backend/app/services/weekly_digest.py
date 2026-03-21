from datetime import date, timedelta
from sqlalchemy import func, extract
from ..extensions import db
from ..models import Expense, Category, Bill
from ..services.cache import cache_get, cache_set
from ..services.reminders import send_email
import logging

logger = logging.getLogger("finmind.weekly_digest")

DIGEST_CACHE_TTL = 1800  # 30 minutes


def generate_weekly_digest(user_id: int, ref_date: date | None = None) -> dict:
    today = ref_date or date.today()
    week_end = today
    week_start = today - timedelta(days=6)
    prev_week_end = week_start - timedelta(days=1)
    prev_week_start = prev_week_end - timedelta(days=6)

    cache_key = f"user:{user_id}:weekly_digest:{week_start.isoformat()}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Current week expenses
    current_expenses = _get_expenses_in_range(user_id, week_start, week_end)
    current_total = sum(float(e.amount) for e in current_expenses if e.expense_type != "INCOME")
    current_income = sum(float(e.amount) for e in current_expenses if e.expense_type == "INCOME")

    # Previous week expenses
    prev_expenses = _get_expenses_in_range(user_id, prev_week_start, prev_week_end)
    prev_total = sum(float(e.amount) for e in prev_expenses if e.expense_type != "INCOME")
    prev_income = sum(float(e.amount) for e in prev_expenses if e.expense_type == "INCOME")

    # Week-over-week change
    if prev_total > 0:
        wow_change_pct = round(((current_total - prev_total) / prev_total) * 100, 1)
    else:
        wow_change_pct = 0.0 if current_total == 0 else 100.0

    # Category breakdown for current week
    category_breakdown = _get_category_breakdown(user_id, week_start, week_end)

    # Top categories
    top_categories = sorted(category_breakdown, key=lambda c: c["amount"], reverse=True)[:5]

    # Daily spending for current week
    daily_spending = _get_daily_spending(user_id, week_start, week_end)

    # Spending trend (up/down/stable)
    if wow_change_pct > 5:
        trend = "up"
    elif wow_change_pct < -5:
        trend = "down"
    else:
        trend = "stable"

    # Upcoming bills in next 7 days
    upcoming_bills = _get_upcoming_bills(user_id, today, today + timedelta(days=7))

    # Insights
    insights = _generate_insights(
        current_total, prev_total, wow_change_pct, trend, top_categories, current_income
    )

    digest = {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "prev_week_start": prev_week_start.isoformat(),
            "prev_week_end": prev_week_end.isoformat(),
        },
        "summary": {
            "total_expenses": round(current_total, 2),
            "total_income": round(current_income, 2),
            "net_flow": round(current_income - current_total, 2),
            "prev_week_expenses": round(prev_total, 2),
            "prev_week_income": round(prev_income, 2),
            "wow_change_pct": wow_change_pct,
            "trend": trend,
            "transaction_count": len(current_expenses),
        },
        "category_breakdown": category_breakdown,
        "top_categories": top_categories,
        "daily_spending": daily_spending,
        "upcoming_bills": upcoming_bills,
        "insights": insights,
    }

    cache_set(cache_key, digest, ttl_seconds=DIGEST_CACHE_TTL)
    return digest


def send_weekly_digest_email(user_id: int, to_email: str, ref_date: date | None = None) -> bool:
    digest = generate_weekly_digest(user_id, ref_date)
    summary = digest["summary"]
    period = digest["period"]

    subject = f"FinMind Weekly Digest: {period['week_start']} to {period['week_end']}"

    body_lines = [
        f"Your Weekly Financial Summary ({period['week_start']} to {period['week_end']})",
        "",
        f"Total Expenses: ${summary['total_expenses']:.2f}",
        f"Total Income: ${summary['total_income']:.2f}",
        f"Net Flow: ${summary['net_flow']:.2f}",
        f"Week-over-Week Change: {summary['wow_change_pct']:+.1f}%",
        f"Trend: {summary['trend'].capitalize()}",
        f"Transactions: {summary['transaction_count']}",
        "",
        "Top Categories:",
    ]

    for cat in digest["top_categories"]:
        body_lines.append(f"  - {cat['category_name']}: ${cat['amount']:.2f} ({cat['share_pct']:.1f}%)")

    if digest["upcoming_bills"]:
        body_lines.append("")
        body_lines.append("Upcoming Bills (next 7 days):")
        for bill in digest["upcoming_bills"]:
            body_lines.append(f"  - {bill['name']}: ${bill['amount']:.2f} (due {bill['next_due_date']})")

    if digest["insights"]:
        body_lines.append("")
        body_lines.append("Insights:")
        for insight in digest["insights"]:
            body_lines.append(f"  - {insight}")

    body = "\n".join(body_lines)
    result = send_email(to_email, subject, body)
    logger.info("Weekly digest email sent=%s user=%s", result, user_id)
    return result


def _get_expenses_in_range(user_id: int, start: date, end: date) -> list:
    return (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .all()
    )


def _get_category_breakdown(user_id: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
            func.count(Expense.id).label("count"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == user_id),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    total = sum(float(r.total_amount or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": round(float(r.total_amount or 0), 2),
            "count": r.count,
            "share_pct": round((float(r.total_amount or 0) / total) * 100, 1) if total > 0 else 0,
        }
        for r in rows
    ]


def _get_daily_spending(user_id: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at)
        .all()
    )
    spent_map = {r.spent_at: float(r.total) for r in rows}
    result = []
    current = start
    while current <= end:
        result.append({
            "date": current.isoformat(),
            "amount": round(spent_map.get(current, 0), 2),
        })
        current += timedelta(days=1)
    return result


def _get_upcoming_bills(user_id: int, start: date, end: date) -> list[dict]:
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
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
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
        }
        for b in bills
    ]


def _generate_insights(
    current_total: float,
    prev_total: float,
    wow_pct: float,
    trend: str,
    top_categories: list[dict],
    current_income: float,
) -> list[str]:
    insights = []

    if trend == "up" and abs(wow_pct) > 10:
        insights.append(
            f"Your spending increased by {wow_pct:.1f}% compared to last week. "
            "Consider reviewing your expenses."
        )
    elif trend == "down":
        insights.append(
            f"Great job! You reduced spending by {abs(wow_pct):.1f}% compared to last week."
        )
    elif trend == "stable":
        insights.append("Your spending is consistent with last week.")

    if current_income > 0 and current_total > current_income:
        insights.append(
            f"You spent ${current_total - current_income:.2f} more than you earned this week."
        )
    elif current_income > 0 and current_total < current_income:
        savings = current_income - current_total
        insights.append(f"You saved ${savings:.2f} this week. Keep it up!")

    if top_categories:
        top = top_categories[0]
        if top["share_pct"] > 50:
            insights.append(
                f"{top['category_name']} accounts for {top['share_pct']:.0f}% of your spending. "
                "Consider diversifying or reducing this category."
            )

    return insights
