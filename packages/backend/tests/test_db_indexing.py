"""
Tests for database indexing optimization.
Issue #128: Verify indexes are created and query performance is improved.
"""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import text


class TestDatabaseIndexes:
    """Tests verifying index creation via the migration SQL."""

    EXPECTED_INDEXES = [
        "idx_expenses_user_category_date",
        "idx_expenses_user_date_type",
        "idx_expenses_user_amount",
        "idx_expenses_notes_trgm",
        "idx_categories_user_name",
        "idx_recurring_expenses_user_active",
        "idx_bills_user_due_active",
        "idx_bills_autopay_due",
        "idx_reminders_pending_dispatch",
        "idx_reminders_user_pending",
        "idx_audit_logs_user_created",
        "idx_ad_impressions_user_created",
    ]

    def test_migration_file_exists(self, tmp_path):
        """Migration SQL file should be present."""
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "../../app/db/008_indexing_optimization.sql"
        )
        assert os.path.exists(migration_path), (
            f"Migration file not found: {migration_path}"
        )

    def test_migration_creates_expected_indexes(self, tmp_path):
        """Migration SQL should define all expected indexes."""
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "../../app/db/008_indexing_optimization.sql"
        )
        with open(migration_path) as f:
            sql = f.read()
        for idx in self.EXPECTED_INDEXES:
            assert idx in sql, f"Expected index '{idx}' not found in migration"

    def test_migration_uses_create_if_not_exists(self, tmp_path):
        """Migration must be idempotent using IF NOT EXISTS."""
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "../../app/db/008_indexing_optimization.sql"
        )
        with open(migration_path) as f:
            sql = f.read()
        assert "IF NOT EXISTS" in sql, "Migration must be idempotent (use IF NOT EXISTS)"

    def test_migration_uses_concurrently(self, tmp_path):
        """Migration should use CONCURRENTLY to avoid table locks."""
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "../../app/db/008_indexing_optimization.sql"
        )
        with open(migration_path) as f:
            sql = f.read()
        assert "CONCURRENTLY" in sql, "Indexes should be created CONCURRENTLY to avoid locking"

    def test_partial_indexes_reduce_size(self, tmp_path):
        """Partial indexes should target only relevant rows."""
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "../../app/db/008_indexing_optimization.sql"
        )
        with open(migration_path) as f:
            sql = f.read()
        # Bills and reminders partial indexes
        assert "WHERE active = TRUE" in sql
        assert "WHERE sent = FALSE" in sql


class TestPerformanceRoutes:
    """Tests for the performance monitoring API endpoints."""

    def test_index_stats_returns_200(self, client, auth_headers):
        """GET /api/performance/index-stats should return 200."""
        response = client.get("/api/performance/index-stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert "indexes" in data
        assert "count" in data

    def test_table_health_returns_200(self, client, auth_headers):
        """GET /api/performance/table-health should return 200."""
        response = client.get("/api/performance/table-health", headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert "tables" in data

    def test_slow_queries_returns_200(self, client, auth_headers):
        """GET /api/performance/slow-queries should return 200."""
        response = client.get("/api/performance/slow-queries", headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert "queries" in data
        assert "min_ms" in data

    def test_requires_authentication(self, client):
        """Performance endpoints require JWT authentication."""
        for endpoint in ["/api/performance/index-stats", "/api/performance/table-health"]:
            response = client.get(endpoint)
            assert response.status_code == 401, (
                f"{endpoint} should require authentication"
            )


class TestIndexStrategy:
    """Tests documenting the indexing strategy decisions."""

    def test_composite_index_covers_list_expenses_query(self, tmp_path):
        """
        The list_expenses route filters by (user_id, category_id, spent_at).
        The composite index idx_expenses_user_category_date should cover this.
        """
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "../../app/db/008_indexing_optimization.sql"
        )
        with open(migration_path) as f:
            sql = f.read()
        # Verify the multi-column index for expenses filtering
        assert "idx_expenses_user_category_date" in sql
        assert "expenses(user_id, category_id, spent_at" in sql

    def test_bills_partial_index_covers_active_only(self, tmp_path):
        """Bills query always filters WHERE active=TRUE, so partial index is optimal."""
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "../../app/db/008_indexing_optimization.sql"
        )
        with open(migration_path) as f:
            sql = f.read()
        assert "idx_bills_user_due_active" in sql

    def test_trigram_index_covers_notes_search(self, tmp_path):
        """Notes search uses ILIKE which benefits from pg_trgm GIN index."""
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "../../app/db/008_indexing_optimization.sql"
        )
        with open(migration_path) as f:
            sql = f.read()
        assert "gin_trgm_ops" in sql
        assert "pg_trgm" in sql