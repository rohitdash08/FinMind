from datetime import date, timedelta
from decimal import Decimal
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Bill, Category, Expense, User
from ..services.ai import monthly_budget_suggestion
import logging

bp = Blueprint("insights", __name__)
logger = logging.getLogger("finmind.insights")


@bp.get("/budget-suggestion")
@jwt_required()
def budget_suggestion():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None
    suggestion = monthly_budget_suggestion(
        uid,
        ym,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    logger.info("Budget suggestion served user=%s month=%s", uid, ym)
    return jsonify(suggestion)


@bp.get("/weekly-summary")
@jwt_required()
def weekly_summary():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    currency = (
        (request.args.get("currency") or (user.preferred_currency if user else "INR"))
        .strip()
        .upper()
    )
    week_start = _parse_week_start(request.args.get("week_start"))
    if week_start is None:
        return jsonify(error="week_start must be YYYY-MM-DD"), 400

    week_end = week_start + timedelta(days=6)
    previous_start = week_start - timedelta(days=7)
    previous_end = week_start - timedelta(days=1)

    current_expenses = _expenses_for_window(uid, week_start, week_end, currency)
    previous_expenses = _expenses_for_window(
        uid, previous_start, previous_end, currency
    )
    categories = {
        category.id: category.name
        for category in db.session.query(Category).filter_by(user_id=uid).all()
    }
    upcoming_bills = _upcoming_bills(uid, week_start, week_end, currency)

    payload = _build_weekly_summary(
        current_expenses=current_expenses,
        previous_expenses=previous_expenses,
        categories=categories,
        upcoming_bills=upcoming_bills,
        week_start=week_start,
        week_end=week_end,
        currency=currency,
    )
    logger.info("Weekly summary served user=%s week_start=%s", uid, week_start)
    return jsonify(payload)


def _parse_week_start(raw: str | None) -> date | None:
    if not raw:
        today = date.today()
        return today - timedelta(days=today.weekday())
    try:
        requested = date.fromisoformat(raw.strip())
    except ValueError:
        return None
    return requested - timedelta(days=requested.weekday())


def _expenses_for_window(
    uid: int, start: date, end: date, currency: str
) -> list[Expense]:
    return (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.currency == currency,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .order_by(Expense.spent_at.asc(), Expense.id.asc())
        .all()
    )


def _upcoming_bills(uid: int, start: date, end: date, currency: str) -> list[Bill]:
    return (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.currency == currency,
            Bill.active.is_(True),
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
        )
        .order_by(Bill.next_due_date.asc(), Bill.id.asc())
        .all()
    )


def _build_weekly_summary(
    *,
    current_expenses: list[Expense],
    previous_expenses: list[Expense],
    categories: dict[int, str],
    upcoming_bills: list[Bill],
    week_start: date,
    week_end: date,
    currency: str,
) -> dict:
    expense_total = sum(
        _decimal(e.amount) for e in current_expenses if e.expense_type == "EXPENSE"
    )
    income_total = sum(
        _decimal(e.amount) for e in current_expenses if e.expense_type == "INCOME"
    )
    previous_expense_total = sum(
        _decimal(e.amount) for e in previous_expenses if e.expense_type == "EXPENSE"
    )
    category_totals = _category_totals(current_expenses)
    previous_category_totals = _category_totals(previous_expenses)
    daily = _daily_totals(current_expenses, week_start)
    category_rows = _category_rows(
        category_totals, previous_category_totals, categories, expense_total
    )
    bill_rows = [
        {
            "id": bill.id,
            "name": bill.name,
            "amount": _round_decimal(bill.amount),
            "currency": bill.currency,
            "due_date": bill.next_due_date.isoformat(),
            "autopay_enabled": bill.autopay_enabled,
        }
        for bill in upcoming_bills
    ]
    top_expenses = [
        {
            "id": expense.id,
            "amount": _round_decimal(expense.amount),
            "category": categories.get(expense.category_id, "Uncategorized"),
            "description": expense.notes,
            "spent_at": expense.spent_at.isoformat(),
        }
        for expense in sorted(
            [e for e in current_expenses if e.expense_type == "EXPENSE"],
            key=lambda item: _decimal(item.amount),
            reverse=True,
        )[:5]
    ]
    change_amount = expense_total - previous_expense_total

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "currency": currency,
        "totals": {
            "income": _round_decimal(income_total),
            "expenses": _round_decimal(expense_total),
            "net_flow": _round_decimal(income_total - expense_total),
            "transaction_count": len(current_expenses),
            "average_daily_expense": _round_decimal(expense_total / Decimal("7")),
        },
        "previous_week": {
            "expenses": _round_decimal(previous_expense_total),
            "change_amount": _round_decimal(change_amount),
            "change_pct": _percent_change(expense_total, previous_expense_total),
        },
        "categories": category_rows,
        "daily": daily,
        "top_expenses": top_expenses,
        "upcoming_bills": bill_rows,
        "insights": _insights(
            expense_total=expense_total,
            previous_expense_total=previous_expense_total,
            category_rows=category_rows,
            upcoming_bills=bill_rows,
        ),
    }


