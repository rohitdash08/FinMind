"""
Database indexing optimization for financial queries.
Adds indexes for common query patterns.
"""
from sqlalchemy import text
from ..extensions import db


def create_indexes(engine=None):
    """Create optimized indexes for financial queries.
    
    Args:
        engine: SQLAlchemy engine to use. If None, uses db.engine.
    """
    if engine is None:
        engine = db.engine
    
    indexes = [
        # User lookups
        "CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, spent_at);",
        "CREATE INDEX IF NOT EXISTS idx_expenses_user_category ON expenses(user_id, category_id);",
        
        # Date range queries
        "CREATE INDEX IF NOT EXISTS idx_expenses_spent_at ON expenses(spent_at);",
        "CREATE INDEX IF NOT EXISTS idx_expenses_created_at ON expenses(created_at);",
        
        # Category lookups
        "CREATE INDEX IF NOT EXISTS idx_categories_user_id ON categories(user_id);",
        
        # Recurring expenses
        "CREATE INDEX IF NOT EXISTS idx_recurring_user_active ON recurring_expenses(user_id, active);",
        
        # Bills
        "CREATE INDEX IF NOT EXISTS idx_bills_user_id ON bills(user_id);",
        
        # Composite indexes for common dashboard queries
        "CREATE INDEX IF NOT EXISTS idx_expenses_user_type_date ON expenses(user_id, expense_type, spent_at);",
    ]
    
    with engine.connect() as conn:
        for index_sql in indexes:
            conn.execute(text(index_sql))
        conn.commit()
    
    return len(indexes)


def drop_indexes(engine=None):
    """Drop all custom indexes.
    
    Args:
        engine: SQLAlchemy engine to use. If None, uses db.engine.
    """
    if engine is None:
        engine = db.engine
    
    index_names = [
        "idx_expenses_user_id",
        "idx_expenses_user_date",
        "idx_expenses_user_category",
        "idx_expenses_spent_at",
        "idx_expenses_created_at",
        "idx_categories_user_id",
        "idx_recurring_user_active",
        "idx_bills_user_id",
        "idx_expenses_user_type_date",
    ]
    
    with engine.connect() as conn:
        for name in index_names:
            conn.execute(text(f"DROP INDEX IF EXISTS {name};"))
        conn.commit()
    
    return len(index_names)


def get_indexes(engine=None):
    """Get list of all indexes in the database.
    
    Args:
        engine: SQLAlchemy engine to use. If None, uses db.engine.
        
    Returns:
        List of index names
    """
    if engine is None:
        engine = db.engine
    
    # This works for both SQLite and PostgreSQL
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';"
        ))
        return [row[0] for row in result]
