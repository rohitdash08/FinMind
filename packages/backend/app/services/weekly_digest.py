from datetime import date, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import Bill, Category, Expense


def build_weekly_digest(uid: int, end_date: date | None = None) -> dict:
    period_end = end_date or date.today()
    period_start = period_end - timedelta(days=6)
    previous_end = period_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)

    current = _period_totals(uid, period_start, period_end)
    previous = _period_totals(uid, previous_start, previous_end)
    top_categories = _top_categories(uid, period_start, period_end)
    largest_transactions = _largest_transactions(uid, period_start, period_end)
    upcoming_bills = _upcoming_bills(
        uid, period_end + timedelta(days=1), period_end + timedelta(days=7)
    )

    digest = {
        "period": {
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "days": 7,
        },
        "summary": {
            **current,
            "net_flow": round(current["income"] - current["expenses"], 2),
            "transaction_count": current["transaction_count"],
        },
        "comparison": _build_comparison(current, previous),
        "top_categories": top_categories,
        "largest_transactions": largest_transactions,
        "upcoming_bills": upcoming_bills,
        "insights": _build_insights(current, previous, top_categories, upcoming_bills),
    }
    return digest


def _period_totals(uid: int, start: date, end: date) -> dict:
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
    count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar()
    )
    return {
        "income": round(float(income or 0), 2),
        "expenses": round(float(expenses or 0), 2),
        "transaction_count": int(count or 0),
    }


def _top_categories(uid: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("amount"),
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
        .limit(3)
        .all()
    )
    return [
        {
            "category_id": row.category_id,
            "category_name": row.category_name,
            "amount": round(float(row.amount or 0), 2),
        }
        for row in rows
    ]


def _largest_transactions(uid: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .order_by(Expense.amount.desc(), Expense.spent_at.desc())
        .limit(5)
        .all()
    )
    return [
        {
            "id": row.id,
            "description": row.notes or "Transaction",
            "amount": round(float(row.amount), 2),
            "currency": row.currency,
            "date": row.spent_at.isoformat(),
            "type": row.expense_type,
            "category_id": row.category_id,
        }
        for row in rows
    ]


def _upcoming_bills(uid: int, start: date, end: date) -> list[dict]:
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
            "id": bill.id,
            "name": bill.name,
            "amount": round(float(bill.amount), 2),
            "currency": bill.currency,
            "next_due_date": bill.next_due_date.isoformat(),
        }
        for bill in bills
    ]


def _build_comparison(current: dict, previous: dict) -> dict:
    return {
        "previous_expenses": previous["expenses"],
        "expense_change": round(current["expenses"] - previous["expenses"], 2),
        "expense_change_pct": _percent_change(
            current["expenses"], previous["expenses"]
        ),
        "previous_income": previous["income"],
        "income_change": round(current["income"] - previous["income"], 2),
        "income_change_pct": _percent_change(current["income"], previous["income"]),
    }


def _percent_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


def _build_insights(
    current: dict,
    previous: dict,
    top_categories: list[dict],
    upcoming_bills: list[dict],
) -> list[str]:
    insights: list[str] = []
    expense_delta = current["expenses"] - previous["expenses"]
    if previous["expenses"] > 0:
        direction = "up" if expense_delta > 0 else "down"
        change_pct = abs(_percent_change(current["expenses"], previous["expenses"]))
        insights.append(
            f"Spending is {direction} {change_pct}% versus the previous week."
        )
    elif current["expenses"] > 0:
        insights.append(
            "This is the first week with recorded spending in the comparison window."
        )
    else:
        insights.append("No spending was recorded this week.")

    if top_categories:
        top = top_categories[0]
        insights.append(
            f"Top spending category is {top['category_name']} at {top['amount']:.2f}."
        )

    if upcoming_bills:
        total_due = sum(item["amount"] for item in upcoming_bills)
        insights.append(
            f"{len(upcoming_bills)} bill(s) due next week totaling {total_due:.2f}."
        )

    if current["income"] < current["expenses"]:
        insights.append(
            "Weekly expenses are higher than income; review discretionary spend."
        )
    else:
        insights.append("Weekly income covers recorded expenses.")

    return insights
