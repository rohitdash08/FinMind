"""Spending velocity & burn rate analysis.

Tracks how fast money is being spent, projects when budget will be exhausted,
and provides velocity metrics across time periods.
"""

from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category


def analyze_burn_rate(user_id: int, days: int = 30) -> dict:
    """Calculate spending velocity and burn rate over the given period."""
    end = date.today()
    start = end - timedelta(days=days)

    rows = (
        db.session.query(Expense.date, func.sum(Expense.amount))
        .filter(Expense.user_id == user_id, Expense.date >= start, Expense.date <= end)
        .group_by(Expense.date)
        .order_by(Expense.date)
        .all()
    )

    if not rows:
        return {
            "period_days": days,
            "total_spent": 0,
            "daily_average": 0,
            "weekly_average": 0,
            "monthly_projected": 0,
            "velocity_trend": "insufficient_data",
            "daily_breakdown": [],
            "acceleration": 0,
        }

    daily = {r[0]: float(r[1]) for r in rows}
    total = sum(daily.values())
    active_days = len(daily)
    daily_avg = total / max(active_days, 1)

    # Fill gaps for trend analysis
    all_days = []
    current = start
    while current <= end:
        all_days.append({"date": current.isoformat(), "amount": round(daily.get(current, 0), 2)})
        current += timedelta(days=1)

    # Velocity trend: compare first half vs second half
    amounts = [d["amount"] for d in all_days]
    mid = len(amounts) // 2
    first_half_avg = sum(amounts[:mid]) / max(mid, 1)
    second_half_avg = sum(amounts[mid:]) / max(len(amounts) - mid, 1)

    if first_half_avg == 0:
        acceleration = 100.0 if second_half_avg > 0 else 0.0
    else:
        acceleration = round((second_half_avg - first_half_avg) / first_half_avg * 100, 1)

    if acceleration > 10:
        trend = "accelerating"
    elif acceleration < -10:
        trend = "decelerating"
    else:
        trend = "steady"

    return {
        "period_days": days,
        "total_spent": round(total, 2),
        "daily_average": round(daily_avg, 2),
        "weekly_average": round(daily_avg * 7, 2),
        "monthly_projected": round(daily_avg * 30, 2),
        "velocity_trend": trend,
        "acceleration": acceleration,
        "active_days": active_days,
        "daily_breakdown": all_days,
    }


def budget_runway(user_id: int, budget: float, days: int = 30) -> dict:
    """Project when budget will be exhausted based on current burn rate."""
    burn = analyze_burn_rate(user_id, days)
    daily_avg = burn["daily_average"]

    if daily_avg <= 0:
        return {
            "budget": budget,
            "daily_burn": 0,
            "days_remaining": None,
            "projected_exhaustion": None,
            "status": "no_spending",
        }

    days_left = budget / daily_avg
    exhaustion = date.today() + timedelta(days=int(days_left))

    if days_left > 30:
        status = "healthy"
    elif days_left > 14:
        status = "caution"
    elif days_left > 7:
        status = "warning"
    else:
        status = "critical"

    return {
        "budget": budget,
        "daily_burn": daily_avg,
        "days_remaining": round(days_left, 1),
        "projected_exhaustion": exhaustion.isoformat(),
        "status": status,
        "monthly_projected": burn["monthly_projected"],
        "velocity_trend": burn["velocity_trend"],
    }


def category_velocity(user_id: int, days: int = 30) -> list[dict]:
    """Break down spending velocity by category."""
    end = date.today()
    start = end - timedelta(days=days)

    rows = (
        db.session.query(Category.name, func.sum(Expense.amount), func.count(Expense.id))
        .join(Category, Expense.category_id == Category.id)
        .filter(Expense.user_id == user_id, Expense.date >= start, Expense.date <= end)
        .group_by(Category.name)
        .all()
    )

    total = sum(float(r[1]) for r in rows) if rows else 0
    result = []
    for name, amount, count in rows:
        amt = float(amount)
        result.append({
            "category": name,
            "total": round(amt, 2),
            "daily_average": round(amt / days, 2),
            "transaction_count": count,
            "percentage": round(amt / total * 100, 1) if total > 0 else 0,
        })

    result.sort(key=lambda x: x["total"], reverse=True)
    return result


def weekly_comparison(user_id: int, weeks: int = 4) -> dict:
    """Compare spending across recent weeks."""
    end = date.today()
    start = end - timedelta(weeks=weeks)

    rows = (
        db.session.query(Expense.date, func.sum(Expense.amount))
        .filter(Expense.user_id == user_id, Expense.date >= start, Expense.date <= end)
        .group_by(Expense.date)
        .all()
    )

    daily = {r[0]: float(r[1]) for r in rows}

    week_data = []
    for w in range(weeks):
        w_end = end - timedelta(weeks=w)
        w_start = w_end - timedelta(days=6)
        total = sum(daily.get(w_start + timedelta(days=d), 0) for d in range(7))
        week_data.append({
            "week": f"W-{w}",
            "start": w_start.isoformat(),
            "end": w_end.isoformat(),
            "total": round(total, 2),
            "daily_avg": round(total / 7, 2),
        })

    week_data.reverse()

    totals = [w["total"] for w in week_data]
    if len(totals) >= 2 and totals[0] > 0:
        wow_change = round((totals[-1] - totals[0]) / totals[0] * 100, 1)
    else:
        wow_change = 0

    return {
        "weeks": week_data,
        "overall_change_pct": wow_change,
    }
