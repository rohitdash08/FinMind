from datetime import date, timedelta
from collections import defaultdict

from sqlalchemy import func, extract
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Expense, Category, Bill

bp = Blueprint("digest", __name__)


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _get_weekly_expenses(uid: int, weeks: int = 4):
    """Return expenses grouped by week and category for the last N weeks."""
    today = date.today()
    start = _week_start(today) - timedelta(weeks=weeks * 7)

    rows = (
        db.session.query(
            func.date_trunc("week", Expense.spent_at).label("week_start"),
            Category.name.label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
            func.count(Expense.id).label("txn_count"),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.expense_type == "EXPENSE",
        )
        .group_by("week_start", "category_name")
        .order_by("week_start", func.sum(Expense.amount).desc())
        .all()
    )

    weeks_map: dict[str, dict] = defaultdict(lambda: {"categories": [], "total": 0.0, "txn_count": 0})
    for row in rows:
        ws = row.week_start.strftime("%Y-%m-%d") if row.week_start else "unknown"
        cat = row.category_name or "Uncategorized"
        total = float(row.total or 0)
        weeks_map[ws]["categories"].append({"category": cat, "amount": total, "count": row.txn_count})
        weeks_map[ws]["total"] += total
        weeks_map[ws]["txn_count"] += row.txn_count

    # Fill in missing weeks
    result = []
    for i in range(weeks):
        ws = _week_start(today) - timedelta(weeks=(weeks - 1 - i) * 7)
        key = ws.strftime("%Y-%m-%d")
        entry = weeks_map.get(key, {"categories": [], "total": 0.0, "txn_count": 0})
        entry["week_start"] = key
        entry["week_end"] = (ws + timedelta(days=6)).strftime("%Y-%m-%d")
        result.append(entry)

    return result


def _compute_wow_deltas(weeks_data: list[dict]) -> list[dict]:
    """Add week-over-week delta and trend to each week."""
    for i, week in enumerate(weeks_data):
        if i == 0:
            week["wow_delta"] = None
            week["wow_delta_pct"] = None
            week["trend"] = "flat"
            continue
        prev_total = weeks_data[i - 1]["total"]
        curr_total = week["total"]
        if prev_total > 0:
            delta = curr_total - prev_total
            pct = round((delta / prev_total) * 100, 1)
            week["wow_delta"] = round(delta, 2)
            week["wow_delta_pct"] = pct
            week["trend"] = "up" if delta > 0 else "down" if delta < 0 else "flat"
        else:
            week["wow_delta"] = round(curr_total, 2)
            week["wow_delta_pct"] = None
            week["trend"] = "up" if curr_total > 0 else "flat"
    return weeks_data


def _get_top_categories(weeks_data: list[dict], top_n: int = 5) -> list[dict]:
    """Aggregate top categories across all weeks."""
    cat_totals: dict[str, float] = defaultdict(float)
    for week in weeks_data:
        for cat in week["categories"]:
            cat_totals[cat["category"]] += cat["amount"]
    sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [{"category": name, "total": round(total, 2)} for name, total in sorted_cats]


def _get_upcoming_bills(uid: int) -> list[dict]:
    """Return bills due in the next 7 days."""
    today = date.today()
    upcoming = today + timedelta(days=7)
    bills = (
        Bill.query
        .filter(
            Bill.user_id == uid,
            Bill.next_due_date >= today,
            Bill.next_due_date <= upcoming,
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount or 0),
            "currency": b.currency or "INR",
            "due_date": b.next_due_date.strftime("%Y-%m-%d") if b.next_due_date else None,
            "cadence": b.cadence or "monthly",
        }
        for b in bills
    ]


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    weeks = request.args.get("weeks", 4, type=int)
    weeks = max(1, min(12, weeks))

    weeks_data = _get_weekly_expenses(uid, weeks)
    weeks_data = _compute_wow_deltas(weeks_data)
    top_categories = _get_top_categories(weeks_data)
    upcoming = _get_upcoming_bills(uid)

    overall_total = sum(w["total"] for w in weeks_data)
    overall_count = sum(w["txn_count"] for w in weeks_data)
    avg_weekly = round(overall_total / len(weeks_data), 2) if weeks_data else 0

    return jsonify({
        "period": {
            "weeks": len(weeks_data),
            "from": weeks_data[0]["week_start"] if weeks_data else None,
            "to": weeks_data[-1]["week_end"] if weeks_data else None,
        },
        "summary": {
            "total_spending": round(overall_total, 2),
            "total_transactions": overall_count,
            "average_weekly": avg_weekly,
        },
        "weekly_breakdown": weeks_data,
        "top_categories": top_categories,
        "upcoming_bills": upcoming,
    })


def _is_valid_week_param(val: str | None) -> bool:
    if val is None:
        return True
    try:
        n = int(val)
        return 1 <= n <= 12
    except (ValueError, TypeError):
        return False
