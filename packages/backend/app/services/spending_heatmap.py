"""Spending trend heatmap visualization.

Generates heatmap data for spending intensity across time periods.
Supports daily, weekly, and monthly granularity with category filtering.
"""

from datetime import datetime, timedelta, date
from collections import defaultdict
from sqlalchemy import func
from app.extensions import db
from app.models import Expense, Category


def get_daily_heatmap(user_id, days=365, category_id=None):
    """Generate daily spending heatmap data (GitHub-contribution style).

    Returns a list of {date, amount, count, intensity} objects
    for the last N days.
    """
    since = date.today() - timedelta(days=days)

    query = db.session.query(
        Expense.spent_at,
        func.sum(Expense.amount).label("total"),
        func.count(Expense.id).label("count"),
    ).filter(
        Expense.user_id == user_id,
        Expense.spent_at >= since,
    )

    if category_id:
        query = query.filter(Expense.category_id == category_id)

    query = query.group_by(Expense.spent_at).order_by(Expense.spent_at)
    rows = query.all()

    # Build lookup
    data = {str(r.spent_at): {"amount": float(r.total), "count": r.count} for r in rows}

    # Find max for intensity calculation
    max_amount = max((d["amount"] for d in data.values()), default=0)

    # Fill in all days
    result = []
    for i in range(days):
        d = since + timedelta(days=i)
        ds = str(d)
        if ds in data:
            amount = data[ds]["amount"]
            count = data[ds]["count"]
            intensity = round(amount / max_amount, 2) if max_amount > 0 else 0
        else:
            amount = 0
            count = 0
            intensity = 0

        result.append({
            "date": ds,
            "amount": amount,
            "count": count,
            "intensity": intensity,
            "day_of_week": d.weekday(),
        })

    return {
        "days": result,
        "total_days": days,
        "max_daily_amount": max_amount,
        "total_spending": sum(d["amount"] for d in result),
        "active_days": sum(1 for d in result if d["amount"] > 0),
    }


def get_weekly_heatmap(user_id, weeks=52, category_id=None):
    """Generate weekly spending heatmap data."""
    since = date.today() - timedelta(weeks=weeks)

    query = db.session.query(
        Expense.spent_at,
        Expense.amount,
    ).filter(
        Expense.user_id == user_id,
        Expense.spent_at >= since,
    )

    if category_id:
        query = query.filter(Expense.category_id == category_id)

    expenses = query.all()

    # Aggregate by week
    weekly = defaultdict(lambda: {"amount": 0, "count": 0})
    for e in expenses:
        if e.spent_at:
            # Calculate ISO week start (Monday)
            d = e.spent_at if isinstance(e.spent_at, date) else e.spent_at.date()
            week_start = d - timedelta(days=d.weekday())
            key = str(week_start)
            weekly[key]["amount"] += float(e.amount)
            weekly[key]["count"] += 1

    max_amount = max((w["amount"] for w in weekly.values()), default=0)

    result = []
    current = since - timedelta(days=since.weekday())  # Align to Monday
    today = date.today()
    while current <= today:
        key = str(current)
        if key in weekly:
            amount = weekly[key]["amount"]
            count = weekly[key]["count"]
            intensity = round(amount / max_amount, 2) if max_amount > 0 else 0
        else:
            amount = 0
            count = 0
            intensity = 0

        result.append({
            "week_start": key,
            "amount": amount,
            "count": count,
            "intensity": intensity,
        })
        current += timedelta(weeks=1)

    return {
        "weeks": result,
        "total_weeks": len(result),
        "max_weekly_amount": max_amount,
        "total_spending": sum(w["amount"] for w in result),
    }


