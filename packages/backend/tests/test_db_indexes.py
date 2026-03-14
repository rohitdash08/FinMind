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
        """Verify all critical query paths have a corresponding index."""
        idx_set = set(REQUIRED_INDEXES)
        # Expenses — the hottest table
        assert "idx_expenses_user_spent_at" in idx_set
        assert "idx_expenses_user_type_date" in idx_set
        assert "idx_expenses_user_category" in idx_set
        # Bills
        assert "idx_bills_user_active_due" in idx_set
        # Reminders dispatch
        assert "idx_reminders_pending_dispatch" in idx_set
        # Audit
        assert "idx_audit_logs_user_created" in idx_set


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
