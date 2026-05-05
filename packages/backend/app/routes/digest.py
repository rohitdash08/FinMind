from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, text
from ..extensions import db
from ..models import Expense, Bill, Category
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


def get_week_start(d: date) -> date:
    """Get the Monday of the week for a given date."""
    return d - timedelta(days=d.weekday())


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """
    Weekly spending digest with WoW trend analysis, category breakdown, and upcoming bills.
    
    Query params:
        weeks: number of weeks to look back (4, 8, 12). Default 4.
    """
    uid = int(get_jwt_identity())
    
    try:
        weeks = int(request.args.get("weeks", "4"))
        if weeks not in (4, 8, 12):
            weeks = 4
    except ValueError:
        weeks = 4
    
    today = date.today()
    end_date = get_week_start(today) + timedelta(days=6)  # End of current week
    start_date = end_date - timedelta(weeks=weeks - 1, days=6)  # Start of N weeks ago
    
    # Get expenses grouped by week and category
    # Using date_trunc to group by week (Monday start)
    query = text("""
        SELECT 
            date_trunc('week', e.spent_at)::date as week_start,
            c.id as category_id,
            c.name as category_name,
            SUM(e.amount) as total
        FROM expenses e
        LEFT JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = :uid
            AND e.spent_at >= :start_date
            AND e.spent_at <= :end_date
        GROUP BY date_trunc('week', e.spent_at)::date, c.id, c.name
        ORDER BY week_start DESC, total DESC
    """)
    
    result = db.session.execute(query, {
        "uid": uid,
        "start_date": start_date,
        "end_date": end_date
    })
    rows = result.fetchall()
    
    # Organize data by week
    weekly_data = {}
    for row in rows:
        week_start = row.week_start
        if week_start not in weekly_data:
            weekly_data[week_start] = {"total": 0, "categories": []}
        weekly_data[week_start]["total"] += float(row.total or 0)
        if row.category_id:
            weekly_data[week_start]["categories"].append({
                "category_id": row.category_id,
                "category_name": row.category_name,
                "amount": float(row.total or 0)
            })
    
    # Build weekly summaries with WoW delta
    weeks_list = []
    sorted_weeks = sorted(weekly_data.keys(), reverse=True)
    prev_week_total = None
    
    for week_start in sorted_weeks:
        week_total = weekly_data[week_start]["total"]
        
        # Calculate WoW delta
        delta_percent = None
        trend = "flat"
        if prev_week_total is not None and prev_week_total > 0:
            delta_percent = ((week_total - prev_week_total) / prev_week_total) * 100
            if delta_percent > 5:
                trend = "up"
            elif delta_percent < -5:
                trend = "down"
            else:
                trend = "flat"
        
        # Sort categories by amount and take top 5
        categories = sorted(
            weekly_data[week_start]["categories"],
            key=lambda x: x["amount"],
            reverse=True
        )[:5]
        
        weeks_list.append({
            "week_start": week_start.isoformat(),
            "week_end": (week_start + timedelta(days=6)).isoformat(),
            "total": round(week_total, 2),
            "delta_percent": round(delta_percent, 1) if delta_percent is not None else None,
            "trend": trend,
            "categories": categories
        })
        
        prev_week_total = week_total
    
    # Get overall category breakdown for the period
    cat_query = text("""
        SELECT 
            c.id as category_id,
            c.name as category_name,
            SUM(e.amount) as total
        FROM expenses e
        LEFT JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = :uid
            AND e.spent_at >= :start_date
            AND e.spent_at <= :end_date
            AND c.id IS NOT NULL
        GROUP BY c.id, c.name
        ORDER BY total DESC
        LIMIT 5
    """)
    
    cat_result = db.session.execute(cat_query, {
        "uid": uid,
        "start_date": start_date,
        "end_date": end_date
    })
    cat_rows = cat_result.fetchall()
    
    top_categories = [
        {
            "category_id": row.category_id,
            "category_name": row.category_name,
            "amount": float(row.total or 0)
        }
        for row in cat_rows
    ]
    
    # Get upcoming bills (next 7 days)
    upcoming_end = today + timedelta(days=7)
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active == True,
            Bill.next_due_date >= today,
            Bill.next_due_date <= upcoming_end
        )
        .order_by(Bill.next_due_date)
        .all()
    )
    
    upcoming_bills = [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat()
        }
        for b in bills
    ]
    
    # Calculate summary totals
    current_week_total = weeks_list[0]["total"] if weeks_list else 0
    previous_weeks_total = sum(w["total"] for w in weeks_list[1:]) if len(weeks_list) > 1 else 0
    
    logger.info("Weekly digest user=%s weeks=%s", uid, weeks)
    
    return jsonify({
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "weeks": weeks
        },
        "summary": {
            "current_week_total": current_week_total,
            "previous_weeks_total": round(previous_weeks_total, 2),
            "current_week": weeks_list[0]["week_start"] if weeks_list else None
        },
        "weeks": weeks_list,
        "top_categories": top_categories,
        "upcoming_bills": upcoming_bills
    })