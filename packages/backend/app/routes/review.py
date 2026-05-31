from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import extract, func
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Bill, Category, Expense

bp = Blueprint("review", __name__)


@bp.get("/monthly-review")
@jwt_required()
def monthly_review():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    if not _is_valid_month(ym):
        return jsonify(error="invalid month, expected YYYY-MM"), 400

    year, month = map(int, ym.split("-"))

    prev_dt = date(year, month, 1) - timedelta(days=1)
    prev_ym = prev_dt.strftime("%Y-%m")
    prev_year, prev_month = map(int, prev_ym.split("-"))

    current = _aggregate(uid, year, month)
    previous = _aggregate(uid, prev_year, prev_month)

    reviews = _build_reviews(current, previous)

    recommendations = _build_recommendations(current, previous)

    payload = {
        "period": ym,
        "previous_period": prev_ym,
        "current": current,
        "previous": previous,
        "reviews": reviews,
        "recommendations": recommendations,
    }
    return jsonify(payload)


def _aggregate(uid, year, month):
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    exp = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    transaction_count = (
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
        )
        .scalar()
    )
    category_rows = (
        db.session.query(
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == uid),
        )
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    bills_total = (
        db.session.query(func.coalesce(func.sum(Bill.amount), 0))
        .filter(Bill.user_id == uid, Bill.active.is_(True))
        .scalar()
    )
    return {
        "total_income": float(income or 0),
        "total_expenses": float(exp or 0),
        "net_flow": float((income or 0) - (exp or 0)),
        "transaction_count": transaction_count or 0,
        "categories": [
            {
                "name": r.category_name,
                "amount": float(r.total_amount or 0),
            }
            for r in category_rows
        ],
        "bills_total": float(bills_total or 0),
    }


def _build_reviews(current, previous):
    reviews = []
    cur_exp = current["total_expenses"]
    prev_exp = previous["total_expenses"]
    change = cur_exp - prev_exp
    pct = ((change / prev_exp) * 100) if prev_exp > 0 else 0

    if abs(pct) >= 15:
        direction = "increase" if pct > 0 else "decrease"
        severity = "high" if abs(pct) >= 30 else "medium"
        reviews.append(
            {
                "type": "spending_change",
                "severity": severity,
                "title": f"Expenses {direction}d by {abs(pct):.0f}%",
                "description": f"Your expenses went from ${prev_exp:.2f} to ${cur_exp:.2f}. "
                + (
                    "Review discretionary spending."
                    if pct > 0
                    else "Keep up the good work!"
                ),
                "change_pct": round(pct, 1),
            }
        )

    top_current = current["categories"][:1]
    top_previous = previous["categories"][:1]
    if top_current and top_previous:
        tc = top_current[0]
        tp = top_previous[0]
        if tc["name"] != tp["name"]:
            reviews.append(
                {
                    "type": "top_category_shift",
                    "severity": "medium",
                    "title": f"Top category shifted to {tc['name']}",
                    "description": f"Your biggest expense category changed from {tp['name']} to {tc['name']}.",
                    "category": tc["name"],
                }
            )

    if current["net_flow"] < 0:
        reviews.append(
            {
                "type": "negative_flow",
                "severity": "high",
                "title": "Negative cash flow detected",
                "description": f"You spent ${abs(current['net_flow']):.2f} more than you earned. "
                "Consider reducing non-essential expenses.",
                "amount": round(abs(current["net_flow"]), 2),
            }
        )

    savings_rate = (
        ((current["net_flow"] / current["total_income"]) * 100)
        if current["total_income"] > 0
        else 0
    )
    if savings_rate < 10 and current["total_income"] > 0:
        reviews.append(
            {
                "type": "low_savings_rate",
                "severity": "medium",
                "title": f"Savings rate at {savings_rate:.0f}%",
                "description": "Aim for at least 20% savings rate. "
                "Look for areas to trim expenses or increase income.",
                "savings_rate": round(savings_rate, 1),
            }
        )

    if current["bills_total"] > current["total_income"] * 0.5:
        reviews.append(
            {
                "type": "high_bills_ratio",
                "severity": "high",
                "title": "Bills exceed 50% of income",
                "description": "Your recurring bills are a large portion of income. "
                "Consider negotiating or switching providers.",
                "bills_ratio": round(
                    (current["bills_total"] / current["total_income"]) * 100, 1
                ),
            }
        )

    if current["transaction_count"] == 0:
        reviews.append(
            {
                "type": "no_transactions",
                "severity": "info",
                "title": "No transactions this month",
                "description": "Start tracking your expenses to get meaningful insights.",
            }
        )

    return reviews


def _build_recommendations(current, previous):
    recommendations = []

    top_category = current["categories"][0] if current["categories"] else None
    if top_category and top_category["amount"] > current["total_expenses"] * 0.4:
        recommendations.append(
            {
                "action": "review_top_category",
                "priority": "high",
                "message": f"Review spending on '{top_category['name']}' — "
                f"it makes up {(top_category['amount'] / current['total_expenses'] * 100):.0f}% of expenses.",
                "category": top_category["name"],
            }
        )

    if current["total_expenses"] > 0 and previous["total_expenses"] > 0:
        trend = "increasing" if current["total_expenses"] > previous["total_expenses"] else "decreasing"
        recommendations.append(
            {
                "action": "trend_awareness",
                "priority": "medium",
                "message": f"Your spending is {trend}. "
                + (
                    "Set a budget to keep it in check."
                    if trend == "increasing"
                    else "Great discipline! Consider investing the surplus."
                ),
                "trend": trend,
            }
        )

    if current["total_income"] == 0:
        recommendations.append(
            {
                "action": "track_income",
                "priority": "medium",
                "message": "No income tracked this month. Add income entries for accurate net flow.",
            }
        )

    recommendations.append(
        {
            "action": "set_budget",
            "priority": "low",
            "message": "Set up category budgets to proactively manage spending.",
        }
    )

    return recommendations


def _is_valid_month(ym: str) -> bool:
    if len(ym) != 7 or ym[4] != "-":
        return False
    parts = ym.split("-")
    if not (parts[0].isdigit() and parts[1].isdigit()):
        return False
    m = int(parts[1])
    return 1 <= m <= 12
