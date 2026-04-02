from datetime import date, timedelta
from decimal import Decimal
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, extract
from ..extensions import db
from ..models import Expense, Category
from ..services.cache import cache_get, cache_set
import logging

bp = Blueprint("analytics", __name__)
logger = logging.getLogger("finmind.analytics")


def _heatmap_cache_key(user_id: int, year: int, aggregation: str, category_id: int | None) -> str:
    cat_part = str(category_id) if category_id else "all"
    return f"user:{user_id}:heatmap:{year}:{aggregation}:{cat_part}"


@bp.get("/heatmap")
@jwt_required()
def spending_heatmap():
    """Generate day-by-day spending data suitable for heatmap visualization."""
    uid = int(get_jwt_identity())
    
    try:
        year = int(request.args.get("year", date.today().year))
    except ValueError:
        return jsonify(error="invalid year"), 400
    
    category_id = request.args.get("category")
    if category_id:
        try:
            category_id = int(category_id)
        except ValueError:
            return jsonify(error="invalid category id"), 400
    else:
        category_id = None
    
    aggregation = request.args.get("aggregation", "daily").lower()
    if aggregation not in ("daily", "weekly", "monthly"):
        return jsonify(error="aggregation must be daily, weekly, or monthly"), 400
    
    cache_key = _heatmap_cache_key(uid, year, aggregation, category_id)
    cached = cache_get(cache_key)
    if cached:
        logger.info("Heatmap cache hit user=%s year=%s", uid, year)
        return jsonify(cached)
    
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    prev_year_start = date(year - 1, 1, 1)
    prev_year_end = date(year - 1, 12, 31)
    
    try:
        query = (
            db.session.query(
                Expense.spent_at,
                Expense.amount,
                Expense.category_id,
            )
            .filter(
                Expense.user_id == uid,
                Expense.spent_at >= year_start,
                Expense.spent_at <= year_end,
                Expense.expense_type != "INCOME",
            )
        )
        
        if category_id:
            query = query.filter(Expense.category_id == category_id)
        
        expenses = query.all()
        
        prev_query = (
            db.session.query(
                Expense.spent_at,
                Expense.amount,
            )
            .filter(
                Expense.user_id == uid,
                Expense.spent_at >= prev_year_start,
                Expense.spent_at <= prev_year_end,
                Expense.expense_type != "INCOME",
            )
        )
        
        if category_id:
            prev_query = prev_query.filter(Expense.category_id == category_id)
        
        prev_expenses = prev_query.all()
        
        if aggregation == "daily":
            heatmap_data = _aggregate_daily(expenses, year)
        elif aggregation == "weekly":
            heatmap_data = _aggregate_weekly(expenses, year)
        else:
            heatmap_data = _aggregate_monthly(expenses, year)
        
        current_total = sum(float(e.amount) for e in expenses)
        prev_total = sum(float(e.amount) for e in prev_expenses)
        
        if prev_total > 0:
            change_pct = round(((current_total - prev_total) / prev_total) * 100, 2)
        else:
            change_pct = 0.0 if current_total == 0 else 100.0
        
        comparison = {
            "current_period_total": round(current_total, 2),
            "previous_period_total": round(prev_total, 2),
            "change_amount": round(current_total - prev_total, 2),
            "change_percent": change_pct,
            "period_type": "year_over_year",
        }
        
        response = {
            "data": heatmap_data,
            "comparison": comparison,
            "metadata": {
                "year": year,
                "category_id": category_id,
                "aggregation": aggregation,
                "total_transactions": len(expenses),
                "date_range": {
                    "start": year_start.isoformat(),
                    "end": year_end.isoformat(),
                },
            },
        }
        
        cache_set(cache_key, response, ttl_seconds=300)
        logger.info("Heatmap generated user=%s year=%s aggregation=%s", uid, year, aggregation)
        
        return jsonify(response)
    
    except Exception as e:
        logger.exception("Heatmap generation failed user=%s", uid)
        return jsonify(error="failed to generate heatmap", details=str(e)), 500


