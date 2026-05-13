from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ..extensions import db
from ..models import Bill, Category, Expense


def _as_float(value: Decimal | int | float | None) -> float:
    return round(float(value or 0), 2)


def _week_bounds(reference: date | None = None) -> tuple[date, date]:
    current = reference or date.today()
    start = current - timedelta(days=current.weekday())
    return start, start + timedelta(days=6)


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None if current else 0.0
    return round(((current - previous) / previous) * 100, 2)


def _trend(current: float, previous: float) -> str:
    if previous == 0 and current > 0:
        return "new"
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "flat"


def _expense_window(
    uid: int,
    start: date,
    end: date,
    currency: str | None = None,
) -> list[Expense]:
    query = db.session.query(Expense).filter(
        Expense.user_id == uid,
        Expense.spent_at >= start,
        Expense.spent_at <= end,
    )
    if currency:
        query = query.filter(Expense.currency == currency)
    return query.order_by(Expense.spent_at.asc(), Expense.id.asc()).all()


def _category_names(uid: int, category_ids: set[int]) -> dict[int, str]:
    if not category_ids:
        return {}
    rows = (
        db.session.query(Category)
        .filter(Category.user_id == uid, Category.id.in_(category_ids))
        .all()
    )
    return {row.id: row.name for row in rows}


def _summarize_expenses(
    uid: int,
    expenses: list[Expense],
    start: date,
    end: date,
) -> dict[str, Any]:
    category_ids = {e.category_id for e in expenses if e.category_id is not None}
    categories = _category_names(uid, category_ids)
    days = {
        (start + timedelta(days=i)).isoformat(): {
            "date": (start + timedelta(days=i)).isoformat(),
            "income": 0.0,
            "expenses": 0.0,
            "net": 0.0,
        }
        for i in range((end - start).days + 1)
    }
    category_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"category_id": None, "category_name": "Uncategorized", "amount": 0.0}
    )
    income_total = 0.0
    expense_total = 0.0
    transactions = 0
    top_expenses: list[dict[str, Any]] = []

    for item in expenses:
        amount = _as_float(item.amount)
        day = days[item.spent_at.isoformat()]
        if item.expense_type == "INCOME":
            income_total += amount
            day["income"] = round(day["income"] + amount, 2)
        else:
            expense_total += amount
            day["expenses"] = round(day["expenses"] + amount, 2)
            key = str(item.category_id or "uncategorized")
            category_totals[key]["category_id"] = item.category_id
            category_totals[key]["category_name"] = (
                categories.get(item.category_id, "Uncategorized")
                if item.category_id
                else "Uncategorized"
            )
            category_totals[key]["amount"] = round(
                category_totals[key]["amount"] + amount, 2
            )
            top_expenses.append(
                {
                    "id": item.id,
                    "description": item.notes or "",
                    "amount": amount,
                    "currency": item.currency,
                    "date": item.spent_at.isoformat(),
                    "category_id": item.category_id,
                    "category_name": category_totals[key]["category_name"],
                }
            )
        day["net"] = round(day["income"] - day["expenses"], 2)
        transactions += 1

    breakdown = sorted(
        category_totals.values(), key=lambda row: row["amount"], reverse=True
    )
    for row in breakdown:
        row["share_pct"] = (
            round((row["amount"] / expense_total) * 100, 2) if expense_total else 0.0
        )

    return {
        "income": round(income_total, 2),
        "expenses": round(expense_total, 2),
        "net": round(income_total - expense_total, 2),
        "transaction_count": transactions,
        "daily": list(days.values()),
        "category_breakdown": breakdown,
        "top_expenses": sorted(
            top_expenses, key=lambda row: row["amount"], reverse=True
        )[:5],
    }


