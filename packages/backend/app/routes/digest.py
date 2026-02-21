"""Smart Digest API routes for weekly financial summaries."""
from flask import Blueprint, request, jsonify, g
from ..extensions import db
from ..models import Expense, Category, Bill
from datetime import datetime, timedelta
from sqlalchemy import func, extract
from decimal import Decimal

bp = Blueprint("digest", __name__, url_prefix="/digest")


def get_week_range(week_offset=0):
    """Get start and end dates for a week.
    
    Args:
        week_offset: Number of weeks ago (0 = current week, 1 = last week, etc.)
    
    Returns:
        tuple: (start_date, end_date)
    """
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday()) - timedelta(weeks=week_offset)
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week


def get_week_label(start_date, end_date):
    """Get a human-readable label for the week."""
    return f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"


@bp.route("/weekly", methods=["GET"])
def get_weekly_digest():
    """Get weekly financial digest with trends and insights."""
    # Get week offset from query param (default: last week)
    week_offset = request.args.get("week", default=1, type=int)
    
    # Current week (for comparison)
    current_start, current_end = get_week_range(0)
    # Target week
    target_start, target_end = get_week_range(week_offset)
    # Previous week (for trend comparison)
    prev_start, prev_end = get_week_range(week_offset + 1)
    
    # Get expenses for target week
    target_expenses = Expense.query.filter(
        Expense.user_id == g.user.id,
        Expense.spent_at >= target_start,
        Expense.spent_at <= target_end
    ).all()
    
    # Get expenses for previous week (for comparison)
    prev_expenses = Expense.query.filter(
        Expense.user_id == g.user.id,
        Expense.spent_at >= prev_start,
        Expense.spent_at <= prev_end
    ).all()
    
    # Calculate totals
    target_total = sum(float(e.amount) for e in target_expenses)
    prev_total = sum(float(e.amount) for e in prev_expenses)
    
    # Calculate week-over-week change
    if prev_total > 0:
        wow_change = ((target_total - prev_total) / prev_total) * 100
    else:
        wow_change = 0 if target_total == 0 else 100
    
    # Group by category
    category_breakdown = {}
    for expense in target_expenses:
        cat_name = "Uncategorized"
        if expense.category_id:
            cat = Category.query.get(expense.category_id)
            if cat:
                cat_name = cat.name
        
        if cat_name not in category_breakdown:
            category_breakdown[cat_name] = {"amount": 0, "count": 0}
        category_breakdown[cat_name]["amount"] += float(expense.amount)
        category_breakdown[cat_name]["count"] += 1
    
    # Sort categories by amount
    sorted_categories = sorted(
        category_breakdown.items(),
        key=lambda x: x[1]["amount"],
        reverse=True
    )
    
    # Get top spending category
    top_category = sorted_categories[0] if sorted_categories else (None, {"amount": 0, "count": 0})
    
    # Daily spending pattern
    daily_spending = {}
    for expense in target_expenses:
        day_name = expense.spent_at.strftime("%A")
        if day_name not in daily_spending:
            daily_spending[day_name] = 0
        daily_spending[day_name] += float(expense.amount)
    
    # Get upcoming bills
    upcoming_bills = Bill.query.filter(
        Bill.user_id == g.user.id,
        Bill.active == True,
        Bill.next_due_date >= datetime.now().date(),
        Bill.next_due_date <= datetime.now().date() + timedelta(days=7)
    ).all()
    
    upcoming_bills_total = sum(float(b.amount) for b in upcoming_bills)
    
    # Generate insights
    insights = []
    
    # Insight 1: Spending comparison
    if wow_change > 20:
        insights.append({
            "type": "warning",
            "message": f"Your spending increased by {wow_change:.1f}% compared to last week."
        })
    elif wow_change < -20:
        insights.append({
            "type": "success",
            "message": f"Great job! You spent {abs(wow_change):.1f}% less than last week."
        })
    
    # Insight 2: Top category
    if top_category[0]:
        percentage = (top_category[1]["amount"] / target_total * 100) if target_total > 0 else 0
        insights.append({
            "type": "info",
            "message": f"Your highest spending category was '{top_category[0]}' at {percentage:.1f}% of total."
        })
    
    # Insight 3: Daily pattern
    if daily_spending:
        max_day = max(daily_spending.items(), key=lambda x: x[1])
        insights.append({
            "type": "info",
            "message": f"You spent the most on {max_day[0]} ({g.user.preferred_currency} {max_day[1]:,.2f})."
        })
    
    # Insight 4: Upcoming bills
    if upcoming_bills:
        insights.append({
            "type": "reminder",
            "message": f"You have {len(upcoming_bills)} bill(s) due this week, totaling {g.user.preferred_currency} {upcoming_bills_total:,.2f}."
        })
    
    # Build response
    digest = {
        "week_label": get_week_label(target_start, target_end),
        "week_start": target_start.isoformat(),
        "week_end": target_end.isoformat(),
        "summary": {
            "total_spent": round(target_total, 2),
            "currency": g.user.preferred_currency,
            "transaction_count": len(target_expenses),
            "avg_daily": round(target_total / 7, 2) if target_total > 0 else 0
        },
        "comparison": {
            "previous_week_total": round(prev_total, 2),
            "week_over_week_change": round(wow_change, 2),
            "trend": "up" if wow_change > 5 else "down" if wow_change < -5 else "stable"
        },
        "category_breakdown": [
            {
                "category": cat,
                "amount": round(data["amount"], 2),
                "count": data["count"],
                "percentage": round((data["amount"] / target_total * 100), 2) if target_total > 0 else 0
            }
            for cat, data in sorted_categories
        ],
        "daily_spending": daily_spending,
        "top_spending_category": {
            "name": top_category[0],
            "amount": round(top_category[1]["amount"], 2),
            "count": top_category[1]["count"]
        } if top_category[0] else None,
        "upcoming_bills": {
            "count": len(upcoming_bills),
            "total_amount": round(upcoming_bills_total, 2),
            "bills": [
                {
                    "id": b.id,
                    "name": b.name,
                    "amount": float(b.amount),
                    "due_date": b.next_due_date.isoformat()
                }
                for b in upcoming_bills
            ]
        },
        "insights": insights
    }
    
    return jsonify({"digest": digest}), 200


