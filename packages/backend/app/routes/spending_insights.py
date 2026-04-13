from datetime import date, timedelta
from collections import defaultdict

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import Expense, Category
import logging

bp = Blueprint("spending_insights", __name__)
logger = logging.getLogger("finmind.spending_insights")

CONCENTRATION_THRESHOLD = 0.40  # warn if one category > 40%
SPIKE_THRESHOLD = 0.30  # > 30% increase
DROP_THRESHOLD = 0.30  # > 30% decrease


@bp.get("")
@jwt_required()
def get_spending_insights():
    uid = int(get_jwt_identity())

    # Determine date range: default last 30 days
    days = int(request.args.get("days", "30"))
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # Previous period for comparison
    prev_start = start_date - timedelta(days=days)
    prev_end = start_date - timedelta(days=1)

    # Current period expenses by category
    current_rows = (
        db.session.query(
            Expense.category_id,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
        )
        .group_by(Expense.category_id)
        .all()
    )

    # Previous period expenses by category
    prev_rows = (
        db.session.query(
            Expense.category_id,
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= prev_start,
            Expense.spent_at <= prev_end,
        )
        .group_by(Expense.category_id)
        .all()
    )

    prev_by_cat = {row.category_id: float(row.total) for row in prev_rows}

    # Load category names
    cat_ids = {row.category_id for row in current_rows if row.category_id}
    cat_ids.update(cid for cid in prev_by_cat if cid)
    categories_map = {}
    if cat_ids:
        cats = db.session.query(Category).filter(Category.id.in_(cat_ids)).all()
        categories_map = {c.id: c.name for c in cats}

    total_spent = sum(float(row.total) for row in current_rows)
    daily_average = round(total_spent / days, 2) if days > 0 else 0.0

    insights = []
    categories = []

    for row in current_rows:
        cat_id = row.category_id
        cat_name = categories_map.get(cat_id, "Uncategorized")
        current_total = float(row.total)
        prev_total = prev_by_cat.get(cat_id, 0.0)

        cat_entry = {
            "category_id": cat_id,
            "category_name": cat_name,
            "current_total": round(current_total, 2),
            "previous_total": round(prev_total, 2),
            "transaction_count": row.count,
        }

        # Spike detection
        if prev_total > 0:
            change_pct = (current_total - prev_total) / prev_total
            cat_entry["change_pct"] = round(change_pct * 100, 1)

            if change_pct > SPIKE_THRESHOLD:
                insights.append({
                    "type": "spike",
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "change_pct": round(change_pct * 100, 1),
                    "explanation": (
                        f"Spending on {cat_name} increased by "
                        f"{round(change_pct * 100, 1)}% compared to the "
                        f"previous {days}-day period."
                    ),
                })
            elif change_pct < -DROP_THRESHOLD:
                insights.append({
                    "type": "drop",
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "change_pct": round(change_pct * 100, 1),
                    "explanation": (
                        f"Spending on {cat_name} decreased by "
                        f"{round(abs(change_pct) * 100, 1)}% compared to the "
                        f"previous {days}-day period."
                    ),
                })
        elif current_total > 0:
            cat_entry["change_pct"] = None
            insights.append({
                "type": "new_category",
                "category_id": cat_id,
                "category_name": cat_name,
                "explanation": (
                    f"New spending detected in {cat_name} with no "
                    f"activity in the previous period."
                ),
            })

        # Concentration warning
        if total_spent > 0 and (current_total / total_spent) > CONCENTRATION_THRESHOLD:
            pct = round((current_total / total_spent) * 100, 1)
            insights.append({
                "type": "concentration",
                "category_id": cat_id,
                "category_name": cat_name,
                "concentration_pct": pct,
                "explanation": (
                    f"{cat_name} accounts for {pct}% of total spending. "
                    f"Consider diversifying or reviewing this category."
                ),
            })

        categories.append(cat_entry)

    logger.info("Spending insights served user=%s insights=%s", uid, len(insights))

    return jsonify({
        "insights": insights,
        "categories": categories,
        "total_spent": round(total_spent, 2),
        "daily_average": daily_average,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days,
        },
    })
