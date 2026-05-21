from datetime import date, timedelta
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
    raw_week_start = request.args.get("week_start")
    try:
        week_start = _parse_week_start(raw_week_start)
    except ValueError:
        return jsonify(error="invalid week_start"), 400

    currency = (
        (
            request.args.get("currency")
            or (user.preferred_currency if user else None)
            or "INR"
        )
        .strip()[:10]
        .upper()
    )
    payload = _build_weekly_summary(uid, week_start, currency)
    logger.info(
        "Weekly summary served user=%s week_start=%s currency=%s",
        uid,
        week_start.isoformat(),
        currency,
    )
    return jsonify(payload)


def _parse_week_start(raw: str | None) -> date:
    if raw and raw.strip():
        selected = date.fromisoformat(raw.strip())
    else:
        selected = date.today()
    return selected - timedelta(days=selected.weekday())


def _build_weekly_summary(uid: int, week_start: date, currency: str) -> dict:
    week_end = week_start + timedelta(days=6)
    previous_start = week_start - timedelta(days=7)
    previous_end = week_start - timedelta(days=1)
    current_expenses = _expenses_for_period(uid, week_start, week_end, currency)
    previous_expenses = _expenses_for_period(
        uid, previous_start, previous_end, currency
    )
    current_breakdown = _aggregate_expenses(current_expenses)
    previous_breakdown = _aggregate_expenses(previous_expenses)
    category_names = _category_names(
        uid,
        [
            category_id
            for category_id in current_breakdown["categories"].keys()
            if category_id is not None
        ],
    )

    category_breakdown = _category_breakdown(
        current_breakdown["categories"],
        previous_breakdown["categories"],
        current_breakdown["expenses_total"],
        category_names,
    )
    daily_breakdown = _daily_breakdown(week_start, current_expenses)
    upcoming_bills = _upcoming_bills(uid, week_start, week_end, currency)
    comparison = _comparison(
        current_breakdown["expenses_total"], previous_breakdown["expenses_total"]
    )
    summary = {
        "income": _money(current_breakdown["income_total"]),
        "expenses": _money(current_breakdown["expenses_total"]),
        "net_flow": _money(
            current_breakdown["income_total"] - current_breakdown["expenses_total"]
        ),
        "transaction_count": len(current_expenses),
        "average_daily_expense": _money(current_breakdown["expenses_total"] / 7),
        "savings_rate_pct": _percent(
            current_breakdown["income_total"] - current_breakdown["expenses_total"],
            current_breakdown["income_total"],
        ),
    }
    return {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "previous_week_start": previous_start.isoformat(),
            "previous_week_end": previous_end.isoformat(),
        },
        "currency": currency,
        "summary": summary,
        "comparison": comparison,
        "category_breakdown": category_breakdown,
        "daily_breakdown": daily_breakdown,
        "largest_expenses": _largest_expenses(current_expenses),
        "upcoming_bills": upcoming_bills,
        "highlights": _highlights(summary, category_breakdown, comparison),
        "insights": _insights(summary, category_breakdown, daily_breakdown),
        "recommendations": _recommendations(
            summary, category_breakdown, comparison, upcoming_bills
        ),
    }


def _expenses_for_period(
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


def _aggregate_expenses(items: list[Expense]) -> dict:
    income_total = 0.0
    expenses_total = 0.0
    categories: dict[int | None, dict] = {}
    for item in items:
        amount = float(item.amount or 0)
        if str(item.expense_type or "").upper() == "INCOME":
            income_total += amount
            continue
        expenses_total += amount
        bucket = categories.setdefault(
            item.category_id,
            {"amount": 0.0, "transaction_count": 0},
        )
        bucket["amount"] += amount
        bucket["transaction_count"] += 1
    return {
        "income_total": income_total,
        "expenses_total": expenses_total,
        "categories": categories,
    }


def _category_names(uid: int, category_ids: list[int]) -> dict[int, str]:
    if not category_ids:
        return {}
    rows = (
        db.session.query(Category)
        .filter(Category.user_id == uid, Category.id.in_(category_ids))
        .all()
    )
    return {row.id: row.name for row in rows}


def _category_breakdown(
    current: dict, previous: dict, current_total: float, names: dict[int, str]
) -> list[dict]:
    rows = []
    for category_id, data in current.items():
        amount = data["amount"]
        previous_amount = previous.get(category_id, {}).get("amount", 0.0)
        rows.append(
            {
                "category_id": category_id,
                "category_name": names.get(category_id, "Uncategorized"),
                "amount": _money(amount),
                "share_pct": _percent(amount, current_total),
                "previous_amount": _money(previous_amount),
                "change_pct": _percent(amount - previous_amount, previous_amount),
                "transaction_count": data["transaction_count"],
            }
        )
    return sorted(rows, key=lambda row: row["amount"], reverse=True)


def _daily_breakdown(week_start: date, items: list[Expense]) -> list[dict]:
    days = {week_start + timedelta(days=offset): 0.0 for offset in range(7)}
    for item in items:
        if str(item.expense_type or "").upper() == "INCOME":
            continue
        if item.spent_at in days:
            days[item.spent_at] += float(item.amount or 0)
    return [
        {
            "date": day.isoformat(),
            "day": day.strftime("%a"),
            "expenses": _money(amount),
        }
        for day, amount in days.items()
    ]


def _upcoming_bills(uid: int, start: date, end: date, currency: str) -> list[dict]:
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.currency == currency,
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
        )
        .order_by(Bill.next_due_date.asc(), Bill.id.asc())
        .all()
    )
    return [
        {
            "id": bill.id,
            "name": bill.name,
            "amount": _money(float(bill.amount or 0)),
            "due_date": bill.next_due_date.isoformat(),
            "autopay_enabled": bill.autopay_enabled,
        }
        for bill in bills
    ]


