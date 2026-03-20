"""
Database Indexing Optimization for Financial Queries.

Adds composite indexes to the most frequently queried columns:
- expenses: (user_id, spent_at) — most dashboard/insight queries filter by user + date
- expenses: (user_id, category_id) — category breakdown queries
- expenses: (user_id, amount) — amount range searches
- bills: (user_id, next_due_date) — upcoming bills / overdue detection
- bills: (user_id, active) — active bills listing
- recurring_expenses: (user_id, active) — active recurring expense lookup
- reminders: (user_id, sent, send_at) — pending reminder processing
- categories: (user_id, name) — category name lookups

Provides a migration runner + verification utilities.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from .. import db


# ── Index definitions ────────────────────────────────────────────────────────

INDEX_DEFINITIONS = [
    # Expenses: user+date (most common query pattern)
    {
        "name": "idx_expenses_user_spent_at",
        "table": "expenses",
        "columns": ["user_id", "spent_at"],
        "rationale": "Covers all date-range expense queries filtered by user",
    },
    # Expenses: user+category (category breakdowns)
    {
        "name": "idx_expenses_user_category",
        "table": "expenses",
        "columns": ["user_id", "category_id"],
        "rationale": "Covers category breakdown and per-category totals",
    },
    # Expenses: user+amount (amount range search)
    {
        "name": "idx_expenses_user_amount",
        "table": "expenses",
        "columns": ["user_id", "amount"],
        "rationale": "Covers amount range filters in search and anomaly detection",
    },
    # Bills: user+due_date
    {
        "name": "idx_bills_user_due_date",
        "table": "bills",
        "columns": ["user_id", "next_due_date"],
        "rationale": "Covers upcoming bills and overdue bill detection",
    },
    # Bills: user+active
    {
        "name": "idx_bills_user_active",
        "table": "bills",
        "columns": ["user_id", "active"],
        "rationale": "Covers active bill listings and reliability scoring",
    },
    # Recurring expenses: user+active
    {
        "name": "idx_recurring_user_active",
        "table": "recurring_expenses",
        "columns": ["user_id", "active"],
        "rationale": "Covers active recurring expense listings",
    },
    # Reminders: user+sent+send_at (pending reminder dispatch)
    {
        "name": "idx_reminders_user_sent_at",
        "table": "reminders",
        "columns": ["user_id", "sent", "send_at"],
        "rationale": "Covers pending reminder polling (scheduler query)",
    },
    # Categories: user+name
    {
        "name": "idx_categories_user_name",
        "table": "categories",
        "columns": ["user_id", "name"],
        "rationale": "Covers category name lookups for categorization",
    },
]


@dataclass
class IndexStatus:
    name: str
    table: str
    columns: list[str]
    exists: bool
    rationale: str


@dataclass
class IndexingReport:
    total_indexes: int
    existing: int
    created: int
    failed: int
    index_statuses: list[IndexStatus]
    generated_at: str


def _index_exists(index_name: str) -> bool:
    """Check if an index already exists in the database."""
    try:
        result = db.session.execute(
            db.text("SELECT name FROM sqlite_master WHERE type='index' AND name=:name"),
            {"name": index_name}
        ).fetchone()
        return result is not None
    except Exception:
        # For non-SQLite databases or if check fails, assume doesn't exist
        return False


def _create_index(index_def: dict) -> tuple[bool, Optional[str]]:
    """
    Create a single index. Returns (success, error_message).
    Uses IF NOT EXISTS for idempotent execution.
    """
    name = index_def["name"]
    table = index_def["table"]
    columns = ", ".join(index_def["columns"])
    sql = f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})"
    try:
        db.session.execute(db.text(sql))
        db.session.commit()
        return True, None
    except Exception as e:
        db.session.rollback()
        return False, str(e)


def run_index_migration() -> IndexingReport:
    """
    Apply all missing database indexes.

    This is idempotent — indexes that already exist are skipped.

    Returns:
        IndexingReport with status of each index.
    """
    statuses: list[IndexStatus] = []
    created = 0
    failed = 0
    existing = 0

    for idx_def in INDEX_DEFINITIONS:
        already_exists = _index_exists(idx_def["name"])
        if already_exists:
            statuses.append(IndexStatus(
                name=idx_def["name"],
                table=idx_def["table"],
                columns=idx_def["columns"],
                exists=True,
                rationale=idx_def["rationale"],
            ))
            existing += 1
            continue

        success, error = _create_index(idx_def)
        if success:
            statuses.append(IndexStatus(
                name=idx_def["name"],
                table=idx_def["table"],
                columns=idx_def["columns"],
                exists=True,
                rationale=idx_def["rationale"],
            ))
            created += 1
        else:
            statuses.append(IndexStatus(
                name=idx_def["name"],
                table=idx_def["table"],
                columns=idx_def["columns"],
                exists=False,
                rationale=f"FAILED: {error}",
            ))
            failed += 1

    return IndexingReport(
        total_indexes=len(INDEX_DEFINITIONS),
        existing=existing,
        created=created,
        failed=failed,
        index_statuses=statuses,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )


def get_index_health() -> dict:
    """
    Check current state of all defined indexes.
    Returns dict with counts and per-index status.
    """
    statuses = []
    for idx_def in INDEX_DEFINITIONS:
        exists = _index_exists(idx_def["name"])
        statuses.append({
            "name": idx_def["name"],
            "table": idx_def["table"],
            "columns": idx_def["columns"],
            "exists": exists,
            "rationale": idx_def["rationale"],
        })

    total = len(INDEX_DEFINITIONS)
    present = sum(1 for s in statuses if s["exists"])

    return {
        "total_defined": total,
        "present": present,
        "missing": total - present,
        "health_pct": round(present / total * 100, 1) if total > 0 else 0,
        "indexes": statuses,
    }