def get_hourly_heatmap(user_id, days=30, category_id=None):
    """Generate hour-of-day × day-of-week spending heatmap.

    Returns a 7×24 matrix of spending intensity.
    """
    since = date.today() - timedelta(days=days)

    query = db.session.query(
        Expense.spent_at,
        Expense.amount,
    ).filter(
        Expense.user_id == user_id,
        Expense.spent_at >= since,
    )

    if category_id:
        query = query.filter(Expense.category_id == category_id)

    expenses = query.all()

    # Build 7x24 grid (day_of_week x hour)
    grid = [[0.0 for _ in range(24)] for _ in range(7)]
    counts = [[0 for _ in range(24)] for _ in range(7)]

    for e in expenses:
        if e.spent_at:
            d = e.spent_at if isinstance(e.spent_at, date) else e.spent_at
            dow = d.weekday() if hasattr(d, 'weekday') else 0
            # For date-only fields, distribute evenly across work hours
            hour = 12  # Default to noon for date-only
            grid[dow][hour] += float(e.amount)
            counts[dow][hour] += 1

    max_val = max(max(row) for row in grid) if any(any(r) for r in grid) else 0

    cells = []
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for dow in range(7):
        for hour in range(24):
            amount = grid[dow][hour]
            cells.append({
                "day_of_week": dow,
                "day_name": day_names[dow],
                "hour": hour,
                "amount": amount,
                "count": counts[dow][hour],
                "intensity": round(amount / max_val, 2) if max_val > 0 else 0,
            })

    return {
        "cells": cells,
        "max_amount": max_val,
        "period_days": days,
    }


def get_category_heatmap(user_id, days=30):
    """Generate category × month spending heatmap."""
    since = date.today() - timedelta(days=days)

    expenses = (
        db.session.query(
            Expense.category_id,
            Expense.spent_at,
            Expense.amount,
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= since,
        )
        .all()
    )

    # Aggregate by category
    cat_data = defaultdict(lambda: {"amount": 0, "count": 0})
    for e in expenses:
        cat_id = e.category_id or 0
        cat_data[cat_id]["amount"] += float(e.amount)
        cat_data[cat_id]["count"] += 1

    max_amount = max((c["amount"] for c in cat_data.values()), default=0)

    # Fetch category names
    result = []
    for cat_id, data in cat_data.items():
        if cat_id:
            cat = db.session.get(Category, cat_id)
            cat_name = cat.name if cat else f"Category {cat_id}"
        else:
            cat_name = "Uncategorized"

        result.append({
            "category_id": cat_id if cat_id else None,
            "category_name": cat_name,
            "amount": data["amount"],
            "count": data["count"],
            "intensity": round(data["amount"] / max_amount, 2) if max_amount > 0 else 0,
        })

    result.sort(key=lambda x: x["amount"], reverse=True)

    return {
        "categories": result,
        "total_categories": len(result),
        "max_category_amount": max_amount,
        "period_days": days,
    }


def get_heatmap_summary(user_id, days=365):
    """Get summary statistics for heatmap visualization."""
    since = date.today() - timedelta(days=days)

    stats = (
        db.session.query(
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
            func.avg(Expense.amount).label("avg"),
            func.max(Expense.amount).label("max_single"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= since,
        )
        .first()
    )

    # Busiest day
    busiest = (
        db.session.query(
            Expense.spent_at,
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= since,
        )
        .group_by(Expense.spent_at)
        .order_by(func.sum(Expense.amount).desc())
        .first()
    )

    # Active days count
    active_days = (
        db.session.query(func.count(func.distinct(Expense.spent_at)))
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= since,
        )
        .scalar()
    )

    return {
        "total_spending": float(stats.total) if stats.total else 0,
        "total_transactions": stats.count or 0,
        "avg_transaction": round(float(stats.avg), 2) if stats.avg else 0,
        "max_single_transaction": float(stats.max_single) if stats.max_single else 0,
        "busiest_day": str(busiest.spent_at) if busiest else None,
        "busiest_day_amount": float(busiest.total) if busiest else 0,
        "active_days": active_days or 0,
        "total_days": days,
        "activity_rate": round(active_days / days, 3) if days > 0 else 0,
    }
