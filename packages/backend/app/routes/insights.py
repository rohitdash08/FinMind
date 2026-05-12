from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from ..extensions import db
from ..models import Bill, Category, Expense
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
    try:
        week_start = _parse_week_start(request.args.get("week_start"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    currency = (request.args.get("currency") or "").strip().upper() or None
    payload = _build_weekly_summary(uid, week_start, currency)
    logger.info(
        "Weekly summary served user=%s week_start=%s currency=%s",
        uid,
        week_start.isoformat(),
        currency or "ALL",
    )
    return jsonify(payload)


def _parse_week_start(raw_value: str | None) -> date:
    if not raw_value:
        today = date.today()
        return today - timedelta(days=today.weekday())
    try:
        week_start = date.fromisoformat(raw_value.strip())
    except ValueError as exc:
        raise ValueError("invalid week_start, expected YYYY-MM-DD") from exc
    if week_start.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    return week_start


def _build_weekly_summary(uid: int, week_start: date, currency: str | None):
    week_end = week_start + timedelta(days=6)
    next_week_start = week_start + timedelta(days=7)
    previous_week_start = week_start - timedelta(days=7)

    current_rows = _expense_rows(uid, week_start, next_week_start, currency)
    previous_rows = _expense_rows(uid, previous_week_start, week_start, currency)
    upcoming_bills = _upcoming_bills(uid, week_start, next_week_start, currency)

    current_totals = _totals(current_rows)
    previous_totals = _totals(previous_rows)
    categories = _category_breakdown(current_rows, previous_rows)
    daily = _daily_breakdown(current_rows, week_start)

    summary = {
        "income": current_totals["income"],
        "expenses": current_totals["expenses"],
        "net_flow": round(current_totals["income"] - current_totals["expenses"], 2),
        "transaction_count": len(current_rows),
        "average_daily_expense": round(current_totals["expenses"] / 7, 2),
    }
    previous_summary = {
        "income": previous_totals["income"],
        "expenses": previous_totals["expenses"],
        "net_flow": round(previous_totals["income"] - previous_totals["expenses"], 2),
        "expense_delta": round(
            current_totals["expenses"] - previous_totals["expenses"], 2
        ),
        "expense_delta_pct": _pct_change(
            previous_totals["expenses"], current_totals["expenses"]
        ),
    }

    return {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "previous_week_start": previous_week_start.isoformat(),
            "currency": currency,
        },
        "summary": summary,
        "previous_week": previous_summary,
        "daily_breakdown": daily,
        "category_breakdown": categories,
        "upcoming_bills": upcoming_bills,
        "insights": _insights(
            summary, previous_summary, categories, daily, upcoming_bills
        ),
    }


def _expense_rows(uid: int, start: date, end: date, currency: str | None):
    query = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at < end,
        )
        .order_by(Expense.spent_at.asc(), Expense.id.asc())
    )
    if currency:
        query = query.filter(func.upper(Expense.currency) == currency)
    return query.all()


def _totals(rows: list[Expense]) -> dict[str, float]:
    income = 0.0
    expenses = 0.0
    for row in rows:
        amount = float(row.amount or 0)
        if row.expense_type == "INCOME":
            income += amount
        else:
            expenses += amount
    return {"income": round(income, 2), "expenses": round(expenses, 2)}


def _category_breakdown(current_rows: list[Expense], previous_rows: list[Expense]):
    current = _category_amounts(current_rows)
    previous = _category_amounts(previous_rows)
    total = sum(item["amount"] for item in current.values())
    rows = []
    for key, item in current.items():
        prev_amount = previous.get(key, {"amount": 0.0})["amount"]
        rows.append(
            {
                "category_id": item["category_id"],
                "category_name": item["category_name"],
                "amount": round(item["amount"], 2),
                "transaction_count": item["transaction_count"],
                "share_pct": (
                    round((item["amount"] / total) * 100, 2) if total > 0 else 0
                ),
                "previous_amount": round(prev_amount, 2),
                "change_amount": round(item["amount"] - prev_amount, 2),
                "change_pct": _pct_change(prev_amount, item["amount"]),
            }
        )
    return sorted(rows, key=lambda item: item["amount"], reverse=True)


