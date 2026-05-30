from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import Bill, Category, Expense, User


def weekly_financial_summary(
    user_id: int,
    *,
    week_start: date | None = None,
    currency: str | None = None,
) -> dict:
    start = _week_start(week_start or date.today())
    end = start + timedelta(days=6)
    previous_start = start - timedelta(days=7)
    previous_end = start - timedelta(days=1)

    user = db.session.get(User, user_id)
    response_currency = currency or (user.preferred_currency if user else "INR")

    current_rows = _expense_rows(user_id, start, end, currency)
    previous_rows = _expense_rows(user_id, previous_start, previous_end, currency)
    bills = _upcoming_bills(user_id, start, end, currency)

    summary = _summarize_rows(current_rows)
    previous = _summarize_rows(previous_rows)
    category_breakdown = _category_breakdown(current_rows)
    daily_breakdown = _daily_breakdown(current_rows, start)
    top_expenses = _top_expenses(current_rows)
    comparison = _comparison(summary, previous)

    return {
        "period": {
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "previous_week_start": previous_start.isoformat(),
            "previous_week_end": previous_end.isoformat(),
        },
        "currency": response_currency,
        "summary": summary,
        "comparison": comparison,
        "category_breakdown": category_breakdown,
        "daily_breakdown": daily_breakdown,
        "top_expenses": top_expenses,
        "upcoming_bills": bills,
        "insights": _insights(summary, comparison, category_breakdown, bills),
        "recommendations": _recommendations(
            summary, comparison, category_breakdown, bills
        ),
        "method": "deterministic",
    }


def parse_week_start(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return _week_start(date.fromisoformat(raw.strip()))
    except ValueError as exc:
        raise ValueError("invalid week_start, expected YYYY-MM-DD") from exc


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _expense_rows(
    user_id: int,
    start: date,
    end: date,
    currency: str | None,
) -> list[Expense]:
    query = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .order_by(Expense.spent_at.asc(), Expense.id.asc())
    )
    if currency:
        query = query.filter(Expense.currency == currency)
    return query.all()


def _upcoming_bills(
    user_id: int,
    start: date,
    end: date,
    currency: str | None,
) -> list[dict]:
    query = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active.is_(True),
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
        )
        .order_by(Bill.next_due_date.asc(), Bill.id.asc())
    )
    if currency:
        query = query.filter(Bill.currency == currency)
    return [
        {
            "id": bill.id,
            "name": bill.name,
            "amount": _money(bill.amount),
            "currency": bill.currency,
            "next_due_date": bill.next_due_date.isoformat(),
            "cadence": bill.cadence.value,
        }
        for bill in query.all()
    ]


def _summarize_rows(rows: list[Expense]) -> dict:
    income = sum(
        _as_decimal(row.amount) for row in rows if row.expense_type == "INCOME"
    )
    expenses = sum(
        _as_decimal(row.amount) for row in rows if row.expense_type != "INCOME"
    )
    return {
        "income": _money(income),
        "expenses": _money(expenses),
        "net_flow": _money(income - expenses),
        "transaction_count": len(rows),
        "expense_count": sum(1 for row in rows if row.expense_type != "INCOME"),
        "income_count": sum(1 for row in rows if row.expense_type == "INCOME"),
        "average_daily_expense": _money(expenses / Decimal("7")),
    }


def _comparison(current: dict, previous: dict) -> dict:
    current_expenses = Decimal(str(current["expenses"]))
    previous_expenses = Decimal(str(previous["expenses"]))
    expense_delta = current_expenses - previous_expenses
    return {
        "previous_expenses": _money(previous_expenses),
        "expense_delta": _money(expense_delta),
        "expense_delta_pct": _percent_change(current_expenses, previous_expenses),
        "expense_trend": _trend(expense_delta),
    }


