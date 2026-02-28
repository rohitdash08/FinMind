"""Tests for database indexing optimization."""

import pytest
from app.services.db_indexing import get_index_sql, analyze_query_performance


class TestIndexSQL:
    def test_returns_list(self):
        sqls = get_index_sql()
        assert isinstance(sqls, list)
        assert len(sqls) >= 10

    def test_all_create_index(self):
        for sql in get_index_sql():
            assert sql.startswith("CREATE INDEX IF NOT EXISTS")

    def test_expenses_indexes_exist(self):
        sqls = " ".join(get_index_sql())
        assert "ix_expenses_user_spent_at" in sqls
        assert "ix_expenses_user_category" in sqls
        assert "ix_expenses_user_type_date" in sqls

    def test_bills_indexes_exist(self):
        sqls = " ".join(get_index_sql())
        assert "ix_bills_user_next_due" in sqls
        assert "ix_bills_user_autopay" in sqls

    def test_recurring_indexes_exist(self):
        sqls = " ".join(get_index_sql())
        assert "ix_recurring_user_active" in sqls

    def test_reminders_indexes_exist(self):
        sqls = " ".join(get_index_sql())
        assert "ix_reminders_user_date" in sqls

    def test_desc_ordering(self):
        sqls = " ".join(get_index_sql())
        assert "DESC" in sqls


class TestIndexAPI:
    def test_list_indexes(self, client):
        resp = client.get("/db/indexes")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "indexes" in data
        assert len(data["indexes"]) >= 10

    def test_apply_indexes(self, client):
        resp = client.post("/db/indexes/apply")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "results" in data
        for r in data["results"]:
            assert r["status"] in ("ok", "exists", "error")
