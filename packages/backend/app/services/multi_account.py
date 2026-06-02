"""
Multi-account financial overview dashboard.
Aggregates data across multiple accounts for a unified view.
"""
from ..extensions import db
from ..models import User, Expense, Category
from sqlalchemy import func
from datetime import datetime, timedelta


def get_multi_account_summary(user_id: int, category_ids: list = [], 
                              start_date: datetime = None, 
                              end_date: datetime = None) -> dict:
    """Get aggregated financial summary across multiple categories.
    
    Args:
        user_id: User ID
        category_ids: Optional list of category IDs to filter by
        start_date: Optional start date for date range filter
        end_date: Optional end date for date range filter
        
    Returns:
        dict with financial summary
    """
    query = db.session.query(
        func.sum(Expense.amount).label("total"),
        func.count(Expense.id).label("count"),
        func.avg(Expense.amount).label("avg_amount")
    ).filter(Expense.user_id == user_id)
    
    # Apply category filter
    if category_ids:
        query = query.filter(Expense.category_id.in_(category_ids))
    
    # Apply date range filter
    if start_date:
        query = query.filter(Expense.spent_at >= start_date)
    if end_date:
        query = query.filter(Expense.spent_at <= end_date)
    
    result = query.first()
    
    # Get by category
    by_category_query = db.session.query(
        Category.name,
        func.sum(Expense.amount).label("total")
    ).join(Expense).filter(
        Expense.user_id == user_id
    )
    
    if category_ids:
        by_category_query = by_category_query.filter(Expense.category_id.in_(category_ids))
    if start_date:
        by_category_query = by_category_query.filter(Expense.spent_at >= start_date)
    if end_date:
        by_category_query = by_category_query.filter(Expense.spent_at <= end_date)
    
    by_category = by_category_query.group_by(Category.name).all()
    
    # Get monthly trend
    monthly_query = db.session.query(
        func.strftime('%Y-%m', Expense.spent_at).label('month'),
        func.sum(Expense.amount).label('total')
    ).filter(Expense.user_id == user_id)
    
    if category_ids:
        monthly_query = monthly_query.filter(Expense.category_id.in_(category_ids))
    if start_date:
        monthly_query = monthly_query.filter(Expense.spent_at >= start_date)
    if end_date:
        monthly_query = monthly_query.filter(Expense.spent_at <= end_date)
    
    monthly = monthly_query.group_by('month').order_by('month').all()
    
    return {
        "total_spent": float(result.total or 0),
        "transaction_count": result.count or 0,
        "average_transaction": float(result.avg_amount or 0),
        "by_category": {name: float(total) for name, total in by_category},
        "monthly_trend": {month: float(total) for month, total in monthly},
        "date_range": {
            "start": start_date.isoformat() if start_date else None,
            "end": end_date.isoformat() if end_date else None,
        }
    }
