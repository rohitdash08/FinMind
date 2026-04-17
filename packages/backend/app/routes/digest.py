from datetime import date, timedelta
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Category, Bill
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


def _week_range(ref_date=None):
    d = ref_date or date.today()
    week_start = d - timedelta(days=d.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def _weekly_expenses(uid, start, end):
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("cat_name"),
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
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
    return rows


def _weekly_income(uid, start, end):
    total = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    return float(total or 0)


def _upcoming_bills(uid, from_date, days=14):
    cutoff = from_date + timedelta(days=days)
    bills = (
        Bill.query.filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= from_date,
            Bill.next_due_date <= cutoff,
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    return [
        {
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "due_date": b.next_due_date.isoformat(),
            "days_until": (b.next_due_date - from_date).days,
        }
        for b in bills
    ]


def _top_expense_transactions(uid, start, end, limit=5):
    rows = (
        Expense.query.filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "amount": float(e.amount),
            "currency": e.currency,
            "notes": e.notes or "",
            "date": e.spent_at.isoformat(),
            "category_id": e.category_id,
        }
        for e in rows
    ]


def _compare_weeks(uid, current_start, current_end):
    prev_start = current_start - timedelta(days=7)
    prev_end = current_start - timedelta(days=1)

    curr_rows = _weekly_expenses(uid, current_start, current_end)
    prev_rows = _weekly_expenses(uid, prev_start, prev_end)

    curr_total = sum(float(r.total) for r in curr_rows)
    prev_total = sum(float(r.total) for r in prev_rows)

    if prev_total > 0:
        change_pct = round(((curr_total - prev_total) / prev_total) * 100, 1)
    else:
        change_pct = 0.0

    curr_cats = {r.cat_name: float(r.total) for r in curr_rows}
    prev_cats = {r.cat_name: float(r.total) for r in prev_rows}
    all_cats = set(curr_cats) | set(prev_cats)

    category_changes = []
    for cat in all_cats:
        c = curr_cats.get(cat, 0)
        p = prev_cats.get(cat, 0)
        if p > 0:
            pct = round(((c - p) / p) * 100, 1)
        elif c > 0:
            pct = 100.0
        else:
            pct = 0.0
        category_changes.append({
            "category": cat,
            "this_week": round(c, 2),
            "last_week": round(p, 2),
            "change_pct": pct,
        })

    category_changes.sort(key=lambda x: abs(x["change_pct"]), reverse=True)

    return {
        "total_this_week": round(curr_total, 2),
        "total_last_week": round(prev_total, 2),
        "change_pct": change_pct,
        "category_changes": category_changes[:5],
    }


def _generate_insights(comparison, categories, upcoming_bills):
    insights = []

    if comparison["change_pct"] > 20:
        insights.append(
            f"Spending is up {comparison['change_pct']}% compared to last week. "
            f"Consider reviewing your top categories."
        )
    elif comparison["change_pct"] < -20:
        insights.append(
            f"Great job! Spending dropped {abs(comparison['change_pct'])}% vs last week."
        )

    if categories:
        top = categories[0]
        share = (
            round(top["total"] / comparison["total_this_week"] * 100, 1)
            if comparison["total_this_week"] > 0
            else 0
        )
        if share > 40:
            insights.append(
                f"'{top['cat_name']}' accounts for {share}% of this week's spending. "
                f"Consider setting a sub-budget for it."
            )

    for change in comparison.get("category_changes", [])[:3]:
        if change["change_pct"] > 50 and change["this_week"] > 0:
            insights.append(
                f"'{change['category']}' spiked {change['change_pct']}% "
                f"({change['last_week']} -> {change['this_week']})."
            )

    if upcoming_bills:
        urgent = [b for b in upcoming_bills if b["days_until"] <= 3]
        if urgent:
            names = ", ".join(b["name"] for b in urgent)
            insights.append(f"Bills due within 3 days: {names}")

    if not insights:
        insights.append("Your spending looks stable this week. Keep it up!")

    return insights


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    week_start, week_end = _week_range()

    rows = _weekly_expenses(uid, week_start, week_end)
    income = _weekly_income(uid, week_start, week_end)
    total_expenses = sum(float(r.total) for r in rows)
    comparison = _compare_weeks(uid, week_start, week_end)
    bills = _upcoming_bills(uid, week_end)
    top_txns = _top_expense_transactions(uid, week_start, week_end)

    categories = [
        {
            "category_id": r.category_id,
            "category_name": r.cat_name,
            "total": float(r.total),
            "transaction_count": r.count,
            "share_pct": (
                round(float(r.total) / total_expenses * 100, 1)
                if total_expenses > 0
                else 0
            ),
        }
        for r in rows
    ]

    insights = _generate_insights(comparison, categories, bills)
    logger.info("Weekly digest served user=%s week=%s", uid, week_start.isoformat())

    return jsonify({
        "period": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
        },
        "summary": {
            "total_income": round(income, 2),
            "total_expenses": round(total_expenses, 2),
            "net_flow": round(income - total_expenses, 2),
            "transaction_count": sum(r.count for r in rows),
        },
        "comparison_with_last_week": comparison,
        "category_breakdown": categories,
        "top_transactions": top_txns,
        "upcoming_bills": bills,
        "insights": insights,
    })


@bp.get("/weekly/history")
@jwt_required()
def weekly_history():
    uid = int(get_jwt_identity())
    weeks = []
    ref = date.today()

    for i in range(4):
        ws, we = _week_range(ref - timedelta(weeks=i))
        rows = _weekly_expenses(uid, ws, we)
        total = sum(float(r.total) for r in rows)
        inc = _weekly_income(uid, ws, we)
        weeks.append({
            "week_start": ws.isoformat(),
            "week_end": we.isoformat(),
            "total_expenses": round(total, 2),
            "total_income": round(inc, 2),
            "net_flow": round(inc - total, 2),
            "top_category": rows[0].cat_name if rows else None,
        })

    return jsonify({"weeks": weeks})
