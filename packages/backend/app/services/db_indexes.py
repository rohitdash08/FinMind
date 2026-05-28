"""Database indexing optimization for FinMind.

Creates and manages indexes for high-frequency financial queries:
- Expense queries by user, date, category, type
- Bill queries by user, status, due_date
- Reminder queries by user, status, next_trigger
- Auth queries by email (unique)
- Composite indexes for common filter combinations
"""

import logging
from sqlalchemy import text, inspect
from ..extensions import db

logger = logging.getLogger("finmind.indexes")

# Index definitions: (index_name, table, columns, unique)
INDEX_DEFINITIONS = [
    # --- Expenses ---
    ("ix_expenses_user_id", "expenses", ["user_id"], False),
    ("ix_expenses_spent_at", "expenses", ["spent_at"], False),
    ("ix_expenses_type", "expenses", ["expense_type"], False),
    ("ix_expenses_user_date", "expenses", ["user_id", "spent_at"], False),
    ("ix_expenses_user_type_date", "expenses", ["user_id", "expense_type", "spent_at"], False),
    ("ix_expenses_user_category", "expenses", ["user_id", "category_id"], False),
    ("ix_expenses_user_currency", "expenses", ["user_id", "currency"], False),

    # --- Bills ---
    ("ix_bills_user_id", "bills", ["user_id"], False),
    ("ix_bills_status", "bills", ["status"], False),
    ("ix_bills_due_date", "bills", ["due_date"], False),
    ("ix_bills_user_status", "bills", ["user_id", "status"], False),
    ("ix_bills_user_due", "bills", ["user_id", "due_date"], False),

    # --- Reminders ---
    ("ix_reminders_user_id", "reminders", ["user_id"], False),
    ("ix_reminders_status", "reminders", ["status"], False),
    ("ix_reminders_next_trigger", "reminders", ["next_trigger"], False),
    ("ix_reminders_user_status_trigger", "reminders", ["user_id", "status", "next_trigger"], False),

    # --- Categories ---
    ("ix_categories_user_id", "categories", ["user_id"], False),

    # --- Users ---
    ("ix_users_email", "users", ["email"], True),
]


def get_existing_indexes(table_name: str) -> set:
    """Get set of existing index names for a table."""
    inspector = inspect(db.engine)
    indexes = inspector.get_indexes(table_name)
    return {idx["name"] for idx in indexes}


def create_missing_indexes() -> dict:
    """Create all missing indexes. Returns summary dict."""
    created = []
    skipped = []
    errors = []

    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()

    for idx_name, table, columns, unique in INDEX_DEFINITIONS:
        if table not in existing_tables:
            skipped.append((idx_name, f"table {table} not found"))
            continue

        existing = get_existing_indexes(table)
        if idx_name in existing:
            skipped.append((idx_name, "already exists"))
            continue

        cols = ", ".join(columns)
        unique_str = "UNIQUE " if unique else ""
        sql = f"CREATE {unique_str}INDEX {idx_name} ON {table} ({cols})"

        try:
            db.session.execute(text(sql))
            db.session.commit()
            created.append(idx_name)
            logger.info("Created index: %s on %s(%s)", idx_name, table, cols)
        except Exception as e:
            db.session.rollback()
            errors.append((idx_name, str(e)))
            logger.error("Failed to create index %s: %s", idx_name, e)

    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "total_defined": len(INDEX_DEFINITIONS),
    }


def get_index_usage_stats() -> list:
    """Get index usage statistics from PostgreSQL (if available)."""
    try:
        result = db.session.execute(text("""
            SELECT
                schemaname, relname as table_name,
                indexrelname as index_name,
                idx_scan as times_used,
                idx_tup_read as tuples_read,
                idx_tup_fetch as tuples_fetched
            FROM pg_stat_user_indexes
            ORDER BY idx_scan DESC
        """))
        return [dict(row._mapping) for row in result]
    except Exception:
        # SQLite or non-PG database
        return []


def drop_all_custom_indexes() -> int:
    """Drop all custom indexes defined in this module. For testing."""
    count = 0
    for idx_name, table, _, _ in INDEX_DEFINITIONS:
        try:
            db.session.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
            db.session.commit()
            count += 1
        except Exception:
            db.session.rollback()
    return count
