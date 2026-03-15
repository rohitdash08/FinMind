"""Database indexing optimization utilities.

Provides tools for:
  - Analyzing query performance
  - Verifying index coverage
  - Generating index usage reports
  - Identifying missing indexes
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text, inspect

from ..extensions import db
from ..models import Expense, Bill, Reminder, Category, RecurringExpense

logger = logging.getLogger("finmind.indexing")


# ─── Index verification ────────────────────────────────────────────────


def get_table_indexes(table_name: str) -> list[dict]:
    """Get all indexes for a given table.

    Works with SQLAlchemy's inspector to list indexes regardless of backend.
    """
    inspector = inspect(db.engine)
    try:
        indexes = inspector.get_indexes(table_name)
    except Exception:
        indexes = []
    return [
        {
            "name": idx.get("name", ""),
            "columns": list(idx.get("column_names", [])),
            "unique": idx.get("unique", False),
        }
        for idx in indexes
    ]


def get_all_indexes() -> dict[str, list[dict]]:
    """Get indexes for all application tables."""
    tables = [
        "users", "categories", "expenses", "recurring_expenses",
        "bills", "reminders", "ad_impressions", "subscription_plans",
        "user_subscriptions", "audit_logs",
    ]
    result = {}
    for table in tables:
        try:
            result[table] = get_table_indexes(table)
        except Exception:
            result[table] = []
    return result


# ─── Query pattern analysis ─────────────────────────────────────────────


COMMON_QUERY_PATTERNS = [
    {
        "name": "List expenses by date range",
        "table": "expenses",
        "columns": ["user_id", "spent_at"],
        "index_name": "idx_expenses_user_date",
        "frequency": "very_high",
        "description": "Primary listing query — every page load",
    },
    {
        "name": "Expenses by category and date",
        "table": "expenses",
        "columns": ["user_id", "category_id", "spent_at"],
        "index_name": "idx_expenses_user_category_date",
        "frequency": "high",
        "description": "Category reports and filtering",
    },
    {
        "name": "Expense text search",
        "table": "expenses",
        "columns": ["notes"],
        "index_name": "idx_expenses_notes_trgm",
        "frequency": "medium",
        "description": "Search by expense description",
    },
    {
        "name": "Monthly expense aggregation",
        "table": "expenses",
        "columns": ["user_id", "spent_at", "amount"],
        "index_name": "idx_expenses_user_date_amount",
        "frequency": "high",
        "description": "Monthly totals and summaries",
    },
    {
        "name": "Expense type filtering",
        "table": "expenses",
        "columns": ["user_id", "expense_type"],
        "index_name": "idx_expenses_user_type",
        "frequency": "medium",
        "description": "Income vs expense filtering",
    },
    {
        "name": "Active recurring expenses",
        "table": "recurring_expenses",
        "columns": ["user_id", "active"],
        "index_name": "idx_recurring_user_active",
        "frequency": "medium",
        "description": "Listing active recurring expenses",
    },
    {
        "name": "Upcoming bills",
        "table": "bills",
        "columns": ["user_id", "next_due_date"],
        "index_name": "idx_bills_user_due",
        "frequency": "high",
        "description": "Dashboard upcoming bills widget",
    },
    {
        "name": "Pending reminders",
        "table": "reminders",
        "columns": ["send_at"],
        "index_name": "idx_reminders_pending",
        "frequency": "high",
        "description": "Cron job: find reminders to send",
    },
    {
        "name": "Category lookup",
        "table": "categories",
        "columns": ["user_id", "name"],
        "index_name": "idx_categories_user",
        "frequency": "high",
        "description": "Category listing and lookup",
    },
]


def analyze_index_coverage() -> dict:
    """Analyze which common query patterns have index coverage.

    Returns a report showing covered and uncovered query patterns.
    """
    all_indexes = get_all_indexes()

    covered = []
    missing = []

    for pattern in COMMON_QUERY_PATTERNS:
        table = pattern["table"]
        table_indexes = all_indexes.get(table, [])

        # Check if any index covers the required columns
        has_coverage = False
        matching_index = None
        for idx in table_indexes:
            idx_cols = idx["columns"]
            # Check if pattern columns are a prefix of the index columns
            if _is_prefix(pattern["columns"], idx_cols):
                has_coverage = True
                matching_index = idx["name"]
                break

        entry = {
            "query_pattern": pattern["name"],
            "table": table,
            "required_columns": pattern["columns"],
            "frequency": pattern["frequency"],
            "description": pattern["description"],
        }

        if has_coverage:
            entry["status"] = "covered"
            entry["index_name"] = matching_index
            covered.append(entry)
        else:
            entry["status"] = "missing"
            entry["suggested_index"] = pattern["index_name"]
            missing.append(entry)

    return {
        "total_patterns": len(COMMON_QUERY_PATTERNS),
        "covered": len(covered),
        "missing": len(missing),
        "coverage_percentage": round(
            len(covered) / len(COMMON_QUERY_PATTERNS) * 100, 1
        ) if COMMON_QUERY_PATTERNS else 0,
        "covered_patterns": covered,
        "missing_patterns": missing,
    }


def _is_prefix(required: list[str], index_cols: list[str]) -> bool:
    """Check if required columns are a prefix of the index columns."""
    if len(required) > len(index_cols):
        return False
    return all(r == i for r, i in zip(required, index_cols))


# ─── Performance benchmarks ─────────────────────────────────────────────


def benchmark_expense_queries(user_id: int) -> list[dict]:
    """Run common expense queries and measure execution info.

    Note: Actual EXPLAIN ANALYZE requires PostgreSQL.
    This provides query execution metrics for testing.
    """
    results = []
    today = date.today()
    month_start = today.replace(day=1)

    queries = [
        {
            "name": "List expenses (current month)",
            "query": db.session.query(Expense).filter(
                Expense.user_id == user_id,
                Expense.spent_at >= month_start,
                Expense.spent_at <= today,
            ).order_by(Expense.spent_at.desc()),
        },
        {
            "name": "Monthly total",
            "query": db.session.query(
                db.func.sum(Expense.amount)
            ).filter(
                Expense.user_id == user_id,
                Expense.spent_at >= month_start,
                Expense.spent_at <= today,
            ),
        },
        {
            "name": "Category breakdown",
            "query": db.session.query(
                Expense.category_id,
                db.func.sum(Expense.amount),
                db.func.count(Expense.id),
            ).filter(
                Expense.user_id == user_id,
                Expense.spent_at >= month_start,
            ).group_by(Expense.category_id),
        },
        {
            "name": "Search expenses",
            "query": db.session.query(Expense).filter(
                Expense.user_id == user_id,
                Expense.notes.ilike("%test%"),
            ),
        },
    ]

    for q_info in queries:
        import time
        start = time.perf_counter()
        try:
            result = q_info["query"].all()
            elapsed = (time.perf_counter() - start) * 1000  # ms
            results.append({
                "query": q_info["name"],
                "execution_time_ms": round(elapsed, 2),
                "row_count": len(result) if isinstance(result, list) else 1,
                "status": "ok",
            })
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            results.append({
                "query": q_info["name"],
                "execution_time_ms": round(elapsed, 2),
                "row_count": 0,
                "status": f"error: {str(e)[:100]}",
            })

    return results


def get_table_statistics() -> list[dict]:
    """Get row counts and estimated sizes for all tables."""
    tables = [
        "users", "categories", "expenses", "recurring_expenses",
        "bills", "reminders", "ad_impressions", "subscription_plans",
        "user_subscriptions", "audit_logs",
    ]
    stats = []
    for table in tables:
        try:
            count = db.session.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar()
            stats.append({
                "table": table,
                "row_count": count,
                "status": "ok",
            })
        except Exception:
            stats.append({
                "table": table,
                "row_count": 0,
                "status": "error",
            })
    return stats
