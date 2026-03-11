from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Expense, Bill


def get_weekly_expense_summary(db: Session, user_id: int, week_offset: int = 0):
    """
    Aggregate expenses for a given week (default: current week).
    week_offset=0 means the most recent completed 7-day window.
    """
    now = datetime.utcnow()
    end_date = now - timedelta(weeks=week_offset)
    start_date = end_date - timedelta(days=7)

    expenses = (
        db.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.date >= start_date,
            Expense.date < end_date,
        )
        .all()
    )

    total_spent = sum(e.amount for e in expenses)
    by_category = defaultdict(float)
    for e in expenses:
        by_category[e.category] += e.amount

    top_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:3]

    return {
        "period_start": start_date.date().isoformat(),
        "period_end": end_date.date().isoformat(),
        "total_spent": round(total_spent, 2),
        "transaction_count": len(expenses),
        "by_category": {k: round(v, 2) for k, v in by_category.items()},
        "top_categories": [{"category": k, "amount": round(v, 2)} for k, v in top_categories],
    }


def get_weekly_bill_summary(db: Session, user_id: int, week_offset: int = 0):
    """
    Summarise bills due within the target week.
    """
    now = datetime.utcnow()
    end_date = now - timedelta(weeks=week_offset)
    start_date = end_date - timedelta(days=7)

    bills = (
        db.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.due_date >= start_date,
            Bill.due_date < end_date,
        )
        .all()
    )

    total_due = sum(b.amount for b in bills)
    paid = [b for b in bills if b.is_paid]
    unpaid = [b for b in bills if not b.is_paid]

    return {
        "total_bills": len(bills),
        "total_due": round(total_due, 2),
        "paid_count": len(paid),
        "unpaid_count": len(unpaid),
        "unpaid_amount": round(sum(b.amount for b in unpaid), 2),
    }


def generate_insights(expense_summary: dict, bill_summary: dict, previous_expense_summary: Optional[dict] = None) -> list:
    """
    Derive human-readable insight strings from aggregated data.
    """
    insights = []

    if expense_summary["transaction_count"] == 0:
        insights.append("No expenses recorded this week — great job keeping spending in check!")
    else:
        insights.append(
            f"You spent ${expense_summary['total_spent']:.2f} across "
            f"{expense_summary['transaction_count']} transaction(s) this week."
        )

    if expense_summary["top_categories"]:
        top = expense_summary["top_categories"][0]
        insights.append(
            f"Your highest spending category was '{top['category']}' at ${top['amount']:.2f}."
        )

    if previous_expense_summary is not None:
        prev_total = previous_expense_summary.get("total_spent", 0)
        curr_total = expense_summary["total_spent"]
        if prev_total > 0:
            change_pct = ((curr_total - prev_total) / prev_total) * 100
            direction = "up" if change_pct >= 0 else "down"
            insights.append(
                f"Spending is {direction} {abs(change_pct):.1f}% compared to last week "
                f"(${prev_total:.2f} → ${curr_total:.2f})."
            )

    if bill_summary["unpaid_count"] > 0:
        insights.append(
            f"You have {bill_summary['unpaid_count']} unpaid bill(s) totalling "
            f"${bill_summary['unpaid_amount']:.2f} from this period."
        )
    elif bill_summary["total_bills"] > 0:
        insights.append("All bills for this period have been paid. Well done!")

    return insights


def build_weekly_digest(db: Session, user_id: int):
    """
    Build a complete weekly financial digest for a user.
    Returns a structured dict ready for API serialisation or email delivery.
    """
    current = get_weekly_expense_summary(db, user_id, week_offset=0)
    previous = get_weekly_expense_summary(db, user_id, week_offset=1)
    bills = get_weekly_bill_summary(db, user_id, week_offset=0)
    insights = generate_insights(current, bills, previous_expense_summary=previous)

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "expense_summary": current,
        "previous_week_expense_summary": previous,
        "bill_summary": bills,
        "insights": insights,
    }
