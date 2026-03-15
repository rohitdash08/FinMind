from datetime import date, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Category, Expense
from ..services.cache import cache_get, cache_set
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


def _parse_week(raw: str) -> tuple[date, date] | None:
    try:
        year_str, week_str = raw.split("-W")
        year = int(year_str)
        week = int(week_str)
        if not (1 <= week <= 53):
            return None
        start = date.fromisocalendar(year, week, 1)
        end = start + timedelta(days=6)
        return start, end
    except (ValueError, AttributeError):
        return None


def _week_key(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _digest_cache_key(uid: int, week: str) -> str:
    return f"user:{uid}:weekly_digest:{week}"


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    week_param = (request.args.get("week") or "").strip()
    if not week_param:
        today = date.today()
        week_param = _week_key(today)

    parsed = _parse_week(week_param)
    if parsed is None:
        return jsonify(error="invalid week, expected YYYY-WNN"), 400

    start, end = parsed

    cached = cache_get(_digest_cache_key(uid, week_param))
    if cached:
        return jsonify(cached)

    total_spent = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
        or 0
    )

    total_income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
        or 0
    )

    category_rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
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
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    category_breakdown = []
    for r in category_rows:
        amt = float(r.total_amount or 0)
        pct = round((amt / total_spent) * 100, 2) if total_spent > 0 else 0
        category_breakdown.append(
            {
                "category_id": r.category_id,
                "category_name": r.category_name,
                "amount": amt,
                "share_pct": pct,
            }
        )

    prev_start = start - timedelta(days=7)
    prev_end = end - timedelta(days=7)

    prev_spent = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= prev_start,
            Expense.spent_at <= prev_end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
        or 0
    )

    if prev_spent > 0:
        wow_change = round(((total_spent - prev_spent) / prev_spent) * 100, 2)
    elif total_spent > 0:
        wow_change = 100.0
    else:
        wow_change = 0.0

    trends = []
    if len(category_breakdown) > 0:
        top = category_breakdown[0]
        trends.append(
            f"Top spending category: {top['category_name']}"
            f" ({top['share_pct']}% of total)"
        )
    if wow_change > 10:
        trends.append(f"Spending increased {wow_change}% compared to previous week")
    elif wow_change < -10:
        trends.append(
            f"Spending decreased {abs(wow_change)}% compared to previous week"
        )
    else:
        trends.append("Spending is roughly stable week-over-week")

    insights = []
    if total_spent > total_income and total_income > 0:
        insights.append("You spent more than you earned this week")
    if total_spent == 0:
        insights.append("No expenses recorded this week")
    if len(category_breakdown) == 1 and total_spent > 0:
        insights.append(
            "All spending is in one category — consider diversifying tracking"
        )
    if len(category_breakdown) > 5:
        insights.append("Spending spread across many categories this week")

    payload = {
        "week": week_param,
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "total_spent": total_spent,
        "total_income": total_income,
        "category_breakdown": category_breakdown,
        "week_over_week_change": wow_change,
        "trends": trends,
        "insights": insights,
    }

    cache_set(_digest_cache_key(uid, week_param), payload, ttl_seconds=600)
    logger.info("Weekly digest served user=%s week=%s", uid, week_param)
    return jsonify(payload)
