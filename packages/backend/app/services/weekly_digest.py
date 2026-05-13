from datetime import date, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import Bill, Category, Expense, User


def build_weekly_summary(
    user_id: int,
    week_start: str | None = None,
    currency: str | None = None,
) -> dict:
    start = _parse_week_start(week_start)
    end = start + timedelta(days=6)
    previous_start = start - timedelta(days=7)
    previous_end = start - timedelta(days=1)
    selected_currency = _resolve_currency(user_id, currency)

    current_rows = _expense_rows(user_id, start, end, selected_currency)
    previous_rows = _expense_rows(
        user_id, previous_start, previous_end, selected_currency
    )

    current = _summarize_transactions(current_rows)
    previous = _summarize_transactions(previous_rows)
    daily = _daily_breakdown(current_rows, start)
    categories = _category_breakdown(current["categories"], previous["categories"])
    category_trends = _category_trends(current["categories"], previous["categories"])
    upcoming_bills = _upcoming_bills(user_id, start, end, selected_currency)

    net_flow = _money(current["income"] - current["expenses"])
    previous_net_flow = _money(previous["income"] - previous["expenses"])
    summary = {
        "income": _money(current["income"]),
        "expenses": _money(current["expenses"]),
        "net_flow": net_flow,
        "transaction_count": current["transaction_count"],
        "income_transaction_count": current["income_transaction_count"],
        "expense_transaction_count": current["expense_transaction_count"],
        "average_daily_expense": _money(current["expenses"] / 7),
        "savings_rate_pct": (
            round((net_flow / current["income"]) * 100, 2)
            if current["income"] > 0
            else 0.0
        ),
    }
    comparison = {
        "previous_income": _money(previous["income"]),
        "previous_expenses": _money(previous["expenses"]),
        "previous_net_flow": previous_net_flow,
        "income_delta": _money(current["income"] - previous["income"]),
        "expense_delta": _money(current["expenses"] - previous["expenses"]),
        "net_flow_delta": _money(net_flow - previous_net_flow),
        "income_change_pct": _pct_change(current["income"], previous["income"]),
        "expense_change_pct": _pct_change(current["expenses"], previous["expenses"]),
        "net_flow_change_pct": _cash_flow_pct_change(net_flow, previous_net_flow),
    }

    highlights, insights, recommendations = _build_digest_text(
        summary=summary,
        comparison=comparison,
        categories=categories,
        category_trends=category_trends,
        daily=daily,
        upcoming_bills=upcoming_bills,
        currency=selected_currency,
    )

    return {
        "period": {
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "previous_week_start": previous_start.isoformat(),
            "previous_week_end": previous_end.isoformat(),
            "currency": selected_currency,
        },
        "summary": summary,
        "comparison": comparison,
        "daily_breakdown": daily,
        "category_breakdown": categories,
        "category_trends": category_trends,
        "largest_expenses": _largest_expenses(current["expense_rows"]),
        "upcoming_bills": upcoming_bills,
        "highlights": highlights,
        "insights": insights,
        "recommendations": recommendations,
        "method": "heuristic",
    }


def _parse_week_start(raw_value: str | None) -> date:
    if not raw_value:
        today = date.today()
        return today - timedelta(days=today.weekday())
    try:
        parsed = date.fromisoformat(raw_value.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError("invalid week_start, expected YYYY-MM-DD") from exc
    if parsed.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    return parsed


def _resolve_currency(user_id: int, requested: str | None) -> str:
    cleaned = (requested or "").strip().upper()
    if cleaned:
        return cleaned[:10]
    user = db.session.get(User, user_id)
    return ((user.preferred_currency if user else None) or "INR").upper()[:10]


def _expense_rows(user_id: int, start: date, end: date, currency: str):
    return (
        db.session.query(Expense, Category.name)
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == user_id),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            func.upper(Expense.currency) == currency,
        )
        .order_by(Expense.spent_at.asc(), Expense.id.asc())
        .all()
    )


def _summarize_transactions(rows) -> dict:
    summary = {
        "income": 0.0,
        "expenses": 0.0,
        "transaction_count": 0,
        "income_transaction_count": 0,
        "expense_transaction_count": 0,
        "categories": {},
        "expense_rows": [],
    }

    for expense, category_name in rows:
        amount = _money(expense.amount)
        expense_type = (expense.expense_type or "EXPENSE").upper()
        summary["transaction_count"] += 1
        if expense_type == "INCOME":
            summary["income"] += amount
            summary["income_transaction_count"] += 1
            continue

        summary["expenses"] += amount
        summary["expense_transaction_count"] += 1
        key = expense.category_id if expense.category_id is not None else "uncat"
        category = summary["categories"].setdefault(
            key,
            {
                "category_id": expense.category_id,
                "category_name": category_name or "Uncategorized",
                "amount": 0.0,
                "transaction_count": 0,
            },
        )
        category["amount"] += amount
        category["transaction_count"] += 1
        summary["expense_rows"].append(
            {
                "id": expense.id,
                "description": expense.notes or "Transaction",
                "amount": amount,
                "currency": expense.currency,
                "date": expense.spent_at.isoformat(),
                "category_id": expense.category_id,
                "category_name": category["category_name"],
            }
        )

    summary["income"] = _money(summary["income"])
    summary["expenses"] = _money(summary["expenses"])
    return summary


