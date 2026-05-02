from collections import defaultdict
from datetime import date, timedelta

from ..extensions import db
from ..models import Bill, Category, Expense, User


def build_weekly_digest(
    user_id: int,
    anchor_date: date | None = None,
    currency: str | None = None,
):
    """Build a deterministic weekly financial summary for one user.

    The digest covers the Monday-Sunday week containing ``anchor_date`` and only
    includes records owned by ``user_id``. Amounts are returned as floats rounded
    to two decimals so API clients receive stable JSON values.
    """
    anchor = anchor_date or date.today()
    start_date = anchor - timedelta(days=anchor.weekday())
    end_date = start_date + timedelta(days=6)
    user = db.session.get(User, user_id)
    selected_currency = (
        currency or (user.preferred_currency if user else None) or "INR"
    ).upper()

    current = _summarize_expenses(user_id, selected_currency, start_date, end_date)
    previous_start_date = start_date - timedelta(days=7)
    previous_end_date = start_date - timedelta(days=1)
    previous = _summarize_expenses(
        user_id, selected_currency, previous_start_date, previous_end_date
    )

    category_breakdown = [
        {
            "category": category,
            "amount": _money(amount),
            "transaction_count": current["category_counts"][category],
        }
        for category, amount in sorted(
            current["category_amounts"].items(), key=lambda item: (-item[1], item[0])
        )
    ]
    category_trends = _build_category_trends(
        current["category_amounts"], previous["category_amounts"]
    )
    top_expenses = sorted(
        current["top_expense_rows"],
        key=lambda item: (-item["amount"], item["date"], item["id"]),
    )[:5]

    upcoming_bills = [
        {
            "id": bill.id,
            "name": bill.name,
            "amount": _money(bill.amount),
            "currency": bill.currency,
            "due_date": bill.next_due_date.isoformat(),
            "cadence": bill.cadence.value,
        }
        for bill in db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active.is_(True),
            Bill.currency == selected_currency,
            Bill.next_due_date >= start_date,
            Bill.next_due_date <= end_date,
        )
        .order_by(Bill.next_due_date.asc(), Bill.id.asc())
        .all()
    ]

    net_cash_flow = _money(current["income_total"] - current["expense_total"])
    expense_delta = _money(current["expense_total"] - previous["expense_total"])
    expense_percent_change = _percent_change(
        current["expense_total"], previous["expense_total"]
    )
    return {
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "comparison": {
            "previous_period": {
                "start_date": previous_start_date.isoformat(),
                "end_date": previous_end_date.isoformat(),
            },
            "previous_expenses": _money(previous["expense_total"]),
            "expense_delta": expense_delta,
            "expense_percent_change": expense_percent_change,
        },
        "currency": selected_currency,
        "totals": {
            "income": _money(current["income_total"]),
            "expenses": _money(current["expense_total"]),
            "net_cash_flow": net_cash_flow,
            "transaction_count": current["transaction_count"],
        },
        "category_breakdown": category_breakdown,
        "category_trends": category_trends,
        "top_expenses": top_expenses,
        "upcoming_bills": upcoming_bills,
        "highlights": _build_highlights(
            selected_currency, net_cash_flow, category_breakdown, upcoming_bills
        ),
    }


def _summarize_expenses(user_id: int, currency: str, start_date: date, end_date: date):
    expenses = (
        db.session.query(Expense, Category.name)
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == user_id,
            Expense.currency == currency,
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
        )
        .order_by(Expense.spent_at.asc(), Expense.id.asc())
        .all()
    )

    income_total = 0.0
    expense_total = 0.0
    transaction_count = 0
    category_amounts: dict[str, float] = defaultdict(float)
    category_counts: dict[str, int] = defaultdict(int)
    top_expense_rows = []

    for expense, category_name in expenses:
        amount = _money(expense.amount)
        expense_type = (expense.expense_type or "EXPENSE").upper()
        transaction_count += 1
        if expense_type == "INCOME":
            income_total += amount
            continue

        expense_total += amount
        category = category_name or "Uncategorized"
        category_amounts[category] += amount
        category_counts[category] += 1
        top_expense_rows.append(
            {
                "id": expense.id,
                "description": expense.notes or "",
                "amount": amount,
                "currency": expense.currency,
                "category": category,
                "date": expense.spent_at.isoformat(),
            }
        )

    return {
        "income_total": income_total,
        "expense_total": expense_total,
        "transaction_count": transaction_count,
        "category_amounts": category_amounts,
        "category_counts": category_counts,
        "top_expense_rows": top_expense_rows,
    }


def _build_category_trends(current_amounts, previous_amounts):
    trends = []
    categories = sorted(set(current_amounts) | set(previous_amounts))
    for category in categories:
        current = _money(current_amounts.get(category, 0.0))
        previous = _money(previous_amounts.get(category, 0.0))
        delta = _money(current - previous)
        if delta > 0:
            direction = "up"
        elif delta < 0:
            direction = "down"
        else:
            direction = "flat"
        trends.append(
            {
                "category": category,
                "current_amount": current,
                "previous_amount": previous,
                "delta": delta,
                "percent_change": _percent_change(current, previous),
                "trend": direction,
            }
        )
    return sorted(trends, key=lambda item: (-abs(item["delta"]), item["category"]))


def _percent_change(current: float, previous: float) -> float | None:
    if previous == 0:
        if current == 0:
            return 0.0
        return None
    return _money(((current - previous) / previous) * 100)


def _build_highlights(
    currency: str,
    net_cash_flow: float,
    category_breakdown,
    upcoming_bills,
):
    direction = "positive" if net_cash_flow >= 0 else "negative"
    highlights = [
        f"You ended the week {direction} by {currency} {abs(net_cash_flow):.2f}."
    ]
    if category_breakdown:
        top_category = category_breakdown[0]
        highlights.append(
            f"{top_category['category']} was your highest spending category at "
            f"{currency} {top_category['amount']:.2f}."
        )
    else:
        highlights.append("No expenses were recorded for this week.")
    if upcoming_bills:
        highlights.append(f"{len(upcoming_bills)} bill(s) are due during this week.")
    return highlights


def _money(value) -> float:
    return round(float(value or 0), 2)
