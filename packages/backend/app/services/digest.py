"""Weekly financial digest generator.

Analyses the past 7 days of user activity and produces a structured
summary highlighting:
- Total income & expenses vs prior week (with % change)
- Top spending categories
- Largest individual transactions
- Upcoming bills in the next 7 days
- Week-over-week trend insights
- Actionable savings tips
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from sqlalchemy import extract, func
import logging

from ..extensions import db
from ..models import Bill, Category, Expense

logger = logging.getLogger("finmind.digest")


def _week_range(anchor: date | None = None):
    """Return (start, end) for the 7 days ending on *anchor* (inclusive)."""
    end = anchor or date.today()
    start = end - timedelta(days=6)
    return start, end


def _prev_week_range(anchor: date | None = None):
    end = (anchor or date.today()) - timedelta(days=7)
    start = end - timedelta(days=6)
    return start, end


def _pct_change(current, previous):
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)


def _money(val):
    return round(float(val or 0), 2)


# ------------------------------------------------------------------
# Core digest builder
# ------------------------------------------------------------------

def generate_weekly_digest(user_id: int, anchor: date | None = None):
    """Build a full weekly digest dict for *user_id*.

    Parameters
    ----------
    anchor : date, optional
        The last day of the reporting week.  Defaults to today.
    """
    start, end = _week_range(anchor)
    prev_start, prev_end = _prev_week_range(anchor)

    digest = {
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "summary": _build_summary(user_id, start, end, prev_start, prev_end),
        "top_categories": _top_categories(user_id, start, end),
        "largest_transactions": _largest_transactions(user_id, start, end),
        "upcoming_bills": _upcoming_bills(user_id, end),
        "insights": [],
        "generated_at": datetime.utcnow().isoformat(),
    }

    digest["insights"] = _derive_insights(digest)
    return digest


# ------------------------------------------------------------------
# Section builders
# ------------------------------------------------------------------

def _build_summary(user_id, start, end, prev_start, prev_end):
    income = _amount_by_type(user_id, start, end, is_income=True)
    expenses = _amount_by_type(user_id, start, end, is_income=False)
    prev_income = _amount_by_type(user_id, prev_start, prev_end, is_income=True)
    prev_expenses = _amount_by_type(user_id, prev_start, prev_end, is_income=False)
    tx_count = _transaction_count(user_id, start, end)
    prev_tx_count = _transaction_count(user_id, prev_start, prev_end)

    return {
        "total_income": _money(income),
        "total_expenses": _money(expenses),
        "net_savings": _money(income - expenses),
        "transaction_count": tx_count,
        "previous_week": {
            "total_income": _money(prev_income),
            "total_expenses": _money(prev_expenses),
            "net_savings": _money(prev_income - prev_expenses),
            "transaction_count": prev_tx_count,
        },
        "change": {
            "income_pct": _pct_change(income, prev_income),
            "expenses_pct": _pct_change(expenses, prev_expenses),
            "savings_pct": _pct_change(income - expenses,
                                        prev_income - prev_expenses),
            "transaction_count_pct": _pct_change(tx_count, prev_tx_count),
        },
    }


def _amount_by_type(user_id, start, end, *, is_income):
    cond = Expense.expense_type == "INCOME" if is_income else Expense.expense_type != "INCOME"
    val = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.user_id == user_id, Expense.spent_at >= start,
                Expense.spent_at <= end, cond)
        .scalar()
    )
    return float(val or 0)


def _transaction_count(user_id, start, end):
    return (
        db.session.query(func.count(Expense.id))
        .filter(Expense.user_id == user_id, Expense.spent_at >= start,
                Expense.spent_at <= end)
        .scalar()
    ) or 0


def _top_categories(user_id, start, end, limit=5):
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("name"),
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .outerjoin(Category,
                   (Category.id == Expense.category_id) & (Category.user_id == user_id))
        .filter(Expense.user_id == user_id, Expense.spent_at >= start,
                Expense.spent_at <= end, Expense.expense_type != "INCOME")
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .limit(limit)
        .all()
    )
    grand = sum(float(r.total or 0) for r in rows)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.name,
            "amount": _money(r.total),
            "transaction_count": r.count,
            "share_pct": round(float(r.total or 0) / grand * 100, 1) if grand else 0,
        }
        for r in rows
    ]


def _largest_transactions(user_id, start, end, limit=5):
    rows = (
        db.session.query(Expense)
        .filter(Expense.user_id == user_id, Expense.spent_at >= start,
                Expense.spent_at <= end)
        .order_by(Expense.amount.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "amount": _money(e.amount),
            "type": e.expense_type,
            "notes": e.notes or "Transaction",
            "date": e.spent_at.isoformat(),
            "currency": e.currency,
        }
        for e in rows
    ]


def _upcoming_bills(user_id, ref_date, days=7):
    deadline = ref_date + timedelta(days=days)
    bills = (
        db.session.query(Bill)
        .filter(Bill.user_id == user_id, Bill.active.is_(True),
                Bill.next_due_date >= ref_date,
                Bill.next_due_date <= deadline)
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": _money(b.amount),
            "currency": b.currency,
            "due_date": b.next_due_date.isoformat(),
            "autopay": b.autopay_enabled,
        }
        for b in bills
    ]


# ------------------------------------------------------------------
# Insight engine
# ------------------------------------------------------------------

def _derive_insights(digest):
    """Generate human-readable insights from the computed digest."""
    insights = []
    summary = digest["summary"]
    change = summary["change"]

    # Spending trend
    if change["expenses_pct"] > 20:
        insights.append({
            "type": "warning",
            "title": "Spending Spike",
            "message": (
                f"Your expenses increased {change['expenses_pct']}% "
                f"compared to last week. Review your top spending "
                f"categories to identify areas to cut back."
            ),
        })
    elif change["expenses_pct"] < -10:
        insights.append({
            "type": "positive",
            "title": "Great Savings Week",
            "message": (
                f"You spent {abs(change['expenses_pct'])}% less than last "
                f"week. Keep up the good financial discipline!"
            ),
        })

    # Net savings
    if summary["net_savings"] > 0:
        insights.append({
            "type": "positive",
            "title": "Positive Cash Flow",
            "message": (
                f"You saved {summary['net_savings']:.2f} this week. "
                f"Consider moving surplus funds to a savings goal."
            ),
        })
    elif summary["net_savings"] < 0:
        insights.append({
            "type": "warning",
            "title": "Negative Cash Flow",
            "message": (
                f"You spent {abs(summary['net_savings']):.2f} more than "
                f"you earned this week. Check for non-essential expenses."
            ),
        })

    # Top category dominance
    cats = digest["top_categories"]
    if cats and cats[0]["share_pct"] > 50:
        insights.append({
            "type": "info",
            "title": "Category Dominance",
            "message": (
                f'"{cats[0]["category_name"]}" accounts for '
                f'{cats[0]["share_pct"]}% of your weekly spending. '
                f"Diversifying expenses may reveal savings opportunities."
            ),
        })

    # Upcoming bills reminder
    bills = digest["upcoming_bills"]
    if bills:
        total = sum(b["amount"] for b in bills)
        insights.append({
            "type": "info",
            "title": "Bills Due Soon",
            "message": (
                f"You have {len(bills)} bill(s) due in the next 7 days "
                f"totalling {total:.2f}. Make sure your accounts are funded."
            ),
        })

    # No activity
    if summary["transaction_count"] == 0:
        insights.append({
            "type": "info",
            "title": "No Activity",
            "message": (
                "No transactions recorded this week. If you made purchases, "
                "remember to log them for accurate tracking."
            ),
        })

    return insights