def _comparison(current: float, previous: float) -> dict:
    change = current - previous
    if change > 0:
        trend = "up"
    elif change < 0:
        trend = "down"
    else:
        trend = "flat"
    return {
        "previous_expenses": _money(previous),
        "expense_change": _money(change),
        "expense_change_pct": _percent(change, previous),
        "trend": trend,
    }


def _largest_expenses(items: list[Expense]) -> list[dict]:
    expenses = [
        item for item in items if str(item.expense_type or "").upper() != "INCOME"
    ]
    expenses.sort(key=lambda item: float(item.amount or 0), reverse=True)
    return [
        {
            "id": item.id,
            "description": item.notes or "Expense",
            "amount": _money(float(item.amount or 0)),
            "date": item.spent_at.isoformat(),
        }
        for item in expenses[:5]
    ]


def _highlights(summary: dict, categories: list[dict], comparison: dict) -> list[str]:
    if summary["transaction_count"] == 0:
        return ["No transactions were recorded for this week."]
    top = categories[0]["category_name"] if categories else "uncategorized spending"
    direction = "lower" if comparison["trend"] == "down" else "higher"
    return [
        f"You logged {summary['transaction_count']} transactions this week.",
        f"Top spending area: {top}.",
        (
            f"Expenses were {direction} than last week by "
            f"{abs(comparison['expense_change_pct'])}%."
        ),
    ]


def _insights(
    summary: dict, categories: list[dict], daily_breakdown: list[dict]
) -> list[str]:
    insights = []
    if summary["net_flow"] >= 0:
        insights.append(f"Net flow stayed positive at {summary['net_flow']}.")
    else:
        insights.append(f"Net flow was negative at {summary['net_flow']}.")
    if categories and categories[0]["share_pct"] >= 50:
        insights.append(
            f"{categories[0]['category_name']} made up "
            f"{categories[0]['share_pct']}% of spending."
        )
    peak_day = max(daily_breakdown, key=lambda row: row["expenses"])
    if peak_day["expenses"] > 0:
        insights.append(f"Highest spending day was {peak_day['day']}.")
    if not insights:
        insights.append("No spending signals yet; add transactions to build a digest.")
    return insights


def _recommendations(
    summary: dict, categories: list[dict], comparison: dict, bills: list[dict]
) -> list[str]:
    recommendations = []
    if comparison["trend"] == "up" and comparison["expense_change_pct"] >= 15:
        recommendations.append(
            "Review this week's largest expenses before next week starts."
        )
    if categories and categories[0]["share_pct"] >= 50:
        recommendations.append(
            f"Set a soft cap for {categories[0]['category_name']} next week."
        )
    unpaid_manual_bills = [bill for bill in bills if not bill["autopay_enabled"]]
    if unpaid_manual_bills:
        recommendations.append("Schedule manual bill payments before their due dates.")
    if summary["net_flow"] < 0:
        recommendations.append(
            "Move one flexible purchase out of this week to recover cash flow."
        )
    if not recommendations:
        recommendations.append(
            "Keep the current weekly pattern and recheck after new expenses post."
        )
    return recommendations


def _money(value: float) -> float:
    return round(float(value or 0), 2)


def _percent(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100, 2)