def _category_amounts(rows: list[Expense]):
    category_ids = {row.category_id for row in rows if row.category_id is not None}
    names = {}
    if category_ids:
        names = {
            category.id: category.name
            for category in db.session.query(Category)
            .filter(Category.id.in_(category_ids))
            .all()
        }
    grouped = {}
    for row in rows:
        if row.expense_type == "INCOME":
            continue
        key = row.category_id or 0
        if key not in grouped:
            grouped[key] = {
                "category_id": row.category_id,
                "category_name": names.get(row.category_id, "Uncategorized"),
                "amount": 0.0,
                "transaction_count": 0,
            }
        grouped[key]["amount"] += float(row.amount or 0)
        grouped[key]["transaction_count"] += 1
    return grouped


def _daily_breakdown(rows: list[Expense], week_start: date):
    by_day = {
        (week_start + timedelta(days=offset)): {"income": 0.0, "expenses": 0.0}
        for offset in range(7)
    }
    for row in rows:
        if row.spent_at not in by_day:
            continue
        key = "income" if row.expense_type == "INCOME" else "expenses"
        by_day[row.spent_at][key] += float(row.amount or 0)
    return [
        {
            "date": day.isoformat(),
            "income": round(values["income"], 2),
            "expenses": round(values["expenses"], 2),
            "net_flow": round(values["income"] - values["expenses"], 2),
        }
        for day, values in by_day.items()
    ]


def _upcoming_bills(uid: int, start: date, end: date, currency: str | None):
    query = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= start,
            Bill.next_due_date < end,
        )
        .order_by(Bill.next_due_date.asc())
    )
    if currency:
        query = query.filter(func.upper(Bill.currency) == currency)
    return [
        {
            "id": bill.id,
            "name": bill.name,
            "amount": float(bill.amount or 0),
            "currency": bill.currency,
            "next_due_date": bill.next_due_date.isoformat(),
            "cadence": bill.cadence.value,
            "autopay_enabled": bill.autopay_enabled,
        }
        for bill in query.limit(8).all()
    ]


def _pct_change(previous: float, current: float):
    if previous == 0:
        return None if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 2)


def _insights(summary, previous_summary, categories, daily, upcoming_bills):
    insights = []
    if summary["transaction_count"] == 0:
        insights.append(
            {
                "type": "empty_week",
                "severity": "info",
                "message": "No transactions were recorded for this week.",
            }
        )
        return insights

    if categories:
        top = categories[0]
        insights.append(
            {
                "type": "top_category",
                "severity": "info",
                "message": (
                    f"{top['category_name']} is the top spending category at "
                    f"{top['share_pct']}% of weekly expenses."
                ),
            }
        )

    delta = previous_summary["expense_delta"]
    if delta > 0:
        insights.append(
            {
                "type": "spending_increase",
                "severity": "warning",
                "message": (
                    f"Weekly expenses increased by {delta:.2f} versus last week."
                ),
            }
        )
    elif delta < 0:
        insights.append(
            {
                "type": "spending_decrease",
                "severity": "success",
                "message": (
                    "Weekly expenses decreased by "
                    f"{abs(delta):.2f} versus last week."
                ),
            }
        )

    no_spend_days = [item["date"] for item in daily if item["expenses"] == 0]
    if no_spend_days:
        insights.append(
            {
                "type": "no_spend_days",
                "severity": "info",
                "message": f"{len(no_spend_days)} day(s) had no recorded expenses.",
            }
        )

    if upcoming_bills:
        total_due = round(sum(item["amount"] for item in upcoming_bills), 2)
        insights.append(
            {
                "type": "upcoming_bills",
                "severity": "warning",
                "message": (
                    f"{len(upcoming_bills)} bill(s) totaling {total_due:.2f} "
                    "are due during this week."
                ),
            }
        )

    if summary["net_flow"] >= 0:
        insights.append(
            {
                "type": "positive_cash_flow",
                "severity": "success",
                "message": "Income covered expenses for this week.",
            }
        )
    else:
        insights.append(
            {
                "type": "negative_cash_flow",
                "severity": "warning",
                "message": "Expenses exceeded income for this week.",
            }
        )
    return insights