def _category_breakdown(rows: list[Expense]) -> list[dict]:
    category_ids = {row.category_id for row in rows if row.category_id is not None}
    category_names = {}
    if category_ids:
        for category in db.session.query(Category).filter(
            Category.id.in_(category_ids)
        ):
            category_names[category.id] = category.name

    totals: dict[int | None, Decimal] = {}
    for row in rows:
        if row.expense_type == "INCOME":
            continue
        totals[row.category_id] = totals.get(
            row.category_id, Decimal("0")
        ) + _as_decimal(row.amount)
    grand_total = sum(totals.values(), Decimal("0"))
    breakdown = []
    for category_id, amount in sorted(
        totals.items(), key=lambda item: item[1], reverse=True
    ):
        breakdown.append(
            {
                "category_id": category_id,
                "category_name": category_names.get(category_id, "Uncategorized"),
                "amount": _money(amount),
                "share_pct": (
                    round(float((amount / grand_total) * Decimal("100")), 2)
                    if grand_total
                    else 0.0
                ),
            }
        )
    return breakdown


def _daily_breakdown(rows: list[Expense], start: date) -> list[dict]:
    daily = {
        start
        + timedelta(days=offset): {"income": Decimal("0"), "expenses": Decimal("0")}
        for offset in range(7)
    }
    for row in rows:
        bucket = daily[row.spent_at]
        if row.expense_type == "INCOME":
            bucket["income"] += _as_decimal(row.amount)
        else:
            bucket["expenses"] += _as_decimal(row.amount)
    return [
        {
            "date": day.isoformat(),
            "income": _money(values["income"]),
            "expenses": _money(values["expenses"]),
            "net_flow": _money(values["income"] - values["expenses"]),
        }
        for day, values in daily.items()
    ]


def _top_expenses(rows: list[Expense]) -> list[dict]:
    expenses = [row for row in rows if row.expense_type != "INCOME"]
    expenses.sort(key=lambda row: _as_decimal(row.amount), reverse=True)
    return [
        {
            "id": row.id,
            "description": row.notes or "Expense",
            "amount": _money(row.amount),
            "currency": row.currency,
            "date": row.spent_at.isoformat(),
            "category_id": row.category_id,
        }
        for row in expenses[:5]
    ]


def _insights(
    summary: dict,
    comparison: dict,
    category_breakdown: list[dict],
    bills: list[dict],
) -> list[str]:
    insights = []
    if summary["transaction_count"] == 0:
        insights.append("No transactions were recorded for this week.")
    elif comparison["expense_trend"] == "up":
        insights.append(
            "Weekly expenses rose by "
            f"{comparison['expense_delta_pct']}% compared with the previous week."
        )
    elif comparison["expense_trend"] == "down":
        insights.append("Weekly expenses decreased compared with the previous week.")
    else:
        insights.append("Weekly expenses were flat compared with the previous week.")

    if category_breakdown:
        top = category_breakdown[0]
        insights.append(
            f"{top['category_name']} was the largest spending category at "
            f"{top['share_pct']}% of expenses."
        )
    if bills:
        total_due = sum(Decimal(str(bill["amount"])) for bill in bills)
        insights.append(
            f"{len(bills)} bill(s) are due this week totaling {_money(total_due)}."
        )
    return insights


def _recommendations(
    summary: dict,
    comparison: dict,
    category_breakdown: list[dict],
    bills: list[dict],
) -> list[str]:
    recommendations = []
    if summary["net_flow"] < 0:
        recommendations.append(
            "Review discretionary spending before adding new recurring costs."
        )
    if comparison["expense_trend"] == "up" and category_breakdown:
        recommendations.append(
            "Set a temporary cap for "
            f"{category_breakdown[0]['category_name']} next week."
        )
    if bills:
        recommendations.append(
            "Reserve cash for upcoming bills before allocating savings."
        )
    if not recommendations:
        recommendations.append(
            "Keep the current budget rhythm and revisit the digest next week."
        )
    return recommendations


def _percent_change(current: Decimal, previous: Decimal) -> float | None:
    if previous == 0:
        return None if current == 0 else 100.0
    return round(float(((current - previous) / previous) * Decimal("100")), 2)


def _trend(delta: Decimal) -> str:
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _as_decimal(value) -> Decimal:
    return Decimal(str(value or "0"))


def _money(value) -> float:
    return round(float(_as_decimal(value)), 2)