def _aggregate_daily(expenses, year):
    from collections import defaultdict
    daily_data = defaultdict(lambda: {"amount": Decimal(0), "count": 0, "categories": defaultdict(Decimal)})
    
    for exp in expenses:
        day_key = exp.spent_at.isoformat()
        daily_data[day_key]["amount"] += exp.amount
        daily_data[day_key]["count"] += 1
        if exp.category_id:
            daily_data[day_key]["categories"][exp.category_id] += exp.amount
    
    category_ids = set()
    for day_data in daily_data.values():
        category_ids.update(day_data["categories"].keys())
    
    category_names = {}
    if category_ids:
        cat_rows = db.session.query(Category.id, Category.name).filter(Category.id.in_(category_ids)).all()
        category_names = {c.id: c.name for c in cat_rows}
    
    result = []
    for day_key in sorted(daily_data.keys()):
        data = daily_data[day_key]
        top_cat_id = None
        top_cat_amount = Decimal(0)
        for cat_id, amt in data["categories"].items():
            if amt > top_cat_amount:
                top_cat_amount = amt
                top_cat_id = cat_id
        
        result.append({
            "date": day_key,
            "amount": round(float(data["amount"]), 2),
            "transaction_count": data["count"],
            "top_category": category_names.get(top_cat_id) if top_cat_id else None,
        })
    
    return result


def _aggregate_weekly(expenses, year):
    from collections import defaultdict
    weekly_data = defaultdict(lambda: {"amount": Decimal(0), "count": 0, "categories": defaultdict(Decimal)})
    
    for exp in expenses:
        iso_cal = exp.spent_at.isocalendar()
        week_key = f"{iso_cal[0]}-W{iso_cal[1]:02d}"
        weekly_data[week_key]["amount"] += exp.amount
        weekly_data[week_key]["count"] += 1
        if exp.category_id:
            weekly_data[week_key]["categories"][exp.category_id] += exp.amount
    
    category_ids = set()
    for week_data in weekly_data.values():
        category_ids.update(week_data["categories"].keys())
    
    category_names = {}
    if category_ids:
        cat_rows = db.session.query(Category.id, Category.name).filter(Category.id.in_(category_ids)).all()
        category_names = {c.id: c.name for c in cat_rows}
    
    result = []
    for week_key in sorted(weekly_data.keys()):
        data = weekly_data[week_key]
        top_cat_id = None
        top_cat_amount = Decimal(0)
        for cat_id, amt in data["categories"].items():
            if amt > top_cat_amount:
                top_cat_amount = amt
                top_cat_id = cat_id
        
        year_part, week_part = map(int, week_key.split("-W"))
        week_num = int(week_part)
        jan4 = date(year_part, 1, 4)
        week_start = jan4 + timedelta(days=(week_num - 1) * 7 - jan4.weekday())
        
        result.append({
            "date": week_key,
            "week_start": week_start.isoformat(),
            "amount": round(float(data["amount"]), 2),
            "transaction_count": data["count"],
            "top_category": category_names.get(top_cat_id) if top_cat_id else None,
        })
    
    return result


def _aggregate_monthly(expenses, year):
    from collections import defaultdict
    monthly_data = defaultdict(lambda: {"amount": Decimal(0), "count": 0, "categories": defaultdict(Decimal)})
    
    for exp in expenses:
        month_key = exp.spent_at.strftime("%Y-%m")
        monthly_data[month_key]["amount"] += exp.amount
        monthly_data[month_key]["count"] += 1
        if exp.category_id:
            monthly_data[month_key]["categories"][exp.category_id] += exp.amount
    
    category_ids = set()
    for month_data in monthly_data.values():
        category_ids.update(month_data["categories"].keys())
    
    category_names = {}
    if category_ids:
        cat_rows = db.session.query(Category.id, Category.name).filter(Category.id.in_(category_ids)).all()
        category_names = {c.id: c.name for c in cat_rows}
    
    result = []
    for month_key in sorted(monthly_data.keys()):
        data = monthly_data[month_key]
        top_cat_id = None
        top_cat_amount = Decimal(0)
        for cat_id, amt in data["categories"].items():
            if amt > top_cat_amount:
                top_cat_amount = amt
                top_cat_id = cat_id
        
        result.append({
            "date": month_key,
            "amount": round(float(data["amount"]), 2),
            "transaction_count": data["count"],
            "top_category": category_names.get(top_cat_id) if top_cat_id else None,
        })
    
    return result
