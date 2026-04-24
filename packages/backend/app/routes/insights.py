from datetime import date, timedelta
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Bill, Category, Expense
from ..services.ai import monthly_budget_suggestion

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
    """Return a deterministic weekly financial digest for the signed-in user."""
    uid = int(get_jwt_identity())
    try:
        week_start = _parse_week_start(request.args.get("week_start"))
    except ValueError:
        return jsonify(error="invalid week_start, expected YYYY-MM-DD"), 400

    week_end = week_start + timedelta(days=6)
    previous_start = week_start - timedelta(days=7)
    previous_end = week_start - timedelta(days=1)

    current = _window_metrics(uid, week_start, week_end)
    previous = _window_metrics(uid, previous_start, previous_end)
    upcoming_bills = _upcoming_bills(uid, week_end + timedelta(days=1), week_end + timedelta(days=14))
    top_category = current["category_breakdown"][0] if current["category_breakdown"] else None

    payload = {
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "previous_week_start": previous_start.isoformat(),
            "previous_week_end": previous_end.isoformat(),
        },
        "summary": {
            "income": current["income"],
            "expenses": current["expenses"],
            "net_flow": round(current["income"] - current["expenses"], 2),
            "transactions_count": current["transactions_count"],
            "average_daily_spend": round(current["expenses"] / 7, 2),
            "upcoming_bills_total": round(sum(b["amount"] for b in upcoming_bills), 2),
            "upcoming_bills_count": len(upcoming_bills),
        },
        "trends": {
            "expense_change_pct": _pct_change(previous["expenses"], current["expenses"]),
            "income_change_pct": _pct_change(previous["income"], current["income"]),
            "net_flow_change": round(
                (current["income"] - current["expenses"])
                - (previous["income"] - previous["expenses"]),
                2,
            ),
            "top_category": top_category["category_name"] if top_category else None,
        },
        "category_breakdown": current["category_breakdown"],
        "highlights": _highlights(current, previous, top_category),
        "insights": _insights(current, previous, upcoming_bills, top_category),
        "recommendations": _recommendations(current, previous, upcoming_bills, top_category),
        "upcoming_bills": upcoming_bills,
    }
    logger.info("Weekly summary served user=%s week_start=%s", uid, week_start)
    return jsonify(payload)


def _parse_week_start(raw: str | None) -> date:
    if raw:
        parsed = date.fromisoformat(raw.strip())
    else:
        today = date.today()
        parsed = today - timedelta(days=today.weekday())
    return parsed


def _window_metrics(user_id: int, start: date, end: date) -> dict:
    rows = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .all()
    )
    income = round(
        sum(float(e.amount or 0) for e in rows if e.expense_type == "INCOME"), 2
    )
    expenses = round(
        sum(float(e.amount or 0) for e in rows if e.expense_type != "INCOME"), 2
    )
    category_rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == user_id),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    category_breakdown = []
    for row in category_rows:
        amount = round(float(row.total_amount or 0), 2)
        category_breakdown.append(
            {
                "category_id": row.category_id,
                "category_name": row.category_name,
                "amount": amount,
                "share_pct": round((amount / expenses) * 100, 2) if expenses else 0,
            }
        )
    return {
        "income": income,
        "expenses": expenses,
        "transactions_count": len(rows),
        "category_breakdown": category_breakdown,
    }


def _upcoming_bills(user_id: int, start: date, end: date) -> list[dict]:
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == user_id,
            Bill.active.is_(True),
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
        )
        .order_by(Bill.next_due_date.asc(), Bill.id.asc())
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
        }
        for b in bills
    ]


def _pct_change(previous: float, current: float) -> float | None:
    if previous == 0:
        return None if current else 0.0
    return round(((current - previous) / previous) * 100, 2)


def _money(value: float) -> str:
    return f"{value:.2f}"


def _highlights(current: dict, previous: dict, top_category: dict | None) -> list[str]:
    highlights = [
        f"Spent {_money(current['expenses'])} across {current['transactions_count']} transactions.",
        f"Net flow was {_money(current['income'] - current['expenses'])}.",
    ]
    change = _pct_change(previous["expenses"], current["expenses"])
    if change is not None:
        direction = "up" if change > 0 else "down"
        highlights.append(f"Spending was {abs(change):.1f}% {direction} vs the previous week.")
    if top_category:
        highlights.append(
            f"Top category was {top_category['category_name']} at {_money(top_category['amount'])}."
        )
    return highlights


def _insights(
    current: dict, previous: dict, upcoming_bills: list[dict], top_category: dict | None
) -> list[dict]:
    insights = []
    net_flow = current["income"] - current["expenses"]
    if net_flow < 0:
        insights.append(
            {
                "type": "cash_flow",
                "severity": "warning",
                "title": "Negative weekly cash flow",
                "message": f"Expenses exceeded income by {_money(abs(net_flow))} this week.",
            }
        )
    else:
        insights.append(
            {
                "type": "cash_flow",
                "severity": "positive",
                "title": "Positive weekly cash flow",
                "message": f"Income exceeded expenses by {_money(net_flow)} this week.",
            }
        )

    expense_change = _pct_change(previous["expenses"], current["expenses"])
    if expense_change is not None and expense_change >= 25:
        insights.append(
            {
                "type": "trend",
                "severity": "warning",
                "title": "Spending accelerated",
                "message": f"Weekly spending increased {expense_change:.1f}% from the previous week.",
            }
        )
    elif expense_change is not None and expense_change <= -10:
        insights.append(
            {
                "type": "trend",
                "severity": "positive",
                "title": "Spending improved",
                "message": f"Weekly spending decreased {abs(expense_change):.1f}% from the previous week.",
            }
        )

    if top_category and top_category["share_pct"] >= 50:
        insights.append(
            {
                "type": "category_concentration",
                "severity": "info",
                "title": "Category concentration",
                "message": f"{top_category['category_name']} made up {top_category['share_pct']:.1f}% of spending.",
            }
        )
    if upcoming_bills:
        insights.append(
            {
                "type": "upcoming_bills",
                "severity": "info",
                "title": "Bills due soon",
                "message": f"{len(upcoming_bills)} bills totaling {_money(sum(b['amount'] for b in upcoming_bills))} are due in the next 14 days.",
            }
        )
    return insights


def _recommendations(
    current: dict, previous: dict, upcoming_bills: list[dict], top_category: dict | None
) -> list[str]:
    recommendations = []
    if current["expenses"] > current["income"] and current["income"] > 0:
        recommendations.append(
            "Pause non-essential purchases until weekly expenses are back below income."
        )
    if top_category and top_category["share_pct"] >= 35:
        recommendations.append(
            f"Review {top_category['category_name']} transactions first; it is the largest weekly spend driver."
        )
    if upcoming_bills:
        recommendations.append(
            "Reserve cash for upcoming bills before making discretionary purchases."
        )
    change = _pct_change(previous["expenses"], current["expenses"])
    if change is not None and change > 0:
        recommendations.append(
            "Compare this week’s largest transactions against last week to identify avoidable increases."
        )
    if not recommendations:
        recommendations.append("Maintain the current spending pace and keep tracking transactions weekly.")
    return recommendations