def _category_totals(expenses: list[Expense]) -> dict[int | None, Decimal]:
    totals: dict[int | None, Decimal] = {}
    for expense in expenses:
        if expense.expense_type != "EXPENSE":
            continue
        totals[expense.category_id] = totals.get(
            expense.category_id, Decimal("0")
        ) + _decimal(expense.amount)
    return totals


def _daily_totals(expenses: list[Expense], week_start: date) -> list[dict]:
    days = {
        week_start
        + timedelta(days=offset): {
            "date": (week_start + timedelta(days=offset)).isoformat(),
            "income": Decimal("0"),
            "expenses": Decimal("0"),
            "net_flow": Decimal("0"),
        }
        for offset in range(7)
    }
    for expense in expenses:
        row = days[expense.spent_at]
        amount = _decimal(expense.amount)
        if expense.expense_type == "INCOME":
            row["income"] += amount
            row["net_flow"] += amount
        else:
            row["expenses"] += amount
            row["net_flow"] -= amount
    return [
        {
            "date": row["date"],
            "income": _round_decimal(row["income"]),
            "expenses": _round_decimal(row["expenses"]),
            "net_flow": _round_decimal(row["net_flow"]),
        }
        for row in days.values()
    ]


def _category_rows(
    current: dict[int | None, Decimal],
    previous: dict[int | None, Decimal],
    categories: dict[int, str],
    expense_total: Decimal,
) -> list[dict]:
    rows = []
    for category_id, amount in current.items():
        prior = previous.get(category_id, Decimal("0"))
        change_amount = amount - prior
        rows.append(
            {
                "category_id": category_id,
                "category": categories.get(category_id, "Uncategorized"),
                "amount": _round_decimal(amount),
                "share_pct": _percent_share(amount, expense_total),
                "previous_amount": _round_decimal(prior),
                "change_amount": _round_decimal(change_amount),
                "change_pct": _percent_change(amount, prior),
                "trend": _trend(change_amount),
            }
        )
    return sorted(rows, key=lambda item: item["amount"], reverse=True)


def _insights(
    *,
    expense_total: Decimal,
    previous_expense_total: Decimal,
    category_rows: list[dict],
    upcoming_bills: list[dict],
) -> list[str]:
    insights: list[str] = []
    if expense_total == 0:
        insights.append("No expenses were recorded for this week.")
    elif previous_expense_total == 0:
        insights.append(
            "This is the first week with recorded spending in the comparison window."
        )
    else:
        change_pct = _percent_change(expense_total, previous_expense_total)
        direction = "higher" if change_pct > 0 else "lower"
        insights.append(
            f"Weekly spending is {abs(change_pct):.1f}% {direction} than last week."
        )
    if category_rows:
        top = category_rows[0]
        insights.append(
            f"{top['category']} was the top spending category at {top['share_pct']:.1f}% of expenses."
        )
    if upcoming_bills:
        bill_total = sum(_decimal(bill["amount"]) for bill in upcoming_bills)
        insights.append(
            f"{len(upcoming_bills)} bills totaling {_round_decimal(bill_total):.2f} are due this week."
        )
    return insights


def _trend(change_amount: Decimal) -> str:
    if change_amount > 0:
        return "UP"
    if change_amount < 0:
        return "DOWN"
    return "FLAT"


def _percent_change(current: Decimal, previous: Decimal) -> float:
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return _round_decimal(((current - previous) / previous) * Decimal("100"))


def _percent_share(amount: Decimal, total: Decimal) -> float:
    if total == 0:
        return 0.0
    return _round_decimal((amount / total) * Decimal("100"))


def _decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _round_decimal(value) -> float:
    return float(_decimal(value).quantize(Decimal("0.01")))