def _daily_breakdown(rows, start: date) -> list[dict]:
    by_day = {
        start
        + timedelta(days=offset): {
            "date": (start + timedelta(days=offset)).isoformat(),
            "income": 0.0,
            "expenses": 0.0,
            "net_flow": 0.0,
            "transaction_count": 0,
        }
        for offset in range(7)
    }

    for expense, _category_name in rows:
        day = by_day.get(expense.spent_at)
        if day is None:
            continue
        amount = _money(expense.amount)
        if (expense.expense_type or "EXPENSE").upper() == "INCOME":
            day["income"] += amount
        else:
            day["expenses"] += amount
        day["transaction_count"] += 1
        day["net_flow"] = day["income"] - day["expenses"]

    return [
        {
            **values,
            "income": _money(values["income"]),
            "expenses": _money(values["expenses"]),
            "net_flow": _money(values["net_flow"]),
        }
        for values in by_day.values()
    ]


def _category_breakdown(current: dict, previous: dict) -> list[dict]:
    total = sum(float(item["amount"] or 0) for item in current.values())
    rows = []
    for key, item in current.items():
        amount = _money(item["amount"])
        previous_amount = _money(previous.get(key, {}).get("amount", 0.0))
        rows.append(
            {
                "category_id": item["category_id"],
                "category_name": item["category_name"],
                "amount": amount,
                "transaction_count": item["transaction_count"],
                "share_pct": round((amount / total) * 100, 2) if total > 0 else 0.0,
                "previous_amount": previous_amount,
                "change_amount": _money(amount - previous_amount),
                "change_pct": _pct_change(amount, previous_amount),
            }
        )
    return sorted(rows, key=lambda row: (-row["amount"], row["category_name"]))


def _category_trends(current: dict, previous: dict) -> list[dict]:
    rows = []
    for key in set(current) | set(previous):
        current_item = current.get(key)
        previous_item = previous.get(key)
        display = current_item or previous_item
        current_amount = _money((current_item or {}).get("amount", 0.0))
        previous_amount = _money((previous_item or {}).get("amount", 0.0))
        change_amount = _money(current_amount - previous_amount)
        rows.append(
            {
                "category_id": display["category_id"],
                "category_name": display["category_name"],
                "current_amount": current_amount,
                "previous_amount": previous_amount,
                "change_amount": change_amount,
                "change_pct": _pct_change(current_amount, previous_amount),
                "trend": _trend(change_amount),
            }
        )
    return sorted(
        rows,
        key=lambda row: (-abs(row["change_amount"]), row["category_name"]),
    )


def _largest_expenses(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: (-row["amount"], row["date"], row["id"]))[:5]


def _upcoming_bills(user_id: int, start: date, end: date, currency: str) -> list[dict]:
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active.is_(True),
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
            func.upper(Bill.currency) == currency,
        )
        .order_by(Bill.next_due_date.asc(), Bill.id.asc())
        .limit(8)
        .all()
    )
    return [
        {
            "id": bill.id,
            "name": bill.name,
            "amount": _money(bill.amount),
            "currency": bill.currency,
            "next_due_date": bill.next_due_date.isoformat(),
            "cadence": bill.cadence.value,
            "autopay_enabled": bill.autopay_enabled,
        }
        for bill in bills
    ]


