"""Database indexing optimization for financial queries.

Adds composite and single-column indexes to improve query performance
for common financial operations: filtering by user, date ranges,
category lookups, and dashboard aggregations.
"""

from app.extensions import db


# Index definitions for each table
INDEXES = [
    # Expenses: most queried table
    db.Index("ix_expenses_user_spent_at", "expenses", "user_id", "spent_at"),
    db.Index("ix_expenses_user_category", "expenses", "user_id", "category_id"),
    db.Index("ix_expenses_user_type_date", "expenses", "user_id", "expense_type", "spent_at"),
    db.Index("ix_expenses_spent_at", "expenses", "spent_at"),

    # Bills: due date queries and autopay filtering
    db.Index("ix_bills_user_next_due", "bills", "user_id", "next_due_date"),
    db.Index("ix_bills_user_autopay", "bills", "user_id", "autopay_enabled"),

    # Categories: user lookup
    db.Index("ix_categories_user_id", "categories", "user_id"),

    # Recurring expenses: active recurring by user
    db.Index("ix_recurring_user_active", "recurring_expenses", "user_id", "active"),

    # Reminders: upcoming reminders
    db.Index("ix_reminders_user_date", "reminders", "user_id", "remind_at"),
]


def create_indexes(engine):
    """Create all performance indexes.

    Safe to run multiple times - uses IF NOT EXISTS semantics.
    """
    results = []
    for idx_sql in get_index_sql():
        try:
            engine.execute(idx_sql)
            results.append({"sql": idx_sql, "status": "created"})
        except Exception as e:
            if "already exists" in str(e).lower():
                results.append({"sql": idx_sql, "status": "exists"})
            else:
                results.append({"sql": idx_sql, "status": "error", "error": str(e)})
    return results


def get_index_sql():
    """Generate CREATE INDEX IF NOT EXISTS SQL statements."""
    return [
        # Expenses indexes
        "CREATE INDEX IF NOT EXISTS ix_expenses_user_spent_at ON expenses (user_id, spent_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_expenses_user_category ON expenses (user_id, category_id)",
        "CREATE INDEX IF NOT EXISTS ix_expenses_user_type_date ON expenses (user_id, expense_type, spent_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_expenses_spent_at ON expenses (spent_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_expenses_amount ON expenses (amount)",

        # Bills indexes
        "CREATE INDEX IF NOT EXISTS ix_bills_user_next_due ON bills (user_id, next_due_date)",
        "CREATE INDEX IF NOT EXISTS ix_bills_user_autopay ON bills (user_id, autopay_enabled)",

        # Categories indexes
        "CREATE INDEX IF NOT EXISTS ix_categories_user_id ON categories (user_id)",

        # Recurring expenses indexes
        "CREATE INDEX IF NOT EXISTS ix_recurring_user_active ON recurring_expenses (user_id, active)",
        "CREATE INDEX IF NOT EXISTS ix_recurring_start_date ON recurring_expenses (start_date)",

        # Reminders indexes
        "CREATE INDEX IF NOT EXISTS ix_reminders_user_date ON reminders (user_id, remind_at)",
    ]


def analyze_query_performance(engine):
    """Run EXPLAIN ANALYZE on common queries and return results.

    Returns a list of query analysis results for monitoring.
    """
    common_queries = [
        {
            "name": "expenses_by_user_date_range",
            "sql": "SELECT * FROM expenses WHERE user_id = 1 AND spent_at BETWEEN '2026-01-01' AND '2026-02-28' ORDER BY spent_at DESC",
        },
        {
            "name": "expenses_by_category",
            "sql": "SELECT category_id, SUM(amount) FROM expenses WHERE user_id = 1 GROUP BY category_id",
        },
        {
            "name": "upcoming_bills",
            "sql": "SELECT * FROM bills WHERE user_id = 1 AND next_due_date >= CURRENT_DATE ORDER BY next_due_date",
        },
        {
            "name": "monthly_totals",
            "sql": "SELECT expense_type, SUM(amount) FROM expenses WHERE user_id = 1 AND spent_at >= '2026-02-01' GROUP BY expense_type",
        },
    ]

    results = []
    for q in common_queries:
        try:
            explain = engine.execute(f"EXPLAIN QUERY PLAN {q['sql']}").fetchall()
            results.append({"name": q["name"], "plan": [str(row) for row in explain]})
        except Exception as e:
            results.append({"name": q["name"], "error": str(e)})
    return results
