from datetime import date, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import Category, Expense


def _week_start(value: date | None = None) -> date:
    anchor = value or date.today()
    return anchor - timedelta(days=anchor.weekday())


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


def _totals(uid: int, start: date, end: date) -> dict[str, float]:
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
    income_value = round(float(income or 0), 2)
    expense_value = round(float(expenses or 0), 2)
    return {
        "income": income_value,
        "expenses": expense_value,
        "net_flow": round(income_value - expense_value, 2),
    }


def _category_totals(uid: int, start: date, end: date) -> list[dict]:
    rows = (
        db.session.query(
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
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .limit(5)
        .all()
    )
    total = sum(float(row.amount or 0) for row in rows)
    return [
        {
            "category_name": row.category_name,
            "amount": round(float(row.amount or 0), 2),
            "share_pct": (
                round((float(row.amount or 0) / total) * 100, 2) if total > 0 else 0
            ),
        }
        for row in rows
    ]


def _insights(
    *,
    totals: dict[str, float],
    previous_totals: dict[str, float],
    top_categories: list[dict],
) -> list[str]:
    items: list[str] = []
    change = _pct_change(totals["expenses"], previous_totals["expenses"])
    if totals["net_flow"] >= 0:
        items.append(
            f"Positive weekly cash flow of {totals['net_flow']:.2f}; "
            "keep the surplus assigned."
        )
    else:
        items.append(
            f"Negative weekly cash flow of {abs(totals['net_flow']):.2f}; "
            "review upcoming discretionary spend."
        )
    if change > 0:
        items.append(f"Spending increased {change:.2f}% compared with the prior week.")
    elif change < 0:
        items.append(
            f"Spending decreased {abs(change):.2f}% compared with the prior week."
        )
    else:
        items.append("Spending was flat compared with the prior week.")
    if top_categories:
        top = top_categories[0]
        items.append(
            f"{top['category_name']} was the largest category at "
            f"{top['share_pct']:.2f}% of spend."
        )
    return items


def _actions(totals: dict[str, float], top_categories: list[dict]) -> list[str]:
    actions = []
    if totals["net_flow"] > 0:
        actions.append("Move part of this week's surplus into savings or debt payoff.")
    else:
        actions.append(
            "Pause one non-essential purchase next week to restore positive cash flow."
        )
    if top_categories:
        actions.append(
            f"Set a specific cap for {top_categories[0]['category_name']} "
            "before the next week starts."
        )
    actions.append(
        "Review recurring bills due in the next 7 days before adding new commitments."
    )
    return actions


def weekly_financial_digest(uid: int, week_start: date | None = None) -> dict:
    start = _week_start(week_start)
    end = start + timedelta(days=6)
    previous_start = start - timedelta(days=7)
    previous_end = start - timedelta(days=1)
    totals = _totals(uid, start, end)
    previous_totals = _totals(uid, previous_start, previous_end)
    top_categories = _category_totals(uid, start, end)
    return {
        "period": {
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "previous_week_start": previous_start.isoformat(),
            "previous_week_end": previous_end.isoformat(),
        },
        "summary": {
            **totals,
            "previous_week_expenses": previous_totals["expenses"],
            "spending_change_pct": _pct_change(
                totals["expenses"], previous_totals["expenses"]
            ),
        },
        "top_categories": top_categories,
        "insights": _insights(
            totals=totals,
            previous_totals=previous_totals,
            top_categories=top_categories,
        ),
        "recommended_actions": _actions(totals, top_categories),
        "method": "heuristic",
    }