@bp.route("/weekly/history", methods=["GET"])
def get_weekly_history():
    """Get spending history for the last N weeks."""
    weeks = request.args.get("weeks", default=4, type=int)
    weeks = min(weeks, 12)  # Cap at 12 weeks
    
    history = []
    
    for i in range(weeks):
        start, end = get_week_range(i + 1)  # Start from last week
        
        expenses = Expense.query.filter(
            Expense.user_id == g.user.id,
            Expense.spent_at >= start,
            Expense.spent_at <= end
        ).all()
        
        total = sum(float(e.amount) for e in expenses)
        
        history.append({
            "week_label": get_week_label(start, end),
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "total_spent": round(total, 2),
            "transaction_count": len(expenses)
        })
    
    return jsonify({"history": history}), 200


@bp.route("/trends", methods=["GET"])
def get_trends():
    """Get spending trends analysis."""
    # Get last 4 weeks of data
    weeks_data = []
    category_trends = {}
    
    for i in range(4):
        start, end = get_week_range(i + 1)
        
        expenses = Expense.query.filter(
            Expense.user_id == g.user.id,
            Expense.spent_at >= start,
            Expense.spent_at <= end
        ).all()
        
        total = sum(float(e.amount) for e in expenses)
        weeks_data.append({
            "week": get_week_label(start, end),
            "total": total
        })
        
        # Track category trends
        for expense in expenses:
            cat_name = "Uncategorized"
            if expense.category_id:
                cat = Category.query.get(expense.category_id)
                if cat:
                    cat_name = cat.name
            
            if cat_name not in category_trends:
                category_trends[cat_name] = []
            category_trends[cat_name].append(float(expense.amount))
    
    # Calculate trends
    if len(weeks_data) >= 2:
        recent_avg = sum(w["total"] for w in weeks_data[:2]) / 2
        older_avg = sum(w["total"] for w in weeks_data[2:]) / 2 if len(weeks_data) > 2 else recent_avg
        
        if older_avg > 0:
            trend_percentage = ((recent_avg - older_avg) / older_avg) * 100
        else:
            trend_percentage = 0
        
        spending_trend = "increasing" if trend_percentage > 10 else "decreasing" if trend_percentage < -10 else "stable"
    else:
        trend_percentage = 0
        spending_trend = "insufficient_data"
    
    # Find trending categories
    trending_categories = []
    for cat, amounts in category_trends.items():
        if len(amounts) >= 2:
            recent = sum(amounts[:2]) / 2
            older = sum(amounts[2:]) / 2 if len(amounts) > 2 else recent
            if older > 0:
                change = ((recent - older) / older) * 100
                if abs(change) > 20:  # Significant change
                    trending_categories.append({
                        "category": cat,
                        "trend": "increasing" if change > 0 else "decreasing",
                        "change_percentage": round(change, 2)
                    })
    
    return jsonify({
        "trends": {
            "weekly_data": weeks_data,
            "spending_trend": spending_trend,
            "trend_percentage": round(trend_percentage, 2),
            "trending_categories": sorted(trending_categories, key=lambda x: abs(x["change_percentage"]), reverse=True)[:5]
        }
    }), 200