def _upcoming_bills(
    uid: int,
    start: date,
    end: date,
    currency: str | None = None,
) -> list[dict[str, Any]]:
    query = db.session.query(Bill).filter(
        Bill.user_id == uid,
        Bill.active.is_(True),
        Bill.next_due_date >= start,
        Bill.next_due_date <= end,
    )
    if currency:
        query = query.filter(Bill.currency == currency)
    bills = query.order_by(Bill.next_due_date.asc(), Bill.id.asc()).all()
    return [
        {
            "id": bill.id,
            "name": bill.name,
            "amount": _as_float(bill.amount),
            "currency": bill.currency,
            "next_due_date": bill.next_due_date.isoformat(),
            "cadence": (
                bill.cadence.value if hasattr(bill.cadence, "value") else bill.cadence
            ),
            "autopay_enabled": bill.autopay_enabled,
        }
        for bill in bills
    ]


def _build_insights(
    current: dict[str, Any],
    previous: dict[str, Any],
    upcoming_bills: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    insights: list[str] = []
    recommendations: list[str] = []

    expense_delta = _pct_change(current["expenses"], previous["expenses"])
    if expense_delta is None and current["expenses"]:
        insights.append("This is the first week with tracked expenses in this view.")
    elif expense_delta is not None:
        if expense_delta > 10:
            insights.append(f"Expenses rose {expense_delta:.2f}% versus last week.")
            recommendations.append(
                "Review the categories with the largest weekly increase."
            )
        elif expense_delta < -10:
            insights.append(
                f"Expenses fell {abs(expense_delta):.2f}% versus last week."
            )
            recommendations.append(
                "Keep the constraints that reduced spending this week."
            )
        else:
            insights.append("Expenses stayed within 10% of last week.")

    if current["net"] >= 0:
        insights.append("Net flow is positive for the selected week.")
    else:
        insights.append("Net flow is negative for the selected week.")
        recommendations.append("Delay non-essential purchases until income catches up.")

    if current["category_breakdown"]:
        top = current["category_breakdown"][0]
        insights.append(
            f"{top['category_name']} is the top spending category at {top['share_pct']:.2f}%."
        )
        if top["share_pct"] >= 40:
            recommendations.append(
                f"Set a tighter weekly cap for {top['category_name']} before next week starts."
            )

    if upcoming_bills:
        total_due = round(sum(bill["amount"] for bill in upcoming_bills), 2)
        insights.append(
            f"{len(upcoming_bills)} bills are due this week totaling {total_due:.2f}."
        )
        recommendations.append("Reserve bill cash before discretionary spend.")

    if not insights:
        insights.append("No weekly activity found for this period.")
        recommendations.append(
            "Add expenses or income to generate a useful weekly digest."
        )

    return insights, recommendations


def weekly_financial_digest(
    uid: int,
    reference_date: date | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    week_start, week_end = _week_bounds(reference_date)
    previous_start = week_start - timedelta(days=7)
    previous_end = week_end - timedelta(days=7)
    currency_filter = (currency or "").strip().upper() or None

    current = _summarize_expenses(
        uid,
        _expense_window(uid, week_start, week_end, currency_filter),
        week_start,
        week_end,
    )
    previous = _summarize_expenses(
        uid,
        _expense_window(uid, previous_start, previous_end, currency_filter),
        previous_start,
        previous_end,
    )
    upcoming = _upcoming_bills(uid, week_start, week_end, currency_filter)
    insights, recommendations = _build_insights(current, previous, upcoming)

    return {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "previous_week_start": previous_start.isoformat(),
            "previous_week_end": previous_end.isoformat(),
        },
        "currency": currency_filter,
        "summary": {
            "income": current["income"],
            "expenses": current["expenses"],
            "net": current["net"],
            "transaction_count": current["transaction_count"],
            "previous_expenses": previous["expenses"],
            "expense_change_pct": _pct_change(
                current["expenses"], previous["expenses"]
            ),
            "expense_trend": _trend(current["expenses"], previous["expenses"]),
        },
        "daily": current["daily"],
        "category_breakdown": current["category_breakdown"],
        "top_expenses": current["top_expenses"],
        "upcoming_bills": upcoming,
        "insights": insights,
        "recommendations": recommendations,
        "method": "deterministic",
    }
