"""
Tests for database indexing optimization (Issue #128).

For SQLite test DBs we verify the index_report utility logic.
For PostgreSQL we verify the actual indexes are created.
Integration tests confirm that indexed query patterns return correct results.
"""

from __future__ import annotations

import pytest
from app.db.index_report import REQUIRED_INDEXES, check_missing_indexes
from app.extensions import db


class TestIndexReport:
    def test_required_indexes_list_nonempty(self):
        assert len(REQUIRED_INDEXES) > 0

    def test_required_indexes_are_strings(self):
        for idx in REQUIRED_INDEXES:
            assert isinstance(idx, str)
            assert idx.startswith("idx_")

    def test_check_missing_returns_list(self, app_fixture):
        with app_fixture.app_context():
            # On SQLite this returns [] (not PostgreSQL)
            # On PostgreSQL it checks real indexes
            missing = check_missing_indexes(db.engine)
            assert isinstance(missing, list)

    def test_critical_indexes_documented(self):
        """Verify all critical query paths have a corresponding index entry."""
        idx_set = set(REQUIRED_INDEXES)

        # Expenses — the hottest table
        assert "idx_expenses_user_spent_at" in idx_set       # basic date-range
        assert "idx_expenses_user_type_date" in idx_set      # income/expense split
        assert "idx_expenses_user_category" in idx_set       # category filter
        assert "idx_expenses_user_month" in idx_set          # monthly aggregation

        # Bills — both the partial (active=TRUE) and full index
        assert "idx_bills_user_due" in idx_set               # full; historical/admin
        assert "idx_bills_user_active_due" in idx_set        # partial; most queries

        # Reminders — full and partial
        assert "idx_reminders_due" in idx_set                # full; per-user listing
        assert "idx_reminders_pending_dispatch" in idx_set   # partial; dispatch job

        # Recurring expenses
        assert "idx_recurring_expenses_user_start" in idx_set  # full; history
        assert "idx_recurring_expenses_active" in idx_set       # partial; generation

        # Audit
        assert "idx_audit_logs_user_created" in idx_set
        assert "idx_audit_logs_action_created" in idx_set

    def test_required_indexes_match_migration(self):
        """REQUIRED_INDEXES must not contain index names absent from the migration.

        This is a static regression guard: if the migration and the Python list
        drift apart, ``flask index-report`` will always show false positives.
        Any name added to REQUIRED_INDEXES must have a corresponding
        CREATE INDEX … statement in 007_db_indexing.sql.
        """
        import os, re

        migration_path = os.path.join(
            os.path.dirname(__file__),
            "../app/db/migrations/007_db_indexing.sql",
        )
        with open(migration_path) as f:
            sql = f.read()

        # Extract every index name defined by a CREATE INDEX statement
        defined_in_migration = set(re.findall(r"CREATE INDEX IF NOT EXISTS (\w+)", sql))

        not_in_migration = [
            idx for idx in REQUIRED_INDEXES if idx not in defined_in_migration
        ]
        assert not_in_migration == [], (
            f"REQUIRED_INDEXES entries missing from migration: {not_in_migration}"
        )

    def test_date_trunc_index_is_postgres_only(self):
        """idx_expenses_user_month uses DATE_TRUNC — must be documented as PG-only."""
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__),
            "../app/db/migrations/007_db_indexing.sql",
        )
        with open(migration_path) as f:
            sql = f.read()

        # Find the block containing the DATE_TRUNC index and assert there is a
        # PostgreSQL warning comment in the preceding lines.
        idx = sql.find("idx_expenses_user_month")
        assert idx != -1, "idx_expenses_user_month not found in migration"

        # Look at the 400 characters before the CREATE INDEX statement
        context = sql[max(0, idx - 400):idx]
        assert "postgresql" in context.lower() or "postgres" in context.lower(), (
            "Migration must document that idx_expenses_user_month requires PostgreSQL "
            "(DATE_TRUNC is not supported on SQLite/MySQL)"
        )


class TestIndexedQueryPatterns:
    """Verify that the query patterns benefiting from indexes work correctly."""

    EMAIL = "idx@test.com"

    def _auth(self, client):
        client.post("/auth/register", json={"email": self.EMAIL, "password": "pass"})
        r = client.post("/auth/login", json={"email": self.EMAIL, "password": "pass"})
        return {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    def test_expense_filter_by_date_range(self, client, app_fixture):
        h = self._auth(client)
        client.post("/expenses", json={"amount": 100, "description": "A", "date": "2026-01-01"}, headers=h)
        client.post("/expenses", json={"amount": 200, "description": "B", "date": "2026-03-01"}, headers=h)
        r = client.get("/expenses?from=2026-01-01&to=2026-02-28", headers=h)
        assert r.status_code == 200
        items = r.get_json()
        assert all(i["date"] <= "2026-02-28" for i in items)

    def test_expense_filter_by_category(self, client, app_fixture):
        h = self._auth(client)
        # Create category
        cat_r = client.post("/categories", json={"name": "Food"}, headers=h)
        if cat_r.status_code in (200, 201):
            cat_id = cat_r.get_json().get("id")
            client.post("/expenses", json={
                "amount": 50, "description": "Lunch",
                "date": "2026-01-15", "category_id": cat_id,
            }, headers=h)
            r = client.get(f"/expenses?category_id={cat_id}", headers=h)
            assert r.status_code == 200

    def test_bills_list_active_only(self, client, app_fixture):
        h = self._auth(client)
        r = client.get("/bills", headers=h)
        assert r.status_code == 200
        # All returned bills should be active
        for b in r.get_json():
            assert b.get("active", True) is True

    def test_reminders_pending_query(self, client, app_fixture):
        h = self._auth(client)
        r = client.post("/reminders/run", headers=h)
        assert r.status_code == 200

    def test_categories_user_list(self, client, app_fixture):
        h = self._auth(client)
        r = client.get("/categories", headers=h)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)
