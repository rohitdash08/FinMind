
"""
Multi-account financial overview dashboard.
Aggregates data across multiple accounts for a unified view.
"""
from ..extensions import db
from ..models import User, Expense, Category
from sqlalchemy import func
from datetime import datetime, timedelta


def get_multi_account_summary(user_id: int, account_ids: list = None) -> dict:
    """Get aggregated financial summary across multiple accounts."""
    query = db.session.query(
        func.sum(Expense.amount).label("total"),
        func.count(Expense.id).label("count"),
        func.avg(Expense.amount).label("avg_amount")
    ).filter(Expense.user_id == user_id)
    
    if account_ids:
        query = query.filter(Expense.category_id.in_(account_ids))
    
    result = query.first()
    
    # Get by category
    by_category = db.session.query(
        Category.name,
        func.sum(Expense.amount).label("total")
    ).join(Expense).filter(
        Expense.user_id == user_id
    ).group_by(Category.name).all()
    
    return {
        "total_spent": float(result.total or 0),
        "transaction_count": result.count or 0,
        "average_transaction": float(result.avg_amount or 0),
        "by_category": {name: float(total) for name, total in by_category}
    }
