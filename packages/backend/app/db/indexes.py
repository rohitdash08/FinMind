
"""
Database indexing optimization for financial queries.
Adds indexes for common query patterns.
"""


def create_indexes(migration):
    """Create optimized indexes for financial queries."""
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
    
    return indexes