def _build_digest_text(
    summary: dict,
    comparison: dict,
    categories: list[dict],
    category_trends: list[dict],
    daily: list[dict],
    upcoming_bills: list[dict],
    currency: str,
) -> tuple[list[str], list[dict], list[str]]:
    highlights: list[str] = []
    insights: list[dict] = []
    recommendations: list[str] = []

    if summary["transaction_count"] == 0:
        highlights.append("No transactions were recorded for this week.")
        insights.append(
            {
                "type": "activity",
                "severity": "info",
                "title": "No weekly activity",
                "detail": (
                    "Add income and expense transactions to generate weekly trends."
                ),
            }
        )
        recommendations.append("Log this week's transactions to unlock the digest.")
        return highlights, insights, recommendations

    highlights.append(
        "Net flow was "
        f"{_format_money(summary['net_flow'], currency)} from "
        f"{_format_money(summary['income'], currency)} income and "
        f"{_format_money(summary['expenses'], currency)} expenses."
    )

    expense_delta = comparison["expense_delta"]
    if comparison["previous_expenses"] > 0:
        direction = "higher" if expense_delta >= 0 else "lower"
        highlights.append(
            "Expenses were "
            f"{abs(comparison['expense_change_pct']):.2f}% {direction} than last week."
        )
    elif summary["expenses"] > 0:
        highlights.append(
            "This was the first week with expenses in the comparison window."
        )

    if categories:
        top_category = categories[0]
        highlights.append(
            f"{top_category['category_name']} led spending at "
            f"{_format_money(top_category['amount'], currency)} "
            f"({top_category['share_pct']:.2f}% of expenses)."
        )
        insights.append(
            {
                "type": "top_category",
                "severity": "info",
                "title": f"{top_category['category_name']} led spending",
                "detail": (
                    f"{top_category['category_name']} represented "
                    f"{top_category['share_pct']:.2f}% of weekly expenses."
                ),
            }
        )
        if top_category["share_pct"] >= 40:
            recommendations.append(
                f"Set a cap for {top_category['category_name']} before next week."
            )

    if summary["net_flow"] >= 0:
        insights.append(
            {
                "type": "cash_flow",
                "severity": "success",
                "title": "Positive weekly cash flow",
                "detail": (
                    "Income covered expenses by "
                    f"{_format_money(summary['net_flow'], currency)}."
                ),
            }
        )
        recommendations.append("Move part of this week's surplus to savings.")
    else:
        insights.append(
            {
                "type": "cash_flow",
                "severity": "warning",
                "title": "Negative weekly cash flow",
                "detail": (
                    "Expenses exceeded income by "
                    f"{_format_money(abs(summary['net_flow']), currency)}."
                ),
            }
        )
        recommendations.append("Review the largest expense before adding new spend.")

    if expense_delta > 0:
        insights.append(
            {
                "type": "spending_increase",
                "severity": "warning",
                "title": "Spending increased",
                "detail": (
                    "Weekly expenses increased by "
                    f"{_format_money(expense_delta, currency)} from the prior week."
                ),
            }
        )
    elif expense_delta < 0:
        insights.append(
            {
                "type": "spending_decrease",
                "severity": "success",
                "title": "Spending decreased",
                "detail": (
                    "Weekly expenses decreased by "
                    f"{_format_money(abs(expense_delta), currency)} "
                    "from the prior week."
                ),
            }
        )

    if category_trends:
        trend = category_trends[0]
        if trend["change_amount"] != 0:
            insights.append(
                {
                    "type": "category_trend",
                    "severity": "info",
                    "title": f"{trend['category_name']} changed most",
                    "detail": (
                        f"{trend['category_name']} moved "
                        f"{_format_money(abs(trend['change_amount']), currency)} "
                        f"{trend['trend']} versus last week."
                    ),
                }
            )

    expense_days = [item for item in daily if item["expenses"] > 0]
    if expense_days:
        highest_day = max(expense_days, key=lambda item: item["expenses"])
        insights.append(
            {
                "type": "daily_trend",
                "severity": "info",
                "title": "Highest spend day",
                "detail": (
                    f"{highest_day['date']} had the highest spending at "
                    f"{_format_money(highest_day['expenses'], currency)}."
                ),
            }
        )

    if upcoming_bills:
        total_due = _money(sum(item["amount"] for item in upcoming_bills))
        highlights.append(
            f"{len(upcoming_bills)} bill(s) totaling "
            f"{_format_money(total_due, currency)} are due this week."
        )
        insights.append(
            {
                "type": "upcoming_bills",
                "severity": "warning",
                "title": "Bills due this week",
                "detail": (
                    f"{len(upcoming_bills)} upcoming bill(s) total "
                    f"{_format_money(total_due, currency)}."
                ),
            }
        )
        recommendations.append(
            "Reserve cash for bills due before making extra payments."
        )

    if summary["income"] == 0 and summary["expenses"] > 0:
        recommendations.append("Record income deposits to track true cash flow.")

    return _dedupe(highlights), insights, _dedupe(recommendations)


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return 0.0 if current == 0 else None
    return round(((current - previous) / previous) * 100, 2)


def _cash_flow_pct_change(current: float, previous: float) -> float | None:
    if previous <= 0:
        return 0.0 if current == previous else None
    return _pct_change(current, previous)


def _trend(delta: float) -> str:
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _format_money(amount: float, currency: str) -> str:
    return f"{currency} {float(amount or 0):.2f}"


def _money(value) -> float:
    return round(float(value or 0), 2)


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
